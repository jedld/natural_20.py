"""Stack-aware movement: edge descent, shaft falls, window exits, flying ascent."""

from __future__ import annotations

from typing import Any, Optional

from natural20.die_roll import DieRoll
from natural20.map_stack import MapStack
from natural20.map_stack_descent import preview_fall_damage


def _apply_fall_damage(entity, damage_die: str, battle, session, source=None):
    if not damage_die:
        return None
    roll = DieRoll.roll(damage_die)
    damage = int(roll.result()) if hasattr(roll, 'result') else int(roll)
    if session and getattr(session, 'event_manager', None):
        session.event_manager.received_event({
            'event': 'console',
            'source': source or entity,
            'target': entity,
            'message': f"{entity.name} falls and takes {damage} bludgeoning damage ({damage_die}).",
        })
    entity.take_damage(damage, battle=battle, damage_type='bludgeoning', session=session)
    return damage


_entity_relocation_hooks: list = []


def on_entity_relocation(hook) -> None:
    """Register a callback invoked after transfer_entity_to_map relocates an entity."""
    if hook not in _entity_relocation_hooks:
        _entity_relocation_hooks.append(hook)


def _notify_entity_relocation(entity) -> None:
    for hook in _entity_relocation_hooks:
        try:
            hook(entity)
        except Exception:
            pass


def transfer_entity_to_map(entity, from_map, to_map, lx: int, ly: int, battle=None):
    """Remove entity from from_map and place on to_map at local coords."""
    from_map.remove(entity, battle=battle)
    to_map.add(entity, lx, ly, group=getattr(entity, 'group', 'b'))
    _notify_entity_relocation(entity)


def resolve_stack_move_after_step(
    entity,
    battle_map,
    lx: int,
    ly: int,
    *,
    battle=None,
    session=None,
    is_flying_or_jumping: bool = False,
) -> Optional[dict[str, Any]]:
    """After a move step, apply stack transitions. Returns effect dict if map changed."""
    stack: Optional[MapStack] = getattr(battle_map, 'map_stack', None)
    if stack is None or session is None:
        return None

    floor = stack.floor_for_map(battle_map.name)
    if floor is None:
        return None

    wx, wy, elev = stack.local_to_world(battle_map.name, lx, ly)

    # Ascend from base floor through a shared stack opening (stairs / shaft).
    if floor.is_base and stack.is_stack_opening(wx, wy) and not is_flying_or_jumping:
        upper = stack.upper_floor_at(wx, wy, elev)
        if upper and upper.map_name != battle_map.name:
            local = stack.world_to_local(wx, wy, upper.map_name)
            if local and upper.map.placeable(entity, local[0], local[1], battle):
                transfer_entity_to_map(entity, battle_map, upper.map, local[0], local[1], battle)
                entity.altitude_ft = 0.0
                return {'type': 'stack_transition', 'map': upper.map, 'position': list(local)}

    # Window fall-through on overlay
    if stack.is_window_at(wx, wy, battle_map.name):
        obj = _window_object_at(battle_map, lx, ly)
        props = getattr(obj, 'properties', {}) if obj else {}
        if props.get('fall_through') and not is_flying_or_jumping:
            return _descend_to_lower_floor(entity, stack, battle_map, wx, wy, elev, battle, session, prone=True)

    # Stack opening shaft
    if stack.is_stack_opening(wx, wy) and not is_flying_or_jumping:
        return _descend_to_lower_floor(entity, stack, battle_map, wx, wy, elev, battle, session, prone=True)

    # Edge exit from overlay (out of bounds local)
    if not floor.is_base:
        local = stack.world_to_local(wx, wy, battle_map.name)
        if local is None:
            exit_target = stack.resolve_edge_exit(battle_map.name, lx, ly)
            if exit_target:
                base_name, blx, bly = exit_target
                base_map = session.maps[base_name]
                transfer_entity_to_map(entity, battle_map, base_map, blx, bly, battle)
                entity.altitude_ft = 0.0
                return {'type': 'stack_transition', 'map': base_map, 'position': [blx, bly]}

    # Flying ascent into upper floor at open column
    if is_flying_or_jumping and getattr(entity, 'can_fly', lambda: False)():
        upper = stack.upper_floor_at(wx, wy, elev)
        if upper and upper.map_name != battle_map.name:
            local = stack.world_to_local(wx, wy, upper.map_name)
            if local and upper.map.placeable(entity, local[0], local[1], battle):
                transfer_entity_to_map(entity, battle_map, upper.map, local[0], local[1], battle)
                entity.altitude_ft = 0.0
                return {'type': 'stack_transition', 'map': upper.map, 'position': list(local)}

    return None


def _window_object_at(battle_map, lx: int, ly: int):
    for obj, pos in battle_map.interactable_objects.items():
        if pos[0] == lx and pos[1] == ly:
            props = getattr(obj, 'properties', {}) or {}
            if props.get('type') == 'window' or props.get('fall_through'):
                return obj
    return None


def _descend_to_lower_floor(entity, stack, battle_map, wx, wy, elev, battle, session, prone=False):
    lower = stack.lower_floor_at(wx, wy, elev)
    if lower is None:
        base = next((f for f in stack.floors if f.is_base), None)
        if base is None:
            return None
        lower = base
    local = stack.world_to_local(wx, wy, lower.map_name)
    if local is None:
        return None
    delta = stack.elevation_delta_ft(elev, lower.elevation_ft)
    damage_die = stack.fall_damage_die(delta)
    fall_preview = preview_fall_damage(entity, damage_die)
    if fall_preview['die'] and session:
        _apply_fall_damage(entity, fall_preview['die'], battle, session)
    if hasattr(entity, 'dead') and entity.dead():
        return None
    transfer_entity_to_map(entity, battle_map, lower.map, local[0], local[1], battle)
    entity.altitude_ft = 0.0
    if prone and hasattr(entity, 'make_prone'):
        try:
            entity.make_prone()
        except Exception:
            pass
    return {'type': 'stack_fall', 'map': lower.map, 'position': list(local), 'fall_ft': delta}


def apply_voluntary_stack_descent(entity, battle_map, descent_info, *, battle=None, session=None):
    """Execute a planned voluntary stack descent after walking to the egress tile."""
    if not descent_info:
        return None
    stack: Optional[MapStack] = getattr(battle_map, 'map_stack', None)
    if stack is None or session is None:
        return None

    to_map_name = descent_info.get('to_map')
    to_map = session.maps.get(to_map_name)
    if to_map is None:
        return None

    land = descent_info.get('land_position') or descent_info.get('target_position')
    if not land or len(land) < 2:
        return None

    lx, ly = int(land[0]), int(land[1])
    floor = stack.floor_for_map(battle_map.name)
    if floor is None:
        return None
    wx, wy, elev = stack.local_to_world(battle_map.name, *battle_map.position_of(entity))
    lower = stack.lower_floor_at(wx, wy, elev)
    if lower is None:
        lower = stack.floor_for_map(to_map_name)
    delta = float(descent_info.get('fall_ft') or 0.0)
    if lower is not None and delta <= 0:
        delta = stack.elevation_delta_ft(elev, lower.elevation_ft)

    damage_die = stack.fall_damage_die(delta)
    fall_preview = preview_fall_damage(entity, damage_die)
    if fall_preview['die']:
        _apply_fall_damage(entity, fall_preview['die'], battle, session)
    if hasattr(entity, 'dead') and entity.dead():
        return None

    transfer_entity_to_map(entity, battle_map, to_map, lx, ly, battle)
    entity.altitude_ft = 0.0
    if descent_info.get('prone_on_land') and hasattr(entity, 'make_prone'):
        try:
            entity.make_prone()
        except Exception:
            pass

    return {
        'type': 'stack_fall',
        'map': to_map,
        'position': [lx, ly],
        'fall_ft': delta,
        'voluntary': True,
        'descent_type': descent_info.get('descent_type'),
    }
