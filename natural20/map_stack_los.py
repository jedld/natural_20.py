"""Height-aware line of sight across map stacks (3D x, y, z)."""

from __future__ import annotations

import math
from typing import Optional

from natural20.map_stack import MapStack
from natural20.utils.list_utils import bresenham_line_of_sight


def _vertical_deck_blocks(
    stack: MapStack,
    wx: int,
    wy: int,
    viewer_elev: float,
    target_elev: float,
) -> bool:
    """Return True when an overlay floor deck blocks vertical sight in one column."""
    if viewer_elev == target_elev:
        return False
    direction = _sight_direction(viewer_elev, target_elev)
    for floor in stack.overlay_floors():
        fe = floor.elevation_ft
        if viewer_elev < target_elev:
            if not (viewer_elev < fe <= target_elev):
                continue
        elif not (target_elev < fe <= viewer_elev):
            continue
        local = stack.world_to_local(wx, wy, floor.map_name)
        if local is None:
            continue
        if not stack.has_slab_at(floor, local[0], local[1]):
            continue
        if _floor_deck_pierced(stack, wx, wy, floor, viewer_elev, target_elev):
            continue
        if stack.floor_mask_blocks(wx, wy, direction):
            return True
        return True
    return False


def _vertical_ceiling_blocks(
    stack: MapStack,
    wx: int,
    wy: int,
    viewer_elev: float,
    target_elev: float,
) -> bool:
    """Return True when a finite room ceiling blocks vertical sight in one column."""
    if viewer_elev >= target_elev:
        return False
    column_xy = (wx, wy)
    for floor in stack.floors:
        local = stack.world_to_local(wx, wy, floor.map_name)
        if local is None or not stack.has_slab_at(floor, local[0], local[1]):
            continue
        ceiling = stack.ceiling_elevation_ft(wx, wy, floor)
        if math.isinf(ceiling):
            continue
        if not _ray_crosses_floor_plane(
            viewer_elev, target_elev, ceiling, column_xy, column_xy, column_xy
        ):
            continue
        if _ceiling_pierced(stack, wx, wy, floor, viewer_elev, target_elev):
            continue
        if stack.floor_mask_blocks(wx, wy, 'up'):
            return True
        return True
    return False


def stack_can_see(
    stack: MapStack,
    viewer,
    target,
    viewer_map,
    target_map,
    *,
    battle=None,
    distance: Optional[int] = None,
    heavy_cover: bool = False,
) -> bool:
    """Return True if viewer can see target across floors in the same stack."""
    v_world = _sight_world_position(viewer, viewer_map)
    t_world = _sight_world_position(target, target_map)
    if v_world is None or t_world is None:
        return False

    vpos = stack.world_to_local(v_world.x, v_world.y, viewer_map.name)
    tpos = stack.world_to_local(t_world.x, t_world.y, target_map.name)
    if vpos is None or tpos is None:
        return False

    if distance is not None:
        dist = math.floor(math.sqrt((v_world.x - t_world.x) ** 2 + (v_world.y - t_world.y) ** 2))
        if dist > distance:
            return False

    viewer_xy = (v_world.x, v_world.y)
    target_xy = (t_world.x, t_world.y)

    if viewer_xy == target_xy:
        if _vertical_deck_blocks(stack, viewer_xy[0], viewer_xy[1], v_world.elevation_ft, t_world.elevation_ft):
            return False
        if _vertical_ceiling_blocks(stack, viewer_xy[0], viewer_xy[1], v_world.elevation_ft, t_world.elevation_ft):
            return False
        if viewer_map == target_map:
            return bool(target_map.can_see_square(viewer, tpos, inclusive=True))
        return True

    ray = bresenham_line_of_sight(v_world.x, v_world.y, t_world.x, t_world.y)
    if ray and len(ray) > 2:
        for wx, wy in ray[1:-1]:
            if _column_blocks_sight(
                stack,
                wx,
                wy,
                v_world.elevation_ft,
                t_world.elevation_ft,
                viewer_map.name,
                viewer_xy,
                target_xy,
            ):
                return False

    if viewer_map == target_map:
        return bool(target_map.can_see_square(viewer, tpos, inclusive=True))

    # Cross-floor: geometric 3D ray cleared; verify target tile visibility.
    try:
        return bool(target_map.can_see_square(viewer, tpos, inclusive=True))
    except Exception:
        return True


def _sight_world_position(entity, battle_map):
    if hasattr(entity, 'sight_world_position'):
        return entity.sight_world_position(battle_map)
    return entity.world_position(battle_map)


def _sight_direction(viewer_elev: float, target_elev: float) -> str:
    return 'up' if viewer_elev < target_elev else 'down'


def _ray_crosses_floor_plane(
    viewer_elev: float,
    target_elev: float,
    plane_elev: float,
    column_xy: tuple[int, int],
    viewer_xy: tuple[int, int],
    target_xy: tuple[int, int],
) -> bool:
    """True when a horizontal floor/ceiling at plane_elev blocks the vertical segment."""
    if viewer_elev == target_elev:
        return False
    if column_xy == viewer_xy and plane_elev == viewer_elev:
        return False
    if column_xy == target_xy and plane_elev == target_elev:
        return False
    lo, hi = min(viewer_elev, target_elev), max(viewer_elev, target_elev)
    if viewer_elev < target_elev:
        return viewer_elev < plane_elev <= target_elev
    return target_elev < plane_elev <= viewer_elev


def _ray_passes_floor_volume(
    viewer_elev: float,
    target_elev: float,
    floor_elev: float,
    column_xy: tuple[int, int],
    viewer_xy: tuple[int, int],
    target_xy: tuple[int, int],
) -> bool:
    """True when volumetric obstacles on this floor elevation should be checked."""
    lo, hi = min(viewer_elev, target_elev), max(viewer_elev, target_elev)
    if floor_elev < lo or floor_elev > hi:
        return False
    if column_xy == viewer_xy and floor_elev == viewer_elev:
        return False
    if column_xy == target_xy and floor_elev == target_elev:
        return False
    return True


def _floor_deck_pierced(
    stack: MapStack,
    wx: int,
    wy: int,
    floor,
    viewer_elev: float,
    target_elev: float,
) -> bool:
    if stack.is_stack_opening(wx, wy):
        return True
    if stack.is_window_at(wx, wy, floor.map_name):
        return True
    direction = _sight_direction(viewer_elev, target_elev)
    if stack.floor_mask_allows_sight(wx, wy, direction):
        return True
    return False


def _ceiling_pierced(
    stack: MapStack,
    wx: int,
    wy: int,
    floor,
    viewer_elev: float,
    target_elev: float,
) -> bool:
    if stack.is_stack_opening(wx, wy):
        return True
    if stack.is_window_at(wx, wy):
        return True
    if stack.floor_mask_allows_sight(wx, wy, 'up'):
        return True
    return False


def _ceiling_blocks_at_column(
    stack: MapStack,
    wx: int,
    wy: int,
    viewer_elev: float,
    target_elev: float,
    viewer_xy: tuple[int, int],
    target_xy: tuple[int, int],
) -> bool:
    if viewer_elev >= target_elev:
        return False
    column_xy = (wx, wy)
    for floor in stack.floors:
        local = stack.world_to_local(wx, wy, floor.map_name)
        if local is None or not stack.has_slab_at(floor, local[0], local[1]):
            continue
        ceiling = stack.ceiling_elevation_ft(wx, wy, floor)
        if math.isinf(ceiling):
            continue
        if not _ray_crosses_floor_plane(
            viewer_elev, target_elev, ceiling, column_xy, viewer_xy, target_xy
        ):
            continue
        if _ceiling_pierced(stack, wx, wy, floor, viewer_elev, target_elev):
            continue
        if stack.floor_mask_blocks(wx, wy, 'up'):
            return True
        return True
    return False


def _column_blocks_sight(
    stack: MapStack,
    wx: int,
    wy: int,
    viewer_elev: float,
    target_elev: float,
    viewer_map_name: str,
    viewer_xy: tuple[int, int],
    target_xy: tuple[int, int],
) -> bool:
    column_xy = (wx, wy)
    direction = _sight_direction(viewer_elev, target_elev)

    # Overlay floor decks are opaque by default unless pierced (window, shaft, allows_sight mask).
    viewer_floor = stack.floor_for_map(viewer_map_name)
    for floor in stack.overlay_floors():
        fe = floor.elevation_ft
        if not _ray_crosses_floor_plane(viewer_elev, target_elev, fe, column_xy, viewer_xy, target_xy):
            continue
        local = stack.world_to_local(wx, wy, floor.map_name)
        if local is None:
            continue
        lx, ly = local
        if not stack.has_slab_at(floor, lx, ly):
            continue
        # Standing on a deck: oblique rays across the footprint are open air in the
        # room. Only block vertical sight through this column to a target below the slab.
        if (
            viewer_floor is not None
            and viewer_floor.map_name == floor.map_name
            and viewer_elev >= fe
            and column_xy != target_xy
        ):
            continue
        if _floor_deck_pierced(stack, wx, wy, floor, viewer_elev, target_elev):
            continue
        if stack.floor_mask_blocks(wx, wy, direction):
            return True
        return True

    if _ceiling_blocks_at_column(
        stack, wx, wy, viewer_elev, target_elev, viewer_xy, target_xy
    ):
        return True

    # Volumetric walls/objects on each floor elevation the ray traverses.
    viewer_floor = stack.floor_for_map(viewer_map_name)
    for floor in stack.floors:
        fe = floor.elevation_ft
        if not _ray_passes_floor_volume(viewer_elev, target_elev, fe, column_xy, viewer_xy, target_xy):
            continue
        local = stack.world_to_local(wx, wy, floor.map_name)
        if local is None:
            continue
        lx, ly = local
        # Lower-floor walls under the viewer's overlay deck do not block sight from above.
        viewer_local = stack.world_to_local(wx, wy, viewer_floor.map_name) if viewer_floor else None
        if (
            viewer_floor is not None
            and not viewer_floor.is_base
            and viewer_elev >= viewer_floor.elevation_ft
            and floor.elevation_ft < viewer_floor.elevation_ft
            and viewer_local is not None
            and stack.has_slab_at(viewer_floor, viewer_local[0], viewer_local[1])
        ):
            continue
        if stack.is_stack_opening(wx, wy):
            continue
        if (
            viewer_floor is not None
            and not viewer_floor.is_base
            and viewer_elev >= viewer_floor.elevation_ft
            and floor.is_base
            and stack.is_building_exterior_shell(wx, wy)
        ):
            continue
        if floor.map.opaque(lx, ly):
            return True
        if floor.map.base_map[lx][ly] == '#':
            if (
                viewer_floor is not None
                and not viewer_floor.is_base
                and viewer_elev >= viewer_floor.elevation_ft
                and floor.is_base
                and stack.is_building_exterior_shell(wx, wy)
            ):
                continue
            return True

    return False


def _overlay_footprint_ray_blocks(
    stack: MapStack,
    viewer_floor,
    viewer_map_name: str,
    vwx: int,
    vwy: int,
    wx: int,
    wy: int,
) -> bool:
    """Return True when upstairs walls inside the overlay footprint block the ray."""
    omap = viewer_floor.map
    ray = bresenham_line_of_sight(vwx, vwy, wx, wy)
    if not ray:
        return True
    origin = stack.world_to_local(vwx, vwy, viewer_map_name)
    for cx, cy in ray[1:-1]:
        local = stack.world_to_local(cx, cy, viewer_map_name)
        if local is None:
            continue
        lx, ly = local
        if _overlay_cell_blocks_ray(omap, lx, ly, origin=origin):
            return True
    return False


def _base_outdoor_ray_blocks(
    stack: MapStack,
    viewer_floor,
    base_map,
    vwx: int,
    vwy: int,
    wx: int,
    wy: int,
) -> bool:
    """Return True when ground-level geometry blocks elevated outdoor sight."""
    ray = bresenham_line_of_sight(vwx, vwy, wx, wy)
    if not ray:
        return True
    if ray[-1] != (wx, wy):
        ray = [*ray, (wx, wy)]
    omap_name = viewer_floor.map_name if viewer_floor is not None else None
    for cx, cy in ray[1:]:
        if omap_name and stack.world_to_local(cx, cy, omap_name) is not None:
            continue
        if stack.is_building_exterior_shell(cx, cy):
            continue
        if cx < 0 or cy < 0 or cx >= base_map.size[0] or cy >= base_map.size[1]:
            return True
        if base_map.base_map[cx][cy] == '#':
            return True
        try:
            # Elevated sight: do not use origin-dependent corner peeking.
            if base_map.opaque(cx, cy):
                return True
        except Exception:
            pass
    return False


def _overlay_legend_category(omap, lx: int, ly: int) -> str:
    from natural20.map_editor import _categorize_type, _legend_for

    legend = _legend_for(omap.properties)
    leg = legend.get(omap.base_map[lx][ly]) or {}
    return _categorize_type(leg.get('type'))


def _overlay_cell_blocks_ray(omap, lx: int, ly: int, origin=None) -> bool:
    """True when an overlay map cell blocks a horizontal sight ray."""
    if omap.base_map[lx][ly] == '#':
        return True
    category = _overlay_legend_category(omap, lx, ly)
    if category in ('wall', 'door'):
        return True
    try:
        if omap.opaque(lx, ly, origin=origin):
            return True
    except Exception:
        try:
            if omap.opaque(lx, ly):
                return True
        except Exception:
            pass
    return False


def _overlay_edge_allows_peek(omap, lx: int, ly: int) -> bool:
    """True when an overlay border cell is open (not void/wall/door/window)."""
    if omap.base_map[lx][ly] == '#':
        return False
    from natural20.map_editor import _legend_for

    legend = _legend_for(omap.properties)
    leg = legend.get(omap.base_map[lx][ly]) or {}
    type_name = leg.get('type')
    category = _overlay_legend_category(omap, lx, ly)
    if category in ('wall', 'door'):
        return False
    if type_name == 'window':
        return False
    return True


def _overlay_outdoor_egress_allowed(
    stack: MapStack,
    viewer_floor,
    viewer_map_name: str,
    vwx: int,
    vwy: int,
    wx: int,
    wy: int,
) -> bool:
    """True when a ray to an outdoor base cell leaves the overlay through a valid opening."""
    if stack.in_overlay_footprint(viewer_floor, wx, wy):
        return False
    omap = viewer_floor.map
    omap_name = viewer_floor.map_name
    ray = bresenham_line_of_sight(vwx, vwy, wx, wy)
    if not ray:
        return False
    if ray[-1] != (wx, wy):
        ray = [*ray, (wx, wy)]

    egress = None
    for cx, cy in ray:
        local = stack.world_to_local(cx, cy, omap_name)
        if local is not None:
            egress = (cx, cy, local[0], local[1])
        elif egress is not None:
            break
    if egress is None:
        return False

    egress_wx, egress_wy, lx, ly = egress
    if stack.is_window_at(egress_wx, egress_wy, omap_name):
        return True
    return _overlay_edge_allows_peek(omap, lx, ly)


def _overlay_perimeter_wall(omap, lx: int, ly: int) -> bool:
    """True when an overlay border cell is a solid wall (parapet)."""
    ow, oh = omap.size
    if lx != 0 and ly != 0 and lx != ow - 1 and ly != oh - 1:
        return False
    return _overlay_cell_blocks_ray(omap, lx, ly) and _overlay_legend_category(omap, lx, ly) == 'wall'


def _parapet_blocks_outdoor_sight(
    stack: MapStack,
    viewer_floor,
    vwx: int,
    vwy: int,
    wx: int,
    wy: int,
    viewer_eye_ft: float,
) -> bool:
    """Return True when overlay roof parapets block a low viewer from seeing outdoors."""
    if viewer_floor is None or viewer_floor.is_base:
        return False
    omap = viewer_floor.map
    parapet_ft = float(getattr(viewer_floor, 'parapet_height_ft', 0.0) or 0.0)
    if parapet_ft <= 0:
        return False
    deck_elev = viewer_floor.elevation_ft
    sight_min = deck_elev + parapet_ft
    if viewer_eye_ft >= sight_min:
        return False

    ow, oh = omap.size
    ray = bresenham_line_of_sight(vwx, vwy, wx, wy)
    if not ray:
        return False
    for cx, cy in ray[1:]:
        local = stack.world_to_local(cx, cy, viewer_floor.map_name)
        if local is None:
            continue
        lx, ly = local
        on_perimeter = lx == 0 or ly == 0 or lx == ow - 1 or ly == oh - 1
        if not on_perimeter:
            continue
        if not _overlay_perimeter_wall(omap, lx, ly):
            continue
        if stack.is_window_at(cx, cy):
            continue
        return True
    return False


def stack_base_visible_from_overlay(
    stack: MapStack,
    viewer,
    viewer_map,
    base_map,
    wx: int,
    wy: int,
) -> bool:
    """Whether a base-map world cell is visible to a viewer on an overlay floor."""
    viewer_floor = stack.floor_for_map(viewer_map.name)
    if viewer_floor is None or viewer_floor.is_base:
        try:
            return bool(base_map.can_see_square(viewer, (wx, wy)))
        except Exception:
            return False

    viewer_squares = viewer_map.entity_squares(viewer)
    if not viewer_squares:
        return False

    viewer_sight_elev = _sight_world_position(viewer, viewer_map)
    viewer_eye_ft = (
        viewer_sight_elev.elevation_ft - viewer_floor.elevation_ft
        if viewer_sight_elev is not None
        else 0.0
    )

    for pos in viewer_squares:
        vwx, vwy, _viewer_elev = stack.local_to_world(viewer_map.name, pos[0], pos[1])
        if not _overlay_outdoor_egress_allowed(
            stack, viewer_floor, viewer_map.name, vwx, vwy, wx, wy
        ):
            continue
        if _parapet_blocks_outdoor_sight(
            stack, viewer_floor, vwx, vwy, wx, wy, viewer_eye_ft
        ):
            continue
        if _overlay_footprint_ray_blocks(stack, viewer_floor, viewer_map.name, vwx, vwy, wx, wy):
            continue
        if _base_outdoor_ray_blocks(stack, viewer_floor, base_map, vwx, vwy, wx, wy):
            continue
        if _peek_tile_visible(viewer, base_map, wx, wy, vwx, vwy):
            return True
    return False


def stack_peek_visible_at(
    stack: MapStack,
    viewer,
    viewer_map,
    target_map,
    wx: int,
    wy: int,
) -> bool:
    """Return True if viewer on an overlay floor can see a base-map world cell through a window."""
    if not stack.is_window_at(wx, wy, viewer_map.name):
        return False

    viewer_squares = viewer_map.entity_squares(viewer)
    if not viewer_squares:
        return False

    _, _, target_elev = stack.local_to_world(target_map.name, wx, wy)
    target_xy = (wx, wy)

    viewer_sight = _sight_world_position(viewer, viewer_map)

    for pos1 in viewer_squares:
        vwx, vwy, floor_elev = stack.local_to_world(viewer_map.name, pos1[0], pos1[1])
        viewer_elev = (
            viewer_sight.elevation_ft
            if viewer_sight is not None
            else floor_elev + float(getattr(viewer, 'altitude_ft', 0.0) or 0.0)
        )
        viewer_xy = (vwx, vwy)
        ray = bresenham_line_of_sight(vwx, vwy, wx, wy)
        if ray:
            blocked = False
            for cx, cy in ray[1:-1]:
                if _column_blocks_sight(
                    stack,
                    cx,
                    cy,
                    viewer_elev,
                    target_elev,
                    viewer_map.name,
                    viewer_xy,
                    target_xy,
                ):
                    blocked = True
                    break
            if blocked:
                continue
        if _peek_tile_visible(viewer, target_map, wx, wy, vwx, vwy):
            return True
    return False


def _peek_tile_visible(viewer, target_map, wx: int, wy: int, vwx: int, vwy: int) -> bool:
    light = target_map.light_at(wx, wy)
    if light >= 0.5:
        return True
    dist = math.floor(math.sqrt((vwx - wx) ** 2 + (vwy - wy) ** 2))
    try:
        return bool(viewer.darkvision(dist * target_map.feet_per_grid))
    except Exception:
        return False


def stack_squares_in_range(stack: MapStack, origin_map, ox: int, oy: int, radius_squares: int):
    """Yield (map, lx, ly) tuples within Chebyshev range, all floors in stack."""
    wx, wy, _ = stack.local_to_world(origin_map.name, ox, oy)
    for dx in range(-radius_squares, radius_squares + 1):
        for dy in range(-radius_squares, radius_squares + 1):
            if max(abs(dx), abs(dy)) > radius_squares:
                continue
            cx, cy = wx + dx, wy + dy
            for floor in stack.floors_at_world(cx, cy):
                local = stack.world_to_local(cx, cy, floor.map_name)
                if local:
                    yield floor.map, local[0], local[1]
