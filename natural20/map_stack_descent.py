"""Voluntary stack descent pathfinding (Ctrl / jump mode).

Players and NPCs can path to a lower floor only when explicitly opting in.
Plans include fall damage previews, height-adjusted movement cost, and
metadata for the VTT and LLM controllers.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from natural20.ai.path_compute import PathCompute
from natural20.map_stack import MapStack
from natural20.utils.movement import compute_actual_moves


def preview_fall_damage(entity, damage_die: Optional[str]) -> dict[str, Any]:
    """Return fall damage die and whether it is mitigated for ``entity``."""
    if not damage_die:
        return {'die': None, 'mitigated': True, 'reason': 'no_damage'}
    if getattr(entity, 'flying', False):
        return {'die': None, 'mitigated': True, 'reason': 'flying'}
    if hasattr(entity, 'is_flying') and entity.is_flying():
        return {'die': None, 'mitigated': True, 'reason': 'flying'}
    statuses = getattr(entity, 'statuses', []) or []
    if 'feather_fall' in statuses:
        return {'die': None, 'mitigated': True, 'reason': 'feather_fall'}
    return {'die': damage_die, 'mitigated': False, 'reason': None}


def vertical_movement_cost_grids(fall_ft: float, feet_per_grid: int) -> int:
    """Extra movement grids for a vertical drop (1 grid per story height)."""
    if fall_ft <= 0:
        return 0
    return max(1, int(math.ceil(fall_ft / max(1, feet_per_grid))))


def voluntary_descent_edges(
    stack: MapStack,
    map_name: str,
    lx: int,
    ly: int,
    *,
    session=None,
    entity=None,
    battle=None,
) -> list[dict[str, Any]]:
    """Return voluntary descent transitions from ``(map_name, lx, ly)``."""
    floor = stack.floor_for_map(map_name)
    if floor is None or floor.is_base:
        return []

    wx, wy, elev = stack.local_to_world(map_name, lx, ly)
    lower = stack.lower_floor_at(wx, wy, elev)
    if lower is None:
        lower = next((f for f in stack.floors if f.is_base), None)
    if lower is None:
        return []

    land_local = stack.world_to_local(wx, wy, lower.map_name)
    if land_local is None:
        return []

    edges: list[dict[str, Any]] = []
    delta = stack.elevation_delta_ft(elev, lower.elevation_ft)

    if stack.is_window_at(wx, wy, map_name):
        edges.append(_edge_payload(lower, land_local, delta, 'window', prone_on_land=True))

    if stack.is_stack_opening(wx, wy):
        edges.append(_edge_payload(lower, land_local, delta, 'stack_opening', prone_on_land=True))

  # Edge exit: stepping to an out-of-bounds neighbor from a perimeter tile.
    ow, oh = floor.map.size
    if 0 <= lx < ow and 0 <= ly < oh:
        for nx, ny in ((lx + 1, ly), (lx - 1, ly), (lx, ly + 1), (lx, ly - 1)):
            if 0 <= nx < ow and 0 <= ny < oh:
                continue
            exit_target = stack.resolve_edge_exit(map_name, nx, ny)
            if not exit_target:
                continue
            base_name, blx, bly = exit_target
            base_floor = stack.floor_for_map(base_name)
            base_elev = base_floor.elevation_ft if base_floor else 0.0
            edge_delta = stack.elevation_delta_ft(elev, base_elev)
            edges.append({
                'to_map': base_name,
                'to_lx': blx,
                'to_ly': bly,
                'type': 'edge_exit',
                'fall_ft': edge_delta,
                'prone_on_land': False,
            })

    # Deduplicate by target tile + type.
    seen = set()
    unique: list[dict[str, Any]] = []
    for edge in edges:
        key = (edge['to_map'], edge['to_lx'], edge['to_ly'], edge['type'])
        if key in seen:
            continue
        seen.add(key)
        if session is not None:
            dest_map = session.maps.get(edge['to_map'])
            if dest_map is not None and entity is not None:
                if not dest_map.passable(entity, edge['to_lx'], edge['to_ly'], battle, True):
                    continue
        unique.append(edge)
    return unique


def _edge_payload(lower, land_local, delta, descent_type, *, prone_on_land: bool) -> dict[str, Any]:
    return {
        'to_map': lower.map_name,
        'to_lx': land_local[0],
        'to_ly': land_local[1],
        'type': descent_type,
        'fall_ft': delta,
        'prone_on_land': prone_on_land,
    }


def stack_descent_llm_summary(plan: Optional[dict[str, Any]]) -> str:
    """One-line explanation of a voluntary stack descent for LLM prompts."""
    if not plan or not plan.get('stack_descent'):
        return ''
    sd = plan['stack_descent']
    parts = [
        f"Voluntary descent ({sd.get('descent_type', 'fall')})",
        f"{sd.get('from_map')} → {sd.get('to_map')}",
        f"fall {int(sd.get('fall_ft') or 0)} ft",
    ]
    if sd.get('fall_damage_die'):
        parts.append(f"expected damage {sd['fall_damage_die']}")
    elif sd.get('fall_damage_mitigated'):
        parts.append(f"no fall damage ({sd.get('mitigation_reason', 'mitigated')})")
    if sd.get('prone_on_land'):
        parts.append('lands prone')
    return '; '.join(parts)


def plan_voluntary_stack_route(
    path_compute: PathCompute,
    session,
    battle,
    entity,
    source_map,
    source_x: int,
    source_y: int,
    target_map,
    target_x: int,
    target_y: int,
    *,
    available_movement_cost: Optional[int] = None,
    accumulated_path=None,
    door_navigation: bool = False,
) -> Optional[dict[str, Any]]:
    """Plan a route that may include one voluntary descent to a lower floor."""
    stack: Optional[MapStack] = getattr(source_map, 'map_stack', None)
    if stack is None or source_map is target_map:
        return None

    feet_per = getattr(source_map, 'feet_per_grid', 5) or 5
    floor = stack.floor_for_map(source_map.name)
    if floor is None or floor.is_base:
        return None

    best: Optional[dict[str, Any]] = None
    best_total = math.inf
    ow, oh = floor.map.size

    for lx in range(ow):
        for ly in range(oh):
            edges = voluntary_descent_edges(
                stack, source_map.name, lx, ly,
                session=session, entity=entity, battle=battle,
            )
            if not edges:
                continue
            overlay_path = path_compute._compute_path_on(
                source_map, source_x, source_y, lx, ly, door_navigation=door_navigation,
            )
            if overlay_path is None:
                continue
            overlay_cost = max(0, len(overlay_path) - 1)

            for edge in edges:
                if edge['to_map'] != target_map.name:
                    continue
                next_map = session.maps.get(edge['to_map'])
                if next_map is None:
                    continue
                land_lx, land_ly = edge['to_lx'], edge['to_ly']
                base_path = path_compute._compute_path_on(
                    next_map, land_lx, land_ly, target_x, target_y,
                    door_navigation=door_navigation,
                )
                if base_path is None:
                    continue
                vert_grids = vertical_movement_cost_grids(edge['fall_ft'], feet_per)
                base_cost = max(0, len(base_path) - 1)
                total = overlay_cost + vert_grids + base_cost
                if total >= best_total:
                    continue
                best_total = total
                descent_info = {
                    'descent_type': edge['type'],
                    'from_map': source_map.name,
                    'to_map': edge['to_map'],
                    'fall_ft': edge['fall_ft'],
                    'prone_on_land': edge.get('prone_on_land', False),
                    'land_position': [land_lx, land_ly],
                }
                best = {
                    'overlay_path': overlay_path,
                    'base_path': base_path,
                    'descent_info': descent_info,
                }

    if best is None:
        return None

    overlay_path = best['overlay_path']
    base_path = best['base_path']
    descent_info = best['descent_info']

    if accumulated_path:
        full_path = list(accumulated_path)
        if full_path:
            full_path.extend(overlay_path[1:])
        else:
            full_path = overlay_path
    else:
        full_path = overlay_path

    budget = None
    if battle and entity in getattr(battle, 'entities', {}):
        budget = entity.available_movement(battle) / feet_per
    elif available_movement_cost is not None:
        budget = available_movement_cost / feet_per

    movement = compute_actual_moves(entity, full_path, source_map, battle, budget or 9999, test_placement=False)
    vert_grids = vertical_movement_cost_grids(descent_info['fall_ft'], feet_per)
    overlay_spent = movement.original_budget - movement.budget
    base_movement = compute_actual_moves(
        entity, base_path, target_map, battle, movement.budget - vert_grids, test_placement=False,
    )
    base_spent = (movement.budget - vert_grids) - base_movement.budget
    total_spent = overlay_spent + vert_grids + max(0, base_spent)
    movement.budget = movement.original_budget - total_spent

    damage_die = stack.fall_damage_die(descent_info['fall_ft'])
    fall_preview = preview_fall_damage(entity, damage_die)

    stack_descent = {
        **descent_info,
        'fall_damage_die': fall_preview['die'],
        'fall_damage_mitigated': fall_preview['mitigated'],
        'mitigation_reason': fall_preview['reason'],
        'vertical_cost_grids': vert_grids,
        'label': _descent_label(descent_info, fall_preview),
        'base_path': base_path,
        'llm_summary': _descent_label(descent_info, fall_preview),
    }

    terrain_info = []
    for px, py in overlay_path:
        terrain_info.append({
            'x': px,
            'y': py,
            'difficult': bool(source_map.difficult_terrain(entity, px, py, battle)),
        })

    return {
        'path': overlay_path,
        'segments': [
            {'map': source_map.name, 'path': overlay_path},
            {'map': target_map.name, 'path': base_path},
        ],
        'stack_descent': stack_descent,
        'cost': movement.to_dict(),
        'placeable': target_map.placeable(entity, target_x, target_y, battle, False),
        'terrain_info': terrain_info,
        'stack_descent_mode': True,
    }


def _descent_label(descent_info: dict, fall_preview: dict) -> str:
    fall_ft = int(descent_info.get('fall_ft') or 0)
    kind = str(descent_info.get('descent_type') or 'fall').replace('_', ' ')
    label = f'Jump to lower level ({fall_ft} ft {kind})'
    if fall_preview.get('mitigated'):
        label += ' — no fall damage'
    elif fall_preview.get('die'):
        label += f' — {fall_preview["die"]} bludgeoning'
    if descent_info.get('prone_on_land'):
        label += ', lands prone'
    return label
