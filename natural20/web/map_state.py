"""JSON map-state payload for the Three.js VTT client.

Builds a structured snapshot from a ``Map`` plus ``JsonRenderer`` tiles:
floor metadata, fog/light tiles, extruded-wall geometry, and visible tokens.
The 2D VTT continues to use HTML from ``GET /update``; this module is the
JSON twin used by ``GET /map_state``.
"""
from __future__ import annotations

from typing import Any, Iterable

from natural20.item_library.common import StoneWall, StoneWallDirectional
from natural20.item_library.door_object import DoorObject, DoorObjectWall
from natural20.item_library.trap_door import TrapDoor
from natural20.web.vtt3d_catalog import (
    DOOR_KINDS,
    HATCH_KINDS,
    load_vtt3d_catalog,
    resolve_vtt3d_model,
    resolve_vtt3d_walls,
)
from natural20.web.vtt3d_illumination import resolve_illumination

EDGE_NAMES = ('n', 'e', 's', 'w')

_DIRECTION_EDGES = {
    'stone_wall_t': ['n'],
    'stone_wall_tr': ['n', 'e'],
    'stone_wall_r': ['e'],
    'stone_wall_br': ['e', 's'],
    'stone_wall_b': ['s'],
    'stone_wall_bl': ['s', 'w'],
    'stone_wall_l': ['w'],
    'stone_wall_tl': ['n', 'w'],
    'stone_wall_tb': ['n', 's'],
    'stone_wall_lr': ['e', 'w'],
}

_SIZE_SQUARES = {
    'tiny': 1,
    'small': 1,
    'medium': 1,
    'large': 2,
    'huge': 3,
    'gargantuan': 4,
}


def jsonable(value: Any) -> Any:
    """Convert renderer/numpy values into JSON-serializable types."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    item = getattr(value, 'item', None)
    if callable(item):
        try:
            return jsonable(item())
        except Exception:
            pass
    if isinstance(value, bytes):
        return value.decode('utf-8', errors='replace')
    return str(value)


def flatten_tiles(tiles) -> list[dict]:
    """Flatten JsonRenderer's column-major 2D list into tile dicts with x/y."""
    if tiles is None:
        return []
    if isinstance(tiles, list) and tiles and isinstance(tiles[0], dict):
        return [jsonable(t) for t in tiles]
    flat = []
    for row in tiles or []:
        if isinstance(row, dict):
            flat.append(jsonable(row))
            continue
        for tile in row or []:
            if isinstance(tile, dict):
                flat.append(jsonable(tile))
    return flat


def _side_is_opaque_wall(border_flag, window_flag) -> bool:
    """True when this edge is a solid wall, not a window/opening.

    ``border`` marks a collision edge; ``window`` marks that the same edge
    does not block vision (stair wells, railings). Do not use ``passable``.
    """
    try:
        has_border = float(border_flag or 0) != 0.0
    except (TypeError, ValueError):
        has_border = bool(border_flag)
    if not has_border:
        return False
    try:
        is_window = float(window_flag or 0) != 0.0
    except (TypeError, ValueError):
        is_window = bool(window_flag)
    return not is_window


def _edges_from_border(border, window=None) -> list[str]:
    if not isinstance(border, (list, tuple)) or len(border) != 4:
        return []
    windows = window if isinstance(window, (list, tuple)) and len(window) == 4 else (0, 0, 0, 0)
    return [
        name
        for name, flag, win in zip(EDGE_NAMES, border, windows)
        if _side_is_opaque_wall(flag, win)
    ]


def _edges_from_door_pos(door_pos) -> list[str]:
    if door_pos is None:
        return ['n']
    if isinstance(door_pos, int):
        if 0 <= door_pos < 4:
            return [EDGE_NAMES[door_pos]]
        return ['n']
    if isinstance(door_pos, (list, tuple)) and len(door_pos) == 4:
        edges = _edges_from_border(door_pos)
        return edges or ['n']
    return ['n']


def _combo_wall_edges(obj, door_edges=None) -> list[str]:
    """Opaque wall edges on a door-wall that are not the door opening."""
    if not isinstance(obj, DoorObjectWall):
        return []
    door_set = set(door_edges or [])
    return [edge for edge in _edges_for_directional_wall(obj) if edge not in door_set]


def _add_edge_walls(edge_walls, index, x, y, edges) -> None:
    names = [edge for edge in edges or [] if edge in EDGE_NAMES]
    if not names:
        return
    key = (int(x), int(y))
    existing = index.get(key)
    if existing is None:
        entry = {'x': key[0], 'y': key[1], 'edges': list(dict.fromkeys(names))}
        edge_walls.append(entry)
        index[key] = entry
        return
    existing['edges'] = list(dict.fromkeys([*existing['edges'], *names]))


def _edges_for_directional_wall(obj) -> list[str]:
    border = getattr(obj, 'border', None)
    window = getattr(obj, 'window', None)
    if isinstance(border, (list, tuple)) and len(border) == 4:
        # Explicit border (including all-window stair wells) wins; do not
        # fall back to the type's default edges.
        return _edges_from_border(border, window)
    direction = getattr(obj, 'wall_direction', None) or (getattr(obj, 'properties', None) or {}).get('type')
    inferred = list(_DIRECTION_EDGES.get(str(direction or ''), []))
    if not inferred or not isinstance(window, (list, tuple)) or len(window) != 4:
        return inferred
    index = {name: i for i, name in enumerate(EDGE_NAMES)}
    return [name for name in inferred if _side_is_opaque_wall(1, window[index[name]])]


def _token_squares(size_name) -> int:
    if isinstance(size_name, int):
        return max(1, size_name)
    return _SIZE_SQUARES.get(str(size_name or 'medium').lower(), 1)


def build_map_geometry(battle_map, catalog=None) -> dict:
    """Derive solid-cell walls, thin edge walls, and doors from map objects."""
    width, height = battle_map.size
    solid = []
    solid_set = set()
    edge_walls = []
    edge_index = {}
    doors = []
    water = []
    water_set = set()
    models = catalog if catalog is not None else load_vtt3d_catalog(getattr(battle_map, 'session', None))

    def _add_solid(x, y):
        key = (int(x), int(y))
        if key in solid_set:
            return
        solid_set.add(key)
        solid.append([key[0], key[1]])

    def _add_water(x, y):
        key = (int(x), int(y))
        if key in water_set or key in solid_set:
            return
        water_set.add(key)
        water.append([key[0], key[1]])

    for x in range(int(width)):
        for y in range(int(height)):
            try:
                cell = battle_map.base_map[x][y]
            except Exception:
                cell = None
            if cell == '#':
                _add_solid(x, y)
            try:
                objects = battle_map.objects_at(x, y, reveal_concealed=True) or []
            except Exception:
                objects = []
            for obj in objects:
                if isinstance(obj, TrapDoor):
                    continue
                if isinstance(obj, DoorObject) or isinstance(obj, DoorObjectWall):
                    opened = False
                    try:
                        opened = bool(obj.opened())
                    except Exception:
                        opened = str(getattr(obj, 'state', '') or '').lower() in ('open', 'opened')
                    model = resolve_vtt3d_model(obj, models, role='door') or {'kind': 'door'}
                    kind = str(model.get('kind') or 'door').lower()
                    door_edges = _edges_from_door_pos(getattr(obj, 'door_pos', None))
                    wall_edges = _combo_wall_edges(obj, door_edges)
                    if kind == 'skip':
                        _add_edge_walls(edge_walls, edge_index, x, y, wall_edges)
                        continue
                    if kind == 'wall':
                        _add_edge_walls(edge_walls, edge_index, x, y, [*door_edges, *wall_edges])
                        continue
                    entry = {
                        'id': getattr(obj, 'entity_uid', None),
                        'x': x,
                        'y': y,
                        'edges': door_edges,
                        'open': opened,
                        'locked': bool(getattr(obj, 'locked', False)),
                        'kind': kind if (kind in DOOR_KINDS or model.get('src')) else 'door',
                    }
                    if kind == 'window':
                        entry['barred'] = bool(getattr(obj, 'barred', False))
                        entry['cover_pane'] = str(getattr(obj, 'cover_pane', None) or 'glass')
                        entry['window_material'] = str(getattr(obj, 'window_material', None) or 'wood')
                        entry['wall_material'] = str(getattr(obj, 'wall_material', None) or 'stone')
                    if model.get('double') is not None:
                        entry['double'] = bool(model['double'])
                    else:
                        props = getattr(obj, 'properties', None) or {}
                        vtt = props.get('vtt3d') if isinstance(props, dict) else None
                        if isinstance(vtt, dict) and vtt.get('double') is not None:
                            entry['double'] = bool(vtt['double'])
                    if model.get('src') or model.get('scale') is not None:
                        entry['model'] = model
                    doors.append(entry)
                    _add_edge_walls(edge_walls, edge_index, x, y, wall_edges)
                    continue
                if isinstance(obj, StoneWallDirectional):
                    edges = _edges_for_directional_wall(obj)
                    _add_edge_walls(edge_walls, edge_index, x, y, edges)
                    continue
                if isinstance(obj, StoneWall):
                    _add_solid(x, y)
                    continue
                obj_type = str(getattr(obj, 'type', None) or (getattr(obj, 'properties', None) or {}).get('type') or '').lower()
                if obj_type == 'water':
                    _add_water(x, y)

    return {
        'solid_walls': solid,
        'edge_walls': edge_walls,
        'doors': doors,
        'water': water,
    }


def entities_from_tiles(tiles: Iterable[dict], battle_map=None) -> list[dict]:
    """Visible creature tokens (origin square only) from renderer tiles."""
    entities = []
    for tile in tiles:
        token = tile.get('entity')
        uid = tile.get('id')
        if not token or not uid:
            continue
        entry = {
            'uid': uid,
            'x': int(tile.get('x', 0)),
            'y': int(tile.get('y', 0)),
            'token': token,
            'name': tile.get('name') or tile.get('label'),
            'size': _token_squares(tile.get('entity_size')),
            'size_name': tile.get('entity_size') or 'medium',
            'hp': tile.get('hp'),
            'max_hp': tile.get('max_hp'),
            'prone': bool(tile.get('prone')),
            'flying': bool(tile.get('is_flying') or tile.get('flying')),
            'hiding': bool(tile.get('hiding')),
            'dead': bool(tile.get('dead')),
            'unconscious': bool(tile.get('unconscious')),
            'effects': tile.get('effects') or [],
            'is_npc': bool(tile.get('is_npc')),
            'line_of_sight': bool(tile.get('line_of_sight', True)),
        }
        light = visual_light_from_entity(_lookup_map_entity(battle_map, uid)) if battle_map is not None else None
        if light is None:
            light = tile.get('light') if isinstance(tile.get('light'), dict) else None
        if light:
            entry['light'] = light
        entities.append(entry)
    return entities


_SKIP_OBJECT_TYPES = frozenset({
    'wooden_door', 'ground', 'water',
    'spawn_point', 'note', 'switch', 'window',
})
_CHEST_TYPES = frozenset({
    'chest', 'tavern_guest_chest', 'tavern_till_safe',
})
_BARREL_TYPES = frozenset({'barrel', 'crate', 'cask'})
_COVER_LEVELS = frozenset({'half', 'three_quarter', 'total'})
_LIGHT_OBJECT_KINDS = frozenset({'campfire', 'brazier', 'fireplace', 'torch', 'lamp'})


def _has_light_radii(obj: dict | None) -> bool:
    light = (obj or {}).get('light')
    if not isinstance(light, dict):
        return False
    try:
        return float(light.get('bright') or 0) > 0 or float(light.get('dim') or 0) > 0
    except (TypeError, ValueError):
        return False


def classify_object_kind(obj: dict, catalog: dict | None = None) -> str | None:
    """Pick a 3D mesh kind, or None to skip (doors/walls already extruded)."""
    if not obj:
        return None
    spec = resolve_vtt3d_model(obj, catalog, role='object')
    if spec:
        kind = str(spec.get('kind') or '').lower()
        if kind in DOOR_KINDS or kind in ('wall',):
            return None
        if kind == 'gltf' or spec.get('src'):
            return 'gltf'
        if kind in HATCH_KINDS:
            return kind
        if kind == 'stairs':
            return 'stairs'
        if kind and kind not in ('object', 'auto'):
            return kind
    if obj.get('door_highlight') or obj.get('secret_door_marker'):
        return None
    type_name = str(obj.get('type') or '').lower()
    name = str(obj.get('name') or obj.get('label') or '').lower()
    if type_name in ('stairs', 'stair'):
        return 'stairs'
    if type_name in ('chasm', 'bottomless_pit') or 'chasm' in type_name:
        return 'chasm'
    if (
        type_name in _SKIP_OBJECT_TYPES
        or type_name.startswith('stone_wall')
        or type_name.startswith('door_')
        or type_name.startswith('corner_door')
        or type_name.startswith('window_')
        or type_name.startswith('corner_window')
    ):
        return None
    if obj.get('teleporter_marker') or type_name == 'teleporter':
        return 'teleporter'
    if type_name in ('campfire',) or name in ('fire', 'campfire'):
        return 'campfire'
    if type_name == 'brazier' or 'brazier' in name:
        return 'brazier'
    if type_name == 'fireplace' or 'fireplace' in name:
        return 'fireplace'
    if type_name in ('torch', 'torch_mount', 'sconce', 'wall_torch') or 'torch' in name:
        return 'torch'
    has_light = _has_light_radii(obj)
    if obj.get('hide_map_token') and not has_light:
        return None
    if type_name in _CHEST_TYPES or 'chest' in type_name or 'chest' in name:
        return 'chest'
    if type_name in _BARREL_TYPES or 'barrel' in name:
        return 'barrel'
    if type_name == 'tree':
        return 'tree'
    if type_name == 'briar':
        return 'briar'
    cover = obj.get('cover')
    if cover in _COVER_LEVELS:
        return 'cover'
    if has_light or type_name in ('candle', 'lantern', 'hooded_lantern', 'bullseye_lantern', 'light_source'):
        return 'lamp'
    return None


def _lookup_map_entity(battle_map, uid):
    if not uid:
        return None
    session = getattr(battle_map, 'session', None)
    finder = getattr(session, 'entity_by_uid', None) if session is not None else None
    if callable(finder):
        found = finder(uid)
        if found is not None:
            return found
    for entity in getattr(battle_map, 'entities', None) or {}:
        if str(getattr(entity, 'entity_uid', None)) == str(uid):
            return entity
    return None


def visual_light_from_entity(entity) -> dict | None:
    """Read-only snapshot of ``entity.light_properties()`` for 3D lamps."""
    if entity is None:
        return None
    try:
        lp = entity.light_properties()
    except Exception:
        return None
    if not isinstance(lp, dict):
        return None
    try:
        bright = float(lp.get('bright') or 0)
        dim = float(lp.get('dim') or 0)
    except (TypeError, ValueError):
        return None
    if bright <= 0 and dim <= 0:
        return None
    origin = 'item'
    try:
        if callable(getattr(entity, 'has_effect', None)) and entity.has_effect('light_override'):
            origin = 'effect'
    except Exception:
        origin = 'item'
    color = None
    try:
        for entry in entity.current_effects() or []:
            effect = entry.get('effect') if isinstance(entry, dict) else None
            value = getattr(effect, 'color', None)
            if value:
                color = str(value)
                break
    except Exception:
        color = None
    payload = {
        'bright': bright,
        'dim': dim,
        'origin': origin,
        'lit': True,
    }
    if color:
        payload['color'] = color
    return payload


def nearest_wall_edge(x, y, geometry: dict | None) -> str | None:
    """Edge of cell (x,y) that sits against a wall — used to hang a 3D torch."""
    geom = geometry or {}
    solid = {(int(cell[0]), int(cell[1])) for cell in (geom.get('solid_walls') or [])}
    neighbors = (('n', x, y - 1), ('s', x, y + 1), ('e', x + 1, y), ('w', x - 1, y))
    for edge, nx, ny in neighbors:
        if (nx, ny) in solid:
            return edge
    for wall in geom.get('edge_walls') or []:
        if int(wall.get('x', -1)) == int(x) and int(wall.get('y', -1)) == int(y):
            edges = wall.get('edges') or []
            if edges:
                return edges[0]
    opposite = {'n': 's', 's': 'n', 'e': 'w', 'w': 'e'}
    by_cell = {
        (int(wall.get('x', -1)), int(wall.get('y', -1))): wall.get('edges') or []
        for wall in (geom.get('edge_walls') or [])
    }
    for edge, nx, ny in neighbors:
        if opposite[edge] in by_cell.get((nx, ny), []):
            return edge
    return None


def visual_lights_from_map(battle_map, geometry=None, occupied=None) -> list[dict]:
    """YAML ``map.light`` / ``lights`` lamp positions for 3D only.

    Does not write to ``Map.light_at`` or the game illumination grid.
    Skips solid walls, occupied fixtures, and water terrain cells.
    """
    props = getattr(battle_map, 'properties', None) or {}
    catalog = props.get('lights') or {}
    light_rows = (props.get('map') or {}).get('light') or []
    solid = {(int(cell[0]), int(cell[1])) for cell in ((geometry or {}).get('solid_walls') or [])}
    water = {(int(cell[0]), int(cell[1])) for cell in ((geometry or {}).get('water') or [])}
    busy = occupied or set()
    lamps = []
    for y, row in enumerate(light_rows):
        for x, key in enumerate(row or ''):
            if not key or key in '. ':
                continue
            if (x, y) in solid or (x, y) in busy or (x, y) in water:
                continue
            spec = catalog.get(key) or {}
            lamps.append({
                'x': x,
                'y': y,
                'kind': 'torch',
                'lit': True,
                'bright': float(spec.get('bright') or 10),
                'dim': float(spec.get('dim') or 5),
                'edge': nearest_wall_edge(x, y, geometry),
            })
    return lamps


def objects_from_tiles(tiles: Iterable[dict], catalog: dict | None = None) -> list[dict]:
    """Non-wall fixtures visible on tiles (chests, furniture, markers)."""
    seen = set()
    result = []
    for tile in tiles:
        x = int(tile.get('x', 0))
        y = int(tile.get('y', 0))
        for obj in tile.get('objects') or []:
            oid = obj.get('id')
            key = oid or (x, y, obj.get('name'), obj.get('image'))
            if key in seen:
                continue
            seen.add(key)
            kind = classify_object_kind(obj, catalog)
            notes = obj.get('notes') or []
            quick = obj.get('quick_interact') or []
            if not kind and not notes and not quick:
                continue
            entry = {
                'id': oid,
                'x': x,
                'y': y,
                'name': obj.get('name') or obj.get('label'),
                'image': obj.get('image'),
                'type': obj.get('type'),
                'kind': kind,
                'opened': bool(obj.get('opened')),
                'locked': bool(obj.get('locked')),
                'cover': obj.get('cover'),
                'facing': obj.get('facing'),
                'lit': obj.get('lit'),
                'light': obj.get('light'),
                'teleporter_marker': bool(obj.get('teleporter_marker')),
                'teleporter_marker_color': obj.get('teleporter_marker_color'),
                'activated': bool(obj.get('activated')),
                'disarmed': bool(obj.get('disarmed')),
                'concealed': bool(obj.get('concealed')),
                'secret': bool(obj.get('secret')),
                'notes': notes,
                'quick_interact': quick,
                'quick_interact_layout': obj.get('quick_interact_layout'),
                'quick_interact_anchor': obj.get('quick_interact_anchor'),
            }
            spec = resolve_vtt3d_model(obj, catalog, role='object')
            if spec and spec.get('src'):
                entry['model'] = spec
            if kind == 'stairs':
                squares = obj.get('squares')
                if not isinstance(squares, list) or not squares:
                    squares = [[x, y]]
                cleaned = []
                stair_seen: set[tuple[int, int]] = set()
                for item in squares:
                    if not isinstance(item, (list, tuple)) or len(item) < 2:
                        continue
                    try:
                        pt = [int(item[0]), int(item[1])]
                    except (TypeError, ValueError):
                        continue
                    key_pt = (pt[0], pt[1])
                    if key_pt in stair_seen:
                        continue
                    stair_seen.add(key_pt)
                    cleaned.append(pt)
                entry['squares'] = cleaned or [[x, y]]
                try:
                    entry['height'] = float(obj.get('height'))
                except (TypeError, ValueError):
                    entry['height'] = 8.0
                style = str(obj.get('style') or '').strip().lower()
                if style:
                    entry['style'] = style
                raw_solid = obj.get('solid')
                entry['solid'] = True if raw_solid is None else bool(raw_solid)
                for flag in ('open_well', 'wall_attached'):
                    raw_flag = obj.get(flag)
                    if raw_flag is None and spec:
                        raw_flag = spec.get(flag)
                    if raw_flag is not None:
                        entry[flag] = bool(raw_flag)
            if kind == 'chasm':
                try:
                    entry['fall_distance'] = float(obj.get('fall_distance'))
                except (TypeError, ValueError):
                    pass
            result.append(entry)
    return result


def _asset_url(path: str | None) -> str | None:
    if not path:
        return None
    text = str(path).lstrip('/')
    if text.startswith('http://') or text.startswith('https://'):
        return str(path)
    if text.startswith('assets/'):
        return f'/{text}'
    return f'/assets/{text}'


def map_visual_effects(battle_map) -> list[dict]:
    """YAML ``default_effect`` / ``default_effects`` for the 3D weather layer."""
    props = getattr(battle_map, 'properties', None) or {}
    defs = []
    extra = props.get('default_effects')
    if isinstance(extra, (list, tuple)):
        defs.extend(extra)
    raw = props.get('default_effect')
    if isinstance(raw, (list, tuple)):
        defs.extend(raw)
    elif isinstance(raw, dict):
        defs.append(raw)
    payloads = []
    for item in defs:
        if not isinstance(item, dict) or not item.get('effect'):
            continue
        payload = jsonable(item)
        payload.setdefault('action', 'start')
        payload.setdefault('exclusive', False)
        payloads.append(payload)
    return payloads


def build_map_state(
    battle_map,
    tiles,
    *,
    background: str | None = None,
    display_name: str | None = None,
) -> dict:
    """Assemble the ``GET /map_state`` payload."""
    flat_tiles = flatten_tiles(tiles)
    width, height = battle_map.size
    lighting = resolve_illumination(battle_map)
    bg = background
    if not bg:
        filename = battle_map.background_image()
        if filename:
            bg = f'maps/{filename}'
    offset = battle_map.image_offset_px or [0, 0]
    try:
        offset = [int(offset[0]), int(offset[1])]
    except Exception:
        offset = [0, 0]
    catalog = load_vtt3d_catalog(getattr(battle_map, 'session', None))
    geometry = build_map_geometry(battle_map, catalog)
    walls = resolve_vtt3d_walls(battle_map)
    if walls.get('albedo'):
        walls = dict(walls)
        walls['albedo'] = _asset_url(walls['albedo'])
    objects = objects_from_tiles(flat_tiles, catalog)
    for obj in objects:
        if obj.get('kind') in ('torch', 'fireplace'):
            obj['edge'] = nearest_wall_edge(int(obj['x']), int(obj['y']), geometry)
    occupied = {
        (int(obj['x']), int(obj['y']))
        for obj in objects
        if obj.get('kind') in _LIGHT_OBJECT_KINDS
    }
    lights = visual_lights_from_map(battle_map, geometry, occupied)
    return jsonable({
        'map': {
            'name': display_name or getattr(battle_map, 'name', None),
            'size': [int(width), int(height)],
            'feet_per_grid': int(getattr(battle_map, 'feet_per_grid', 5) or 5),
            'background': _asset_url(bg),
            'image_offset_px': offset,
            'illumination': lighting['illumination'],
            'illumination_default': lighting['illumination_default'],
            'illumination_overridden': lighting['illumination_overridden'],
            'walls': walls,
        },
        'tiles': flat_tiles,
        'geometry': geometry,
        'entities': entities_from_tiles(flat_tiles, battle_map),
        'objects': objects,
        'lights': lights,
        'effects': map_visual_effects(battle_map),
    })
