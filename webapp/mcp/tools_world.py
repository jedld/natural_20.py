"""Read-only MCP tools that let the DM-LLM inspect the running game."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .context import MCPContext
from .tool_registry import ToolRegistry, tool, tool_error


def _entity_summary(entity, ctx: MCPContext, include_position: bool = True) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        'entity_uid': getattr(entity, 'entity_uid', None),
        'name': getattr(entity, 'name', None),
        'label': entity.label() if hasattr(entity, 'label') else None,
        'kind': entity.__class__.__name__,
        'is_npc': bool(getattr(entity, 'is_npc', lambda: False)()),
        'hp': _safe(lambda: entity.hp()),
        'max_hp': _safe(lambda: entity.max_hp()),
        'ac': _safe(lambda: entity.armor_class()),
        'statuses': list(getattr(entity, 'statuses', []) or []),
        'dead': _safe(lambda: entity.dead()),
        'unconscious': _safe(lambda: getattr(entity, 'unconscious', lambda: False)()),
    }
    if include_position:
        battle_map = ctx.map_for_entity(entity)
        if battle_map is not None:
            out['map'] = getattr(battle_map, 'name', None)
            try:
                pos = battle_map.entity_or_object_pos(entity)
                out['position'] = list(pos) if pos else None
            except Exception:
                out['position'] = None
        else:
            out['map'] = None
            out['position'] = None
    return out


def _safe(fn):
    try:
        return fn()
    except Exception:
        return None


def register(registry: ToolRegistry) -> None:
    @tool(
        registry,
        name='world.list_maps',
        description='List all loaded maps with size and entity counts.',
        input_schema={'type': 'object', 'properties': {}},
        category='world',
    )
    def list_maps(context: MCPContext):
        cg = context.current_game
        maps = getattr(cg, 'maps', {}) or {}
        result = []
        for name, m in maps.items():
            result.append({
                'name': name,
                'size': list(getattr(m, 'size', []) or []),
                'feet_per_grid': getattr(m, 'feet_per_grid', None),
                'entity_count': len(getattr(m, 'entities', {}) or {}),
                'background_image': _safe(lambda mm=m: mm.background_image()),
            })
        return {'maps': result}

    @tool(
        registry,
        name='world.get_map',
        description='Return a per-map summary including entities, their positions, '
                    'statuses and HP. Supports filtering by entity kind (player/npc/any), '
                    'object kind, name substring, and position bounding box. '
                    'Use filters to efficiently query large maps - e.g., filter by kind="npc" '
                    'to see only enemies, or use bbox to focus on a specific area.',
        input_schema={
            'type': 'object',
            'properties': {
                'map_name': {'type': 'string',
                              'description': 'Map name (omit for the default index map)'},
                'entity_kind': {'type': 'string', 'enum': ['player', 'npc', 'any'],
                                'description': 'Filter entities by kind: "player" for player characters, '
                                               '"npc" for NPCs/enemies, "any" for all (default)'},
                'object_kind': {'type': 'string',
                                'description': 'Filter objects by class name substring (case-insensitive), '
                                               'e.g., "door" to find all door objects'},
                'name_contains': {'type': 'string',
                                  'description': 'Filter entities by name substring (case-insensitive)'},
                'bbox': {'type': 'object',
                         'description': 'Bounding box filter: only include entities/objects within this rectangular area. '
                                        'Format: {"x_min": int, "x_max": int, "y_min": int, "y_max": int}. '
                                        'Coordinates are inclusive.',
                         'properties': {
                             'x_min': {'type': 'integer'},
                             'x_max': {'type': 'integer'},
                             'y_min': {'type': 'integer'},
                             'y_max': {'type': 'integer'},
                         }},
            },
        },
        category='world',
    )
    def get_map(context: MCPContext,
                map_name: Optional[str] = None,
                entity_kind: str = 'any',
                object_kind: Optional[str] = None,
                name_contains: Optional[str] = None,
                bbox: Optional[Dict[str, int]] = None):
        battle_map = context.resolve_map(map_name)
        if battle_map is None:
            raise tool_error(f'Map not found: {map_name}')
        
        # Parse filters
        wanted_kind = (entity_kind or 'any').lower()
        name_needle = (name_contains or '').lower().strip()
        object_kind_needle = (object_kind or '').lower().strip()
        
        # Parse bounding box
        x_min, x_max, y_min, y_max = None, None, None, None
        if bbox:
            x_min = bbox.get('x_min')
            x_max = bbox.get('x_max')
            y_min = bbox.get('y_min')
            y_max = bbox.get('y_max')
        
        def _in_bbox(pos):
            """Check if position is within bounding box."""
            if pos is None:
                return False
            if x_min is not None and pos[0] < x_min:
                return False
            if x_max is not None and pos[0] > x_max:
                return False
            if y_min is not None and pos[1] < y_min:
                return False
            if y_max is not None and pos[1] > y_max:
                return False
            return True
        
        entities: List[Dict[str, Any]] = []
        for ent in (getattr(battle_map, 'entities', {}) or {}).keys():
            # Filter by kind
            is_npc = bool(getattr(ent, 'is_npc', lambda: False)())
            if wanted_kind == 'npc' and not is_npc:
                continue
            if wanted_kind == 'player' and is_npc:
                continue
            
            # Filter by name
            label = (ent.label() if hasattr(ent, 'label') else getattr(ent, 'name', '')) or ''
            if name_needle and name_needle not in label.lower():
                continue
            
            # Filter by position
            try:
                pos = battle_map.entity_or_object_pos(ent)
                if not _in_bbox(pos):
                    continue
            except Exception:
                if bbox is not None:
                    continue
            
            entities.append(_entity_summary(ent, context))
        
        objects: List[Dict[str, Any]] = []
        for obj in (getattr(battle_map, 'interactable_objects', {}) or {}).keys():
            # Filter by object kind
            obj_kind = obj.__class__.__name__.lower()
            if object_kind_needle and object_kind_needle not in obj_kind:
                continue
            
            try:
                pos = battle_map.entity_or_object_pos(obj)
            except Exception:
                pos = None
            
            # Filter by position
            if not _in_bbox(pos):
                continue
            
            objects.append({
                'entity_uid': getattr(obj, 'entity_uid', None),
                'name': getattr(obj, 'name', None),
                'kind': obj.__class__.__name__,
                'position': list(pos) if pos else None,
            })
        
        return {
            'name': getattr(battle_map, 'name', map_name),
            'size': list(getattr(battle_map, 'size', []) or []),
            'feet_per_grid': getattr(battle_map, 'feet_per_grid', None),
            'entities': entities,
            'objects': objects,
            'filters_applied': {
                'entity_kind': wanted_kind,
                'object_kind': object_kind,
                'name_contains': name_contains,
                'bbox': bbox,
            },
            'counts': {
                'entities': len(entities),
                'objects': len(objects),
            },
        }

    @tool(
        registry,
        name='world.list_entities',
        description='List all entities across all maps. Optional filter by kind '
                    '(player, npc), by case-insensitive name substring, '
                    'or by NPC archetype (npc_type) substring.',
        input_schema={
            'type': 'object',
            'properties': {
                'kind': {'type': 'string', 'enum': ['player', 'npc', 'any']},
                'name_contains': {'type': 'string'},
                'npc_type_contains': {
                    'type': 'string',
                    'description': 'Case-insensitive substring match against '
                                   'entity.npc_type (NPC archetype id), e.g. "goblin".',
                },
            },
        },
        category='world',
    )
    def list_entities(context: MCPContext, kind: str = 'any',
                      name_contains: Optional[str] = None,
                      npc_type_contains: Optional[str] = None):
        cg = context.current_game
        wanted = (kind or 'any').lower()
        needle = (name_contains or '').lower().strip()
        npc_needle = (npc_type_contains or '').lower().strip()
        rows = []
        for map_name, m in (getattr(cg, 'maps', {}) or {}).items():
            for ent in (getattr(m, 'entities', {}) or {}).keys():
                is_npc = bool(getattr(ent, 'is_npc', lambda: False)())
                if wanted == 'npc' and not is_npc:
                    continue
                if wanted == 'player' and is_npc:
                    continue
                label = (ent.label() if hasattr(ent, 'label') else getattr(ent, 'name', '')) or ''
                if needle and needle not in label.lower() and needle not in (
                        getattr(ent, 'name', '') or '').lower():
                    continue
                if npc_needle:
                    npc_type = str(getattr(ent, 'npc_type', '') or '').lower()
                    if npc_needle not in npc_type:
                        continue
                summary = _entity_summary(ent, context, include_position=False)
                summary['map'] = map_name
                try:
                    pos = m.entity_or_object_pos(ent)
                    summary['position'] = list(pos) if pos else None
                except Exception:
                    summary['position'] = None
                rows.append(summary)
        return {
            'entities': rows,
            'count': len(rows),
            'filters': {
                'kind': wanted,
                'name_contains': name_contains,
                'npc_type_contains': npc_type_contains,
            },
        }

    @tool(
        registry,
        name='world.get_entity',
        description='Detailed snapshot of a single entity (attributes, abilities, '
                    'inventory, equipped items, prepared spells, position).',
        input_schema={
            'type': 'object',
            'required': ['entity_uid'],
            'properties': {
                'entity_uid': {'type': 'string'},
            },
        },
        category='world',
    )
    def get_entity(context: MCPContext, entity_uid: str):
        ent = context.resolve_entity(entity_uid)
        if ent is None:
            raise tool_error(f'Entity not found: {entity_uid}')
        battle_map = context.map_for_entity(ent)
        result = _entity_summary(ent, context)
        result.update({
            'attributes': dict(getattr(ent, 'attributes', {}) or {}),
            'ability_scores': dict(getattr(ent, 'ability_scores', {}) or {}),
            'properties': _serialise_properties(getattr(ent, 'properties', {}) or {}),
            'inventory': {
                str(k): {'qty': int((v or {}).get('qty', 0))}
                for k, v in (getattr(ent, 'inventory', {}) or {}).items()
            },
            'equipped': list(_safe(lambda: ent.properties.get('equipped', [])) or []),
            'prepared_spells': list(_safe(lambda: ent.prepared_spells()) or []),
            'speed': _safe(lambda: ent.speed()),
            'languages': _safe(lambda: list(ent.languages())) or [],
            'map': getattr(battle_map, 'name', None) if battle_map else None,
        })
        return result

    @tool(
        registry,
        name='world.get_battle',
        description='Return the current battle state (initiative order, '
                    'current turn, round number) or null if no battle is active.',
        input_schema={'type': 'object', 'properties': {}},
        category='world',
    )
    def get_battle(context: MCPContext):
        battle = _safe(lambda: context.current_game.get_current_battle())
        if battle is None:
            return {'active': False}
        order = []
        try:
            for ent in battle.combat_order:
                order.append({
                    'entity_uid': getattr(ent, 'entity_uid', None),
                    'name': getattr(ent, 'name', None),
                    'label': ent.label() if hasattr(ent, 'label') else None,
                })
        except Exception:
            pass
        current = None
        try:
            ct = battle.current_turn()
            current = getattr(ct, 'entity_uid', None)
        except Exception:
            pass
        return {
            'active': True,
            'round': getattr(battle, 'round', None),
            'current_turn_uid': current,
            'order': order,
        }

    @tool(
        registry,
        name='world.list_npc_types',
        description='List all NPC archetypes available to the current campaign '
                    '(usable as the "npc_type" argument when spawning).',
        input_schema={'type': 'object', 'properties': {}},
        category='world',
    )
    def list_npc_types(context: MCPContext):
        sess = context.game_session
        path = getattr(sess, 'root_path', None)
        names: List[str] = []
        if path:
            import os
            npc_dir = os.path.join(path, 'npcs')
            if os.path.isdir(npc_dir):
                for fname in sorted(os.listdir(npc_dir)):
                    if fname.endswith('.yml'):
                        names.append(fname[:-4])
        return {'npc_types': names}

    @tool(
        registry,
        name='world.list_object_types',
        description='List all interactable object archetypes available to '
                    'the campaign (usable as the "object_type" argument when '
                    'calling dm.spawn_object).',
        input_schema={'type': 'object', 'properties': {}},
        category='world',
    )
    def list_object_types(context: MCPContext):
        sess = context.game_session
        try:
            objects = sess.load_yaml_file('items', 'objects') or {}
        except Exception:
            objects = {}
        names = sorted(str(k) for k in objects.keys())
        return {'object_types': names}


def _serialise_properties(props) -> Dict[str, Any]:
    """Best-effort conversion of an entity properties dict to JSON."""
    try:
        data = props.data if hasattr(props, 'data') else props
        out: Dict[str, Any] = {}
        for k, v in dict(data or {}).items():
            try:
                # Drop obviously non-serialisable keys.
                if isinstance(v, (str, int, float, bool, list, dict, type(None))):
                    out[str(k)] = v
            except Exception:
                continue
        return out
    except Exception:
        return {}
