"""Stack-aware targeting helpers for cross-floor combat."""

from __future__ import annotations

import math
from typing import Any, Optional

from natural20.map_stack import MapStack


def stack_world_distance_squares(
    stack: MapStack,
    map1,
    pos1: tuple[int, int],
    map2,
    pos2: tuple[int, int],
) -> float:
    """Horizontal grid distance between two tiles in shared world space."""
    w1 = stack.local_to_world(map1.name, pos1[0], pos1[1])
    w2 = stack.local_to_world(map2.name, pos2[0], pos2[1])
    dx = abs(w1[0] - w2[0])
    dy = abs(w1[1] - w2[1])
    return math.sqrt(dx * dx + dy * dy)


def stack_entity_distance_squares(stack: MapStack, entity1, map1, entity2, map2) -> float:
    """Minimum grid distance between two entities across stack floors."""
    pos1 = map1.entity_or_object_pos(entity1)
    pos2 = map2.entity_or_object_pos(entity2)
    if pos1 is None or pos2 is None:
        return math.inf

    best = math.inf
    for p1 in map1.entity_squares(entity1):
        for p2 in map2.entity_squares(entity2):
            dist = stack_world_distance_squares(stack, map1, tuple(p1), map2, tuple(p2))
            best = min(best, dist)
    return best


def stack_entity_distance_ft(stack: MapStack, entity1, map1, entity2, map2, *, feet_per_grid: int = 5) -> float:
    return stack_entity_distance_squares(stack, entity1, map1, entity2, map2) * feet_per_grid


def things_at_stack_position(stack: MapStack, x: int, y: int) -> list[tuple[Any, int, int, Any]]:
    """Return [(map, lx, ly, thing), ...] for a clicked tile across stack floors."""
    hits: list[tuple[Any, int, int, Any]] = []
    seen: set[str] = set()

    for floor in stack.floors:
        candidates: list[tuple[int, int]] = []
        if 0 <= x < floor.map.size[0] and 0 <= y < floor.map.size[1]:
            candidates.append((x, y))
        local = stack.world_to_local(x, y, floor.map_name)
        if local is not None and local not in candidates:
            candidates.append(local)
        for lx, ly in candidates:
            for thing in floor.map.thing_at(lx, ly):
                uid = str(getattr(thing, 'entity_uid', id(thing)))
                if uid in seen:
                    continue
                seen.add(uid)
                hits.append((floor.map, lx, ly, thing))
    return hits


def entity_at_stack_position(stack: Optional[MapStack], battle_map, x: int, y: int):
    """Resolve a creature at click coordinates, including other floors in the stack."""
    entity = battle_map.entity_at(x, y)
    if entity is not None:
        return entity, battle_map, x, y

    if stack is None:
        return None, battle_map, x, y

    for floor_map, lx, ly, thing in things_at_stack_position(stack, x, y):
        if getattr(thing, 'entity_uid', None) and floor_map.entity_at(lx, ly) is thing:
            return thing, floor_map, lx, ly
    return None, battle_map, x, y


def resolve_entity_uid(session, battle_map, uid: str):
    """Look up an entity by UID across the session, not only the caster's map."""
    if not uid:
        return None
    ent = session.entity_by_uid(uid)
    if ent is not None:
        return ent
    return battle_map.entity_by_uid(uid)


def target_world_position(stack: Optional[MapStack], target, battle=None) -> Optional[list[int]]:
    """Return [wx, wy] for highlighting/targeting a creature across stack floors."""
    target_map = battle.map_for(target) if battle else None
    if target_map is None:
        return None
    pos = target_map.entity_or_object_pos(target)
    if pos is None:
        return None
    if stack is not None:
        wx, wy, _ = stack.local_to_world(target_map.name, pos[0], pos[1])
        return [wx, wy]
    return [pos[0], pos[1]]


def valid_target_positions(stack: Optional[MapStack], caster_map, targets, battle=None) -> dict:
    """Map entity_uid → [x, y] world coords for the VTT target picker."""
    positions = {}
    for target in targets:
        uid = getattr(target, 'entity_uid', None)
        if not uid:
            continue
        pos = target_world_position(stack, target, battle=battle)
        if pos is not None:
            positions[uid] = pos
    return positions
