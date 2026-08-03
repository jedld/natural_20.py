"""Message cantrip path reachability — BFS with cumulative barrier thickness."""

from __future__ import annotations

from collections import deque
from typing import Iterable

from natural20.utils.magical_aura import _barrier_layers_at_square

MESSAGE_RANGE_FT = 120

# RAW: 1 ft stone, 1 inch metal, thin sheet of lead, 3 ft wood.
MESSAGE_PENETRATION_FT = {
    'stone': 1.0,
    'metal': 1.0 / 12.0,
    'lead': 0.0,
    'wood': 3.0,
    'dirt': 3.0,
}


def _fresh_accumulated() -> dict[str, float]:
    return {material: 0.0 for material in MESSAGE_PENETRATION_FT}


def _accumulate_barriers(
    accumulated: dict[str, float],
    battle_map,
    x: int,
    y: int,
    origin: tuple[int, int] | None,
) -> bool:
    """Add barrier layers at (x, y). Return False when penetration limits are exceeded."""
    for material, thickness in _barrier_layers_at_square(battle_map, x, y, origin=origin):
        key = material if material in MESSAGE_PENETRATION_FT else 'stone'
        accumulated[key] = accumulated.get(key, 0.0) + thickness
        limit = MESSAGE_PENETRATION_FT[key]
        if limit <= 0 or accumulated[key] > limit + 1e-9:
            return False
    return True


def _grid_distance_ft(
    from_squares: Iterable[tuple[int, int]],
    x: int,
    y: int,
    feet_per_grid: float,
) -> float:
    best = None
    for sx, sy in from_squares:
        dist = ((sx - x) ** 2 + (sy - y) ** 2) ** 0.5 * feet_per_grid
        if best is None or dist < best:
            best = dist
    return best if best is not None else float('inf')


def entity_in_magical_silence(entity) -> bool:
    if entity is None:
        return False
    statuses = getattr(entity, 'statuses', None) or []
    if 'silenced' in statuses or 'magical_silence' in statuses:
        return True
    for effect_id in ('silence', 'magical_silence'):
        try:
            if entity.has_effect(effect_id):
                return True
        except Exception:
            continue
    return False


def entities_familiar(source, target) -> bool:
    if source is None or target is None:
        return False
    source_group = getattr(source, 'group', None)
    target_group = getattr(target, 'group', None)
    if source_group and target_group and source_group == target_group:
        return True
    source_uid = getattr(source, 'entity_uid', None)
    target_uid = getattr(target, 'entity_uid', None)
    if not source_uid or not target_uid:
        return False
    for buffer in (getattr(source, 'memory_buffer', None) or [], getattr(target, 'memory_buffer', None) or []):
        for entry in buffer:
            if not isinstance(entry, dict):
                continue
            entry_source = entry.get('source')
            entry_targets = entry.get('targets') or entry.get('directed_to') or []
            entry_source_uid = getattr(entry_source, 'entity_uid', None) if entry_source is not None else None
            if entry_source_uid == source_uid and target in entry_targets:
                return True
            if entry_source_uid == target_uid and source in entry_targets:
                return True
    return False


def message_spell_reachable(
    battle_map,
    caster,
    target,
    *,
    range_ft: float = MESSAGE_RANGE_FT,
    allow_familiar_bypass: bool = True,
) -> bool:
    """True when a Message whisper can reach *target* from *caster* on *battle_map*."""
    if battle_map is None or caster is None or target is None:
        return False
    if caster is target:
        return False
    if entity_in_magical_silence(caster) or entity_in_magical_silence(target):
        return False

    feet_per_grid = float(getattr(battle_map, 'feet_per_grid', 5) or 5)
    if battle_map.distance(caster, target) * feet_per_grid > range_ft + 1e-9:
        return False

    caster_squares = [tuple(sq) for sq in battle_map.entity_squares(caster)]
    target_squares = {tuple(sq) for sq in battle_map.entity_squares(target)}
    if not caster_squares or not target_squares:
        return False

    if target_squares.intersection(caster_squares):
        return True

    width, height = battle_map.size
    queue: deque[tuple[int, int, tuple[tuple[str, float], ...]]] = deque()
    visited: set[tuple[int, int, tuple[tuple[str, float], ...]]] = set()

    for start in caster_squares:
        state = (start[0], start[1], tuple(_fresh_accumulated().items()))
        queue.append(state)
        visited.add(state)

    directions = ((0, 1), (0, -1), (1, 0), (-1, 0))

    while queue:
        x, y, acc_items = queue.popleft()
        if (x, y) in target_squares:
            return True

        for dx, dy in directions:
            nx, ny = x + dx, y + dy
            if nx < 0 or ny < 0 or nx >= width or ny >= height:
                continue
            if _grid_distance_ft(caster_squares, nx, ny, feet_per_grid) > range_ft + 1e-9:
                continue

            accumulated = dict(acc_items)
            if not _accumulate_barriers(accumulated, battle_map, nx, ny, origin=(x, y)):
                continue

            state = (nx, ny, tuple(sorted(accumulated.items())))
            if state in visited:
                continue
            visited.add(state)
            queue.append(state)

    if allow_familiar_bypass and entities_familiar(caster, target):
        return True
    return False
