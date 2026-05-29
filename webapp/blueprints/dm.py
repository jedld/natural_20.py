"""DM blueprint — admin, entity management, inventory, and rest endpoints.

Extracted from webapp/app.py.
"""
import math
import os
import re
import uuid

from flask import Blueprint, request, jsonify, session, redirect, url_for, render_template

from natural20.utils.serialization import object_type_to_klass
from natural20.actions.use_item_action import UseItemAction
from natural20.generic_controller import GenericController
from natural20.llm_controller import LlmMcpController
from natural20.player_character import PlayerCharacter
from natural20.web.web_controller import WebController

from .ai import DM_AI_CHAT_SESSION_KEY
from .helpers.auth_utils import user_role
from .helpers.special_effects import special_effects_enabled, is_heavy_special_effect
from .helpers.template_globals import controller_of
from .helpers.runtime_state import (
    get_app,
    get_current_game,
    get_game_session,
    set_game_session,
    get_socketio,
    get_output_logger,
    get_llm_handler,
    get_logger,
    get_level,
    get_active_effects,
    get_active_effects_map,
    get_perf_lock,
    get_perf_stats,
)

dm_bp = Blueprint('dm', __name__)


@dm_bp.route('/admin/saves', methods=['GET'])
def list_saves():
    if not session.get('username'):
        return jsonify(error='Unauthorized'), 401
    if 'dm' not in user_role():
        return jsonify(error='Forbidden'), 403
    saves = []
    try:
        save_dir = getattr(get_current_game(), 'save_dir', os.getcwd())
        for fname in get_current_game().list_states():
            try:
                path = fname if os.path.isabs(fname) else os.path.join(save_dir, fname)
                mtime = os.path.getmtime(path)
                size = os.path.getsize(path)
            except Exception:
                mtime = None
                size = None
            saves.append({
                'filename': fname,
                'mtime': mtime,
                'size': size,
            })
        # Include any additional save_* files not in list_states, for named saves
        try:
            for f in os.listdir(save_dir):
                if f.startswith('save_') and (f.endswith('.yml') or f.endswith('.yml.gz')) and f not in [s['filename'] for s in saves]:
                    try:
                        mtime = os.path.getmtime(os.path.join(save_dir, f))
                        size = os.path.getsize(os.path.join(save_dir, f))
                    except Exception:
                        mtime = None
                        size = None
                    saves.append({'filename': f, 'mtime': mtime, 'size': size})
        except Exception:
            pass

        # Sort by mtime desc if available
        saves.sort(key=lambda x: (x['mtime'] is not None, x['mtime']), reverse=True)
        return jsonify(saves=saves)
    except Exception as e:
        return jsonify(error=str(e)), 500


@dm_bp.route('/admin/save', methods=['POST'])
def admin_save():
    if not session.get('username'):
        return jsonify(error='Unauthorized'), 401
    if 'dm' not in user_role():
        return jsonify(error='Forbidden'), 403
    payload = request.get_json(silent=True) or {}
    name = payload.get('name')
    try:
        # Queue async save to avoid blocking request handler
        get_current_game().save_game_async(name=name)
        return jsonify(status='queued')
    except Exception as e:
        return jsonify(error=str(e)), 500


@dm_bp.route('/admin/load', methods=['POST'])
def admin_load():
    if not session.get('username'):
        return jsonify(error='Unauthorized'), 401
    if 'dm' not in user_role():
        return jsonify(error='Forbidden'), 403
    payload = request.get_json(silent=True) or {}
    filename = payload.get('filename')
    index = payload.get('index')
    try:
        # Load under lock to avoid race with in-flight actions
        with get_current_game().game_state_lock:
            if filename:
                # Pass through as relative; GameManagement.resolve will join with save_dir
                get_current_game().load_save(filename=filename)
            elif index is not None:
                try:
                    idx = int(index)
                except Exception:
                    return jsonify(error='index must be integer'), 400
                get_current_game().load_save(index=idx)
            else:
                # Load latest
                get_current_game().load_save()

        # Notify clients to refresh
        try:
            # Ensure all users reference the newly loaded battle map instance
            get_current_game().set_current_battle_map(get_current_game().get_current_battle_map())
        except Exception:
            pass
        # Update module-level session reference used by many routes
        try:
            set_game_session(get_current_game().game_session)
        except Exception:
            pass
        try:
            get_current_game().refresh_client_map()
        except Exception:
            pass
        # Ensure any tile/object overlays are rebuilt
        get_socketio().emit('message', {'type': 'refresh_map'})
        get_socketio().emit('message', {'type': 'turn', 'message': {'game_time': get_current_game().game_session.game_time}})
        return jsonify(status='ok')
    except Exception as e:
        return jsonify(error=str(e)), 500


@dm_bp.route('/admin/manage_saves', methods=['GET'])
def admin_manage_saves():
    if not session.get('username'):
        return redirect(url_for('auth.login'))
    if 'dm' not in user_role():
        return jsonify(error='Forbidden'), 403
    return render_template('manage_saves.html', title='Manage Saves')


@dm_bp.route('/admin/effect', methods=['POST'])
def admin_effect():
    """DM-only endpoint to broadcast visual effects to connected clients.
    Expects JSON: { effect: 'fog'|'rain'|'snow', action: 'start'|'stop'|'update', config: {...} }
    """
    if not session.get('username'):
        return jsonify(error='Unauthorized'), 401
    if 'dm' not in user_role():
        return jsonify(error='Forbidden'), 403
    payload = request.get_json(silent=True) or {}
    effect = payload.get('effect')
    action = payload.get('action')
    config = payload.get('config') or {}
    scope = (payload.get('scope') or 'global').lower()  # 'global' or 'map'
    target_map_name = payload.get('map')  # optional explicit map name
    if not effect or not action:
        return jsonify(error='effect and action required'), 400
    if not special_effects_enabled() and action != 'stop' and (effect == 'map_default' or is_heavy_special_effect(effect)):
        return jsonify(error='Special effects are disabled by configuration'), 409
    try:
        # Validate and sanitize config per effect type
        def _hex_color(c):
            try:
                return bool(re.match(r'^#[0-9a-fA-F]{6}$', str(c)))
            except Exception:
                return False

        def _clamp(v, lo, hi, cast=float):
            try:
                vv = cast(v)
            except Exception:
                vv = lo
            return max(lo, min(hi, vv))

        def validate_effect_config(name, cfg):
            cfg = dict(cfg or {})
            if name == 'snow':
                cfg['intensity'] = _clamp(cfg.get('intensity', 0.6), 0.0, 1.0)
                cfg['wind'] = _clamp(cfg.get('wind', 0.0), -1.0, 1.0)
                cfg['speed'] = _clamp(cfg.get('speed', 1.0), 0.0, 3.0)
                cfg['flakeSize'] = _clamp(cfg.get('flakeSize', 1.0), 0.2, 3.0)
                cfg['turbulence'] = _clamp(cfg.get('turbulence', 0.35), 0.0, 1.0)
                cfg['gusts'] = bool(cfg.get('gusts', False))
                cfg['gustFreq'] = _clamp(cfg.get('gustFreq', 0.04), 0.0, 2.0)
                cfg['gustStrength'] = _clamp(cfg.get('gustStrength', 0.5), 0.0, 1.0)
                cfg['gustDuration'] = _clamp(cfg.get('gustDuration', 1.8), 0.0, 10.0)
                cfg['dof'] = _clamp(cfg.get('dof', 0.35), 0.0, 1.0)
                cfg['accumulationEnabled'] = bool(cfg.get('accumulationEnabled', False))
                cfg['accumulationRate'] = _clamp(cfg.get('accumulationRate', 0.02), 0.0, 1.0)
                cfg['accumulationMax'] = _clamp(cfg.get('accumulationMax', 0.35), 0.0, 1.0)
                if not _hex_color(cfg.get('accumulationColor', '#ffffff')):
                    cfg['accumulationColor'] = '#ffffff'
                if not _hex_color(cfg.get('color', '#ffffff')):
                    cfg['color'] = '#ffffff'
            elif name == 'rain':
                cfg['intensity'] = _clamp(cfg.get('intensity', 0.6), 0.0, 1.0)
                cfg['wind'] = _clamp(cfg.get('wind', 0.0), -1.0, 1.0)
                cfg['speed'] = _clamp(cfg.get('speed', 1.0), 0.0, 3.0)
                cfg['lightning'] = bool(cfg.get('lightning', False))
                cfg['lightningFreq'] = _clamp(cfg.get('lightningFreq', 0.01), 0.0, 1.0)
                cfg['lightningIntensity'] = _clamp(cfg.get('lightningIntensity', 1.0), 0.0, 3.0)
                if not _hex_color(cfg.get('color', '#a8c0e6')):
                    cfg['color'] = '#a8c0e6'
            elif name == 'fog':
                cfg['density'] = _clamp(cfg.get('density', 0.45), 0.0, 2.0)
                cfg['speed'] = _clamp(cfg.get('speed', 0.7), 0.0, 3.0)
                cfg['contrast'] = _clamp(cfg.get('contrast', 1.0), 0.2, 3.0)
                cfg['grain'] = _clamp(cfg.get('grain', 0.15), 0.0, 0.5)
                cfg['falloff'] = _clamp(cfg.get('falloff', 1.0), 0.0, 3.0)
                if not _hex_color(cfg.get('color', '#cfcfd6')):
                    cfg['color'] = '#cfcfd6'
            else:
                # unknown effect: keep as-is to avoid breaking custom effects
                cfg = cfg
            return cfg

        config = validate_effect_config(effect, config)

        # Broadcast to all connected clients
        payload = {'effect': effect, 'action': action, 'config': config}
        get_socketio().emit('effect:set', payload)
        # persist effect state per game so new clients or refreshed pages will re-apply the effect
        try:
            game_key = getattr(get_current_game().game_session, 'root_path', None) or getattr(get_game_session(), 'root_path', None) or get_level()
            if scope == 'map':
                # Determine target map name
                try:
                    if not target_map_name:
                        cur_map = get_current_game().get_map_for_user(session['username'])
                        target_map_name = getattr(cur_map, 'name', None)
                except Exception:
                    target_map_name = None

                if effect == 'map_default' and action == 'start':
                    # Clear per-map overrides and broadcast map default
                    try:
                        if game_key in get_active_effects_map() and target_map_name in get_active_effects_map()[game_key]:
                            prev = get_active_effects_map()[game_key].pop(target_map_name, {})
                        else:
                            prev = {}
                        for ef_name in list(prev.keys()):
                            try:
                                get_socketio().emit('effect:set', {'effect': ef_name, 'action': 'stop'})
                            except Exception:
                                pass
                        # emit map default
                        try:
                            cur_map = get_current_game().get_map_for_user(session['username'])
                            props = getattr(cur_map, 'properties', {}) or {}
                            map_def = props.get('default_effect')
                            if map_def:
                                get_socketio().emit('effect:set', map_def)
                        except Exception:
                            pass
                    except Exception:
                        pass
                else:
                    # Persist per-map override
                    get_active_effects_map().setdefault(game_key, {}).setdefault(target_map_name, {})
                    if action == 'stop':
                        # Remove this effect from the map overrides
                        try:
                            get_active_effects_map()[game_key][target_map_name].pop(effect, None)
                        except Exception:
                            pass
                    else:
                        get_active_effects_map()[game_key][target_map_name][effect] = {'effect': effect, 'action': 'start', 'config': config}
            else:
                # Global scope (existing behavior)
                if effect == 'map_default' and action == 'start':
                    # remove any DM-persisted effects for this game
                    prev = get_active_effects().pop(game_key, {})
                    for ef_name in list(prev.keys()):
                        try:
                            get_socketio().emit('effect:set', {'effect': ef_name, 'action': 'stop'})
                        except Exception:
                            pass
                    try:
                        cur_map = get_current_game().get_map_for_user(session['username'])
                        props = getattr(cur_map, 'properties', {}) or {}
                        map_def = props.get('default_effect')
                        if map_def:
                            get_socketio().emit('effect:set', map_def)
                    except Exception:
                        pass
                else:
                    if action == 'stop':
                        if game_key in get_active_effects() and effect in get_active_effects()[game_key]:
                            del get_active_effects()[game_key][effect]
                    else:
                        get_active_effects().setdefault(game_key, {})[effect] = {'effect': effect, 'action': 'start', 'config': config}
        except Exception:
            # non-fatal; proceed
            pass
        return jsonify(status='ok')
    except Exception as e:
        return jsonify(error=str(e)), 500
@dm_bp.route('/admin/perf', methods=['GET'])
def admin_perf():
    if not session.get('username'):
        return jsonify(error='Unauthorized'), 401
    if 'dm' not in user_role():
        return jsonify(error='Forbidden'), 403
    with get_perf_lock():
        routes = []
        for ep, b in get_perf_stats()['routes'].items():
            routes.append({
                'endpoint': ep,
                'count': b['count'],
                'avg_ms': round(b['total_ms'] / b['count'], 2) if b['count'] else 0,
                'max_ms': round(b['max_ms'], 2),
                'last_ms': round(b['last_ms'], 2),
                'slow': b['slow'],
            })
        routes.sort(key=lambda r: r['avg_ms'] * r['count'], reverse=True)
        snapshot = {
            'slow_threshold_ms': get_perf_stats()['slow_threshold_ms'],
            'routes': routes,
            'socket_emits': dict(get_perf_stats()['socket_emits']),
            'recent_slow': list(get_perf_stats()['recent_slow']),
        }
    return jsonify(snapshot)


@dm_bp.route('/admin/perf/reset', methods=['POST'])
def admin_perf_reset():
    if not session.get('username'):
        return jsonify(error='Unauthorized'), 401
    if 'dm' not in user_role():
        return jsonify(error='Forbidden'), 403
    with get_perf_lock():
        get_perf_stats()['routes'].clear()
        get_perf_stats()['socket_emits'].clear()
        get_perf_stats()['recent_slow'].clear()
    return jsonify(status='ok')
@dm_bp.route('/available_npcs', methods=['GET'])
def get_available_npcs():
    """Get list of available NPCs for spawning"""
    # Check if user is DM
    if 'dm' not in user_role():
        return jsonify(error='Only DMs can access NPC list'), 403

    try:
        cached = getattr(app, '_available_npcs_cache', None)
        if cached is None:
            # Use session.load_npcs() to get actual NPC instances with full data
            npcs = get_game_session().load_npcs()

            npc_list = []
            for npc in npcs:
                npc_list.append({
                    'id': npc.npc_type if hasattr(npc, 'npc_type') else npc.properties.get('id', 'unknown'),
                    'name': npc.label() if hasattr(npc, 'label') else npc.properties.get('label', npc.name),
                    'type': npc.properties.get('type', 'Unknown'),
                    'image': npc.token_image() if hasattr(npc, 'token_image') else npc.properties.get('token', f'{npc.name}.png'),
                    'cr': npc.properties.get('cr', 'Unknown'),
                    'size': npc.properties.get('size', 'Medium'),
                    'ac': npc.armor_class() if hasattr(npc, 'armor_class') else npc.properties.get('ac', 'Unknown'),
                    'hp': npc.max_hp() if hasattr(npc, 'max_hp') else npc.properties.get('hp', 'Unknown')
                })

            npc_list.sort(key=lambda x: x['name'].lower())
            get_app()._available_npcs_cache = npc_list
            cached = npc_list

        return jsonify(npcs=cached)

    except Exception as e:
        get_logger().error(f"Error getting available NPCs: {str(e)}")
        return jsonify(error='Failed to load NPCs'), 500

@dm_bp.route('/available_objects', methods=['GET'])
def get_available_objects():
    """Get list of available objects for spawning"""
    # Check if user is DM
    if 'dm' not in user_role():
        return jsonify(error='Only DMs can access object list'), 403

    try:
        cached = getattr(app, '_available_objects_cache', None)
        if cached is None:
            # Load all objects from the objects.yml file
            all_objects = get_game_session().load_yaml_file('items', 'objects')

            object_list = []
            for object_id, object_data in all_objects.items():
                if object_data.get('token_editor_image'):
                    token_image = object_data['token_editor_image']
                else:
                    token_image = f'{object_id}.png'

                object_list.append({
                    'id': object_id,
                    'name': object_data.get('name', object_id.replace('_', ' ').title()),
                    'description': object_data.get('description', ''),
                    'image': token_image,
                    'ac': object_data.get('default_ac', 'N/A'),
                    'hp': object_data.get('max_hp', 'N/A'),
                    'passable': object_data.get('passable', False),
                    'opaque': object_data.get('opaque', True),
                    'color': object_data.get('color', 'brown')
                })

            object_list.sort(key=lambda x: x['name'])
            get_app()._available_objects_cache = object_list
            cached = object_list

        return jsonify(objects=cached)

    except Exception as e:
        get_logger().error(f"Error loading objects: {str(e)}")
        return jsonify(error=f'Failed to load objects: {str(e)}'), 500

@dm_bp.route('/spawn_npc', methods=['POST'])
def spawn_npc():
    """Spawn an NPC at the specified coordinates"""
    # Check if user is DM
    if 'dm' not in user_role():
        return jsonify(error='Only DMs can spawn NPCs'), 403
    
    if not request.json:
        return jsonify(error='No data provided'), 400
    
    npc_type = request.json.get('npc_type')
    x = request.json.get('x')
    y = request.json.get('y')
    
    if not npc_type or x is None or y is None:
        return jsonify(error='Missing required parameters'), 400
    
    try:
        battle_map = get_current_game().get_map_for_user(session['username'])
        
        # Check if the position is within map bounds
        if (x < 0 or y < 0 or x >= battle_map.size[1] or y >= battle_map.size[0]):
            return jsonify(error='Position is outside map bounds'), 400
        
        # Check if the position is occupied by an entity
        if battle_map.entity_at(x, y):
            return jsonify(error='Position is occupied'), 400
        
        # Create the NPC
        try:
            npc = get_game_session().npc(npc_type, {"rand_life": True})
        except FileNotFoundError:
            return jsonify(error=f'NPC type "{npc_type}" not found'), 400
        except Exception as e:
            return jsonify(error=f'Failed to create NPC: {str(e)}'), 400
        
        # Add to map using the add method (which handles placement and group assignment)
        battle_map.add(npc, x, y, group='b')
        
        # If there's an active battle, optionally add to initiative
        battle = get_current_game().get_current_battle()
        if battle:
            # For now, don't automatically add to initiative
            # The DM can manually add them if needed
            pass
        
        get_logger().info(f"DM {session['username']} spawned {npc_type} at ({x}, {y})")
        
        # Notify all clients of the map update
        get_socketio().emit('message', {'type': 'refresh_map'})
        
        return jsonify(status='ok', entity_uid=npc.entity_uid)
        
    except Exception as e:
        get_logger().error(f"Error spawning NPC: {str(e)}")
        return jsonify(error=f'Failed to spawn NPC: {str(e)}'), 500

@dm_bp.route('/spawn_object', methods=['POST'])
def spawn_object():
    """Spawn an object at the specified coordinates"""
    # Check if user is DM
    if 'dm' not in user_role():
        return jsonify(error='Only DMs can spawn objects'), 403
    
    if not request.json:
        return jsonify(error='No data provided'), 400
    
    object_type = request.json.get('object_type')
    x = request.json.get('x')
    y = request.json.get('y')
    
    if not object_type or x is None or y is None:
        return jsonify(error='Missing required parameters'), 400
    
    try:
        battle_map = get_current_game().get_map_for_user(session['username'])
        
        # Check if the position is within map bounds
        if (x < 0 or y < 0 or x >= battle_map.size[0] or y >= battle_map.size[1]):
            return jsonify(error='Position is outside map bounds'), 400
        
        # For objects, we allow placement on occupied squares (unlike NPCs)
        # Objects can be placed on top of terrain or other non-entity objects
        
        # Create the object
        try:
            # Load object properties from objects.yml
            object_properties = get_game_session().load_object(object_type)
            if not object_properties:
                return jsonify(error=f'Object type "{object_type}" not found'), 400
            
            # Check if object is placeable
            if not object_properties.get('placeable', True):
                return jsonify(error=f'Object type "{object_type}" is not placeable'), 400
            
            # Create object instance
            object_klass = object_type_to_klass(object_properties['item_class'])
            object_instance = object_klass(get_game_session(), battle_map, {
                **object_properties,
                'type': object_type,
                'entity_uid': str(uuid.uuid4())
            })
            
        except Exception as e:
            return jsonify(error=f'Failed to create object: {str(e)}'), 400
        
        # Add object to the map
        battle_map.place_object(object_instance, x, y)
        
        # Also add to interactable_objects if it has interactions
        if hasattr(object_instance, 'available_interactions') and object_instance.available_interactions(object_instance, None, admin=True):
            battle_map.interactable_objects[object_instance] = [x, y]
        
        get_logger().info(f"DM {session['username']} spawned {object_type} at ({x}, {y})")
        
        # Notify all clients of the map update
        get_socketio().emit('message', {'type': 'refresh_map'})
        
        return jsonify(status='ok', entity_uid=object_instance.entity_uid)
        
    except Exception as e:
        get_logger().error(f"Error spawning object: {str(e)}")
        return jsonify(error=f'Failed to spawn object: {str(e)}'), 500

@dm_bp.route('/delete_entity', methods=['POST'])
def delete_entity():
    """Delete an entity from the battlefield"""
    # Check if user is DM
    if 'dm' not in user_role():
        return jsonify(error='Only DMs can delete entities'), 403
    
    if not request.json:
        return jsonify(error='No data provided'), 400
    
    entity_uid = request.json.get('entity_uid')
    
    if not entity_uid:
        return jsonify(error='Missing entity_uid parameter'), 400
    
    try:
        # Find the entity across all maps
        entity = get_current_game().get_entity_by_uid(entity_uid)
        if not entity:
            return jsonify(error='Entity not found'), 404
        
        # Find which map contains the entity
        battle_map = None
        for map_obj in get_current_game().maps.values():
            if map_obj.entity_by_uid(entity_uid):
                battle_map = map_obj
                break
        
        if not battle_map:
            return jsonify(error='Entity not found on any map'), 404
        
        # Remove from battle if it exists
        battle = get_current_game().get_current_battle()
        if battle and entity in battle.combat_order:
            battle.remove(entity, from_map=False)
        
        # Remove from map
        battle_map.remove(entity)
        
        get_logger().info(f"DM {session['username']} deleted entity {entity.label()} ({entity_uid})")
        
        # Notify all clients of the map update
        get_socketio().emit('message', {'type': 'refresh_map'})
        
        return jsonify(status='ok', entity_uid=entity_uid)
        
    except Exception as e:
        get_logger().error(f"Error deleting entity: {str(e)}")
        return jsonify(error=f'Failed to delete entity: {str(e)}'), 500

@dm_bp.route('/move_entity', methods=['POST'])
def move_entity():
    """Move an existing entity to a new position (for PCs that already exist)"""
    # Check if user is DM
    if 'dm' not in user_role():
        return jsonify(error='Only DMs can move entities'), 403
    
    if not request.json:
        return jsonify(error='No data provided'), 400
    
    entity_uid = request.json.get('entity_uid')
    x = request.json.get('x')
    y = request.json.get('y')
    
    if not entity_uid or x is None or y is None:
        return jsonify(error='Missing required parameters'), 400
    
    try:
        # Find the entity across all maps
        entity = get_current_game().get_entity_by_uid(entity_uid)
        if not entity:
            return jsonify(error='Entity not found'), 404
        
        # Get the target map (current map for user)
        target_map = get_current_game().get_map_for_user(session['username'])
        
        # Check if the position is within map bounds
        if (x < 0 or y < 0 or x >= target_map.size[1] or y >= target_map.size[0]):
            return jsonify(error='Position is outside map bounds'), 400
        
        # Check if the position is occupied by another entity
        if target_map.entity_at(x, y):
            return jsonify(error='Position is occupied'), 400
        
        # Find current map containing the entity
        current_map = None
        for map_obj in get_current_game().maps.values():
            if map_obj.entity_by_uid(entity_uid):
                current_map = map_obj
                break
        
        # Remove from current map if it's on a different map
        if current_map and current_map != target_map:
            current_map.remove(entity)
        elif current_map == target_map:
            # Just move within the same map
            current_map.remove(entity)
        
        # Add to target map at new position
        target_map.add(entity, x, y, entity.group)
        
        get_logger().info(f"DM {session['username']} moved entity {entity.label()} to ({x}, {y})")
        
        # Notify all clients of the map update
        get_socketio().emit('message', {'type': 'refresh_map'})
        
        return jsonify(status='ok', entity_uid=entity_uid)
        
    except Exception as e:
        get_logger().error(f"Error moving entity: {str(e)}")
        return jsonify(error=f'Failed to move entity: {str(e)}'), 500

@dm_bp.route('/available_pcs', methods=['GET'])
def available_pcs():
    """Get available player characters for spawning"""
    # Check if user is DM
    if 'dm' not in user_role():
        return jsonify(error='Only DMs can access player characters'), 403
    
    try:
        # Load all characters from the session
        characters = get_game_session().load_characters()
        
        # Convert to list of dictionaries for JSON response
        pc_list = []
        for char in characters:
            pc_list.append({
                'entity_uid': char.entity_uid,
                'name': char.name,
                'label': char.label(),
                'token_image': char.token_image(),
                'class_and_level': char.class_and_level() if hasattr(char, 'class_and_level') else [],
                'race': char.race() if hasattr(char, 'race') else 'Unknown'
            })
        
        # Sort alphabetically by name
        pc_list.sort(key=lambda x: x['name'])
        
        return jsonify(status='ok', pcs=pc_list)
        
    except Exception as e:
        get_logger().error(f"Error loading player characters: {str(e)}")
        return jsonify(error=f'Failed to load player characters: {str(e)}'), 500

@dm_bp.route('/update_npc', methods=['POST'])
def update_npc():
    """Update NPC properties (name, group, description, backstory)"""
    # Check if user is DM
    if 'dm' not in user_role():
        return jsonify(error='Only DMs can update NPCs'), 403
    
    if not request.json:
        return jsonify(error='No data provided'), 400
    
    entity_id = request.json.get('entity_id')
    name = request.json.get('name')
    group = request.json.get('group')
    description = request.json.get('description')
    backstory = request.json.get('backstory')
    
    if not entity_id:
        return jsonify(error='Missing entity_id parameter'), 400
    
    try:
        battle_map = get_current_game().get_map_for_user(session['username'])
        entity = battle_map.entity_by_uid(entity_id)
        
        if not entity:
            return jsonify(error='Entity not found'), 404
        
        if not entity.is_npc():
            return jsonify(error='Can only update NPCs'), 400
        
        # Update properties
        if name is not None:
            if name.strip():
                entity.properties['label'] = name.strip()
            elif 'label' in entity.properties:
                del entity.properties['label']  # Remove custom label to fall back to original name
        
        if group is not None and group in ['a', 'b', 'c']:
            entity.group = group
            entity.properties['group'] = group
        
        if description is not None:
            entity.properties['description'] = description.strip()
        
        if backstory is not None:
            entity.properties['backstory'] = backstory.strip()
        
        get_logger().info(f"DM {session['username']} updated NPC {entity_id}: name='{name}', group='{group}'")
        
        # Notify all clients of the entity update (in case name/group affects display)
        get_socketio().emit('message', {'type': 'refresh_map'})
        
        return jsonify(success=True)
        
    except Exception as e:
        get_logger().error(f"Error updating NPC: {str(e)}")
        return jsonify(error=f'Failed to update NPC: {str(e)}'), 500

@dm_bp.route('/update_npc_default_controller', methods=['POST'])
def update_npc_default_controller():
    if 'dm' not in user_role():
        return jsonify({'success': False, 'error': 'DM access required'}), 403
    try:
        data = request.get_json() if request.is_json else request.form
        new_value = data.get('value')
        if new_value not in ['manual', 'ai', 'llm']:
            return jsonify({'success': False, 'error': 'Invalid controller value'}), 400
        get_current_game().npc_controller = new_value
        return jsonify({'success': True, 'npc_default_controller': get_current_game().npc_controller})
    except Exception as e:
        get_logger().error(f"Failed to update npc_default_controller: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500



@dm_bp.route('/add', methods=['GET'])
def add():
    battle_map = get_current_game().get_map_for_user(session['username'])
    battle = get_current_game().get_current_battle()
    entity_uid = request.args.get('id')
    entity = battle_map.entity_by_uid(entity_uid)
    if entity is None:
        return jsonify(error='Entity not found'), 404

    if battle:
        # Mid-battle add: actually roll initiative for the new entity, build
        # a controller for it, and slot it in to act NEXT (i.e. at the "top"
        # of the remaining round) without disturbing the current turn.
        if 'dm' not in user_role():
            return jsonify(error='Only DMs can add entities to an active battle'), 403

        # If already in the battle, no-op (idempotent), but still return the
        # rendered turn-order row so the caller doesn't break.
        already_in_battle = entity in battle.entities

        default_group = 'a' if isinstance(entity, PlayerCharacter) else 'b'

        if not already_in_battle:
            controller = get_current_game().build_combat_controller_for_entity(entity)
            if controller is None:
                controller = GenericController(get_game_session())
            try:
                controller.register_handlers_on(entity)
            except Exception:
                pass

            with get_current_game().game_state_lock:
                # Add to the battle (don't auto-add to initiative; we want to
                # control placement so the new entity acts next this round).
                battle.add(entity, default_group, controller=controller)
                # Roll initiative for the new entity and insert it directly
                # after the current turn so it acts on this round at the
                # "top" relative to whoever still has to go.
                state = battle.entities.get(entity)
                if state is not None:
                    try:
                        state['initiative'] = entity.initiative(battle)
                    except Exception:
                        state['initiative'] = 0
                    # Make sure it's not already in combat_order, then insert
                    # right after the current actor.
                    if entity not in battle.combat_order:
                        insert_at = (battle.current_turn_index + 1) if battle.combat_order else 0
                        battle.combat_order.insert(insert_at, entity)

        get_socketio().emit('message', {'type': 'initiative', 'message': {'index': battle.current_turn_index}})
        get_socketio().emit('message', {'type': 'turn', 'message': {}})
        get_socketio().emit('message', {'type': 'refresh_map'})
        # Return the rendered turn-order row so the existing client code
        # (which appends the response to #turn-order) keeps working.
        return render_template('add.html', entity=entity, is_pc=isinstance(entity, PlayerCharacter),
                               default_controller=('manual' if isinstance(entity, PlayerCharacter)
                                                   else get_current_game().effective_npc_combat_controller()))
    else:
        is_pc = isinstance(entity, PlayerCharacter)
        default_controller = 'manual' if is_pc else get_current_game().effective_npc_combat_controller()
        return render_template('add.html', entity=entity, is_pc=is_pc, default_controller=default_controller)


@dm_bp.route('/remove_from_battle', methods=['POST'])
def remove_from_battle():
    """DM-only: remove an entity from the active battle's initiative without
    removing it from the map. The entity becomes a non-participant again and
    can act/move freely (subject to lazy-add rules)."""
    if 'dm' not in user_role():
        return jsonify(error='Only DMs can modify the initiative'), 403
    battle = get_current_game().get_current_battle()
    if not battle:
        return jsonify(error='No active battle'), 400
    data = request.get_json(silent=True) or request.form
    entity_uid = data.get('entity_uid') or data.get('id')
    if not entity_uid:
        return jsonify(error='Missing entity_uid'), 400
    entity = get_current_game().get_entity_by_uid(entity_uid)
    if entity is None:
        return jsonify(error='Entity not found'), 404
    with get_current_game().game_state_lock:
        if entity in battle.entities or entity in battle.combat_order:
            battle.remove(entity, from_map=False)
        # If we just removed the last combatant on one side the battle may
        # be over; check and clean up so non-participants can act freely.
        try:
            if battle.battle_ends():
                get_current_game().end_current_battle()
        except Exception:
            pass
    get_socketio().emit('message', {'type': 'initiative',
                              'message': {'index': battle.current_turn_index if get_current_game().get_current_battle() else None}})
    get_socketio().emit('message', {'type': 'turn', 'message': {}})
    get_socketio().emit('message', {'type': 'refresh_map'})
    return jsonify(status='ok')


@dm_bp.route('/tracks', methods=['GET'])
def get_tracks():
    current_soundtrack = get_current_game().current_soundtrack
    tracks = []
    for index, track in enumerate(SOUNDTRACKS):
        track_data = {
            'id': track['name'],
            'url': track['file'],
            'name': track['name'],
        }
        tracks.append(track_data)
    if current_soundtrack:
        current_soundtrack_name = current_soundtrack['name']
    else:
        current_soundtrack_name = None
    print(f"current soundtrack {current_soundtrack_name}")
    return render_template('soundtrack.jinja', tracks=tracks, current_soundtrack=current_soundtrack, current_soundtrack_name=current_soundtrack_name)

@dm_bp.route('/sound', methods=['POST'])
def sound():
    track_id = request.json.get('track_id', 'background')

    get_current_game().play_soundtrack(track_id)
    return jsonify(status='ok')

@dm_bp.route('/volume', methods=['POST'])
def set_volume():
    volume = int(request.json['volume'])
    get_current_game().set_volume(volume)
   
    return jsonify(status='ok')

@dm_bp.route('/seek', methods=['POST'])
def seek():
    time_s = int(request.json['time'])
    get_current_game().seek_soundtrack(time_s)
    return jsonify(status='ok')



@dm_bp.route('/unequip', methods=['POST'])
def unequip():
    battle_map = get_current_game().get_map_for_user(session['username'])
    entity_id = request.form['id']
    item_id = request.form['item_id']
    entity = battle_map.entity_by_uid(entity_id)
    if entity:
        entity.unequip(item_id)
        get_socketio().emit('message', {'type': 'refresh_map'})
        return jsonify(status='ok')
    return jsonify(error="Entity not found"), 404

@dm_bp.route('/equip', methods=['POST'])
def equip():
    battle_map = get_current_game().get_map_for_user(session['username'])
    entity_id = request.form['id']
    item_id = request.form['item_id']
    entity = battle_map.entity_by_uid(entity_id)
    if entity:
        entity.equip(item_id)
        get_socketio().emit('message', {'type': 'refresh_map'})
        return jsonify(status='ok')

    return jsonify(error="Entity not found"), 404


@dm_bp.route('/dm/items_catalog', methods=['GET'])
def dm_items_catalog():
    """Return the full catalog of items (weapons + equipment + objects) for DM autocomplete."""
    if 'dm' not in user_role():
        return jsonify(error='DM access required'), 403

    query = (request.args.get('q') or '').strip().lower()
    catalog = []

    def _push(name, payload, category):
        if not isinstance(payload, dict):
            return
        label = payload.get('label') or payload.get('name') or str(name)
        entry = {
            'name': str(name),
            'label': str(label),
            'category': category,
            'type': payload.get('type') or payload.get('subtype') or category,
            'image': payload.get('image') or str(name),
            'weight': payload.get('weight'),
            'cost': payload.get('cost'),
        }
        if query and query not in entry['name'].lower() and query not in entry['label'].lower():
            return
        catalog.append(entry)

    try:
        for name, payload in (get_game_session().load_weapons() or {}).items():
            _push(name, payload, 'weapon')
    except Exception:
        pass
    try:
        for name, payload in (get_game_session().load_all_equipments() or {}).items():
            _push(name, payload, 'equipment')
    except Exception:
        pass
    try:
        objects = get_game_session().load_yaml_file('items', 'objects') or {}
        for name, payload in objects.items():
            _push(name, payload, 'object')
    except Exception:
        pass

    catalog.sort(key=lambda e: (e['category'], e['label'].lower()))
    return jsonify(items=catalog)


def _dm_resolve_entity(entity_id):
    """Locate an entity (or object with inventory) by uid for DM operations."""
    entity = get_current_game().get_entity_by_uid(entity_id)
    if entity is not None:
        return entity
    maps_attr = getattr(get_current_game(), 'maps', None)
    if maps_attr:
        for battle_map in maps_attr.values():
            try:
                ent = battle_map.object_by_uid(entity_id)
            except Exception:
                ent = None
            if ent is not None:
                return ent
    return None


@dm_bp.route('/dm/inventory', methods=['GET'])
def dm_inventory_get():
    """Return current inventory of an entity for DM editing."""
    if 'dm' not in user_role():
        return jsonify(error='DM access required'), 403
    entity_id = request.args.get('id')
    if not entity_id:
        return jsonify(error='Missing id'), 400
    entity = _dm_resolve_entity(entity_id)
    if entity is None:
        return jsonify(error='Entity not found'), 404

    items = []
    for name, info in (getattr(entity, 'inventory', {}) or {}).items():
        try:
            details = get_game_session().load_thing(name) or {}
        except Exception:
            details = {}
        items.append({
            'name': str(name),
            'label': details.get('label') or details.get('name') or str(name),
            'qty': int(info.get('qty', 0)) if isinstance(info, dict) else 0,
            'type': details.get('type') or info.get('type') if isinstance(info, dict) else None,
            'image': details.get('image') or str(name),
        })
    items.sort(key=lambda e: e['label'].lower())
    return jsonify(entity_id=entity_id, items=items)


@dm_bp.route('/dm/inventory/add', methods=['POST'])
def dm_inventory_add():
    """DM: add an item (by catalog name) to an entity's inventory."""
    if 'dm' not in user_role():
        return jsonify(success=False, error='DM access required'), 403
    data = request.get_json(silent=True) or request.form
    entity_id = (data.get('entity_id') or '').strip()
    item_name = (data.get('item_name') or '').strip()
    try:
        qty = int(data.get('qty', 1))
    except (TypeError, ValueError):
        qty = 1
    if not entity_id or not item_name:
        return jsonify(success=False, error='entity_id and item_name are required'), 400
    if qty <= 0:
        return jsonify(success=False, error='qty must be positive'), 400

    entity = _dm_resolve_entity(entity_id)
    if entity is None:
        return jsonify(success=False, error='Entity not found'), 404

    try:
        source_item = get_game_session().load_thing(item_name)
    except Exception:
        source_item = None
    if source_item is None:
        return jsonify(success=False, error=f'Unknown item: {item_name}'), 404

    try:
        entity.add_item(item_name, amount=qty)
    except Exception as exc:
        return jsonify(success=False, error=f'Failed to add item: {exc}'), 500

    try:
        get_output_logger().log(
            f"DM gave {qty} x {source_item.get('label') or source_item.get('name') or item_name} to {entity.label()}",
            visibility='dm_only',
        )
    except Exception:
        pass

    get_socketio().emit('message', {'type': 'refresh_map'})
    new_qty = int((entity.inventory.get(item_name) or {}).get('qty', 0))
    return jsonify(success=True, item_name=item_name, qty=new_qty)


@dm_bp.route('/dm/inventory/remove', methods=['POST'])
def dm_inventory_remove():
    """DM: remove (or decrement) an item from an entity's inventory."""
    if 'dm' not in user_role():
        return jsonify(success=False, error='DM access required'), 403
    data = request.get_json(silent=True) or request.form
    entity_id = (data.get('entity_id') or '').strip()
    item_name = (data.get('item_name') or '').strip()
    all_flag = bool(data.get('all'))
    try:
        qty = int(data.get('qty', 1))
    except (TypeError, ValueError):
        qty = 1
    if not entity_id or not item_name:
        return jsonify(success=False, error='entity_id and item_name are required'), 400

    entity = _dm_resolve_entity(entity_id)
    if entity is None:
        return jsonify(success=False, error='Entity not found'), 404

    inventory = getattr(entity, 'inventory', None) or {}
    if item_name not in inventory:
        # Allow removing equipped items as well.
        try:
            equipped = list(entity.properties.get('equipped', []) or [])
        except Exception:
            equipped = []
        if item_name in equipped:
            try:
                entity.unequip(item_name, transfer_inventory=False)
            except Exception as exc:
                return jsonify(success=False, error=f'Failed to unequip: {exc}'), 500
            get_socketio().emit('message', {'type': 'refresh_map'})
            return jsonify(success=True, item_name=item_name, qty=0)
        return jsonify(success=False, error='Entity does not have that item'), 404

    current_qty = int((inventory.get(item_name) or {}).get('qty', 0))
    drop = current_qty if all_flag else max(1, qty)
    try:
        entity.remove_item(item_name, amount=drop)
    except Exception as exc:
        return jsonify(success=False, error=f'Failed to remove item: {exc}'), 500

    try:
        get_output_logger().log(
            f"DM removed {drop} x {item_name} from {entity.label()}",
            visibility='dm_only',
        )
    except Exception:
        pass

    get_socketio().emit('message', {'type': 'refresh_map'})
    new_qty = int((entity.inventory.get(item_name) or {}).get('qty', 0))
    return jsonify(success=True, item_name=item_name, qty=new_qty)


@dm_bp.route('/dm/container/contents', methods=['GET'])
def dm_container_contents():
    """DM: get contents of a container item."""
    if 'dm' not in user_role():
        return jsonify(success=False, error='DM access required'), 403
    
    entity_id = request.args.get('entity_id', '').strip()
    container_name = request.args.get('container_name', '').strip()
    
    if not entity_id or not container_name:
        return jsonify(success=False, error='entity_id and container_name are required'), 400
    
    entity = _dm_resolve_entity(entity_id)
    if entity is None:
        return jsonify(success=False, error='Entity not found'), 404
    
    if not hasattr(entity, 'is_container') or not entity.is_container(container_name):
        return jsonify(success=False, error='Item is not a container'), 404
    
    contents = entity.get_container_contents(container_name)
    return jsonify(success=True, contents=contents)


@dm_bp.route('/dm/container/add', methods=['POST'])
def dm_container_add():
    """DM: add an item to a container."""
    if 'dm' not in user_role():
        return jsonify(success=False, error='DM access required'), 403
    
    data = request.get_json(silent=True) or request.form
    entity_id = (data.get('entity_id') or '').strip()
    container_name = (data.get('container_name') or '').strip()
    item_name = (data.get('item_name') or '').strip()
    try:
        qty = int(data.get('qty', 1))
    except (TypeError, ValueError):
        qty = 1
    
    if not entity_id or not container_name or not item_name:
        return jsonify(success=False, error='entity_id, container_name, and item_name are required'), 400
    
    entity = _dm_resolve_entity(entity_id)
    if entity is None:
        return jsonify(success=False, error='Entity not found'), 404
    
    if not entity.add_to_container(container_name, item_name, qty):
        return jsonify(success=False, error='Failed to add item to container'), 500
    
    get_socketio().emit('message', {'type': 'refresh_map'})
    return jsonify(success=True)


@dm_bp.route('/dm/container/remove', methods=['POST'])
def dm_container_remove():
    """DM: remove an item from a container."""
    if 'dm' not in user_role():
        return jsonify(success=False, error='DM access required'), 403
    
    data = request.get_json(silent=True) or request.form
    entity_id = (data.get('entity_id') or '').strip()
    container_name = (data.get('container_name') or '').strip()
    item_name = (data.get('item_name') or '').strip()
    try:
        qty = int(data.get('qty', 1))
    except (TypeError, ValueError):
        qty = 1
    
    if not entity_id or not container_name or not item_name:
        return jsonify(success=False, error='entity_id, container_name, and item_name are required'), 400
    
    entity = _dm_resolve_entity(entity_id)
    if entity is None:
        return jsonify(success=False, error='Entity not found'), 404
    
    if not entity.remove_from_container(container_name, item_name, qty):
        return jsonify(success=False, error='Failed to remove item from container'), 500
    
    get_socketio().emit('message', {'type': 'refresh_map'})
    return jsonify(success=True)


@dm_bp.route('/equipment', methods=['GET'])
def get_equipment():
    battle_map = get_current_game().get_map_for_user(session['username'])
    entity_id = request.args.get('id')
    entity = battle_map.entity_by_uid(entity_id)
    if entity:
        return render_template('equipment.html', entity=entity)
    return jsonify(error="Entity not found"), 404

@dm_bp.route('/usable_items', methods=['GET'])
def usable_items():
    battle_map = get_current_game().get_map_for_user(session['username'])
    entity_id = request.args.get('id', None)
    if not entity_id:
        return jsonify({"error": "entity_id parameter is required"}), 400
    entity = battle_map.entity_by_uid(entity_id) if battle_map is not None else None
    if entity is None:
        entity = get_current_game().get_entity_by_uid(entity_id)

    if not entity:
        return jsonify({"error": f"Entity with id {entity_id} not found"}), 404
    available_items = entity.usable_items()
    available_items.sort(key=lambda item: item['name'])
    action = UseItemAction(get_game_session(), entity, 'use_item')
    return render_template('usable_items.html', entity=entity, usable_items=available_items, action=action)

 

    return jsonify({
        'volume': volume,
        'distance_ft': range_ft,
        'entities': response
    })

@dm_bp.route('/update_group', methods=['POST'])
def update_group():
    if not request.is_json:
        return jsonify(error='Request must be JSON'), 400
    
    data = request.get_json()
    if not data or 'entity_uid' not in data or 'group' not in data:
        return jsonify(error='Missing required parameters'), 400

    entity_uid = data['entity_uid']
    new_group = data['group']
    
    battle = get_current_game().get_current_battle()
    if not battle:
        return jsonify(error='No active battle'), 400

    entity = get_current_game().get_entity_by_uid(entity_uid)
    if not entity:
        return jsonify(error='Entity not found'), 404

    # Update the entity's group in the battle
    if entity in battle.entities:
        old_group = battle.entities[entity]['group']
        battle.entities[entity]['group'] = new_group
        
        # Update the groups dictionary
        if old_group in battle.groups:
            battle.groups[old_group].discard(entity)
        battle.groups.setdefault(new_group, set()).add(entity)
        
        return jsonify(status='ok')
    else:
        return jsonify(error='Entity not in battle'), 400

@dm_bp.route('/update_controller', methods=['POST'])
def update_controller():
    if not request.is_json:
        return jsonify(error='Request must be JSON'), 400
    
    data = request.get_json()
    if not data or 'entity_uid' not in data or 'controller' not in data:
        return jsonify(error='Missing required parameters'), 400

    entity_uid = data['entity_uid']
    new_controller = data['controller']
    action = data.get('action', 'add')  # Default to add if not specified
    
    battle = get_current_game().get_current_battle()
    if not battle:
        return jsonify(error='No active battle'), 400

    entity = get_current_game().get_entity_by_uid(entity_uid)
    if not entity:
        return jsonify(error='Entity not found'), 404

    battle = get_current_game().get_current_battle()

    # Handle setting engine-side controller kinds
    if action == 'set':
        engine_controller = None
        if new_controller == 'manual':
            engine_controller = WebController(get_game_session(), None)
            engine_controller.add_user("dm")
            get_current_game().web_controllers[entity] = engine_controller
        elif new_controller == 'ai':
            engine_controller = GenericController(get_game_session())
        elif new_controller == 'llm':
            from natural20.llm_controller import LlmMcpController
            engine_controller = LlmMcpController(get_game_session(), llm_provider=get_llm_handler().current_provider)

        if engine_controller and battle:
            engine_controller.register_handlers_on(entity)
            battle.set_controller_for(entity, engine_controller)
        return jsonify(status='ok')

    # Backward-compatible: maintain web controller user sets
    controller = get_current_game().get_controller_for_entity(entity)
    if not controller:
        controller = WebController(get_game_session(), None)
        controller.add_user("dm")
        get_current_game().web_controllers[entity] = controller

    if action == 'add':
        controller.add_user(new_controller)
    elif action == 'remove':
        controller.users.discard(new_controller)

    return jsonify(status='ok')

@dm_bp.route('/update_hp', methods=['POST'])
def update_hp():
    """Update HP values for an entity (DM only)."""
    if 'dm' not in user_role():
        return jsonify({'success': False, 'error': 'DM access required'}), 403
    
    if not request.is_json:
        return jsonify({'success': False, 'error': 'Request must be JSON'}), 400
    
    data = request.get_json()
    if not data or 'entity_id' not in data or 'hp_type' not in data or 'value' not in data:
        return jsonify({'success': False, 'error': 'Missing required parameters'}), 400

    entity_id = data['entity_id']
    hp_type = data['hp_type']
    value = data['value']
    
    # Validate hp_type
    if hp_type not in ['max_hp', 'current_hp', 'temp_hp']:
        return jsonify({'success': False, 'error': 'Invalid HP type'}), 400
    
    # Validate value
    try:
        value = int(value)
        if value < 0:
            return jsonify({'success': False, 'error': 'HP value cannot be negative'}), 400
        if hp_type == 'max_hp' and value < 1:
            return jsonify({'success': False, 'error': 'Max HP must be at least 1'}), 400
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'HP value must be a number'}), 400

    # Find the entity
    battle_map = get_current_game().get_map_for_user(session['username'])
    entity = battle_map.entity_by_uid(entity_id)
    if not entity:
        return jsonify({'success': False, 'error': 'Entity not found'}), 404

    try:
        if hp_type == 'max_hp':
            # Update max HP - need to handle player characters properly
            if hasattr(entity, 'properties') and isinstance(entity.properties, dict):
                # For player characters, we need to set the base max_hp in properties
                # The max_hp() method will add class features like dwarven_toughness
                if hasattr(entity, 'class_feature') and entity.class_feature('dwarven_toughness'):
                    # If they have dwarven toughness, the base max_hp should exclude the level bonus
                    entity.properties['max_hp'] = value - entity.level()
                else:
                    # Normal case - set the max_hp directly
                    entity.properties['max_hp'] = value
                
                # Adjust current HP if it exceeds new max
                if entity.hp() > value:
                    entity.attributes['hp'] = value
            else:
                # For NPCs or other entities without properties
                entity.attributes['max_hp'] = value
                if entity.hp() > value:
                    entity.attributes['hp'] = value
                    
        elif hp_type == 'current_hp':
            # Validate current HP doesn't exceed max HP
            max_hp = entity.max_hp()
            if value > max_hp:
                return jsonify({'success': False, 'error': f'Current HP cannot exceed Max HP ({max_hp})'}), 400
            entity.attributes['hp'] = value
            
        elif hp_type == 'temp_hp':
            entity._temp_hp = value

        # Emit update to refresh the UI for all connected clients
        get_socketio().emit('message', {'type': 'refresh_map'})
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'success': False, 'error': f'Failed to update HP: {str(e)}'}), 500

@dm_bp.route('/update_action_resources', methods=['POST'])
def update_action_resources():
    """Update action resources for an entity during battle (DM only)."""
    if 'dm' not in user_role():
        return jsonify({'success': False, 'error': 'DM access required'}), 403
    
    if not request.is_json:
        return jsonify({'success': False, 'error': 'Request must be JSON'}), 400
    
    data = request.get_json()
    if not data or 'entity_id' not in data or 'resource_type' not in data or 'value' not in data:
        return jsonify({'success': False, 'error': 'Missing required parameters'}), 400

    entity_id = data['entity_id']
    resource_type = data['resource_type']
    value = data['value']
    operation = data.get('operation', 'set')  # 'set', 'add', or 'subtract'
    
    # Validate resource_type
    valid_resources = ['action', 'bonus_action', 'reaction']
    if resource_type not in valid_resources:
        return jsonify({'success': False, 'error': 'Invalid resource type'}), 400
    
    # Validate value
    try:
        value = int(value)
        if value < 0:
            return jsonify({'success': False, 'error': 'Resource value cannot be negative'}), 400
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Resource value must be a number'}), 400

    # Check if there's an active battle
    battle = get_current_game().get_current_battle()
    if not battle:
        return jsonify({'success': False, 'error': 'No active battle found'}), 400

    # Find the entity
    entity = get_current_game().get_entity_by_uid(entity_id)
    if not entity:
        return jsonify({'success': False, 'error': 'Entity not found'}), 404

    # Check if entity is in the battle
    entity_state = battle.entity_state_for(entity)
    if not entity_state:
        return jsonify({'success': False, 'error': 'Entity is not in the current battle'}), 400

    try:
        current_value = entity_state.get(resource_type, 0)
        
        if operation == 'set':
            new_value = value
        elif operation == 'add':
            new_value = current_value + value
        elif operation == 'subtract':
            new_value = max(0, current_value - value)  # Don't allow negative values
        else:
            return jsonify({'success': False, 'error': 'Invalid operation. Use set, add, or subtract'}), 400
        
        # Cap values at reasonable maximums
        max_values = {'action': 10, 'bonus_action': 10, 'reaction': 10}  # Arbitrary but reasonable limits
        new_value = min(new_value, max_values[resource_type])
        
        # Update the resource
        entity_state[resource_type] = new_value
        
        # Log the change for tracking
        get_output_logger().log(
            f"DM updated {entity.label()}'s {resource_type.replace('_', ' ')} from {current_value} to {new_value}",
            visibility='dm_only',
        )
        
        # Emit update to refresh the UI for all connected clients
        get_socketio().emit('message', {'type': 'refresh_map'})
        
        return jsonify({
            'success': True,
            'resource_type': resource_type,
            'old_value': current_value,
            'new_value': new_value
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': f'Failed to update resource: {str(e)}'}), 500

@dm_bp.route('/update_spell_slots', methods=['POST'])
def update_spell_slots():
    """Update spell slots for an entity (DM only)."""
    if 'dm' not in user_role():
        return jsonify({'success': False, 'error': 'DM access required'}), 403
    
    if not request.is_json:
        return jsonify({'success': False, 'error': 'Request must be JSON'}), 400
    
    data = request.get_json()
    if not data or 'entity_id' not in data or 'character_class' not in data or 'level' not in data or 'value' not in data:
        return jsonify({'success': False, 'error': 'Missing required parameters'}), 400

    entity_id = data['entity_id']
    character_class = data['character_class']
    level = data['level']
    value = data['value']
    operation = data.get('operation', 'set')  # 'set', 'add', or 'subtract'
    
    # Validate level
    try:
        level = int(level)
        if level < 1 or level > 9:
            return jsonify({'success': False, 'error': 'Spell level must be between 1 and 9'}), 400
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Level must be a number'}), 400
    
    # Validate value
    try:
        value = int(value)
        if value < 0:
            return jsonify({'success': False, 'error': 'Spell slot value cannot be negative'}), 400
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Spell slot value must be a number'}), 400

    # Find the entity
    battle_map = get_current_game().get_map_for_user(session['username'])
    entity = battle_map.entity_by_uid(entity_id)
    if not entity:
        return jsonify({'success': False, 'error': 'Entity not found'}), 404

    # Check if entity has spells
    if not hasattr(entity, 'spell_slots') or not entity.spell_slots:
        return jsonify({'success': False, 'error': 'Entity does not have spell slots'}), 400

    # Check if character class exists for this entity
    if character_class not in entity.spell_slots:
        return jsonify({'success': False, 'error': f'Character class {character_class} not found for entity'}), 400

    try:
        current_value = entity.spell_slots[character_class].get(level, 0)
        max_value = entity.max_spell_slots(level, character_class)
        
        if operation == 'set':
            new_value = value
        elif operation == 'add':
            new_value = current_value + value
        elif operation == 'subtract':
            new_value = max(0, current_value - value)  # Don't allow negative values
        else:
            return jsonify({'success': False, 'error': 'Invalid operation. Use set, add, or subtract'}), 400
        
        # Cap values at maximum spell slots
        new_value = min(new_value, max_value)
        
        # Update the spell slot
        entity.spell_slots[character_class][level] = new_value
        
        # Log the change for tracking
        get_output_logger().log(
            f"DM updated {entity.label()}'s {character_class} level {level} spell slots from {current_value} to {new_value}",
            visibility='dm_only',
        )
        
        # Emit update to refresh the UI for all connected clients
        get_socketio().emit('message', {'type': 'refresh_map'})
        
        return jsonify({
            'success': True,
            'character_class': character_class,
            'level': level,
            'old_value': current_value,
            'new_value': new_value,
            'max_value': max_value
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': f'Failed to update spell slots: {str(e)}'}), 500


def _can_act_for_entity(entity_uid):
    """True if the current session may issue rest commands for this entity."""
    if 'dm' in user_role():
        return True
    return controller_of(entity_uid, session.get('username'))


def _wizard_arcane_recovery_state(entity):
    """Return (budget, available_levels) for a wizard's arcane recovery, or None."""
    if not hasattr(entity, 'wizard_level'):
        return None
    if int(getattr(entity, 'arcane_recovery', 0) or 0) <= 0:
        return None
    import math as _math
    budget = _math.ceil(entity.wizard_level / 2)
    slots = entity.spell_slots.get('wizard', {}) or {}
    avail = []
    for level in sorted(slots.keys()):
        try:
            lvl_i = int(level)
        except (TypeError, ValueError):
            continue
        if lvl_i < 1 or lvl_i > 5:
            continue
        if lvl_i > budget:
            continue
        if slots.get(level, 0) < entity.max_spell_slots(lvl_i, 'wizard'):
            avail.append(lvl_i)
    return budget, avail


class _WebRestController:
    """Inline controller used to drive the engine's rest hooks from a request."""

    def __init__(self, arcane_picks=None, hit_die_picks=None):
        self._arcane_picks = list(arcane_picks or [])
        # Queue of integer die types (e.g. 8 for d8) the entity should spend
        # during the short rest. ``prompt_hit_die_roll`` returns each in order
        # and yields 'skip' when the queue is empty so the engine stops
        # spending dice.
        self._hit_die_picks = list(hit_die_picks or [])
        self.consumed_picks = []
        self.consumed_hit_die = []

    def arcane_recovery_ui(self, entity, available_levels):
        while self._arcane_picks:
            level = self._arcane_picks.pop(0)
            if level in available_levels:
                self.consumed_picks.append(level)
                return level
        return None

    def prompt_hit_die_roll(self, entity, available_die_types):
        """Pull the next die type the player wants to spend, or 'skip'."""
        while self._hit_die_picks:
            die_type = self._hit_die_picks.pop(0)
            if die_type in available_die_types:
                self.consumed_hit_die.append(die_type)
                return die_type
        return 'skip'


def _entity_rest_snapshot(entity):
    """JSON-friendly snapshot of mutable rest-related state."""
    snapshot = {
        'hp': entity.hp(),
        'max_hp': entity.max_hp(),
        'hit_die': dict(entity.hit_die()) if hasattr(entity, 'hit_die') else {},
        'spell_slots': {
            klass: dict(slots) for klass, slots in (getattr(entity, 'spell_slots', {}) or {}).items()
        },
        'statuses': list(entity.statuses) if hasattr(entity, 'statuses') else [],
    }
    for attr in ('arcane_recovery', 'second_wind_count', 'lay_on_hands_count', 'ki_count', 'max_ki', 'bardic_inspiration_count', 'bardic_inspiration_max', 'wild_shape_count', 'wild_shape_max', 'rage_count', 'rage_max', 'raging', 'rage_rounds_remaining', 'reckless_attack_active'):
        if hasattr(entity, attr):
            snapshot[attr] = getattr(entity, attr)
    return snapshot


@dm_bp.route('/rest/preview', methods=['GET'])
def rest_preview():
    """Return current state and rest options for an entity."""
    if not session.get('username'):
        return jsonify(success=False, error='Unauthorized'), 401
    entity_id = request.args.get('entity_id')
    rest_type = (request.args.get('type') or 'short').lower()
    if rest_type not in ('short', 'long'):
        return jsonify(success=False, error='Invalid rest type'), 400
    if not entity_id:
        return jsonify(success=False, error='Missing entity_id'), 400
    if not _can_act_for_entity(entity_id):
        return jsonify(success=False, error='Forbidden'), 403

    battle_map = get_current_game().get_map_for_user(session['username'])
    entity = battle_map.entity_by_uid(entity_id)
    if entity is None:
        return jsonify(success=False, error='Entity not found'), 404

    battle = get_current_game().get_current_battle()
    in_combat = bool(battle and getattr(battle, 'started', False))
    try:
        availability = entity.rest_status(battle=battle, battle_map=battle_map,
                                          require_rations=True)
    except Exception:
        availability = None
    payload = {
        'success': True,
        'entity_id': entity_id,
        'entity_name': entity.label() if hasattr(entity, 'label') else getattr(entity, 'name', entity_id),
        'type': rest_type,
        'in_combat': in_combat,
        'requires_force': in_combat,
        'is_dm': 'dm' in user_role(),
        'state': _entity_rest_snapshot(entity),
        'availability': availability,
    }
    if availability is not None:
        this_kind = availability.get(rest_type) or {}
        payload['allowed'] = bool(this_kind.get('allowed'))
        payload['blocking_reasons'] = list(this_kind.get('reasons') or [])
        payload['force_overrides'] = bool(this_kind.get('force_overrides'))
        if rest_type == 'long':
            payload['requires_rations'] = bool(this_kind.get('requires_rations'))
            payload['rations_available'] = int(this_kind.get('rations_available') or 0)
    arcane = _wizard_arcane_recovery_state(entity)
    if rest_type == 'short' and arcane is not None:
        budget, levels = arcane
        payload['arcane_recovery'] = {
            'budget': budget,
            'available_levels': levels,
        }
    return jsonify(payload)


@dm_bp.route('/rest', methods=['POST'])
def take_rest():
    """Run a short or long rest for an entity."""
    if not session.get('username'):
        return jsonify(success=False, error='Unauthorized'), 401
    data = request.get_json(silent=True) or request.form
    entity_id = data.get('entity_id')
    rest_type = (data.get('type') or 'short').lower()
    force = bool(data.get('force'))
    arcane_picks = data.get('arcane_picks') or []
    if isinstance(arcane_picks, str):
        try:
            arcane_picks = [int(x) for x in arcane_picks.split(',') if x.strip()]
        except ValueError:
            return jsonify(success=False, error='arcane_picks must be integers'), 400
    try:
        arcane_picks = [int(x) for x in arcane_picks]
    except (TypeError, ValueError):
        return jsonify(success=False, error='arcane_picks must be integers'), 400

    hit_die_picks = data.get('hit_die_picks') or []
    if isinstance(hit_die_picks, str):
        try:
            hit_die_picks = [int(x) for x in hit_die_picks.split(',') if x.strip()]
        except ValueError:
            return jsonify(success=False, error='hit_die_picks must be integers'), 400
    try:
        hit_die_picks = [int(x) for x in hit_die_picks]
    except (TypeError, ValueError):
        return jsonify(success=False, error='hit_die_picks must be integers'), 400

    if rest_type not in ('short', 'long'):
        return jsonify(success=False, error='Invalid rest type'), 400
    if not entity_id:
        return jsonify(success=False, error='Missing entity_id'), 400
    if not _can_act_for_entity(entity_id):
        return jsonify(success=False, error='Forbidden'), 403
    if force and 'dm' not in user_role():
        return jsonify(success=False, error='Only the DM may force a rest during combat'), 403

    battle_map = get_current_game().get_map_for_user(session['username'])
    entity = battle_map.entity_by_uid(entity_id)
    if entity is None:
        return jsonify(success=False, error='Entity not found'), 404

    battle = get_current_game().get_current_battle()
    before = _entity_rest_snapshot(entity)

    # Validate arcane picks against budget and availability before running the rest.
    if rest_type == 'short' and arcane_picks:
        arcane = _wizard_arcane_recovery_state(entity)
        if arcane is None:
            return jsonify(success=False, error='Entity cannot use arcane recovery'), 400
        budget, _avail = arcane
        if sum(arcane_picks) > budget:
            return jsonify(
                success=False,
                error=f'Arcane recovery picks total {sum(arcane_picks)} exceed budget {budget}'
            ), 400

    # Validate hit-die picks against the entity's currently available hit dice.
    if rest_type == 'short' and hit_die_picks:
        if not hasattr(entity, 'hit_die'):
            return jsonify(success=False, error='Entity has no hit dice to spend'), 400
        available = dict(entity.hit_die() or {})
        remaining = {int(k): int(v) for k, v in available.items()}
        for die_type in hit_die_picks:
            if remaining.get(die_type, 0) <= 0:
                return jsonify(
                    success=False,
                    error=f'No d{die_type} hit dice available to spend'
                ), 400
            remaining[die_type] -= 1

    # Inject a controller so wizard arcane recovery can pick slots from request.
    controller_holder = {}
    rest_controller = _WebRestController(
        arcane_picks=arcane_picks,
        hit_die_picks=hit_die_picks,
    )
    if battle is not None:
        original_controller_for = battle.controller_for

        def _proxy_controller_for(target):
            if target is entity:
                return rest_controller
            return original_controller_for(target)

        battle.controller_for = _proxy_controller_for
        controller_holder['restore'] = lambda: setattr(battle, 'controller_for', original_controller_for)

    try:
        if rest_type == 'short':
            entity.short_rest(battle, force=force, prompt=bool(hit_die_picks),
                              battle_map=battle_map)
            time_advance = 60 * 60  # 1 in-game hour
        else:
            entity.long_rest(battle=battle, battle_map=battle_map, force=force,
                             require_rations=True)
            time_advance = 8 * 60 * 60  # 8 in-game hours

        try:
            get_current_game().game_session.increment_game_time(time_advance)
        except Exception:
            pass

        try:
            get_output_logger().log(
                f"{entity.label() if hasattr(entity, 'label') else entity.name} took a {rest_type} rest"
                + (' (DM forced)' if force else '')
            )
        except Exception:
            pass

        get_socketio().emit('message', {'type': 'refresh_map'})
        return jsonify({
            'success': True,
            'entity_id': entity_id,
            'type': rest_type,
            'forced': force,
            'before': before,
            'after': _entity_rest_snapshot(entity),
            'arcane_picks_consumed': rest_controller.consumed_picks,
            'hit_die_consumed': rest_controller.consumed_hit_die,
            'game_time': get_current_game().game_session.game_time,
        })
    except ValueError as e:
        return jsonify(success=False, error=str(e)), 409
    except Exception as e:
        get_logger().exception('Failed to run rest')
        return jsonify(success=False, error=str(e)), 500
    finally:
        if 'restore' in controller_holder:
            controller_holder['restore']()


@dm_bp.route('/dm_move_entity', methods=['POST'])
def dm_move_entity():
    """Move an entity to a specific position (DM only)."""
    if 'dm' not in user_role():
        return jsonify({'success': False, 'error': 'DM access required'}), 403
    
    if not request.is_json:
        return jsonify({'success': False, 'error': 'Request must be JSON'}), 400
    
    data = request.get_json()
    if not data or 'entity_id' not in data or 'x' not in data or 'y' not in data:
        return jsonify({'success': False, 'error': 'Missing required parameters'}), 400

    entity_id = data['entity_id']
    target_x = data['x']
    target_y = data['y']
    
    # Validate coordinates
    try:
        target_x = int(target_x)
        target_y = int(target_y)
        if target_x < 0 or target_y < 0:
            return jsonify({'success': False, 'error': 'Coordinates must be non-negative'}), 400
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Coordinates must be numbers'}), 400

    # Find the entity
    entity = get_current_game().get_entity_by_uid(entity_id)
    if not entity:
        return jsonify({'success': False, 'error': 'Entity not found'}), 404

    # Get the entity's current map
    battle_map = get_current_game().get_map_for_entity(entity)
    if not battle_map:
        return jsonify({'success': False, 'error': 'Entity map not found'}), 404

    # Validate target coordinates are within map bounds
    if target_x >= battle_map.size[0] or target_y >= battle_map.size[1]:
        return jsonify({'success': False, 'error': f'Coordinates out of bounds. Map size is {battle_map.size[0]}x{battle_map.size[1]}'}), 400

    try:
        # Get current position for logging
        current_x, current_y = battle_map.entity_or_object_pos(entity)
        
        # Check if the target position is placeable for this entity
        battle = get_current_game().get_current_battle()
        if not battle_map.placeable(entity, target_x, target_y, battle):
            return jsonify({'success': False, 'error': 'Target position is not placeable for this entity'}), 400
        
        # Perform the move
        battle_map.move_to(entity, target_x, target_y, battle)
        
        # Log the move for tracking
        get_output_logger().log(
            f"DM moved {entity.label()} from ({current_x}, {current_y}) to ({target_x}, {target_y})",
            visibility='dm_only',
        )
        
        # Emit update to refresh the UI for all connected clients
        get_socketio().emit('message', {'type': 'refresh_map'})
        
        return jsonify({
            'success': True,
            'entity_id': entity_id,
            'from': {'x': current_x, 'y': current_y},
            'to': {'x': target_x, 'y': target_y}
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': f'Failed to move entity: {str(e)}'}), 500

@dm_bp.route('/get_users')
def get_users():
    query = request.args.get('query', '').lower()
    if not query:
        return jsonify([])
    
    # Get all users from username_to_sid
    users = []
    for username in get_current_game().username_to_sid.keys():
        if query in username.lower():
            users.append(username)
    
    return jsonify(users)

@dm_bp.route('/admin/campaign-logs/reset', methods=['POST'])
def admin_reset_campaign_logs():
    """DM-only wipe of persisted campaign logs (combat, chat, assistant, journals)."""
    if not session.get('username'):
        return jsonify(error='Unauthorized'), 401
    if 'dm' not in user_role():
        return jsonify(error='Forbidden'), 403
    payload = request.get_json(silent=True) or {}
    clear_buffers = bool(payload.get('clear_live_conversation_buffers'))
    try:
        removed = get_current_game().reset_campaign_logs(
            clear_live_conversation_buffers=clear_buffers,
        )
        get_llm_handler().clear_history()
        session.pop(DM_AI_CHAT_SESSION_KEY, None)
        session.modified = True
        try:
            get_socketio().emit('message', {'type': 'console', 'messages': []})
        except Exception:
            pass
        return jsonify(success=True, removed_counts=removed)
    except Exception as e:
        get_logger().error(f"Error resetting campaign logs: {e}")
        return jsonify(success=False, error=str(e)), 500


@dm_bp.route('/admin/campaign-logs/status', methods=['GET'])
def admin_campaign_logs_status():
    if not session.get('username'):
        return jsonify(error='Unauthorized'), 401
    if 'dm' not in user_role():
        return jsonify(error='Forbidden'), 403
    try:
        db = getattr(get_current_game(), 'campaign_log_db', None)
        counts = db.counts_by_category() if db is not None else {}
        return jsonify(
            success=True,
            db_path=getattr(db, 'db_path', None),
            counts=counts,
        )
    except Exception as e:
        return jsonify(success=False, error=str(e)), 500
