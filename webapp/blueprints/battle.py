"""Battle blueprint — combat loop, actions, and turn management.

Extracted from webapp/app.py.
"""
import json
import uuid

from flask import Blueprint, request, jsonify, session, redirect, url_for, render_template

from natural20.utils.serialization import object_type_to_klass
from natural20.actions.attack_action import AttackAction, TwoWeaponAttackAction, LinkedAttackAction
from natural20.actions.wild_shape_action import WildShapeAttackAction
from natural20.actions.move_action import MoveAction
from natural20.actions.spell_action import SpellAction
from natural20.actions.interact_action import InteractAction
from natural20.actions.use_item_action import UseItemAction
from natural20.actions.ready_action import ReadyAction
from natural20.spell.extensions.hit_computations import AttackSpell
from natural20.entity import Entity
from natural20.action import Action, AsyncReactionHandler
from natural20.battle import Battle
from natural20.generic_controller import GenericController
from natural20.llm_controller import LlmMcpController
from natural20.web.web_controller import WebController
from natural20.dm import DungeonMaster
from natural20.die_roll import DieRoll
from natural20.utils.action_builder import acquire_targets

from .helpers.auth_utils import logged_in, user_role
from .helpers.battle_setup import augment_turn_order_with_party_pcs
from .helpers.pvp import autofill_pvp_battle_turn_order
from .helpers.journal_utils import _record_narration_for_pcs
from .helpers.special_effects import (
    special_effects_enabled,
    map_default_effect_payloads,
    has_enabled_effect_payloads,
)
from .helpers.template_globals import (
    entities_controlled_by,
    entity_owners,
    controller_of,
    visible_log_messages_for_username,
)
from .helpers.action_utils import action_type_to_class, resolve_requested_action_type
from .helpers.runtime_state import (
    get_current_game,
    get_game_session,
    get_socketio,
    get_output_logger,
    get_llm_handler,
    get_logger,
    get_logins,
    get_tile_px,
    get_level,
    get_active_effects,
    get_active_effects_map,
    get_entity_rag_handler,
)

battle_bp = Blueprint('battle', __name__)


@battle_bp.route('/api/combat-log', methods=['GET'])
def combat_log():
    battle = get_current_game().get_current_battle()
    logs = visible_log_messages_for_username(session['username'], user_role())
    response =[{'message': log} for log in logs]
    return jsonify(combat_log=response)

@battle_bp.route('/combat-log', methods=['GET'])
def get_combat_log():
    battle = get_current_game().get_current_battle()
    logs = visible_log_messages_for_username(session['username'], user_role())
    return render_template('combat-log.html', combat_log=logs,
                           username=session['username'], role=user_role())
@battle_bp.route('/start', methods=['POST'])
def start_battle():
    if get_current_game().trigger_event('start_battle'):
        battle_map = get_current_game().get_current_battle_map()
        get_current_game().set_current_battle(Battle(get_game_session(), battle_map, animation_log_enabled=True))
    return jsonify(status='ok')

@battle_bp.route('/stop', methods=['POST'])
def stop_battle():
    battle = get_current_game().get_current_battle()

    if battle:
        get_current_game().end_current_battle()
    return jsonify(status='ok')

@battle_bp.route('/battle', methods=['POST'])
def start_battle_with_initiative():
    if not get_current_game().trigger_event('start_battle'):

        battle_map = get_current_game().get_current_battle_map()

        if not request.json or 'battle_turn_order' not in request.json:
            return jsonify(error='No entities in turn order'), 400

        battle = Battle(get_game_session(), battle_map, animation_log_enabled=True)
        get_current_game().set_current_battle(battle)

        battle_turn_order = augment_turn_order_with_party_pcs(
            get_current_game(),
            battle_map,
            request.json['battle_turn_order'],
        )
        battle_turn_order = autofill_pvp_battle_turn_order(battle_turn_order)
        print(battle_turn_order)
        for param_item in battle_turn_order:
            entity = get_current_game().get_entity_by_uid(param_item['id'])

            ctrl_kind = param_item.get('controller')
            if ctrl_kind == 'ai':
                controller = GenericController(get_game_session())
            elif ctrl_kind == 'llm':
                # Use the same LLM provider configured for the webapp (e.g., Ollama)
                controller = LlmMcpController(get_game_session(), llm_provider=get_llm_handler().current_provider)
            else:
                controller = get_current_game().get_controller_for_entity(entity)

            if controller is None:
                controller = web_controllers = WebController(get_game_session(), None)
                web_controllers.add_user("dm")

            controller.register_handlers_on(entity)
            battle.add(entity, param_item['group'], controller=controller)
        get_output_logger().log("Battle started.", visibility='public')
        battle.start()
    else:
        print("skipping default battle start")
    scheduled = get_current_game().execute_game_loop()
    return jsonify(status='ok', game_loop='scheduled' if scheduled else 'already_running')


@battle_bp.route('/end_turn', methods=['POST'])
def end_turn():
    battle = get_current_game().get_current_battle()

    end_turn_state = True
    try:
        battle.end_turn()
        end_turn_state = False
        battle.next_turn()
        continue_game()
        return jsonify(status='ok')
    except AsyncReactionHandler as e:
        for _, entity, valid_actions in e.resolve():
            valid_actions_str = [[str(action.uid), str(action), action] for action in valid_actions]
            get_current_game().waiting_for_reaction = [entity, e, e.resolve(), valid_actions_str]
            get_current_game().end_turn_state = end_turn_state
            get_socketio().emit('message', {'type': 'reaction', 'message': {'id': entity.entity_uid, 'reaction': e.reaction_type}})
        return jsonify(status='ok')


def continue_game():
    get_current_game().schedule_continue_game_loop()

@battle_bp.route('/turn_order', methods=['GET'])
def get_turn_order():
    battle = get_current_game().get_current_battle()
    return render_template('battle.html', battle=battle, username=session['username'], role=user_role())

@battle_bp.route('/next_turn', methods=['POST'])
def next_turn():
    battle = get_current_game().get_current_battle()
    if battle:
        with get_current_game().game_state_lock:
            current_turn = battle.current_turn()
            if get_current_game().waiting_for_user_input():
                get_current_game().set_waiting_for_user_input(False)
                current_turn.resolve_trigger('end_of_turn')
                battle.end_turn()
                battle.next_turn()
                if battle.battle_ends():
                    get_current_game().end_current_battle()
                    return jsonify(status='ok')

        if get_current_game().get_current_battle():
            get_current_game().schedule_continue_game_loop()

    return jsonify(status='ok')

@battle_bp.route('/reorder_initiative', methods=['POST'])
def reorder_initiative():
    
    # Check if user is DM
    if 'dm' not in user_role():
        return jsonify(error='Only DMs can reorder initiative'), 403
    
    battle = get_current_game().get_current_battle()
    if not battle:
        return jsonify(error='No active battle'), 400
    
    if not request.json or 'entity_order' not in request.json:
        return jsonify(error='No entity order provided'), 400
    
    entity_order = request.json['entity_order']
    
    try:
        # Use the lock to make the operation atomic
        with get_current_game().game_state_lock:
            battle.reorder_initiative(entity_order)
        
        # Notify all clients of the initiative update
        get_socketio().emit('message', { 'type': 'initiative', 'message': {'index': battle.current_turn_index}})
        
        get_logger().info(f"Initiative reordered by {session['username']}: {entity_order}")
        return jsonify(status='ok')
        
    except ValueError as e:
        get_logger().error(f"Failed to reorder initiative: {str(e)}")
        return jsonify(error=str(e)), 400
    except Exception as e:
        get_logger().error(f"Unexpected error reordering initiative: {str(e)}")
        return jsonify(error='Internal server error'), 500
@battle_bp.route('/actions', methods=['GET'])
def get_actions():
    current_user = session['username']
    battle_map = get_current_game().get_map_for_user(current_user)
    battle = get_current_game().get_current_battle()

    id = request.args.get('id')
    if id is None:
        return jsonify(error="No entity id provided"), 400

    entity = get_current_game().get_entity_by_uid(id)
    if entity:
        entity_map = get_current_game().get_map_for_entity(entity) or battle_map
        if entity_map is None:
            return jsonify(error="Entity is not currently on a map"), 409
        if 'dm' in user_role() or current_user in entity_owners(entity):
            # If a battle is in progress but this entity hasn't been added
            # to its initiative yet, treat it as out-of-battle for action
            # availability so the player isn't locked out (they can still
            # walk around, interact with objects, etc.). They will be
            # lazy-joined on contact via loop_environment.
            effective_battle = battle if (battle and entity in battle.entities) else None
            available_actions = entity.available_actions(session, effective_battle, auto_target=False, map=entity_map, interact_only=True, admin_actions='dm' in user_role())
            # Create entity map for looking up target entities
            entity_lookup = entity_map.entities
            return render_template('actions.html', entity=entity, battle=effective_battle, session=get_game_session(), map=entity_map, available_actions=available_actions, entity_map=entity_lookup, is_dm=('dm' in user_role()))
        else:
            return jsonify(error="Forbidden"), 403
    object_ = battle_map.object_by_uid(id)

    if object_:
        available_actions = object_.available_actions(session, battle, auto_target=False, map=battle_map, interact_only=True, admin_actions=True)
        # Create entity map for looking up target entities
        entity_map = battle_map.entities
        return render_template('actions.html', entity=object_, battle=battle, session=get_game_session(), map=battle_map, available_actions=available_actions, entity_map=entity_map, is_dm=('dm' in user_role()))

    return jsonify(error="Entity not found"), 404

@battle_bp.route("/hide", methods=['GET'])
def get_hiding_spots():
   
    battle = get_current_game().get_current_battle()
    entity_id = request.args.get('id')
    entity = get_current_game().get_entity_by_uid(entity_id)
    if entity is None:
        return jsonify(error="Entity not found"), 404
    battle_map = get_current_game().get_map_for_entity(entity)
    hiding_spots = battle_map.hiding_spots_for(entity, battle)
    return jsonify(hiding_spots=hiding_spots)

@battle_bp.route('/target', methods=['GET'])
def get_target():
   
    battle = get_current_game().get_current_battle()
    payload = json.loads(request.args.get('payload'))
   
    entity_id = payload.get('id')
    x = int(payload.get('x'))
    y = int(payload.get('y'))
    action_info = payload.get('action_info')
    opts = payload.get('opts', {})
    choice = opts.get('choice')
    entity = get_current_game().get_entity_by_uid(entity_id)
    battle_map = get_current_game().get_map_for_entity(entity)
    target_entity = battle_map.entity_at(x, y)
    if not target_entity:
        target_position = [x, y]

    if entity and target_entity and action_info in ['AttackAction', 'LinkedAttackAction']:
        action = AttackAction(get_game_session(), entity, 'attack')
        action.using = opts.get('using')
        action.npc_action = opts.get('npc_action', None)
        action.thrown = opts.get('thrown', False)
        action.target = target_entity

        adv_mod, adv_info, attack_mod = action.compute_advantage_info(battle)
        valid_target = target_entity.allow_targeting()
        if battle:
            valid_targets = battle.valid_targets_for(entity, action)
            valid_target = target_entity in valid_targets
        return jsonify(valid_target=valid_target, adv_mod=adv_mod, adv_info=adv_info, attack_mod=attack_mod)

    elif entity and (target_entity or target_position) and action_info =='SpellAction':
        build_map = SpellAction.build(get_game_session(), entity)
        spell_choice = (opts['spell'], opts['at_level'])
        build_map = build_map['next'](spell_choice)
        if target_entity:
            target = target_entity
        else:
            target = target_position

        target_squares = []
        while not isinstance(build_map, Action):
            target_squares = []
            if build_map['param'][0]['type'] == 'select_choice':
                build_map = build_map['next'](choice)
            elif build_map['param'][0]['type'] == 'select_empty_space':
                build_map = build_map['next'](target)
            elif build_map['param'][0]['type'] == 'select_target':
                build_map = build_map['next'](target)
            elif build_map['param'][0]['type'] == 'select_cone':
                entity_x, entity_y = battle_map.entity_or_object_pos(entity)
                require_los = build_map['param'][0]['require_los']
                target_squares = battle_map.squares_in_cone((entity_x, entity_y), (x, y), build_map['param'][0]['range'] // battle_map.feet_per_grid, require_los=require_los)
                build_map = build_map['next']([x, y])
            elif build_map['param'][0]['type'] == 'select_cube':
                # For directional cube AoE (e.g., Thunderwave) originating from caster
                entity_x, entity_y = battle_map.entity_or_object_pos(entity)
                target_squares = battle_map.squares_in_adjacent_cube((entity_x, entity_y), (x, y), size_squares=3)
                build_map = build_map['next']([x, y])
            elif build_map['param'][0]['type'] == 'select_radius':
                # Sphere AoE centered on the targeted square.
                radius_ft = build_map['param'][0].get('radius', 20)
                require_los = build_map['param'][0].get('require_los', False)
                target_squares = battle_map.squares_in_radius(
                    (x, y), radius_ft, require_los=require_los)
                build_map = build_map['next']([x, y])
            elif build_map['param'][0]['type'] == 'select_square':
                # Square AoE centered on the targeted square.
                size_ft = int(build_map['param'][0].get('size', 10))
                side = max(1, size_ft // battle_map.feet_per_grid)
                target_squares = []
                for dx in range(side):
                    for dy in range(side):
                        tx, ty = x + dx, y + dy
                        if 0 <= tx < battle_map.size[0] and 0 <= ty < battle_map.size[1]:
                            target_squares.append([tx, ty])
                build_map = build_map['next']([x, y])
            elif build_map['param'][0]['type'] == 'select_line':
                entity_x, entity_y = battle_map.entity_or_object_pos(entity)
                length_ft = build_map['param'][0].get('range', 30)
                width_ft = build_map['param'][0].get('width', 5)
                target_squares = battle_map.squares_in_line(
                    (entity_x, entity_y), (x, y), length_ft, width_ft)
                build_map = build_map['next']([x, y])
            elif build_map['param'][0]['type'] == 'select_emanation':
                entity_x, entity_y = battle_map.entity_or_object_pos(entity)
                radius_ft = build_map['param'][0].get('radius', 10)
                target_squares = battle_map.squares_in_emanation(
                    entity, radius_ft, include_origin=True)
                build_map = build_map['next']([entity_x, entity_y])
            else:
                raise ValueError(f"Unknown action type {build_map['param'][0]['type']}")

        action = build_map

        if isinstance(action, AttackSpell):
            if not isinstance(target, Entity):
                # Spell attack must resolve to a real creature; otherwise
                # downstream advantage checks call ``target.has_effect`` on
                # raw [x, y] coords and crash. Surface as not-targetable.
                return jsonify(valid_target=False, target_squares=target_squares,
                               errors=['No valid target at the selected square.'])
            adv_mod, adv_info, attack_mod = action.compute_advantage_info(battle)
            valid_target = target.allow_targeting()

            if battle:
                valid_targets = battle.valid_targets_for(entity, action)
                valid_target = target in valid_targets
            return jsonify(valid_target=valid_target, target_squares=target_squares, adv_mod=adv_mod, adv_info=adv_info, attack_mod=attack_mod)
        else:
            action.validate(battle_map, target)
            if len(action.errors)  > 0:
                return jsonify(valid_target=False, errors=action.errors)
            return jsonify(valid_target=True, target_squares=target_squares, errors=action.errors)
    elif entity and target_entity and action_info == 'UseItemAction':
        action = UseItemAction(get_game_session(), entity, 'use_item')
        valid_target = True
        return jsonify(valid_target=valid_target, adv_info=[[],[]], attack_mod=0)
    else:
        success_rate = None

    return jsonify(success_rate=success_rate)

@battle_bp.route('/spells', methods=['GET'])
def get_spell():
    battle_map = get_current_game().get_map_for_user(session['username'])
    battle = get_current_game().get_current_battle()

    entity_id = request.args.get('id')
    entity = battle_map.entity_by_uid(entity_id)
    if entity.familiar():
        entity_class_level = entity.owner.class_and_level()
    else:
        entity_class_level = entity.class_and_level()
    spells_by_level = {}
    for spell_name in entity.available_spells(battle):
        # get spell available levels
        if SpellAction.can_cast(entity, battle, spell_name):
            spell_info = get_game_session().load_spell(spell_name)
            spells_by_level[spell_info['level']] = spells_by_level.get(spell_info['level'], []) + [spell_name]

    entity_x, entity_y = battle_map.entity_or_object_pos(entity)
    return render_template('spells.html', entity=entity, spells_by_level=spells_by_level,
                           entity_x=entity_x, entity_y=entity_y, entity_class_level=entity_class_level)


@battle_bp.route('/reaction', methods=['GET'])
def get_reaction():
    battle = get_current_game().get_current_battle()
    reaction_type = get_current_game().waiting_for_reaction_input()[1].reaction_type
    return render_template(f"reactions/{reaction_type}.html",
                           username=session['username'],
                           waiting_for_reaction=get_current_game().waiting_for_reaction,
                           battle=battle)

@battle_bp.route('/reaction', methods=['POST'])
def handle_reaction():
    battle = get_current_game().get_current_battle()
    reaction_id = request.form.get('reaction')
    if not reaction_id:
        return jsonify(error="No reaction provided"), 400
    if not get_current_game().waiting_for_reaction:
        return jsonify(error="No reaction expected"), 400
    entity, handler, generator, valid_actions_str = get_current_game().waiting_for_reaction_input()

    if reaction_id == 'no-reaction':
        handler.send(None)
    else:
        for _, _, action in valid_actions_str:
            print(f"action {action.uid} == reaction {reaction_id}")
            if str(action.uid) == reaction_id:
                print(f"selected action {action}")
                handler.send(action)
                break
    get_current_game().clear_reaction_input()
    try:
        # Use the lock to make the operation atomic
        with get_current_game().game_state_lock:
            battle.action(handler.action)
            battle.commit(handler.action)
        get_socketio().emit('message', {'type': 'dismiss_reaction', 'message': {}})

        # reaction was during a players end step, in that case we need to start the next turn
        if get_current_game().end_turn_state:
            get_current_game().end_turn_state = False
            battle.next_turn()

        get_current_game().schedule_after_reaction()
    except AsyncReactionHandler as e:
        for _, entity, valid_actions in e.resolve():
            valid_actions_str = [[str(action.uid), str(action), action] for action in valid_actions]
            get_current_game().waiting_for_reaction = [entity, e, e.resolve(), valid_actions_str]
        get_socketio().emit('message', {'type': 'reaction', 'message': {'id': entity.entity_uid, 'reaction': e.reaction_type}})

    return jsonify(status='ok')

@battle_bp.route('/manual_roll', methods=['POST'])
def manual_roll():
    battle = get_current_game().get_current_battle()
    battle_map = get_current_game().get_map_for_user(session['username'])
    entity_id = request.json['id']
    entity = battle_map.entity_by_uid(entity_id)
    roll = request.json['roll']
    advantage = request.json.get('advantage', False)
    disadvantage = request.json.get('disadvantage', False)
    description = request.json.get('description', None)
    roll_result = DieRoll.roll(roll, disadvantage=disadvantage, advantage=advantage,
                entity=entity, battle=battle, description=description)
    get_output_logger().log(
        f"{entity.name} rolled a {roll_result}={roll_result.result()} for {description}",
        visibility={'kind': 'combat', 'entities': [entity]},
    )
  
    return jsonify(roll_result=roll_result.result(), roll_explaination=str(roll_result))

@battle_bp.route('/switch_pov', methods=['POST'])
def switch_pov():
    battle_map = get_current_game().get_map_for_user(session['username'])
    entity_id = request.form['entity_uid']
    entity = get_current_game().get_entity_by_uid(entity_id)
    entity_battle_map = get_current_game().get_map_for_entity(entity)
    get_current_game().set_pov_entity_for_user(session['username'], entity)
    # Switch the user's current map BEFORE resolving the background so a POV
    # change to an entity on a different map returns that map's background
    # (otherwise the previous map's background is returned and the client UI
    # appears stuck on the old map until a manual refresh).
    map_changed = battle_map != entity_battle_map
    if map_changed:
        get_current_game().switch_map_for_user(session['username'], entity_battle_map.name)
    background = get_current_game().get_background_image_for_user(session['username'])
    map_width, map_height = entity_battle_map.size
    tiles_dimension_height = map_height * get_tile_px()
    tiles_dimension_width = map_width * get_tile_px()
    dm_active = False
    # Include map default effect and whether DM has an active override
    map_default = None
    map_defaults = []
    if map_changed:
        try:
            map_defaults = map_default_effect_payloads(entity_battle_map)
            map_default = map_defaults[0] if map_defaults else None
        except Exception:
            map_default = None

        try:
            game_key = getattr(get_current_game().get_game_session(), 'root_path', None) or getattr(get_game_session(), 'root_path', None) or get_level()
            dm_active = has_enabled_effect_payloads(get_active_effects().get(game_key, {}).values())
            try:
                dm_active = dm_active or has_enabled_effect_payloads(get_active_effects_map().get(game_key, {}).get(entity_battle_map.name, {}).values())
            except Exception:
                pass
        except Exception:
            dm_active = False
    return jsonify(background=f"assets/{background}",
        name=entity_battle_map.name,
        pov_entity=entity_id,
        image_offset_px=entity_battle_map.image_offset_px,
        height=tiles_dimension_height,
        width=tiles_dimension_width,
        map_default_effect=map_default,
        map_default_effects=map_defaults,
        dm_active=dm_active,
        special_effects_enabled=special_effects_enabled())

@battle_bp.route('/read_letter', methods=['POST'])
def read_letter():
    battle_map = get_current_game().get_map_for_user(session['username'])
    battle = get_current_game().get_current_battle()
    entity_id = request.form['id']
    item_id = request.form['item_id']

    entity = battle_map.entity_by_uid(entity_id)
    if not entity:
        return jsonify(error="Entity not found"), 404

    # Process the letter for the entity using the provided item_id.
    item, letter_content = entity.read_item(item_id)

    get_output_logger().log(
        f"{entity.name} read {item.get('label', item['name'])}: {letter_content}",
        visibility={'kind': 'entity_only', 'entities': [entity]},
    )

    # process raw text so that linebreaks are preserved when rendering on the web page
    letter_content = letter_content.replace('\n', '<br>')

    return render_template('letter.html', letter_label=item.get('label', item['name']), letter_content=letter_content)

@battle_bp.route('/action', methods=['POST'])
def action():

    battle = get_current_game().get_current_battle()
    action_request = request.json
    entity_id = action_request['id']
    action_type = action_request['action']
    opts = action_request.get('opts', {})

    selected_spell = opts.get('spell')
    at_level = opts.get('at_level')
    choice = action_request.get('choice', opts.get('choice'))
    entity = get_current_game().get_entity_by_uid(entity_id)
    if entity is None:
        return jsonify({'status': 'error', 'message': 'Entity not found'}), 404

    battle_map = get_current_game().get_map_for_entity(entity)
    if battle_map is None:
        return jsonify({'status': 'error', 'message': 'Entity is not currently on a map'}), 409

    pov_entities = entities_controlled_by(session['username'])
    action_info = {}
    action_hash = None
    target_coords = action_request.get('target', None)
    target = None

    # ReadyAction is collected through a chat dialog with the DM rather than
    # the standard target/param flow. Tell the client to open the dialog.
    if action_type == 'ReadyAction':
        return jsonify({
            'action': 'ReadyAction',
            'type': 'requires_dialog',
            'dialog': 'ready_action',
            'endpoint': '/ready_action',
            'entity_uid': entity_id,
            'prompt': 'Describe the trigger and the action you are readying.',
        })

    if target_coords:
        mode = action_request.get('mode', None)
        if mode == 'cone' or mode == 'point_target' or mode == 'cube' or mode == 'square':
            target = [target_coords['x'], target_coords['y']]
        else:
            if isinstance(target_coords, list):
                target = []
                for entity_uids in target_coords:
                    target.append(battle_map.entity_by_uid(entity_uids))
            elif isinstance(target_coords, str):
                # Target is an entity UID
                target = battle_map.entity_by_uid(target_coords)
            else:
                # Target is coordinates
                tx, ty = int(target_coords['x']), int(target_coords['y'])
                targets = battle_map.entities_at(tx, ty)
                if len(targets) == 1:
                    target = targets[0]
                elif len(targets) == 0:
                    # ``entities_at`` filters out hidden / non-targetable
                    # tokens; fall back to the raw token at that square so
                    # entity-required actions (spell attacks, attacks) can
                    # still resolve when the caster legitimately can see
                    # them. If still nothing, surface as a coordinate
                    # target for AoE actions (cone/cube/grease/etc.).
                    fallback = battle_map.entity_at(tx, ty)
                    target = fallback if fallback is not None else [tx, ty]
                else:
                    target_list = [[target.label(), target.entity_uid] for target in targets]
                    return jsonify(status='multiple_targets', message=f"Multiple entities at {target_coords['x']}, {target_coords['y']}",
                                   entities=target_list)

    try:
        if action_type == 'MoveAction':
            path = action_request.get('path', None)
            manual_jump = action_request.get('manual_jump') or []
            action = MoveAction(get_game_session(), entity, 'move')
            if path:
                move_path = sorted([(int(index), [int(coord[0]), int(coord[1])]) for index, coord in enumerate(path)])
                move_path = [coords for _, coords in move_path]
                action.move_path = move_path
                # When this PC isn't a combatant in an active battle, treat
                # the move as exploration and allow paths longer than the
                # entity's standard speed so the user can traverse the map.
                if not battle or entity not in getattr(battle, 'entities', {}):
                    action.unlimited_movement = True
                # store jump indices for backend computation if provided.
                # The web UI sends [takeoff_index, landing_index] where
                # ``takeoff_index`` is the path index of the square the
                # entity launches FROM (the last walked square) and
                # ``landing_index`` is the square it lands ON. The squares
                # that are actually "in flight" — and therefore the ones
                # that need to be marked as jump squares so area triggers
                # treat them as flying — are ``takeoff_index + 1 ..
                # landing_index`` inclusive. Including the takeoff itself
                # would (a) burn a square of jump budget on the spot the
                # PC is standing on, and (b) prevent the long-jump
                # running-start budget from kicking in (because the
                # takeoff square is no longer counted as a "walk").
                try:
                    if isinstance(manual_jump, list) and len(manual_jump) == 2:
                        start_i, end_i = int(manual_jump[0]), int(manual_jump[1])
                        if 0 <= start_i <= end_i < len(move_path):
                            action.jump_index = list(range(start_i + 1, end_i + 1))
                    elif isinstance(manual_jump, list):
                        # already a list of in-flight indices
                        action.jump_index = [int(i) for i in manual_jump if 0 <= int(i) < len(move_path)]
                except Exception:
                    # ignore malformed manual_jump to remain backwards compatible
                    pass
                if battle:
                    result = get_current_game().commit_and_update(session['username'], action, pov_entities)
                    # Check area narrations after battle movement
                    area_narration = battle_map.check_area_narration(entity, move_path[-1])
                    if area_narration:
                        get_socketio().emit('message', {'type': 'narration', 'message': area_narration, 'map_name': battle_map.name})
                        narration_entry = area_narration.get('on_enter', {})
                        narration_text = narration_entry.get('text', '')
                        if narration_text:
                            get_output_logger().log(narration_text, visibility={'kind': 'entities', 'entity_uids': [entity.entity_uid]})
                        try:
                            _record_narration_for_pcs(area_narration, map_name=battle_map.name, target_uids=[entity.entity_uid])
                        except Exception:
                            pass
                    return jsonify(result)
                else:
                    last_coords = move_path[-1]
                    if battle_map.placeable(entity, last_coords[0], last_coords[1]):

                        get_current_game().commit_and_update(session['username'], action, pov_entities)
                        if battle:
                            # POV-aware logs are emitted via commit_and_update; avoid duplicate raw emission
                            logs = battle.get_animation_logs()
                            if logs:
                                get_socketio().emit('message', {'type': 'move', 'message': {
                                    'from': move_path[0], 'to': move_path[-1], 'animation_log': logs
                                }})
                            battle.clear_animation_logs()
                        else:
                            animation_log = []
                            animation_log.append((entity.entity_uid, move_path, None))
                            get_socketio().emit('message', {'type': 'move', 'message': {'from': move_path[0], 'to': move_path[-1], 'animation_log': animation_log}})
                        # Flush any deferred map switch now that the move
                        # animation event has been queued on the client. This
                        # ensures the entity finishes animating into the
                        # teleporter/stairs tile before the destination map
                        # is rendered.
                        try:
                            get_current_game().flush_pending_map_switch(session['username'])
                        except Exception:
                            pass
                        # Check area narrations after free movement
                        area_narration = battle_map.check_area_narration(entity, move_path[-1])
                        if area_narration:
                            get_socketio().emit('message', {'type': 'narration', 'message': area_narration, 'map_name': battle_map.name})
                            narration_entry = area_narration.get('on_enter', {})
                            narration_text = narration_entry.get('text', '')
                            if narration_text:
                                get_output_logger().log(narration_text, visibility={'kind': 'entities', 'entity_uids': [entity.entity_uid]})
                            try:
                                _record_narration_for_pcs(area_narration, map_name=battle_map.name, target_uids=[entity.entity_uid])
                            except Exception:
                                pass
                        get_current_game().loop_environment()
                        return jsonify({'status': 'ok'})
                    else:
                        return jsonify({'status': 'error', 'message': 'Entity not placeable at target location'})
            else:
                action_info['action'] = 'movement'
                action_info['type'] = 'select_path'
                build_map = action.build_map()
                action_info['param'] = build_map['param']
                return jsonify(action_info)
        elif action_type in ['LinkedAttackAction', 'AttackAction', 'TwoWeaponAttackAction', 'WildShapeAttackAction']:
            if action_type == 'WildShapeAttackAction':
                action = WildShapeAttackAction(get_game_session(), entity, 'attack')
            elif action_type == 'AttackAction':
                action = AttackAction(get_game_session(), entity, 'attack')
            else:
                action = TwoWeaponAttackAction(get_game_session(), entity, 'attack')
            action.using = opts.get('using')
            action.npc_action = opts.get('npc_action', None)
            action.thrown = opts.get('thrown', False)

            valid_targets = battle_map.valid_targets_for(entity, action, include_objects=True)
            valid_targets = { target.entity_uid: battle_map.entity_or_object_pos(target) for target in valid_targets}

            if action.npc_action:
                weapon_details = action.npc_action
            else:
                weapon_details = get_game_session().load_weapon(action.using)

            if target_coords:
                if isinstance(target_coords, str):
                    # Target is an entity UID
                    target = battle_map.entity_by_uid(target_coords)
                else:
                    # Target is coordinates
                    target = battle_map.entities_at(int(target_coords['x']), int(target_coords['y']))[0]

                if target and valid_targets.get(target.entity_uid):
                    action.target = target
                    return jsonify(get_current_game().commit_and_update(session['username'], action, pov_entities))
                else:
                    return jsonify(status='error', message=f"Invalid Target {target_coords}")
            else:
                action_info['action'] = 'attack'
                action_info['type'] = 'select_target'
                action_info['valid_targets'] = valid_targets
                action_info['total_targets'] = 1
                if action.thrown:
                    action_info['range'] = weapon_details.get('thrown', {}).get('range')
                    action_info['range_max'] = weapon_details.get('thrown', {}).get('range_max', weapon_details.get('thrown', {}).get('range'))
                else:
                    action_info['range'] = weapon_details['range']
                    action_info['range_max'] = weapon_details.get('range_max', weapon_details['range'])
                action_info['param'] = [
                    {
                        'type': 'select_target',
                        'num': 1,
                        'weapon': action.using,
                        'target_types': ['enemies'],
                    }
                    ]
        else:
            action_class = action_type_to_class(action_type)
            opts = action_request.get('opts', {})
            resolved_action_type = resolve_requested_action_type(
                entity,
                get_game_session(),
                battle,
                battle_map,
                action_class,
                opts.get('action_type'),
            )
            action = action_class(get_game_session(), entity, resolved_action_type)
            action = action.build_map()

            while not isinstance(action, Action):
                if len(action['param'])==1:
                    param_details = action['param'][0]
                    if param_details['type'] == 'select_spell':
                        if selected_spell:
                            action = action['next']((selected_spell, at_level))
                            continue
                        else:
                            action_info['action'] = action_type
                            action_info['type'] = 'select_spell'
                            action_info['param'] = action['param']
                            return jsonify(action_info)
                    elif param_details['type'] == 'select_choice':
                        if choice:
                            action = action['next'](choice)
                            continue
                        else:
                            action_info['action'] = action_type
                            action_info['type'] = 'select_choice'
                            action_info['param'] = action['param']
                            return jsonify(action_info)
                    elif param_details['type'] == 'select_empty_space':
                        if target:
                            action = action['next'](target)
                            continue
                        else:
                            action_info['action'] = action_type
                            action_info['type'] = 'select_empty_space'
                            action_info['param'] = action['param']
                            action_info['range'] = param_details.get('range', 5)
                            action_info['range_max'] = param_details.get('max_range', param_details.get('range', 5))
                            return jsonify(action_info)
                    elif param_details['type'] == 'select_cone':
                        if target:
                            action = action['next'](target)
                            continue
                        else:
                            action_info['action'] = action_type
                            action_info['type'] = 'select_cone'
                            action_info['param'] = action['param']
                            action_info['range'] = param_details.get('range', 5)
                            action_info['range_max'] = param_details.get('max_range', param_details.get('range', 5))
                            return jsonify(action_info)
                    elif param_details['type'] == 'select_cube':
                        if target:
                            action = action['next'](target)
                            continue
                        else:
                            action_info['action'] = action_type
                            action_info['type'] = 'select_cube'
                            action_info['param'] = action['param']
                            action_info['range'] = param_details.get('range', 5)
                            action_info['range_max'] = param_details.get('max_range', param_details.get('range', 5))
                            return jsonify(action_info)
                    elif param_details['type'] == 'select_radius':
                        if target:
                            action = action['next'](target)
                            continue
                        else:
                            action_info['action'] = action_type
                            action_info['type'] = 'select_radius'
                            action_info['param'] = action['param']
                            action_info['range'] = param_details.get('range', 60)
                            action_info['range_max'] = param_details.get('max_range', param_details.get('range', 60))
                            action_info['radius'] = param_details.get('radius', 20)
                            return jsonify(action_info)
                    elif param_details['type'] == 'select_square':
                        if target:
                            action = action['next'](target)
                            continue
                        else:
                            action_info['action'] = action_type
                            action_info['type'] = 'select_square'
                            action_info['param'] = action['param']
                            action_info['range'] = param_details.get('range', 60)
                            action_info['range_max'] = param_details.get('max_range', param_details.get('range', 60))
                            action_info['size'] = param_details.get('size', 10)
                            return jsonify(action_info)
                    elif param_details['type'] == 'select_line':
                        if target:
                            action = action['next'](target)
                            continue
                        else:
                            action_info['action'] = action_type
                            action_info['type'] = 'select_line'
                            action_info['param'] = action['param']
                            action_info['range'] = param_details.get('range', 30)
                            action_info['range_max'] = param_details.get('max_range', param_details.get('range', 30))
                            action_info['width'] = param_details.get('width', 5)
                            return jsonify(action_info)
                    elif param_details['type'] == 'select_emanation':
                        # Emanation centers on the caster — auto-resolve.
                        entity_x, entity_y = battle_map.entity_or_object_pos(entity)
                        action = action['next']([entity_x, entity_y])
                        continue
                    elif param_details['type'] == 'select_target':
                        targeting_spec = dict(param_details)
                        if targeting_spec.get('range') is None and targeting_spec.get('max_range') is None:
                            from natural20.weapons import resolve_targeting_range_ft
                            targeting_spec['range'] = resolve_targeting_range_ft(
                                get_game_session(), targeting_spec, default=5,
                            )
                        valid_targets = battle_map.valid_targets_for(entity, targeting_spec)
                        valid_targets = {target.entity_uid: battle_map.entity_or_object_pos(target) for target in valid_targets}
                        if target:
                            # ``select_target`` requires an actual Entity (or a
                            # list of entities for multi-target spells). If
                            # the client clicked an empty square the upstream
                            # resolver hands us a ``[x, y]`` coordinate pair,
                            # which would explode deep inside the spell when
                            # something like ``target.has_effect(...)`` is
                            # called. Reject those up front with a clear
                            # error so the UI can prompt the user again.
                            if not isinstance(target, Entity) and not (
                                isinstance(target, list)
                                and target
                                and all(isinstance(t, Entity) for t in target)
                            ):
                                return jsonify(
                                    status='error',
                                    error='No valid target at the selected square. Click on a creature.',
                                ), 400
                            action = action['next'](target)
                            continue
                        else:
                            action_info['action'] = action_type
                            action_info['type'] = 'select_target'
                            action_info['valid_targets'] = valid_targets
                            action_info['total_targets'] = param_details['num']
                            action_info['param'] = action['param']
                            action_info['range'] = param_details.get('range', 5)
                            action_info['range_max'] = param_details.get('max_range', param_details.get('range', 5))
                            if param_details.get('num', 1) > 1:
                                target_hints = [ t.entity_uid for t in acquire_targets(param_details, entity, battle, battle_map)]
                                action_info['target_hints'] = target_hints
                                action_info['unique_targets'] = param_details.get('unique_targets', False)
                            return jsonify(action_info)
                    elif param_details['type'] == 'select_item':
                        target_item = opts.get('name', None)
                        if target_item:
                            action = action['next'](target_item)
                            continue
                        else:
                            valid_items = entity.usable_items()
                            action_info['action'] = action_type
                            action_info['type'] = 'select_item'
                            action_info['valid_items'] = valid_items
                            action_info['param'] = action['param']
                            return jsonify(action_info)
                    elif param_details['type'] == 'select_object':
                        object_action_a = opts.get('object_action')
                        if isinstance(object_action_a, list):
                            object_action_a = object_action_a[0]

                        if entity.object() and 'dm' in user_role():
                            gm = DungeonMaster(get_game_session(), name='dm')
                            interact = InteractAction(get_game_session(), gm, 'interact')
                            interact.object_action = object_action_a
                            interact.target = entity
                            return jsonify(get_current_game().commit_and_update(session['username'], interact, pov_entities))
                        else:
                            interact = InteractAction(get_game_session(), entity, 'interact')
                            object =  battle_map.entity_by_uid(opts.get('target'))
                            interact.object_action =  object_action_a
                            interact.target = object
                            action = interact.build_custom_action(interact.object_action, object)
                            continue
                    elif param_details['type'] == 'select_items':
                        target_items = opts.get('items', [])
                        if target_items:
                            action = action['next'](target_items)
                            continue
                        else:
                            valid_items = entity.usable_items()
                            action_info['action'] = action_type
                            action_info['type'] = 'select_items'
                            action_info['mode'] = param_details.get('mode', 'transfer')
                            action_info['valid_items'] = param_details['items']
                            action_info['param'] = action['param']
                            return jsonify(action_info)
                    else:
                        raise ValueError(f"Unknown action type {action_type} {param_details['type']}")
                else:
                    raise ValueError(f"Invalid action map {action}")

            action.validate(battle_map, target=target)
           
            if len(action.errors) > 0:
                return jsonify(status='error', errors=action.errors)

            get_current_game().commit_and_update(session['username'], action, pov_entities)
            return jsonify(status='ok')
        return jsonify(action_info)
    except AsyncReactionHandler as e:
        get_logger().info(f"AsyncReactionHandler during action: {e}")
        for battle, entity, valid_actions in e.resolve():
            valid_actions_str = [[str(action.uid), str(action), action] for action in valid_actions]
            get_current_game().set_waiting_for_reaction_input([entity, e, e.resolve(), valid_actions_str])
        get_socketio().emit('message', {'type': 'reaction', 'message': {'id': entity.entity_uid, 'reaction': e.reaction_type}})
        return jsonify(status='ok')


@battle_bp.route('/ready_action', methods=['POST'])
def ready_action_endpoint():
    """Declare a 5e Ready (Hold) action.

    Body: ``{ id: <entity_uid>, description: "<player free text>" }``

    The webapp passes the description through the configured LLM (with a
    rule-based fallback) to produce a structured trigger + action_spec, and
    if approved commits a :class:`ReadyAction` for the entity.
    """
    from webapp.ready_action_handler import (
        parse_ready_action_request,
        make_llm_resolver,
    )

    payload = request.json or {}
    entity_id = payload.get('id')
    description = (payload.get('description') or '').strip()
    if not entity_id:
        return jsonify(status='error', message='Missing entity id'), 400

    entity = get_current_game().get_entity_by_uid(entity_id)
    if entity is None:
        return jsonify(status='error', message='Entity not found'), 404
    battle = get_current_game().get_current_battle()
    if battle is None:
        return jsonify(status='error', message='No active battle'), 400
    if not ReadyAction.can(entity, battle):
        return jsonify(status='error',
                       message='You cannot ready an action right now.'), 400

    parsed = parse_ready_action_request(entity, battle, description, get_llm_handler())
    if not parsed.get('approved'):
        return jsonify(status='rejected',
                       reason=parsed.get('reason'),
                       trigger=parsed.get('trigger'),
                       action_spec=parsed.get('action_spec')), 200

    # Make sure the engine knows how to resolve trigger time (idempotent).
    if getattr(battle, '_ready_action_resolver', None) is None:
        battle.set_ready_action_resolver(make_llm_resolver(get_llm_handler()))

    ready = ReadyAction(get_current_game().get_game_session(), entity, 'ready', opts={
        'description': description,
        'trigger': parsed['trigger'],
        'action_spec': parsed['action_spec'],
    })
    pov_entities = entities_controlled_by(session['username'])
    get_current_game().commit_and_update(session['username'], ready, pov_entities)
    return jsonify(status='ok',
                   reason=parsed.get('reason'),
                   trigger=parsed['trigger'],
                   action_spec=parsed['action_spec'])


@battle_bp.route('/items', methods=['GET'])
# GET /items?id=rumblebelly&action=InteractAction&opts[action_type]=interact&opts[object_action]=loot&opts[target]=3fb25042-df48-4003-8ddc-dd2b04d5fbeb HTTP/1.1
def get_items():
    battle_map = get_current_game().get_map_for_user(session['username'])
    entity_id = request.args.get('id')
    entity = battle_map.entity_by_uid(entity_id)
    if entity is None:
        return jsonify(error="Entity not found"), 404
    action_type = request.args.get('opts[object_action][]')
    target_object = battle_map.entity_by_uid(request.args.get("opts[target]"))
    if action_type == 'give':
        inventory = entity.inventory_items(get_game_session()) or []
        source_inventory = []
        return render_template('loot_items.html', entity=target_object, source_inventory=source_inventory, inventory=inventory, action_type=action_type, target_object=entity)
    else:
        inventory = target_object.inventory_items(get_game_session()) or []
        source_inventory = entity.inventory_items(get_game_session()) or []
    return render_template('loot_items.html', entity=entity, source_inventory=source_inventory, inventory=inventory, action_type=action_type, target_object=target_object)


@battle_bp.route('/info', methods=['GET'])
def get_info():
    battle_map = get_current_game().get_map_for_user(session['username'])
    battle = get_current_game().get_current_battle()
    info_id = request.args.get('id')
    if not info_id:
        return jsonify(error="Missing required id"), 400

    # Fetch the necessary information based on the info_id
    entity = battle_map.entity_by_uid(info_id)
    if entity is None:
        entity = battle_map.object_by_uid(info_id)
    if entity is None:
        return jsonify(error="Entity not found"), 404

    # Filter out None/empty usernames to avoid mixed-type sorting errors.
    configured_users = [
        login.get('name')
        for login in get_logins()
        if isinstance(login, dict) and isinstance(login.get('name'), str) and login.get('name').strip()
    ]
    connected_users = [
        username
        for username in (get_current_game().username_to_sid or {}).keys()
        if isinstance(username, str) and username.strip()
    ]
    all_users = sorted(set(configured_users + connected_users))
    return render_template('info.html.jinja', entity=entity, session=get_game_session(), battle=battle, restricted=False, role=user_role(), all_users=all_users)

@battle_bp.route('/entity_info', methods=['GET'])
def get_entity_info():
    """Get entity information for the JRPG dialog modal."""
    
    entity_id = request.args.get('entity_id')
    if not entity_id:
        return jsonify({'success': False, 'error': 'Entity ID is required'}), 400
    
    try:
        entity = get_current_game().get_entity_by_uid(entity_id)
        if not entity:
            return jsonify({'success': False, 'error': 'Entity not found'}), 404
        
        # Use EntityRAGHandler to get comprehensive entity context
        entity_info = get_entity_rag_handler().get_entity_context(entity)
        
        return jsonify({'success': True, 'entity': entity_info})
        
    except Exception as e:
        get_logger().error(f"Error getting entity info: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@battle_bp.route('/reset_narrations', methods=['POST'])
def reset_narrations():
    if not session.get('username'):
        return jsonify({'status': 'error', 'message': 'Not logged in'}), 401
    for m in get_current_game().maps.values():
        m._triggered_area_narrations.clear()
    return jsonify({'status': 'ok'})

@battle_bp.route('/turn')
def get_turn():
    battle = get_current_game().get_current_battle()
    if battle:
        print(f"current turn: {battle.current_turn().entity_uid} {session['username']}")
        if 'dm' in user_role() or controller_of(battle.current_turn().entity_uid, session['username']):
            return render_template('turn.jinja', battle=battle, game_session=get_current_game().game_session, username=session['username'])
        else:
            return render_template('turn.jinja', battle=battle, game_session=get_current_game().game_session, username=session['username'], readonly=True)
    else:
        # Exploration mode (no active battle): keep endpoint successful so
        # client refresh calls don't flood console with 400 errors.
        return "", 200

@battle_bp.route('/game_time')
def get_game_time():
    return jsonify({'game_time': get_current_game().game_session.game_time})


@battle_bp.route('/targets_at_position', methods=['GET'])
def get_targets_at_position():
    """Get all valid targets at a specific tile position for target selection modal."""
    
    try:
        entity_id = request.args.get('entity_id')
        x = int(request.args.get('x'))
        y = int(request.args.get('y'))
        action_info = request.args.get('action_info')
        opts = json.loads(request.args.get('opts', '{}'))
        
        if not entity_id or x is None or y is None or not action_info:
            return jsonify({'success': False, 'error': 'Missing required parameters'}), 400
        
        entity = get_current_game().get_entity_by_uid(entity_id)
        if not entity:
            return jsonify({'success': False, 'error': 'Entity not found'}), 404
        
        battle_map = get_current_game().get_map_for_entity(entity)
        battle = get_current_game().get_current_battle()
        
        # Get all things at the position
        things_at_position = battle_map.thing_at(x, y)
        
        # Filter to only valid targets based on the action
        valid_targets = []
        
        if action_info in ['AttackAction', 'LinkedAttackAction', 'WildShapeAttackAction']:
            if action_info == 'WildShapeAttackAction':
                action = WildShapeAttackAction(get_game_session(), entity, 'attack')
            else:
                action = AttackAction(get_game_session(), entity, 'attack')
            action.using = opts.get('using')
            action.npc_action = opts.get('npc_action', None)
            action.thrown = opts.get('thrown', False)
            
            # Check each thing at the position
            for thing in things_at_position:
                if thing and thing.allow_targeting():
                    action.target = thing
                    action.validate(battle_map, target=thing)
                    
                    if not action.errors:
                        if battle:
                            battle_valid_targets = battle.valid_targets_for(entity, action)
                            if thing in battle_valid_targets:
                                valid_targets.append({
                                    'id': thing.entity_uid,
                                    'name': thing.label() if hasattr(thing, 'label') else str(thing),
                                    'type': thing.__class__.__name__,
                                    'image': getattr(thing, 'profile_image', lambda: None)()
                                })
                        else:
                            map_valid_targets = battle_map.valid_targets_for(entity, action)
                            if thing in map_valid_targets:
                                valid_targets.append({
                                    'id': thing.entity_uid,
                                    'name': thing.label() if hasattr(thing, 'label') else str(thing),
                                    'type': thing.__class__.__name__,
                                    'image': getattr(thing, 'profile_image', lambda: None)()
                                })
        
        elif action_info == 'SpellAction':
            build_map = SpellAction.build(get_game_session(), entity)
            spell_choice = (opts['spell'], opts['at_level'])
            build_map = build_map['next'](spell_choice)
            
            # Check each thing at the position
            for thing in things_at_position:
                if thing and thing.allow_targeting():
                    try:
                        # Try to build the action with this target
                        test_build = build_map
                        while not isinstance(test_build, Action):
                            if test_build['param'][0]['type'] == 'select_target':
                                test_build = test_build['next'](thing)
                            elif test_build['param'][0]['type'] == 'select_empty_space':
                                test_build = test_build['next']([x, y])
                            else:
                                break
                        
                        if isinstance(test_build, Action):
                            test_build.validate(battle_map, target=thing)
                            if not test_build.errors:
                                valid_targets.append({
                                    'id': thing.entity_uid,
                                    'name': thing.label() if hasattr(thing, 'label') else str(thing),
                                    'type': thing.__class__.__name__,
                                    'image': getattr(thing, 'profile_image', lambda: None)()
                                })
                    except:
                        # If validation fails, skip this target
                        continue
        
        # Also check if the position itself is a valid target (for area spells)
        try:
            if action_info == 'SpellAction':
                build_map = SpellAction.build(get_game_session(), entity)
                spell_choice = (opts['spell'], opts['at_level'])
                build_map = build_map['next'](spell_choice)
                
                test_build = build_map
                while not isinstance(test_build, Action):
                    if test_build['param'][0]['type'] == 'select_empty_space':
                        test_build = test_build['next']([x, y])
                    else:
                        break
                
                if isinstance(test_build, Action):
                    test_build.validate(battle_map, target=[x, y])
                    if not test_build.errors:
                        valid_targets.append({
                            'id': f'position_{x}_{y}',
                            'name': f'Position ({x}, {y})',
                            'type': 'position',
                            'image': None
                        })
        except:
            # If position validation fails, skip
            pass
        
        return jsonify({
            'success': True,
            'targets': valid_targets,
            'position': {'x': x, 'y': y}
        })
        
    except Exception as e:
        get_logger().error(f"Error getting targets at position: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
