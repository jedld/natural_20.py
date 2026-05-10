"""DM-only mutation tools: HP/status/property edits, spawning, teleport."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .context import MCPContext
from .tool_registry import ToolRegistry, tool, tool_error


def register(registry: ToolRegistry) -> None:
    @tool(
        registry,
        name='dm.set_hp',
        description="Set an entity's current HP to an absolute value. "
                    "Clamped to 0..max_hp. Use this when you need a precise value.",
        input_schema={
            'type': 'object',
            'required': ['entity_uid', 'hp'],
            'properties': {
                'entity_uid': {'type': 'string'},
                'hp': {'type': 'integer', 'minimum': 0},
            },
        },
        category='dm',
    )
    def set_hp(context: MCPContext, entity_uid: str, hp: int):
        ent = _resolve(context, entity_uid)
        max_hp = ent.max_hp() if hasattr(ent, 'max_hp') else None
        clamped = max(0, int(hp))
        if max_hp is not None:
            clamped = min(clamped, int(max_hp))
        try:
            ent.attributes['hp'] = clamped
        except Exception as exc:
            raise tool_error(f'Failed to set hp: {exc}')
        if clamped == 0 and 'unconscious' not in (ent.statuses or []):
            try:
                if hasattr(ent, 'make_unconscious'):
                    ent.make_unconscious()
            except Exception:
                pass
        context.log_dm(f"DM set {ent.label()} HP to {clamped}")
        context.emit_refresh()
        return {'entity_uid': entity_uid, 'hp': clamped, 'max_hp': max_hp}

    @tool(
        registry,
        name='dm.heal',
        description='Heal an entity for a given amount (uses the engine heal() flow).',
        input_schema={
            'type': 'object',
            'required': ['entity_uid', 'amount'],
            'properties': {
                'entity_uid': {'type': 'string'},
                'amount': {'type': 'integer', 'minimum': 1},
            },
        },
        category='dm',
    )
    def heal(context: MCPContext, entity_uid: str, amount: int):
        ent = _resolve(context, entity_uid)
        try:
            ent.heal(int(amount))
        except Exception as exc:
            raise tool_error(f'Failed to heal: {exc}')
        context.log_dm(f"DM healed {ent.label()} for {amount}")
        context.emit_refresh()
        return {'entity_uid': entity_uid, 'hp': ent.hp(), 'max_hp': ent.max_hp()}

    @tool(
        registry,
        name='dm.damage',
        description='Apply damage to an entity using the engine take_damage() flow.',
        input_schema={
            'type': 'object',
            'required': ['entity_uid', 'amount'],
            'properties': {
                'entity_uid': {'type': 'string'},
                'amount': {'type': 'integer', 'minimum': 1},
                'damage_type': {'type': 'string', 'default': 'piercing'},
            },
        },
        category='dm',
    )
    def damage(context: MCPContext, entity_uid: str, amount: int,
               damage_type: str = 'piercing'):
        ent = _resolve(context, entity_uid)
        battle = _safe_call(lambda: context.current_game.get_current_battle())
        try:
            ent.take_damage(int(amount), battle=battle,
                            damage_type=damage_type, session=context.game_session)
        except Exception as exc:
            raise tool_error(f'Failed to apply damage: {exc}')
        context.log_dm(f"DM dealt {amount} {damage_type} to {ent.label()}")
        context.emit_refresh()
        return {'entity_uid': entity_uid, 'hp': ent.hp(), 'max_hp': ent.max_hp()}

    @tool(
        registry,
        name='dm.add_status',
        description='Add a status condition (e.g. "prone", "poisoned", "invisible") to an entity.',
        input_schema={
            'type': 'object',
            'required': ['entity_uid', 'status'],
            'properties': {
                'entity_uid': {'type': 'string'},
                'status': {'type': 'string'},
            },
        },
        category='dm',
    )
    def add_status(context: MCPContext, entity_uid: str, status: str):
        ent = _resolve(context, entity_uid)
        st = str(status).strip().lower()
        try:
            statuses = ent.statuses
            if st not in statuses:
                statuses.append(st)
        except Exception as exc:
            raise tool_error(f'Failed to add status: {exc}')
        context.log_dm(f"DM added status '{st}' to {ent.label()}")
        context.emit_refresh()
        return {'entity_uid': entity_uid, 'statuses': list(ent.statuses)}

    @tool(
        registry,
        name='dm.remove_status',
        description='Remove a status condition from an entity.',
        input_schema={
            'type': 'object',
            'required': ['entity_uid', 'status'],
            'properties': {
                'entity_uid': {'type': 'string'},
                'status': {'type': 'string'},
            },
        },
        category='dm',
    )
    def remove_status(context: MCPContext, entity_uid: str, status: str):
        ent = _resolve(context, entity_uid)
        st = str(status).strip().lower()
        try:
            if st in ent.statuses:
                ent.statuses.remove(st)
        except Exception as exc:
            raise tool_error(f'Failed to remove status: {exc}')
        context.log_dm(f"DM removed status '{st}' from {ent.label()}")
        context.emit_refresh()
        return {'entity_uid': entity_uid, 'statuses': list(ent.statuses)}

    @tool(
        registry,
        name='dm.set_property',
        description="Set or update a key inside an entity's `properties` dict. "
                    "Use sparingly: only safe for primitive (str/int/float/bool/list/dict) values.",
        input_schema={
            'type': 'object',
            'required': ['entity_uid', 'key', 'value'],
            'properties': {
                'entity_uid': {'type': 'string'},
                'key': {'type': 'string'},
                'value': {},
            },
        },
        category='dm',
    )
    def set_property(context: MCPContext, entity_uid: str, key: str, value: Any):
        ent = _resolve(context, entity_uid)
        try:
            ent.properties[key] = value
        except Exception as exc:
            raise tool_error(f'Failed to set property: {exc}')
        context.log_dm(f"DM set {ent.label()}.properties[{key!r}]={value!r}")
        context.emit_refresh()
        return {'entity_uid': entity_uid, 'key': key, 'value': value}

    @tool(
        registry,
        name='dm.spawn_npc',
        description='Spawn an NPC of `npc_type` at (x, y) on the given map. Returns the new entity uid.',
        input_schema={
            'type': 'object',
            'required': ['npc_type', 'x', 'y'],
            'properties': {
                'npc_type': {'type': 'string'},
                'x': {'type': 'integer', 'minimum': 0},
                'y': {'type': 'integer', 'minimum': 0},
                'map_name': {'type': 'string'},
                'group': {'type': 'string', 'default': 'b'},
                'rand_life': {'type': 'boolean', 'default': True},
            },
        },
        category='dm',
    )
    def spawn_npc(context: MCPContext, npc_type: str, x: int, y: int,
                  map_name: Optional[str] = None, group: str = 'b',
                  rand_life: bool = True):
        battle_map = context.resolve_map(map_name)
        if battle_map is None:
            raise tool_error(f'Map not found: {map_name}')
        x, y = int(x), int(y)
        if x < 0 or y < 0 or x >= battle_map.size[0] or y >= battle_map.size[1]:
            raise tool_error('Position is outside map bounds')
        if battle_map.entity_at(x, y):
            raise tool_error('Position is occupied')
        try:
            npc = context.game_session.npc(npc_type, {'rand_life': bool(rand_life)})
        except FileNotFoundError:
            raise tool_error(f'NPC type "{npc_type}" not found')
        except Exception as exc:
            raise tool_error(f'Failed to create NPC: {exc}')
        battle_map.add(npc, x, y, group=group)
        context.log_dm(f"DM spawned {npc_type} at ({x},{y}) on {battle_map.name}")
        context.emit_refresh()
        return {
            'entity_uid': npc.entity_uid,
            'npc_type': npc_type,
            'map': battle_map.name,
            'position': [x, y],
        }

    @tool(
        registry,
        name='dm.spawn_npc_near',
        description='Spawn an NPC near a target entity (by uid or name). '
                    'Finds the first placeable nearby tile and returns the new entity uid.',
        input_schema={
            'type': 'object',
            'required': ['npc_type'],
            'oneOf': [
                {'required': ['target_entity_uid']},
                {'required': ['target_name']},
            ],
            'properties': {
                'npc_type': {'type': 'string'},
                'target_entity_uid': {'type': 'string'},
                'target_name': {'type': 'string'},
                'group': {'type': 'string', 'default': 'b'},
                'rand_life': {'type': 'boolean', 'default': True},
                'max_distance': {'type': 'integer', 'minimum': 1, 'maximum': 5, 'default': 1},
                'include_diagonals': {'type': 'boolean', 'default': True},
            },
        },
        category='dm',
    )
    def spawn_npc_near(context: MCPContext, npc_type: str,
                       target_entity_uid: Optional[str] = None,
                       target_name: Optional[str] = None,
                       group: str = 'b', rand_life: bool = True,
                       max_distance: int = 1,
                       include_diagonals: bool = True):
        target, battle_map, target_pos = _resolve_target_on_map(
            context, target_entity_uid=target_entity_uid, target_name=target_name
        )
        try:
            npc = context.game_session.npc(npc_type, {'rand_life': bool(rand_life)})
        except FileNotFoundError:
            raise tool_error(f'NPC type "{npc_type}" not found')
        except Exception as exc:
            raise tool_error(f'Failed to create NPC: {exc}')

        battle = _safe_call(lambda: context.current_game.get_current_battle())
        found = _find_nearby_placeable_position(
            battle_map,
            npc,
            int(target_pos[0]),
            int(target_pos[1]),
            max_distance=max(1, int(max_distance)),
            include_diagonals=bool(include_diagonals),
            battle=battle,
        )
        if found is None:
            raise tool_error('No free placeable tile found near target entity')

        x, y = found
        battle_map.add(npc, x, y, group=group)
        context.log_dm(
            f"DM spawned {npc_type} near {target.label()} at ({x},{y}) on {battle_map.name}"
        )
        context.emit_refresh()
        return {
            'entity_uid': npc.entity_uid,
            'npc_type': npc_type,
            'map': battle_map.name,
            'position': [x, y],
            'near': {'entity_uid': target.entity_uid, 'name': target.label()},
        }

    @tool(
        registry,
        name='dm.spawn_object',
        description='Spawn an interactable object (catalog name from items/objects.yml) at (x, y).',
        input_schema={
            'type': 'object',
            'required': ['object_type', 'x', 'y'],
            'properties': {
                'object_type': {'type': 'string'},
                'x': {'type': 'integer', 'minimum': 0},
                'y': {'type': 'integer', 'minimum': 0},
                'map_name': {'type': 'string'},
            },
        },
        category='dm',
    )
    def spawn_object(context: MCPContext, object_type: str, x: int, y: int,
                     map_name: Optional[str] = None):
        battle_map = context.resolve_map(map_name)
        if battle_map is None:
            raise tool_error(f'Map not found: {map_name}')
        x, y = int(x), int(y)
        if x < 0 or y < 0 or x >= battle_map.size[0] or y >= battle_map.size[1]:
            raise tool_error('Position is outside map bounds')
        try:
            object_info = context.game_session.load_object(object_type)
        except Exception as exc:
            raise tool_error(f'Unknown object: {object_type} ({exc})')
        try:
            battle_map.place_object(object_info, x, y, object_meta={'name': object_type})
        except Exception as exc:
            raise tool_error(f'Failed to place object: {exc}')
        context.log_dm(f"DM spawned object {object_type} at ({x},{y}) on {battle_map.name}")
        context.emit_refresh()
        return {'object_type': object_type, 'position': [x, y], 'map': battle_map.name}

    @tool(
        registry,
        name='dm.spawn_object_near',
        description='Spawn an interactable object near a target entity (by uid or name). '
                    'Finds the first nearby tile where placement succeeds.',
        input_schema={
            'type': 'object',
            'required': ['object_type'],
            'oneOf': [
                {'required': ['target_entity_uid']},
                {'required': ['target_name']},
            ],
            'properties': {
                'object_type': {'type': 'string'},
                'target_entity_uid': {'type': 'string'},
                'target_name': {'type': 'string'},
                'max_distance': {'type': 'integer', 'minimum': 1, 'maximum': 5, 'default': 1},
                'include_diagonals': {'type': 'boolean', 'default': True},
            },
        },
        category='dm',
    )
    def spawn_object_near(context: MCPContext, object_type: str,
                          target_entity_uid: Optional[str] = None,
                          target_name: Optional[str] = None,
                          max_distance: int = 1,
                          include_diagonals: bool = True):
        target, battle_map, target_pos = _resolve_target_on_map(
            context, target_entity_uid=target_entity_uid, target_name=target_name
        )
        try:
            object_info = context.game_session.load_object(object_type)
        except Exception as exc:
            raise tool_error(f'Unknown object: {object_type} ({exc})')

        candidates = _nearby_offsets(
            max_distance=max(1, int(max_distance)),
            include_diagonals=bool(include_diagonals),
        )
        tx, ty = int(target_pos[0]), int(target_pos[1])
        found = None
        for dx, dy in candidates:
            x, y = tx + dx, ty + dy
            if x < 0 or y < 0 or x >= battle_map.size[0] or y >= battle_map.size[1]:
                continue
            if battle_map.entity_at(x, y):
                continue
            try:
                battle_map.place_object(object_info, x, y, object_meta={'name': object_type})
                found = (x, y)
                break
            except Exception:
                continue

        if found is None:
            raise tool_error('No suitable tile found to place object near target entity')

        x, y = found
        context.log_dm(
            f"DM spawned object {object_type} near {target.label()} at ({x},{y}) on {battle_map.name}"
        )
        context.emit_refresh()
        return {
            'object_type': object_type,
            'map': battle_map.name,
            'position': [x, y],
            'near': {'entity_uid': target.entity_uid, 'name': target.label()},
        }

    @tool(
        registry,
        name='dm.remove_entity',
        description='Remove an entity from its current map (does not delete its registry record).',
        input_schema={
            'type': 'object',
            'required': ['entity_uid'],
            'properties': {'entity_uid': {'type': 'string'}},
        },
        category='dm',
    )
    def remove_entity(context: MCPContext, entity_uid: str):
        ent = _resolve(context, entity_uid)
        battle_map = context.map_for_entity(ent)
        if battle_map is None:
            raise tool_error('Entity is not currently on any map')
        try:
            battle_map.remove(ent)
        except Exception as exc:
            raise tool_error(f'Failed to remove entity: {exc}')
        context.log_dm(f"DM removed {ent.label()} from {battle_map.name}")
        context.emit_refresh()
        return {'entity_uid': entity_uid, 'map': battle_map.name}

    @tool(
        registry,
        name='dm.teleport',
        description='Teleport an entity to (x, y) on its current map (or `map_name` if given). '
                    'Bypasses pathing/initiative; use `actions.move` for in-battle movement.',
        input_schema={
            'type': 'object',
            'required': ['entity_uid', 'x', 'y'],
            'properties': {
                'entity_uid': {'type': 'string'},
                'x': {'type': 'integer', 'minimum': 0},
                'y': {'type': 'integer', 'minimum': 0},
                'map_name': {'type': 'string'},
            },
        },
        category='dm',
    )
    def teleport(context: MCPContext, entity_uid: str, x: int, y: int,
                 map_name: Optional[str] = None):
        ent = _resolve(context, entity_uid)
        battle_map = context.resolve_map(map_name) if map_name else context.map_for_entity(ent)
        if battle_map is None:
            raise tool_error('Map not found for entity')
        x, y = int(x), int(y)
        if x < 0 or y < 0 or x >= battle_map.size[0] or y >= battle_map.size[1]:
            raise tool_error('Coordinates out of bounds')
        battle = _safe_call(lambda: context.current_game.get_current_battle())
        if not battle_map.placeable(ent, x, y, battle):
            raise tool_error('Target position is not placeable for this entity')
        try:
            current_pos = battle_map.entity_or_object_pos(ent)
        except Exception:
            current_pos = None
        # If the entity isn't on this map yet (cross-map teleport), add it.
        if ent not in (battle_map.entities or {}):
            current_map = context.map_for_entity(ent)
            if current_map is not None and current_map is not battle_map:
                try:
                    current_map.remove(ent)
                except Exception:
                    pass
            battle_map.add(ent, x, y, group='b')
        else:
            battle_map.move_to(ent, x, y, battle)
        context.log_dm(
            f"DM teleported {ent.label()} from {list(current_pos) if current_pos else None}"
            f" to ({x},{y}) on {battle_map.name}"
        )
        context.emit_refresh()
        return {
            'entity_uid': entity_uid,
            'from': list(current_pos) if current_pos else None,
            'to': [x, y],
            'map': battle_map.name,
        }

    @tool(
        registry,
        name='dm.add_item',
        description='Add an item (weapon/equipment/object name) to an entity\'s inventory.',
        input_schema={
            'type': 'object',
            'required': ['entity_uid', 'item_name'],
            'properties': {
                'entity_uid': {'type': 'string'},
                'item_name': {'type': 'string'},
                'qty': {'type': 'integer', 'minimum': 1, 'default': 1},
            },
        },
        category='dm',
    )
    def add_item(context: MCPContext, entity_uid: str, item_name: str, qty: int = 1):
        ent = _resolve(context, entity_uid)
        try:
            source = context.game_session.load_thing(item_name)
        except Exception:
            source = None
        if source is None:
            raise tool_error(f'Unknown item: {item_name}')
        try:
            ent.add_item(item_name, amount=int(qty))
        except Exception as exc:
            raise tool_error(f'Failed to add item: {exc}')
        context.log_dm(f"DM gave {qty} x {item_name} to {ent.label()}")
        context.emit_refresh()
        return {
            'entity_uid': entity_uid,
            'item_name': item_name,
            'qty': int((ent.inventory.get(item_name) or {}).get('qty', 0)),
        }

    @tool(
        registry,
        name='dm.remove_item',
        description='Remove (or decrement) an item from an entity\'s inventory.',
        input_schema={
            'type': 'object',
            'required': ['entity_uid', 'item_name'],
            'properties': {
                'entity_uid': {'type': 'string'},
                'item_name': {'type': 'string'},
                'qty': {'type': 'integer', 'minimum': 1, 'default': 1},
                'all': {'type': 'boolean', 'default': False},
            },
        },
        category='dm',
    )
    def remove_item(context: MCPContext, entity_uid: str, item_name: str,
                    qty: int = 1, all: bool = False):  # noqa: A002 - matches public name
        ent = _resolve(context, entity_uid)
        inventory = getattr(ent, 'inventory', {}) or {}
        if item_name not in inventory:
            raise tool_error('Entity does not have that item')
        current_qty = int((inventory.get(item_name) or {}).get('qty', 0))
        drop = current_qty if all else max(1, int(qty))
        try:
            ent.remove_item(item_name, amount=drop)
        except Exception as exc:
            raise tool_error(f'Failed to remove item: {exc}')
        context.log_dm(f"DM removed {drop} x {item_name} from {ent.label()}")
        context.emit_refresh()
        return {
            'entity_uid': entity_uid,
            'item_name': item_name,
            'qty': int((ent.inventory.get(item_name) or {}).get('qty', 0)),
        }

    # ------------------------------------------------------------------
    # Consolidated DM tools (one tool per concept, op-discriminated)
    # ------------------------------------------------------------------

    @tool(
        registry,
        name='dm.equipment',
        description='Equip or unequip an item the entity already owns. '
                    '`op` must be "equip" or "unequip"; `item_id` is the inventory key.',
        input_schema={
            'type': 'object',
            'required': ['entity_uid', 'op', 'item_id'],
            'properties': {
                'entity_uid': {'type': 'string'},
                'op': {'type': 'string', 'enum': ['equip', 'unequip']},
                'item_id': {'type': 'string'},
            },
        },
        category='dm',
    )
    def equipment(context: MCPContext, entity_uid: str, op: str, item_id: str):
        ent = _resolve(context, entity_uid)
        op = (op or '').lower()
        if op not in ('equip', 'unequip'):
            raise tool_error("op must be 'equip' or 'unequip'")
        try:
            (ent.equip if op == 'equip' else ent.unequip)(item_id)
        except Exception as exc:
            raise tool_error(f'Failed to {op}: {exc}')
        context.log_dm(f"DM {op}ped {item_id} on {ent.label()}")
        context.emit_refresh()
        return {
            'entity_uid': entity_uid,
            'op': op,
            'item_id': item_id,
            'equipped': list(_safe_call(lambda: ent.properties.get('equipped', [])) or []),
        }

    @tool(
        registry,
        name='dm.set_resource',
        description='Mutate a numeric resource on an entity. '
                    'resource_type: action | bonus_action | reaction | spell_slot | temp_hp. '
                    'op: set | add | subtract. For spell_slot, `character_class` and `level` are required. '
                    'Battle-required for action/bonus_action/reaction.',
        input_schema={
            'type': 'object',
            'required': ['entity_uid', 'resource_type', 'value'],
            'properties': {
                'entity_uid': {'type': 'string'},
                'resource_type': {
                    'type': 'string',
                    'enum': ['action', 'bonus_action', 'reaction', 'spell_slot', 'temp_hp'],
                },
                'value': {'type': 'integer', 'minimum': 0},
                'op': {'type': 'string', 'enum': ['set', 'add', 'subtract'], 'default': 'set'},
                'character_class': {'type': 'string',
                                     'description': 'Required for spell_slot (e.g. "wizard").'},
                'level': {'type': 'integer', 'minimum': 1, 'maximum': 9,
                           'description': 'Required for spell_slot.'},
            },
        },
        category='dm',
    )
    def set_resource(context: MCPContext, entity_uid: str, resource_type: str,
                     value: int, op: str = 'set',
                     character_class: Optional[str] = None,
                     level: Optional[int] = None):
        ent = _resolve(context, entity_uid)
        op = (op or 'set').lower()
        if op not in ('set', 'add', 'subtract'):
            raise tool_error("op must be 'set', 'add' or 'subtract'")
        rt = (resource_type or '').lower()
        value = int(value)
        if value < 0:
            raise tool_error('value cannot be negative')

        def _apply(current: int, cap: Optional[int]) -> int:
            if op == 'set':
                nv = value
            elif op == 'add':
                nv = current + value
            else:
                nv = max(0, current - value)
            if cap is not None:
                nv = min(nv, cap)
            return nv

        if rt == 'temp_hp':
            current = int(getattr(ent, '_temp_hp', 0) or 0)
            new_value = _apply(current, None)
            ent._temp_hp = new_value
            result = {'entity_uid': entity_uid, 'resource_type': rt,
                      'old_value': current, 'new_value': new_value}
        elif rt == 'spell_slot':
            if not character_class or level is None:
                raise tool_error('character_class and level required for spell_slot')
            slots = getattr(ent, 'spell_slots', None) or {}
            if character_class not in slots:
                raise tool_error(f'Entity has no {character_class} slots')
            try:
                cap = int(ent.max_spell_slots(int(level), character_class))
            except Exception:
                cap = None
            current = int(slots[character_class].get(int(level), 0) or 0)
            new_value = _apply(current, cap)
            slots[character_class][int(level)] = new_value
            result = {'entity_uid': entity_uid, 'resource_type': rt,
                      'character_class': character_class, 'level': int(level),
                      'old_value': current, 'new_value': new_value, 'max_value': cap}
        else:
            # action / bonus_action / reaction
            battle = _safe_call(lambda: context.current_game.get_current_battle())
            if battle is None:
                raise tool_error('No active battle')
            state = battle.entity_state_for(ent)
            if not state:
                raise tool_error('Entity is not in the current battle')
            current = int(state.get(rt, 0) or 0)
            new_value = _apply(current, 10)
            state[rt] = new_value
            result = {'entity_uid': entity_uid, 'resource_type': rt,
                      'old_value': current, 'new_value': new_value}

        context.log_dm(f"DM {op} {rt} on {ent.label()} -> {result['new_value']}")
        context.emit_refresh()
        return result

    @tool(
        registry,
        name='dm.battle_admin',
        description='Mid-battle initiative/group management. '
                    'op: add_combatant | remove_combatant | reorder | set_group | next_turn. '
                    '- add_combatant: adds entity to active battle, rolls initiative, slots in next.\n'
                    '- remove_combatant: drops entity from initiative without removing from map.\n'
                    '- reorder: takes `order` array of entity_uids.\n'
                    '- set_group: requires `group` (e.g. "a"/"b").\n'
                    '- next_turn: advances initiative; no entity_uid needed.',
        input_schema={
            'type': 'object',
            'required': ['op'],
            'properties': {
                'op': {'type': 'string',
                        'enum': ['add_combatant', 'remove_combatant', 'reorder',
                                 'set_group', 'next_turn']},
                'entity_uid': {'type': 'string'},
                'group': {'type': 'string'},
                'order': {'type': 'array', 'items': {'type': 'string'}},
            },
        },
        category='dm',
    )
    def battle_admin(context: MCPContext, op: str,
                     entity_uid: Optional[str] = None,
                     group: Optional[str] = None,
                     order: Optional[List[str]] = None):
        op = (op or '').lower()
        cg = context.current_game
        battle = _safe_call(lambda: cg.get_current_battle())
        if battle is None:
            raise tool_error('No active battle')

        if op == 'next_turn':
            before = _safe_call(lambda: battle.current_turn().entity_uid)
            try:
                battle.next_turn()
            except Exception as exc:
                raise tool_error(f'next_turn failed: {exc}')
            after = _safe_call(lambda: battle.current_turn().entity_uid)
            context.emit_refresh()
            return {'op': op, 'previous_uid': before, 'current_uid': after,
                    'round': getattr(battle, 'round', None)}

        if op == 'reorder':
            if not order or not isinstance(order, list):
                raise tool_error('order (list of entity_uids) is required')
            try:
                battle.reorder_initiative(list(order))
            except ValueError as exc:
                raise tool_error(str(exc))
            context.emit_refresh()
            return {'op': op, 'order': list(order),
                    'current_index': getattr(battle, 'current_turn_index', 0)}

        if not entity_uid:
            raise tool_error('entity_uid required for this op')
        ent = _resolve(context, entity_uid)

        if op == 'add_combatant':
            if ent in battle.entities:
                return {'op': op, 'entity_uid': entity_uid, 'added': False,
                        'reason': 'already in battle'}
            controller = None
            try:
                controller = cg.build_combat_controller_for_entity(ent)
            except Exception:
                controller = None
            if controller is None:
                from natural20.generic_controller import GenericController
                controller = GenericController(context.game_session)
            try:
                controller.register_handlers_on(ent)
            except Exception:
                pass
            from natural20.player_character import PlayerCharacter
            default_group = group or ('a' if isinstance(ent, PlayerCharacter) else 'b')
            battle.add(ent, default_group, controller=controller)
            state = battle.entities.get(ent)
            if state is not None:
                try:
                    state['initiative'] = ent.initiative(battle)
                except Exception:
                    state['initiative'] = 0
                if ent not in battle.combat_order:
                    insert_at = (battle.current_turn_index + 1) if battle.combat_order else 0
                    battle.combat_order.insert(insert_at, ent)
            context.log_dm(f"DM added {ent.label()} to battle (group {default_group})")
            context.emit_refresh()
            return {'op': op, 'entity_uid': entity_uid, 'added': True,
                    'group': default_group}

        if op == 'remove_combatant':
            if ent not in battle.entities and ent not in battle.combat_order:
                return {'op': op, 'entity_uid': entity_uid, 'removed': False}
            try:
                battle.remove(ent, from_map=False)
            except Exception as exc:
                raise tool_error(f'remove failed: {exc}')
            try:
                if battle.battle_ends():
                    cg.end_current_battle()
            except Exception:
                pass
            context.log_dm(f"DM removed {ent.label()} from battle")
            context.emit_refresh()
            return {'op': op, 'entity_uid': entity_uid, 'removed': True}

        if op == 'set_group':
            if not group:
                raise tool_error('group is required')
            if ent not in battle.entities:
                raise tool_error('Entity is not in the current battle')
            old = battle.entities[ent].get('group')
            battle.entities[ent]['group'] = group
            try:
                if old in battle.groups:
                    battle.groups[old].discard(ent)
                battle.groups.setdefault(group, set()).add(ent)
            except Exception:
                pass
            context.log_dm(f"DM moved {ent.label()} from group {old} to {group}")
            context.emit_refresh()
            return {'op': op, 'entity_uid': entity_uid, 'group': group, 'previous': old}

        raise tool_error(f'Unknown op: {op}')

    @tool(
        registry,
        name='dm.set_controller',
        description='Set the engine-side controller for an entity. '
                    'kind: manual (DM web controller) | ai (heuristic) | llm (LlmMcpController).',
        input_schema={
            'type': 'object',
            'required': ['entity_uid', 'kind'],
            'properties': {
                'entity_uid': {'type': 'string'},
                'kind': {'type': 'string', 'enum': ['manual', 'ai', 'llm']},
            },
        },
        category='dm',
    )
    def set_controller(context: MCPContext, entity_uid: str, kind: str):
        ent = _resolve(context, entity_uid)
        cg = context.current_game
        battle = _safe_call(lambda: cg.get_current_battle())
        kind = (kind or '').lower()
        try:
            if kind == 'manual':
                from natural20.web.web_controller import WebController  # type: ignore
                ctrl = WebController(context.game_session, None)
                ctrl.add_user('dm')
                if hasattr(cg, 'web_controllers'):
                    cg.web_controllers[ent] = ctrl
            elif kind == 'ai':
                from natural20.generic_controller import GenericController
                ctrl = GenericController(context.game_session)
            elif kind == 'llm':
                from natural20.llm_controller import LlmMcpController
                ctrl = LlmMcpController(context.game_session)
            else:
                raise tool_error("kind must be 'manual', 'ai' or 'llm'")
        except tool_error.__class__:
            raise
        except Exception as exc:
            raise tool_error(f'Failed to build controller: {exc}')
        try:
            ctrl.register_handlers_on(ent)
        except Exception:
            pass
        if battle is not None:
            try:
                battle.set_controller_for(ent, ctrl)
            except Exception as exc:
                raise tool_error(f'Failed to bind controller: {exc}')
        context.log_dm(f"DM set controller for {ent.label()} -> {kind}")
        return {'entity_uid': entity_uid, 'kind': kind}

    @tool(
        registry,
        name='dm.rest',
        description='Run a short or long rest for an entity. '
                    'Optional `force=true` to override combat restrictions (DM-only). '
                    'arcane_picks (wizard) and hit_die_picks (short rest) are spent in order.',
        input_schema={
            'type': 'object',
            'required': ['entity_uid', 'type'],
            'properties': {
                'entity_uid': {'type': 'string'},
                'type': {'type': 'string', 'enum': ['short', 'long']},
                'force': {'type': 'boolean', 'default': False},
                'arcane_picks': {'type': 'array', 'items': {'type': 'integer'}},
                'hit_die_picks': {'type': 'array', 'items': {'type': 'integer'}},
            },
        },
        category='dm',
    )
    def rest(context: MCPContext, entity_uid: str, type: str,  # noqa: A002
             force: bool = False,
             arcane_picks: Optional[List[int]] = None,
             hit_die_picks: Optional[List[int]] = None):
        ent = _resolve(context, entity_uid)
        rest_type = (type or 'short').lower()
        if rest_type not in ('short', 'long'):
            raise tool_error("type must be 'short' or 'long'")
        cg = context.current_game
        battle = _safe_call(lambda: cg.get_current_battle())
        battle_map = context.map_for_entity(ent)

        # Inline pick controller, mirrors webapp _WebRestController.
        class _Picks:
            def __init__(self, ap, hp):
                self._ap = list(ap or [])
                self._hp = list(hp or [])
                self.consumed_picks = []
                self.consumed_hit_die = []

            def arcane_recovery_ui(self, _entity, available_levels):
                while self._ap:
                    lv = self._ap.pop(0)
                    if lv in available_levels:
                        self.consumed_picks.append(lv)
                        return lv
                return None

            def prompt_hit_die_roll(self, _entity, available_die_types):
                while self._hp:
                    dt = self._hp.pop(0)
                    if dt in available_die_types:
                        self.consumed_hit_die.append(dt)
                        return dt
                return 'skip'

        picks = _Picks(arcane_picks, hit_die_picks)
        restore = None
        if battle is not None:
            original = battle.controller_for

            def _proxy(target, _orig=original, _ent=ent, _p=picks):
                return _p if target is _ent else _orig(target)

            battle.controller_for = _proxy
            restore = lambda: setattr(battle, 'controller_for', original)  # noqa: E731

        try:
            if rest_type == 'short':
                ent.short_rest(battle, force=bool(force),
                                prompt=bool(hit_die_picks),
                                battle_map=battle_map)
            else:
                ent.long_rest(battle=battle, battle_map=battle_map,
                               force=bool(force), require_rations=True)
        except ValueError as exc:
            raise tool_error(str(exc))
        except Exception as exc:
            raise tool_error(f'Rest failed: {exc}')
        finally:
            if restore is not None:
                try:
                    restore()
                except Exception:
                    pass

        context.log_dm(f"DM ran {rest_type} rest for {ent.label()} (force={force})")
        context.emit_refresh()
        return {
            'entity_uid': entity_uid,
            'type': rest_type,
            'forced': bool(force),
            'hp': _safe_call(lambda: ent.hp()),
            'max_hp': _safe_call(lambda: ent.max_hp()),
            'arcane_picks_consumed': picks.consumed_picks,
            'hit_die_consumed': picks.consumed_hit_die,
        }

    @tool(
        registry,
        name='dm.save_load',
        description='Save/load/list campaign save files. '
                    'op: save (optional `name`) | load (optional `filename` or `index`) | list.',
        input_schema={
            'type': 'object',
            'required': ['op'],
            'properties': {
                'op': {'type': 'string', 'enum': ['save', 'load', 'list']},
                'name': {'type': 'string'},
                'filename': {'type': 'string'},
                'index': {'type': 'integer'},
            },
        },
        category='dm',
    )
    def save_load(context: MCPContext, op: str,
                  name: Optional[str] = None,
                  filename: Optional[str] = None,
                  index: Optional[int] = None):
        cg = context.current_game
        op = (op or '').lower()
        if op == 'save':
            try:
                cg.save_game_async(name=name)
            except Exception as exc:
                raise tool_error(f'save failed: {exc}')
            context.log_dm(f"DM queued save {name or '(auto)'}")
            return {'op': op, 'queued': True, 'name': name}
        if op == 'list':
            try:
                saves = cg.list_saves() if hasattr(cg, 'list_saves') else []
            except Exception as exc:
                raise tool_error(f'list failed: {exc}')
            return {'op': op, 'saves': list(saves or [])}
        if op == 'load':
            try:
                if filename:
                    cg.load_save(filename=filename)
                elif index is not None:
                    cg.load_save(index=int(index))
                else:
                    cg.load_save()
            except Exception as exc:
                raise tool_error(f'load failed: {exc}')
            try:
                cg.set_current_battle_map(cg.get_current_battle_map())
            except Exception:
                pass
            try:
                cg.refresh_client_map()
            except Exception:
                pass
            context.emit_refresh()
            context.log_dm(f"DM loaded save filename={filename} index={index}")
            return {'op': op, 'loaded': True, 'filename': filename, 'index': index}
        raise tool_error(f'Unknown op: {op}')

    @tool(
        registry,
        name='dm.sound',
        description='Soundtrack control. op: list | play (track_id) | volume (0-100) | seek (seconds).',
        input_schema={
            'type': 'object',
            'required': ['op'],
            'properties': {
                'op': {'type': 'string', 'enum': ['list', 'play', 'volume', 'seek']},
                'track_id': {'type': 'string'},
                'volume': {'type': 'integer', 'minimum': 0, 'maximum': 100},
                'time': {'type': 'integer', 'minimum': 0},
            },
        },
        category='dm',
    )
    def sound(context: MCPContext, op: str,
              track_id: Optional[str] = None,
              volume: Optional[int] = None,
              time: Optional[int] = None):  # noqa: A002
        cg = context.current_game
        op = (op or '').lower()
        if op == 'list':
            try:
                from webapp.app import SOUNDTRACKS  # lazy import to avoid cycle
            except Exception:
                SOUNDTRACKS = []
            current = getattr(cg, 'current_soundtrack', None)
            return {
                'op': op,
                'tracks': [{'id': t.get('name'), 'name': t.get('name'),
                              'file': t.get('file')} for t in SOUNDTRACKS],
                'current': current.get('name') if current else None,
            }
        if op == 'play':
            if not track_id:
                raise tool_error('track_id required')
            cg.play_soundtrack(track_id)
            context.log_dm(f"DM played soundtrack {track_id}")
            return {'op': op, 'track_id': track_id}
        if op == 'volume':
            if volume is None:
                raise tool_error('volume required')
            cg.set_volume(int(volume))
            return {'op': op, 'volume': int(volume)}
        if op == 'seek':
            if time is None:
                raise tool_error('time required')
            cg.seek_soundtrack(int(time))
            return {'op': op, 'time': int(time)}
        raise tool_error(f'Unknown op: {op}')

    @tool(
        registry,
        name='dm.effect',
        description='Broadcast a visual effect overlay (fog/rain/snow/custom). '
                    'action: start | stop | update. '
                    'scope: global (default) or map (optional `map_name`).',
        input_schema={
            'type': 'object',
            'required': ['effect', 'action'],
            'properties': {
                'effect': {'type': 'string',
                            'description': 'fog | rain | snow | map_default | <custom>'},
                'action': {'type': 'string', 'enum': ['start', 'stop', 'update']},
                'config': {'type': 'object'},
                'scope': {'type': 'string', 'enum': ['global', 'map'], 'default': 'global'},
                'map_name': {'type': 'string'},
            },
        },
        category='dm',
    )
    def effect(context: MCPContext, effect: str, action: str,
               config: Optional[Dict[str, Any]] = None,
               scope: str = 'global',
               map_name: Optional[str] = None):
        socketio = context.socketio
        if socketio is None:
            raise tool_error('socketio not available')
        cfg = dict(config or {})
        payload = {'effect': effect, 'action': action, 'config': cfg}
        try:
            socketio.emit('effect:set', payload)
        except Exception as exc:
            raise tool_error(f'emit failed: {exc}')
        # Persist into the webapp's effect-state caches if importable.
        try:
            from webapp.app import (active_effects, active_effects_map,
                                    LEVEL)  # lazy
            game_key = (getattr(context.game_session, 'root_path', None)
                        or LEVEL)
            if (scope or 'global').lower() == 'map':
                target_map = map_name
                if not target_map:
                    bm = context.resolve_map(None)
                    target_map = getattr(bm, 'name', None)
                bucket = active_effects_map.setdefault(game_key, {}).setdefault(target_map, {})
                if action == 'stop':
                    bucket.pop(effect, None)
                else:
                    bucket[effect] = {'effect': effect, 'action': 'start', 'config': cfg}
            else:
                if action == 'stop':
                    active_effects.get(game_key, {}).pop(effect, None)
                else:
                    active_effects.setdefault(game_key, {})[effect] = {
                        'effect': effect, 'action': 'start', 'config': cfg,
                    }
        except Exception:
            pass
        context.log_dm(f"DM effect {effect}/{action} scope={scope}")
        return {'effect': effect, 'action': action, 'scope': scope,
                'map_name': map_name, 'config': cfg}

    @tool(
        registry,
        name='dm.advance_time',
        description='Advance (or set) the in-game clock by `seconds`. '
                    'Use op="set" to assign an absolute value, "add" to advance.',
        input_schema={
            'type': 'object',
            'required': ['seconds'],
            'properties': {
                'seconds': {'type': 'integer'},
                'op': {'type': 'string', 'enum': ['set', 'add'], 'default': 'add'},
            },
        },
        category='dm',
    )
    def advance_time(context: MCPContext, seconds: int, op: str = 'add'):
        sess = context.game_session
        op = (op or 'add').lower()
        if op == 'set':
            try:
                sess.game_time = int(seconds)
            except Exception as exc:
                raise tool_error(f'failed to set time: {exc}')
        elif op == 'add':
            try:
                sess.increment_game_time(int(seconds))
            except Exception as exc:
                raise tool_error(f'failed to advance time: {exc}')
        else:
            raise tool_error("op must be 'set' or 'add'")
        try:
            context.socketio and context.socketio.emit(
                'message', {'type': 'turn',
                             'message': {'game_time': sess.game_time}})
        except Exception:
            pass
        return {'op': op, 'seconds': int(seconds), 'game_time': sess.game_time}


def _resolve(context: MCPContext, entity_uid: str):
    ent = context.resolve_entity(entity_uid)
    if ent is None:
        raise tool_error(f'Entity not found: {entity_uid}')
    return ent


def _resolve_target_on_map(context: MCPContext,
                           target_entity_uid: Optional[str] = None,
                           target_name: Optional[str] = None):
    if target_entity_uid:
        target = _resolve(context, target_entity_uid)
    elif target_name:
        target = _resolve_by_name(context, target_name)
    else:
        raise tool_error('Provide target_entity_uid or target_name')

    battle_map = context.map_for_entity(target)
    if battle_map is None:
        raise tool_error('Target entity is not currently on any map')
    pos = battle_map.entity_or_object_pos(target)
    if pos is None:
        raise tool_error('Target entity position is unknown on current map')
    return target, battle_map, pos


def _resolve_by_name(context: MCPContext, target_name: str):
    current_map = context.resolve_map(None)
    if current_map is None:
        raise tool_error('No active map available')

    query = str(target_name).strip().lower()
    if not query:
        raise tool_error('target_name cannot be empty')

    exact = []
    contains = []
    for ent in (current_map.entities or {}).keys():
        label = str(_safe_call(lambda: ent.label()) or '').strip()
        ent_name = str(getattr(ent, 'name', '') or '').strip()
        hay = [label.lower(), ent_name.lower()]
        if query in hay:
            exact.append(ent)
        elif any(query in part for part in hay if part):
            contains.append(ent)

    matches = exact if exact else contains
    if not matches:
        raise tool_error(f'No entity named "{target_name}" found on current map')
    if len(matches) > 1:
        names = ', '.join(str(_safe_call(lambda: e.label()) or e.entity_uid) for e in matches[:5])
        raise tool_error(f'Ambiguous target_name "{target_name}"; matches: {names}')
    return matches[0]


def _nearby_offsets(max_distance: int = 1, include_diagonals: bool = True):
    offsets = []
    max_distance = max(1, int(max_distance))
    for dist in range(1, max_distance + 1):
        if include_diagonals:
            for dy in range(-dist, dist + 1):
                for dx in range(-dist, dist + 1):
                    if dx == 0 and dy == 0:
                        continue
                    if max(abs(dx), abs(dy)) != dist:
                        continue
                    offsets.append((dx, dy))
        else:
            offsets.extend([(dist, 0), (0, dist), (-dist, 0), (0, -dist)])
    offsets.sort(key=lambda t: (abs(t[0]) + abs(t[1]), abs(t[1]), abs(t[0]), t[1], t[0]))
    return offsets


def _find_nearby_placeable_position(battle_map, entity, tx: int, ty: int,
                                    max_distance: int = 1,
                                    include_diagonals: bool = True,
                                    battle=None):
    for dx, dy in _nearby_offsets(max_distance=max_distance, include_diagonals=include_diagonals):
        x, y = tx + dx, ty + dy
        if x < 0 or y < 0 or x >= battle_map.size[0] or y >= battle_map.size[1]:
            continue
        if battle_map.placeable(entity, x, y, battle):
            return (x, y)
    return None


def _safe_call(fn):
    try:
        return fn()
    except Exception:
        return None
