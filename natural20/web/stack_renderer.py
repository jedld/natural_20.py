"""Render composited map stack layers for the VTT."""

from __future__ import annotations

from typing import Any, Optional

from natural20.web.json_renderer import JsonRenderer


def _pov_on_map(entity_pov, battle_map):
    """Keep only POV entities that are placed on ``battle_map``."""
    if entity_pov is None or battle_map is None:
        return None
    pov_list = entity_pov if isinstance(entity_pov, list) else [entity_pov]
    on_map = []
    for entity in pov_list:
        if entity is None:
            continue
        try:
            if entity in battle_map.entities:
                on_map.append(entity)
        except Exception:
            pass
    if not on_map:
        return None
    return on_map if len(on_map) > 1 else on_map[0]


def stack_for_map(session, battle_map) -> Optional[Any]:
    if session is None or not hasattr(session, 'map_stacks'):
        return None
    return session.map_stacks.stack_for_map(battle_map.name)


def _resolve_layer_background_asset(map_obj, map_name: str | None = None) -> str:
    """Return map background filename for ``/assets/maps/<filename>``."""
    try:
        filename = map_obj.background_image()
    except Exception:
        filename = None
    if not filename:
        filename = f'{(map_name or getattr(map_obj, "name", None) or "map")}.png'
    return filename


def build_stack_render_layers(session, battle_map, battle, *, padding=None, entity_pov=None) -> Optional[dict[str, Any]]:
    """Build tile layers for a composited stack view, or None if not in a stack."""
    stack = stack_for_map(session, battle_map)
    if stack is None:
        return None

    base_floor = next((f for f in stack.floors if f.is_base), None)
    if base_floor is None:
        return None

    active_floor = stack.floor_for_map(battle_map.name)
    pov_on_map = _pov_entities_on_map(entity_pov, battle_map)

    layers = []
    if active_floor and active_floor.is_base:
        base_pov = entity_pov
        base_peek_config = None
        mask_under_overlay = None
    elif active_floor:
        # Viewing an overlay floor: base shows the town around the building;
        # POV is resolved cross-floor when the token is on the overlay map.
        base_pov = entity_pov
        base_peek_config = None
        mask_under_overlay = active_floor
    else:
        base_pov = None
        base_peek_config = None
        mask_under_overlay = None
    base_renderer = JsonRenderer(base_floor.map, battle, padding=padding)
    base_tiles = base_renderer.render(entity_pov=base_pov if base_pov else None, stack_peek_config=base_peek_config)
    if mask_under_overlay is not None:
        _mask_base_tiles_under_overlay(stack, mask_under_overlay, base_tiles)
        _reveal_base_surround_for_overlay_view(
            stack, mask_under_overlay, base_floor.map, base_tiles, entity_pov, battle_map,
        )
    layers.append({
        'name': base_floor.map_name,
        'role': 'base',
        'anchor': [0, 0],
        'elevation_ft': base_floor.elevation_ft,
        'tiles': base_tiles,
        'background': _resolve_layer_background_asset(base_floor.map, base_floor.map_name),
        'size': list(base_floor.map.size),
        'image_offset_px': list(getattr(base_floor.map, 'image_offset_px', [0, 0]) or [0, 0]),
    })

    base_peek_underlay = None
    composite_mode = bool(active_floor and not active_floor.is_base)
    for floor in stack.floors:
        if floor.is_base:
            continue
        overlay_pov = entity_pov if active_floor and floor.map_name == battle_map.name else None
        # Overlay is composited on the base canvas — skip map padding so border
        # cells are not rendered as opaque fog over the town below.
        renderer = JsonRenderer(floor.map, battle, padding=None)
        tile_grid = renderer.render(entity_pov=overlay_pov)
        _annotate_stack_tiles(stack, floor, tile_grid, viewer_map=battle_map, entity_pov=overlay_pov)
        layers.append({
            'name': floor.map_name,
            'role': 'overlay',
            'anchor': list(floor.anchor),
            'elevation_ft': floor.elevation_ft,
            'tiles': tile_grid,
            'background': _resolve_layer_background_asset(floor.map, floor.map_name),
            'size': list(floor.map.size),
            'image_offset_px': list(getattr(floor.map, 'image_offset_px', [0, 0]) or [0, 0]),
        })
        if active_floor and floor.map_name == battle_map.name:
            base_peek_underlay = build_base_peek_underlay(
                stack,
                base_floor,
                floor,
                battle,
                padding,
                _pov_on_map(entity_pov, battle_map),
                battle_map,
            )

    payload = {
        'id': stack.id,
        'layers': layers,
        'active_map': battle_map.name,
        'composite_mode': composite_mode,
    }
    if composite_mode:
        overlay_floor = active_floor
        payload['anchor'] = list(overlay_floor.anchor)
        payload['active_layer_map'] = overlay_floor.map_name
    if base_peek_underlay is not None:
        payload['base_peek_underlay'] = base_peek_underlay
    return payload


def _mask_base_tiles_under_overlay(stack, overlay_floor, base_grid) -> None:
    """Hide base tiles covered by the overlay footprint (overlay draws on top)."""
    omap = overlay_floor.map_name
    ow, oh = overlay_floor.map.size
    for row in base_grid:
        for tile in row:
            if not isinstance(tile, dict):
                continue
            wx, wy = tile.get('x'), tile.get('y')
            if wx is None or wy is None:
                continue
            local = stack.world_to_local(wx, wy, omap)
            if local is None:
                continue
            lx, ly = local
            if 0 <= lx < ow and 0 <= ly < oh:
                tile['under_overlay'] = True
                tile['line_of_sight'] = True
                tile['opacity'] = 0


def _reveal_base_surround_for_overlay_view(stack, overlay_floor, base_map, base_grid, entity_pov, viewer_map) -> None:
    """Outdoor base tiles around the overlay footprint, with stack-aware LOS."""
    from natural20.map_stack_los import stack_base_visible_from_overlay

    pov_list = entity_pov if isinstance(entity_pov, list) else ([entity_pov] if entity_pov else [])
    pov_list = [e for e in pov_list if e is not None]

    for row in base_grid:
        for tile in row:
            if not isinstance(tile, dict):
                continue
            if tile.get('under_overlay'):
                continue
            wx, wy = tile.get('x'), tile.get('y')
            if wx is None or wy is None:
                continue
            if pov_list and viewer_map is not None:
                tile['line_of_sight'] = any(
                    stack_base_visible_from_overlay(stack, entity, viewer_map, base_map, wx, wy)
                    for entity in pov_list
                )
            else:
                tile['line_of_sight'] = True


def _outdoor_cell_beyond_window(stack, base_floor, overlay_floor, viewer_map, entity, wx: int, wy: int):
    """Step from a window on the overlay toward the outdoors on the base map."""
    if entity is None or viewer_map is None:
        return wx, wy
    viewer_pos = viewer_map.entity_or_object_pos(entity)
    if viewer_pos is None:
        return wx, wy
    vwx, vwy, _ = stack.local_to_world(viewer_map.name, viewer_pos[0], viewer_pos[1])
    dx, dy = wx - vwx, wy - vwy
    if dx == 0 and dy == 0:
        return wx, wy
    step_x = 0 if dx == 0 else (1 if dx > 0 else -1)
    step_y = 0 if dy == 0 else (1 if dy > 0 else -1)
    base = base_floor.map
    omap = overlay_floor.map_name
    for dist in range(1, 32):
        tx = wx + step_x * dist
        ty = wy + step_y * dist
        if tx < 0 or ty < 0 or tx >= base.size[0] or ty >= base.size[1]:
            break
        if stack.world_to_local(tx, ty, omap) is not None:
            continue
        return tx, ty
    return wx, wy


def _edge_cell_allows_peek(omap_obj, lx: int, ly: int) -> bool:
    """True when an overlay border cell is open (not void/wall/door/window)."""
    if omap_obj.base_map[lx][ly] == '#':
        return False
    from natural20.map_editor import _categorize_type, _legend_for

    legend = _legend_for(omap_obj.properties)
    ch = omap_obj.base_map[lx][ly]
    leg = legend.get(ch) or {}
    type_name = leg.get('type')
    category = _categorize_type(type_name)
    if category in ('wall', 'door'):
        return False
    if type_name == 'window':
        return False
    return True


def _edge_peek_world_target(stack, overlay_floor, lx: int, ly: int):
    """World coords of the base cell just outside the overlay along an open map edge."""
    ax, ay = overlay_floor.anchor
    wx, wy = ax + lx, ay + ly
    omap = overlay_floor.map_name
    omap_obj = overlay_floor.map
    ow, oh = overlay_floor.map.size
    if lx < 0 or ly < 0 or lx >= ow or ly >= oh:
        return None
    if not _edge_cell_allows_peek(omap_obj, lx, ly):
        return None
    base = next((f.map for f in stack.floors if f.is_base), None)
    if base is None:
        return None
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nx, ny = lx + dx, ly + dy
        if 0 <= nx < ow and 0 <= ny < oh:
            continue
        tx, ty = wx + dx, wy + dy
        if stack.world_to_local(tx, ty, omap) is not None:
            continue
        if 0 <= tx < base.size[0] and 0 <= ty < base.size[1]:
            return tx, ty
    return None


def _peek_underlay_world_target(stack, base_floor, overlay_floor, viewer_map, entity, lx: int, ly: int):
    ax, ay = overlay_floor.anchor
    wx, wy = ax + lx, ay + ly
    omap = overlay_floor.map_name
    if stack.is_window_at(wx, wy, omap):
        return _outdoor_cell_beyond_window(stack, base_floor, overlay_floor, viewer_map, entity, wx, wy)
    edge = _edge_peek_world_target(stack, overlay_floor, lx, ly)
    if edge is not None:
        return edge
    return None


def _is_edge_peek_cell(stack, floor, lx: int, ly: int) -> bool:
    return _edge_peek_world_target(stack, floor, lx, ly) is not None


def _peek_candidate_at(stack, floor, lx: int, ly: int) -> bool:
    wx, wy, _ = stack.local_to_world(floor.map_name, lx, ly)
    return bool(
        stack.is_window_at(wx, wy, floor.map_name)
        or _is_edge_peek_cell(stack, floor, lx, ly)
    )


def _viewer_can_peek_through(
    stack,
    base_floor,
    overlay_floor,
    viewer_map,
    entity_pov,
    lx: int,
    ly: int,
) -> bool:
    """True when a POV entity on the overlay can see outdoors through this cell."""
    if viewer_map is None or base_floor is None:
        return False
    pov_list = entity_pov if isinstance(entity_pov, list) else ([entity_pov] if entity_pov else [])
    pov_list = [entity for entity in pov_list if entity is not None]
    if not pov_list:
        return False

    entity = pov_list[0]
    peek_target = _peek_underlay_world_target(
        stack, base_floor, overlay_floor, viewer_map, entity, lx, ly,
    )
    if peek_target is None:
        return False

    from natural20.map_stack_los import stack_base_visible_from_overlay

    peek_wx, peek_wy = peek_target
    return any(
        stack_base_visible_from_overlay(
            stack, viewer_entity, viewer_map, base_floor.map, peek_wx, peek_wy,
        )
        for viewer_entity in pov_list
    )


def build_base_peek_underlay(stack, base_floor, overlay_floor, battle, padding, entity_pov, viewer_map):
    """Overlay-sized grid: base-map tiles visible through windows and open map edges."""
    ax, ay = overlay_floor.anchor
    ow, oh = overlay_floor.map.size

    renderer = JsonRenderer(base_floor.map, battle, padding=padding)
    full_base = renderer.render(entity_pov=entity_pov)
    base_by_pos = {
        (t['x'], t['y']): t
        for row in full_base
        for t in row
        if isinstance(t, dict) and t.get('x') is not None and t.get('y') is not None
    }

    result = []
    for ly in range(oh):
        row = []
        for lx in range(ow):
            if not _viewer_can_peek_through(
                stack, base_floor, overlay_floor, viewer_map, entity_pov, lx, ly,
            ):
                row.append(_empty_underlay_tile(lx, ly))
                continue
            peek_target = _peek_underlay_world_target(
                stack,
                base_floor,
                overlay_floor,
                viewer_map,
                entity_pov[0] if isinstance(entity_pov, list) and entity_pov else entity_pov,
                lx,
                ly,
            )
            if peek_target is None:
                row.append(_empty_underlay_tile(lx, ly))
                continue
            peek_wx, peek_wy = peek_target
            base_tile = base_by_pos.get((peek_wx, peek_wy))
            if base_tile is None:
                row.append(_empty_underlay_tile(lx, ly))
                continue
            peek = dict(base_tile)
            peek['x'] = lx
            peek['y'] = ly
            peek['world_x'] = peek_wx
            peek['world_y'] = peek_wy
            peek['line_of_sight'] = True
            row.append(peek)
        result.append(row)
    return result


def stack_floors_for_ui(stack) -> list[dict[str, Any]]:
    """Floor options for the layer-focus UI."""
    if stack is None:
        return []
    floors = []
    for floor in stack.floors:
        short = floor.map_name.replace('_', ' ').title()
        label = f"{short} ({int(floor.elevation_ft)} ft)" if floor.elevation_ft else short
        floors.append({
            'map_name': floor.map_name,
            'label': label,
            'elevation_ft': floor.elevation_ft,
            'is_base': floor.is_base,
        })
    return floors


def annotate_base_tiles_with_stack_overlay_entities(
    stack,
    base_grid,
    battle,
    entity_pov,
    viewer_map,
) -> None:
    """Project overlay-floor creatures onto the base map when POV has stack LOS."""
    from natural20.map_stack_los import stack_can_see

    pov_list = entity_pov if isinstance(entity_pov, list) else ([entity_pov] if entity_pov else [])
    pov_list = [e for e in pov_list if e is not None]
    if not pov_list:
        return

    tile_by_pos: dict[tuple[int, int], dict] = {}
    for row in base_grid:
        for tile in row:
            if isinstance(tile, dict) and tile.get('x') is not None and tile.get('y') is not None:
                tile_by_pos[(tile['x'], tile['y'])] = tile

    for floor in stack.floors:
        if floor.is_base:
            continue
        omap = floor.map
        for entity in list(omap.entities.keys()):
            if not getattr(entity, 'allow_targeting', lambda: True)():
                continue
            pos = omap.entity_or_object_pos(entity)
            if pos is None:
                continue
            wx, wy, _ = stack.local_to_world(floor.map_name, pos[0], pos[1])
            visible = False
            for pov in pov_list:
                pov_map = battle.map_for(pov) if battle else viewer_map
                if battle:
                    visible = battle.can_see(pov, entity)
                else:
                    visible = stack_can_see(stack, pov, entity, pov_map, omap, battle=battle)
                if visible:
                    break
            if not visible:
                continue
            tile = tile_by_pos.get((wx, wy))
            if tile is None or not tile.get('line_of_sight', True):
                continue
            if tile.get('stack_overlay_entity') or (tile.get('id') and tile.get('entity')):
                continue
            _apply_overlay_entity_to_tile(tile, entity, floor, wx, wy, battle)


def _apply_overlay_entity_to_tile(tile, entity, floor, wx: int, wy: int, battle) -> None:
    team_group, team_border_tint = None, None
    try:
        renderer = JsonRenderer(floor.map, battle, padding=None)
        team_group, team_border_tint = renderer._team_visuals_for(entity)
    except Exception:
        pass
    tile.update({
        'id': entity.entity_uid,
        'entity': entity.token_image(),
        'name': entity.label(),
        'label': entity.label(),
        'hp': entity.hp(),
        'max_hp': entity.max_hp(),
        'entity_size': entity.size(),
        'stack_overlay_entity': True,
        'stack_layer_map': floor.map_name,
        'stack_elevation_ft': floor.elevation_ft,
        'world_x': wx,
        'world_y': wy,
        'hiding': entity.hidden(),
        'prone': entity.prone(),
        'dead': entity.dead(),
        'unconscious': entity.unconscious(),
        'effects': [str(effect['effect']) for effect in entity.current_effects()],
        'in_battle': bool(battle and entity in getattr(battle, 'combat_order', [])),
        'opacity': 1.0,
        'team_group': team_group,
        'team_border_tint': team_border_tint,
        'objects': tile.get('objects') or [],
    })


def _empty_underlay_tile(lx: int, ly: int) -> dict:
    return {
        'x': lx,
        'y': ly,
        'line_of_sight': False,
        'opacity': 0,
        'underlay_empty': True,
        'objects': [],
    }


def _pov_entities_on_map(entity_pov, battle_map):
    if not entity_pov or battle_map is None:
        return []
    pov_list = entity_pov if isinstance(entity_pov, list) else [entity_pov]
    on_map = []
    for entity in pov_list:
        if entity is None:
            continue
        try:
            if entity in battle_map.entities:
                on_map.append(entity)
        except Exception:
            pass
    return on_map


def _annotate_stack_tiles(stack, floor, tile_grid, *, viewer_map=None, entity_pov=None) -> None:
    """Tag tiles with peek_through / stack_opening for client compositing."""
    base_floor = next((f for f in stack.floors if f.is_base), None)
    entity = entity_pov
    if isinstance(entity_pov, list):
        entity = entity_pov[0] if entity_pov else None
    ow, oh = floor.map.size
    for row in tile_grid:
        for tile in row:
            if not isinstance(tile, dict):
                continue
            x, y = tile.get('x'), tile.get('y')
            if x is None or y is None:
                continue
            if x < 0 or y < 0 or x >= ow or y >= oh:
                tile['stack_void'] = True
                continue
            wx, wy, _ = stack.local_to_world(floor.map_name, x, y)
            tile['world_x'] = wx
            tile['world_y'] = wy
            tile['layer_map'] = floor.map_name
            tile['stack_opening'] = stack.is_stack_opening(wx, wy)
            is_peek_candidate = _peek_candidate_at(stack, floor, x, y)
            tile['peek_through'] = False
            if (
                is_peek_candidate
                and tile.get('line_of_sight', True)
                and base_floor is not None
                and _viewer_can_peek_through(
                    stack, base_floor, floor, viewer_map, entity_pov, x, y,
                )
            ):
                tile['peek_through'] = True
            if tile['peek_through'] and base_floor is not None:
                peek_target = _peek_underlay_world_target(
                    stack, base_floor, floor, viewer_map, entity, x, y,
                )
                if peek_target is not None:
                    tile['descent_target_x'] = peek_target[0]
                    tile['descent_target_y'] = peek_target[1]
            tile['floor_mask'] = stack.floor_mask_blocks(wx, wy, 'up')
