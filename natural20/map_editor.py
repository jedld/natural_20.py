"""Read/write campaign map YAML for in-browser edit mode."""

from __future__ import annotations

import copy
import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

from natural20.map_annotations import (
    annotation_by_id,
    annotation_label_anchor,
    delete_map_annotation,
    list_map_annotations,
    normalize_annotation,
    translate_annotation,
    upsert_map_annotation,
)
from natural20.yaml_loader import load_yaml

_FILLER_CHARS = {".", " ", None, ""}
_WALL_HINTS = ("wall", "stone_wall")
_DOOR_HINTS = ("door",)
_TELEPORTER_HINTS = ("teleporter",)
_TERRAIN_OVERLAY_TYPES = frozenset({"water", "difficult_terrain", "briar", "ground"})
_LAYER_GRID_KEYS = frozenset({"base", "base_1", "base_2", "meta"})
_LAYER_GRID_ATTR = {
    "base": "base_map",
    "base_1": "base_map_1",
    "base_2": "base_map_2",
}


def resolve_map_yaml_path(session, map_name: str) -> Path:
    maps = (session.game_properties or {}).get("maps") or {}
    rel = maps.get(map_name)
    if not rel:
        raise KeyError(f"Unknown map: {map_name}")
    path = Path(session.root_path) / f"{rel}.yml"
    if not path.is_file():
        path = Path(session.root_path) / rel
    if not path.is_file():
        raise FileNotFoundError(f"Map YAML not found for {map_name}: {path}")
    return path


def load_map_document(path: Path | str) -> dict[str, Any]:
    path = Path(path)
    return load_yaml(path, campaign_root=path.parent.parent) or {}


def save_map_document(path: Path | str, data: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _legend_for(data: dict[str, Any]) -> dict[str, Any]:
    return data.get("legend") or {}


def _map_block(data: dict[str, Any]) -> dict[str, Any]:
    block = data.setdefault("map", {})
    if not isinstance(block, dict):
        raise ValueError("map key must be a mapping")
    return block


def _map_dimensions(map_block: dict[str, Any]) -> tuple[int, int]:
    size = map_block.get("size")
    if isinstance(size, (list, tuple)) and len(size) >= 2:
        return int(size[0]), int(size[1])
    for key in ("base", "base_1", "base_2", "meta"):
        rows = map_block.get(key) or []
        if rows:
            return len(rows[0]), len(rows)
    return 16, 16


def _filler_char_for_layer(layer: str) -> str:
    return "."


def _layer_placements_list(map_block: dict[str, Any]) -> list[dict[str, Any]]:
    placements = map_block.setdefault("layer_placements", [])
    if not isinstance(placements, list):
        raise ValueError("map.layer_placements must be a list")
    return placements


def _slug_for_placement_id(value: str) -> str:
    cleaned = []
    for ch in str(value or "item").lower():
        if ch.isalnum():
            cleaned.append(ch)
        elif cleaned and cleaned[-1] != "_":
            cleaned.append("_")
    slug = "".join(cleaned).strip("_")
    return slug[:40] or "item"


def _new_placement_id(
    layer: str,
    token: str,
    x: int,
    y: int,
    *,
    object_type: str | None = None,
    existing_ids: set[str] | None = None,
) -> str:
    base = object_type or _slug_for_placement_id(token)
    candidate = f"lp_{layer}_{base}_{int(x)}_{int(y)}"
    if not existing_ids or candidate not in existing_ids:
        return candidate
    suffix = 2
    while f"{candidate}_{suffix}" in existing_ids:
        suffix += 1
    return f"{candidate}_{suffix}"


def _ensure_layer_grid(map_block: dict[str, Any], layer: str) -> list[str]:
    if layer not in _LAYER_GRID_KEYS:
        raise ValueError(f"Unsupported layer: {layer}")
    width, height = _map_dimensions(map_block)
    rows = map_block.get(layer)
    filler = _filler_char_for_layer(layer)
    if not rows:
        if layer == "base":
            rows = ["#" * width for _ in range(height)]
            if height >= 2:
                rows[1] = "#" + ("." * (width - 2)) + "#"
        else:
            rows = [filler * width for _ in range(height)]
        map_block[layer] = rows
        return rows
    normalized: list[str] = []
    for row in rows:
        text = str(row)
        if len(text) < width:
            text = text + (filler * (width - len(text)))
        normalized.append(text[:width])
    while len(normalized) < height:
        normalized.append(filler * width)
    map_block[layer] = normalized
    return normalized


def _write_layer_grid_cell(
    map_block: dict[str, Any],
    layer: str,
    x: int,
    y: int,
    token: str,
) -> None:
    grid = _ensure_layer_grid(map_block, layer)
    row_chars = list(grid[int(y)])
    row_chars[int(x)] = str(token)
    grid[int(y)] = "".join(row_chars)


def _clear_layer_grid_cell(
    map_block: dict[str, Any],
    layer: str,
    x: int,
    y: int,
    *,
    expected_token: str | None = None,
) -> None:
    grid = map_block.get(layer)
    if not grid or int(y) >= len(grid) or int(x) >= len(grid[int(y)]):
        return
    row_chars = list(grid[int(y)])
    if expected_token is not None and row_chars[int(x)] != expected_token:
        return
    row_chars[int(x)] = _filler_char_for_layer(layer)
    grid[int(y)] = "".join(row_chars)


def materialize_layer_placement(map_block: dict[str, Any], entry: dict[str, Any]) -> None:
    layer = str(entry.get("layer") or "base_1")
    token = entry.get("token")
    pos = entry.get("pos")
    if token is None or pos is None or len(pos) < 2:
        return
    _write_layer_grid_cell(map_block, layer, int(pos[0]), int(pos[1]), str(token))


def materialize_all_layer_placements(map_block: dict[str, Any]) -> None:
    for entry in map_block.get("layer_placements") or []:
        if isinstance(entry, dict):
            materialize_layer_placement(map_block, entry)


def _find_layer_placement(
    placements: list,
    *,
    placement_id: str | None = None,
    layer: str | None = None,
    x: int | None = None,
    y: int | None = None,
) -> dict[str, Any] | None:
    for entry in placements:
        if not isinstance(entry, dict):
            continue
        if placement_id and str(entry.get("id") or "") == placement_id:
            return entry
        if layer is not None and x is not None and y is not None:
            pos = entry.get("pos") or []
            if (
                str(entry.get("layer") or "") == str(layer)
                and len(pos) >= 2
                and int(pos[0]) == int(x)
                and int(pos[1]) == int(y)
            ):
                return entry
    return None


def _layer_placement_cells(map_block: dict[str, Any]) -> set[tuple[str, int, int]]:
    cells: set[tuple[str, int, int]] = set()
    for entry in map_block.get("layer_placements") or []:
        if not isinstance(entry, dict):
            continue
        pos = entry.get("pos") or []
        if len(pos) < 2:
            continue
        cells.add((str(entry.get("layer") or "base_1"), int(pos[0]), int(pos[1])))
    return cells


def _overlay_item_from_layer_placement(
    entry: dict[str, Any],
    *,
    index: int,
    legend: dict[str, Any],
) -> dict[str, Any]:
    token = str(entry.get("token") or "")
    pos = entry.get("pos") or [0, 0]
    layer = str(entry.get("layer") or "base_1")
    leg = {**dict(legend.get(token) or {}), **{k: v for k, v in entry.items() if k not in {"id", "token", "pos", "layer"}}}
    type_name = leg.get("type")
    category = _categorize_type(type_name)
    label = leg.get("label") or leg.get("name") or token or entry.get("id") or f"placement:{index}"
    placement_id = str(entry.get("id") or f"layer_placements:{index}")
    if layer == "meta" and type_name == "npc":
        kind = "entity"
        category = "npc"
    elif layer == "meta":
        kind = "meta"
    else:
        kind = "terrain"
    item = {
        "id": placement_id,
        "kind": kind,
        "token": token,
        "layer": layer,
        "x": int(pos[0]),
        "y": int(pos[1]),
        "label": str(label),
        "category": category,
        "source": "layer_placements",
        "index": index,
        "object_type": str(type_name) if type_name else None,
        "editable": True,
    }
    _attach_fixture_edges(item, leg, type_name)
    return item


def _entry_uid(token: str, entry: dict[str, Any], legend: dict[str, Any]) -> str | None:
    leg = legend.get(token) or {}
    overrides = entry.get("overrides") or leg.get("overrides") or {}
    if isinstance(overrides, dict) and overrides.get("entity_uid"):
        return str(overrides["entity_uid"])
    for key in ("entity_uid",):
        if entry.get(key):
            return str(entry[key])
        if leg.get(key):
            return str(leg[key])
    return None


def _categorize_type(type_name: str | None) -> str:
    lowered = str(type_name or "").lower()
    if any(hint in lowered for hint in _TELEPORTER_HINTS):
        return "teleporter"
    if any(hint in lowered for hint in _DOOR_HINTS):
        return "door"
    if any(hint in lowered for hint in _WALL_HINTS):
        return "wall"
    return "object"


_WALL_SIDES = ("top", "right", "bottom", "left")
_WALL_SUFFIX_ALIASES = {
    "lt": "tl",
    "rt": "tr",
    "lb": "bl",
    "rb": "br",
}
_BORDER_BY_WALL_SUFFIX = {
    "tl": [1, 0, 0, 1],
    "t": [1, 0, 0, 0],
    "tr": [1, 1, 0, 0],
    "r": [0, 1, 0, 0],
    "br": [0, 1, 1, 0],
    "b": [0, 0, 1, 0],
    "bl": [0, 0, 1, 1],
    "l": [0, 0, 0, 1],
    "tb": [1, 0, 1, 0],
    "lr": [0, 1, 0, 1],
}
_DOOR_SUFFIX_TO_INDEX = {
    "t": 0,
    "top": 0,
    "r": 1,
    "right": 1,
    "b": 2,
    "bottom": 2,
    "l": 3,
    "left": 3,
}
_CORNER_DOOR_PRESETS = {
    "corner_door_tl": {"door_pos": 0, "border": [0, 0, 0, 1]},
    "corner_door_tr": {"door_pos": 3, "border": [1, 0, 0, 0]},
    "corner_door_bl": {"door_pos": 1, "border": [1, 0, 0, 0]},
    "corner_door_br": {"door_pos": 3, "border": [0, 0, 1, 0]},
}


def _fixture_leg_for_edges(leg: dict[str, Any], type_name: str | None) -> dict[str, Any]:
    type_key = str(type_name or leg.get("type") or "")
    preset = _CORNER_DOOR_PRESETS.get(type_key)
    if not preset:
        return leg
    merged = dict(leg)
    merged.setdefault("item_class", "DoorObjectWall")
    merged.setdefault("door_pos", preset["door_pos"])
    merged.setdefault("border", preset["border"])
    return merged


def _border_list_to_edges(border: list[int]) -> dict[str, bool]:
    return {side: bool(border[idx]) for idx, side in enumerate(_WALL_SIDES)}


def _normalize_wall_suffix(type_name: str | None) -> str | None:
    lowered = str(type_name or "").lower()
    if not lowered:
        return None
    if lowered in ("stone_wall", "barrier") or lowered.endswith("_wall") and lowered.count("_") == 1:
        return "full"
    prefix = "stone_wall_"
    if not lowered.startswith(prefix):
        return None
    suffix = lowered[len(prefix) :]
    suffix = _WALL_SUFFIX_ALIASES.get(suffix, suffix)
    return suffix


def _resolve_wall_border_list(type_name: str | None, leg: dict[str, Any]) -> list[int] | None:
    border = leg.get("border")
    if isinstance(border, (list, tuple)) and len(border) >= 4:
        return [int(bool(x)) for x in border[:4]]

    item_class = str(leg.get("item_class") or "")
    type_key = str(type_name or leg.get("type") or "")
    suffix = _normalize_wall_suffix(type_key)

    if item_class == "StoneWall" or suffix == "full":
        return [1, 1, 1, 1]

    if suffix and suffix in _BORDER_BY_WALL_SUFFIX:
        return list(_BORDER_BY_WALL_SUFFIX[suffix])

    if item_class == "StoneWallDirectional":
        return [0, 0, 0, 0]

    if leg.get("wall") or _categorize_type(type_key) == "wall":
        return [1, 1, 1, 1]

    return None


def _door_pos_to_edges(door_pos: Any) -> dict[str, bool] | None:
    if door_pos is None:
        return None
    if isinstance(door_pos, (list, tuple)):
        if len(door_pos) < 4:
            return None
        edges = _border_list_to_edges([int(bool(x)) for x in door_pos[:4]])
        return edges if any(edges.values()) else None
    try:
        index = int(door_pos)
    except (TypeError, ValueError):
        return None
    if index < 0 or index >= len(_WALL_SIDES):
        return None
    edges = {side: False for side in _WALL_SIDES}
    edges[_WALL_SIDES[index]] = True
    return edges


def _infer_door_pos_from_type(type_name: str | None) -> int | None:
    lowered = str(type_name or "").lower()
    if "door" not in lowered:
        return None
    for suffix, index in _DOOR_SUFFIX_TO_INDEX.items():
        if lowered.endswith(f"_{suffix}"):
            return index
    return None


def _resolve_door_edges(type_name: str | None, leg: dict[str, Any]) -> dict[str, bool] | None:
    item_class = str(leg.get("item_class") or "")
    type_key = str(type_name or leg.get("type") or "")
    is_door_wall = item_class == "DoorObjectWall"
    is_door = is_door_wall or item_class == "DoorObject" or _categorize_type(type_key) == "door"
    if not is_door:
        return None

    door_pos = leg.get("door_pos")
    if door_pos is None:
        door_pos = _infer_door_pos_from_type(type_key)

    if is_door_wall or door_pos is not None:
        edges = _door_pos_to_edges(door_pos)
        if edges:
            return edges

    return {side: True for side in _WALL_SIDES}


def _attach_fixture_edges(entry: dict[str, Any], leg: dict[str, Any], type_name: str | None) -> None:
    resolved_leg = _fixture_leg_for_edges(leg, type_name)
    border = _resolve_wall_border_list(type_name, resolved_leg)
    if border and any(border):
        entry["wall_edges"] = _border_list_to_edges(border)

    door_edges = _resolve_door_edges(type_name, resolved_leg)
    if door_edges:
        entry["door_edges"] = door_edges


def _token_category(token: str, legend: dict[str, Any]) -> str:
    leg = legend.get(token) or {}
    return _categorize_type(leg.get("type"))


def _is_filler_char(ch: str | None) -> bool:
    return ch in _FILLER_CHARS


def _should_preserve_destination_cell(dest_ch: str, *, moving_category: str, legend: dict[str, Any]) -> bool:
    if _is_filler_char(dest_ch):
        return False
    if moving_category == "wall":
        return False
    if dest_ch == "#":
        return True
    if dest_ch in legend:
        return True
    return True


def _clear_terrain_source_cell(grid: list[str], x: int, y: int, token: str) -> None:
    row_chars = list(grid[y])
    if row_chars[x] != token:
        return
    row_chars[x] = "."
    grid[y] = "".join(row_chars)


def _upsert_entity_placement(
    map_block: dict[str, Any],
    token: str,
    x: int,
    y: int,
    *,
    layer: str = "object",
) -> None:
    entities = map_block.setdefault("entities", [])
    for entry in entities:
        if not isinstance(entry, dict):
            continue
        if entry.get("token") == token and entry.get("layer", "object") == layer:
            entry["pos"] = [int(x), int(y)]
            return
    entities.append({"token": token, "pos": [int(x), int(y)], "layer": layer})


def _resolve_entity_entry_index(
    entities: list,
    legend: dict[str, Any],
    *,
    item_id: str,
    index: int | None = None,
    token: str | None = None,
    from_x: int | None = None,
    from_y: int | None = None,
) -> int | None:
    """Resolve a map.entities[] row index for edit-mode moves."""
    if index is not None:
        if 0 <= index < len(entities):
            return index
        return None

    if isinstance(item_id, str) and item_id.startswith("entities:"):
        try:
            parsed = int(item_id.split(":", 1)[1])
        except (ValueError, IndexError):
            parsed = None
        if parsed is not None and 0 <= parsed < len(entities):
            return parsed

    for i, entry in enumerate(entities):
        if not isinstance(entry, dict):
            continue
        tok = entry.get("token")
        if _entry_uid(str(tok or ""), entry, legend) == item_id:
            return i

    if token is not None and from_x is not None and from_y is not None:
        for i, entry in enumerate(entities):
            if not isinstance(entry, dict):
                continue
            if str(entry.get("token") or "") != str(token):
                continue
            pos = entry.get("pos") or []
            if len(pos) >= 2 and int(pos[0]) == int(from_x) and int(pos[1]) == int(from_y):
                return i

    return None


def enrich_edit_overlay_with_runtime_uids(battle_map, overlay: dict[str, Any]) -> dict[str, Any]:
    """Attach live entity UIDs so draggable tokens map back to YAML entity rows."""
    if battle_map is None:
        return overlay

    entities_by_pos: dict[tuple[int, int], list[Any]] = {}
    for entity, pos in (getattr(battle_map, "entities", None) or {}).items():
        if not pos or len(pos) < 2:
            continue
        key = (int(pos[0]), int(pos[1]))
        entities_by_pos.setdefault(key, []).append(entity)

    for item in overlay.get("items") or []:
        if item.get("source") != "entities" or item.get("kind") != "entity":
            continue
        try:
            pos_key = (int(item["x"]), int(item["y"]))
        except (TypeError, ValueError, KeyError):
            continue
        candidates = entities_by_pos.get(pos_key) or []
        if not candidates:
            continue
        uid = getattr(candidates[0], "entity_uid", None)
        if uid:
            item["runtime_uid"] = str(uid)

    return overlay


def build_edit_overlay(map_properties: dict[str, Any]) -> dict[str, Any]:
    """Return editable placements and terrain markers for the client overlay."""
    legend = _legend_for(map_properties)
    map_block = map_properties.get("map") or {}
    items: list[dict[str, Any]] = []
    terrain: list[dict[str, Any]] = []

    for index, entry in enumerate(map_block.get("entities") or []):
        if not isinstance(entry, dict):
            continue
        token = entry.get("token")
        pos = entry.get("pos")
        if token is None or pos is None:
            continue
        leg = legend.get(token) or {}
        merged = {**leg, **{k: v for k, v in entry.items() if k not in {"token", "pos", "layer"}}}
        type_name = leg.get("type") or merged.get("type")
        layer = entry.get("layer")
        if type_name == "npc" and layer != "object":
            kind = "entity"
        else:
            kind = "object"
        uid = _entry_uid(str(token), entry, legend) or f"entities:{index}"
        label = (
            (merged.get("overrides") or {}).get("label")
            if isinstance(merged.get("overrides"), dict)
            else None
        ) or merged.get("label") or merged.get("name") or str(token)
        item = {
            "id": uid,
            "kind": kind,
            "token": str(token),
            "x": int(pos[0]),
            "y": int(pos[1]),
            "label": str(label),
            "category": _categorize_type(type_name),
            "source": "entities",
            "index": index,
            "object_type": str(type_name) if type_name else None,
        }
        _attach_fixture_edges(item, merged, type_name)
        items.append(item)

    for index, raw in enumerate(map_properties.get("player_spawn_points") or []):
        if isinstance(raw, dict):
            pos = raw.get("position")
            label = raw.get("name") or f"Spawn {index + 1}"
            group = raw.get("group")
        else:
            pos = raw
            label = f"Spawn {index + 1}"
            group = None
        if not pos:
            continue
        items.append(
            {
                "id": f"spawn:{index}",
                "kind": "spawn_point",
                "x": int(pos[0]),
                "y": int(pos[1]),
                "label": str(label),
                "category": "spawn_point",
                "source": "player_spawn_points",
                "index": index,
                "group": group,
                "object_type": "spawn_point",
            }
        )

    placement_cells = _layer_placement_cells(map_block)
    for index, entry in enumerate(map_block.get("layer_placements") or []):
        if not isinstance(entry, dict):
            continue
        placement_item = _overlay_item_from_layer_placement(entry, index=index, legend=legend)
        if placement_item.get("kind") == "terrain":
            terrain.append(placement_item)
        else:
            items.append(placement_item)

    meta_rows = map_block.get("meta") or []
    for y, row in enumerate(meta_rows):
        for x, ch in enumerate(row):
            if ch in _FILLER_CHARS:
                continue
            if ("meta", int(x), int(y)) in placement_cells:
                continue
            leg = legend.get(ch) or {}
            type_name = leg.get("type")
            uid = _entry_uid(str(ch), {}, legend) or f"meta:{ch}:{x}:{y}"
            label = (leg.get("overrides") or {}).get("label") if isinstance(leg.get("overrides"), dict) else None
            label = label or leg.get("label") or leg.get("name") or str(ch)
            kind = "meta"
            category = _categorize_type(type_name)
            if type_name == "npc":
                kind = "entity"
                category = "npc"
            item = {
                "id": uid,
                "kind": kind,
                "token": str(ch),
                "x": int(x),
                "y": int(y),
                "label": str(label),
                "category": category,
                "source": "meta",
                "object_type": str(type_name) if type_name else None,
            }
            _attach_fixture_edges(item, leg, type_name)
            items.append(item)

    for layer_name in ("base", "base_1", "base_2"):
        grid = map_block.get(layer_name) or []
        for y, row in enumerate(grid):
            for x, ch in enumerate(row):
                if ch in _FILLER_CHARS or ch == "#":
                    continue
                if (layer_name, int(x), int(y)) in placement_cells:
                    continue
                leg = legend.get(ch)
                if not leg:
                    continue
                type_name = leg.get("type")
                category = _categorize_type(type_name)
                if category == "object" and type_name not in _DOOR_HINTS and "wall" not in str(type_name).lower():
                    if type_name not in _TERRAIN_OVERLAY_TYPES:
                        continue
                label = leg.get("label") or leg.get("name") or str(ch)
                terrain_item = {
                    "id": f"terrain:{layer_name}:{x}:{y}",
                    "kind": "terrain",
                    "token": str(ch),
                    "layer": layer_name,
                    "x": int(x),
                    "y": int(y),
                    "label": str(label),
                    "category": category,
                    "object_type": str(type_name) if type_name else None,
                }
                _attach_fixture_edges(terrain_item, leg, type_name)
                terrain.append(terrain_item)

    return {"items": items, "terrain": terrain, "annotations": _annotations_for_overlay(map_properties)}


def _annotations_for_overlay(map_properties: dict[str, Any]) -> list[dict[str, Any]]:
    overlay_items: list[dict[str, Any]] = []
    for entry in list_map_annotations(map_properties):
        item = dict(entry)
        item['source'] = 'map_annotations'
        overlay_items.append(item)
    return overlay_items


def list_map_annotation_documents(session, map_name: str) -> list[dict[str, Any]]:
    path = resolve_map_yaml_path(session, map_name)
    data = load_map_document(path)
    return list_map_annotations(data)


def save_map_annotation(session, map_name: str, annotation: dict[str, Any]) -> dict[str, Any]:
    path = resolve_map_yaml_path(session, map_name)
    normalized = normalize_annotation(annotation)
    data = upsert_map_annotation(load_map_document(path), normalized)
    save_map_document(path, data)
    return annotation_by_id(data, normalized['id']) or normalized


def remove_map_annotation(session, map_name: str, annotation_id: str) -> dict[str, Any]:
    path = resolve_map_yaml_path(session, map_name)
    data = delete_map_annotation(load_map_document(path), annotation_id)
    save_map_document(path, data)
    return data


def move_map_annotation(session, map_name: str, annotation_id: str, x: int, y: int) -> dict[str, Any]:
    path = resolve_map_yaml_path(session, map_name)
    data = load_map_document(path)
    existing = annotation_by_id(data, annotation_id)
    if existing is None:
        raise KeyError(f'annotation not found: {annotation_id}')

    anchor = annotation_label_anchor(existing)
    if anchor is None:
        raise ValueError(f'annotation {annotation_id} cannot be moved')

    dx = int(x) - int(anchor[0])
    dy = int(y) - int(anchor[1])
    if dx == 0 and dy == 0:
        return existing

    moved = translate_annotation(existing, dx, dy)
    data = upsert_map_annotation(data, moved)
    save_map_document(path, data)
    return annotation_by_id(data, moved['id']) or moved


def move_map_item(
    session,
    map_name: str,
    *,
    item_id: str,
    kind: str,
    x: int,
    y: int,
    token: str | None = None,
    layer: str | None = None,
    source: str | None = None,
    index: int | None = None,
    from_x: int | None = None,
    from_y: int | None = None,
) -> dict[str, Any]:
    """Move one editable map item and persist to the campaign YAML file."""
    path = resolve_map_yaml_path(session, map_name)
    data = copy.deepcopy(load_map_document(path))
    map_block = _map_block(data)
    legend = _legend_for(data)

    if kind in {"entity", "object"} and (source == "entities" or source is None):
        entities = map_block.setdefault("entities", [])
        target_idx = _resolve_entity_entry_index(
            entities,
            legend,
            item_id=item_id,
            index=index,
            token=token,
            from_x=from_x,
            from_y=from_y,
        )
        if target_idx is None:
            raise KeyError(f"Entity entry not found: {item_id}")
        entities[target_idx]["pos"] = [int(x), int(y)]
    elif kind == "spawn_point":
        slots = data.setdefault("player_spawn_points", [])
        target_idx = index
        if target_idx is None and item_id.startswith("spawn:"):
            target_idx = int(item_id.split(":", 1)[1])
        if target_idx is None or target_idx < 0 or target_idx >= len(slots):
            raise KeyError(f"Spawn point not found: {item_id}")
        entry = slots[target_idx]
        if isinstance(entry, dict):
            entry["position"] = [int(x), int(y)]
        else:
            slots[target_idx] = [int(x), int(y)]
    elif kind in {"entity", "meta"} and source == "meta":
        meta_rows = map_block.setdefault("meta", [])
        if not meta_rows:
            raise KeyError("meta layer missing")
        move_char = token
        if not move_char:
            for row in meta_rows:
                for cell in row:
                    if cell not in _FILLER_CHARS:
                        leg = legend.get(cell) or {}
                        if _entry_uid(str(cell), {}, legend) == item_id:
                            move_char = cell
                            break
                if move_char:
                    break
        if not move_char:
            raise KeyError(f"Meta token not found: {item_id}")
        old_pos = None
        for row_y, row in enumerate(meta_rows):
            for col_x, cell in enumerate(row):
                if cell == move_char and (
                    _entry_uid(str(cell), {}, legend) == item_id
                    or f"meta:{cell}:{col_x}:{row_y}" == item_id
                ):
                    old_pos = (col_x, row_y)
                    break
            if old_pos:
                break
        if old_pos is None:
            raise KeyError(f"Meta placement not found: {item_id}")
        ox, oy = old_pos
        row_chars = list(meta_rows[oy])
        row_chars[ox] = "."
        meta_rows[oy] = "".join(row_chars)
        if int(y) >= len(meta_rows) or int(x) >= len(meta_rows[int(y)]):
            raise IndexError("Target outside meta grid")
        dest_row = list(meta_rows[int(y)])
        dest_row[int(x)] = move_char
        meta_rows[int(y)] = "".join(dest_row)
    elif source == "layer_placements" or str(item_id).startswith("lp_"):
        placements = _layer_placements_list(map_block)
        target = _find_layer_placement(placements, placement_id=item_id)
        if target is None:
            raise KeyError(f"Layer placement not found: {item_id}")
        old_layer = str(target.get("layer") or "base_1")
        old_pos = target.get("pos") or [0, 0]
        old_token = str(target.get("token") or "")
        if len(old_pos) >= 2:
            _clear_layer_grid_cell(
                map_block,
                old_layer,
                int(old_pos[0]),
                int(old_pos[1]),
                expected_token=old_token or None,
            )
        target["pos"] = [int(x), int(y)]
        materialize_layer_placement(map_block, target)
    elif kind == "terrain":
        if not layer or not token:
            raise ValueError("terrain moves require layer and token")
        grid = map_block.get(layer)
        if not grid:
            raise KeyError(f"Layer not found: {layer}")
        old_pos = None
        for row_y, row in enumerate(grid):
            for col_x, cell in enumerate(row):
                if cell == token and f"terrain:{layer}:{col_x}:{row_y}" == item_id:
                    old_pos = (col_x, row_y)
                    break
            if old_pos:
                break
        if old_pos is None:
            raise KeyError(f"Terrain token not found: {item_id}")
        ox, oy = old_pos
        _clear_terrain_source_cell(grid, ox, oy, token)
        if int(y) >= len(grid) or int(x) >= len(grid[int(y)]):
            raise IndexError("Target outside terrain grid")
        dest_row = list(grid[int(y)])
        dest_ch = dest_row[int(x)]
        moving_category = _token_category(str(token), legend)
        if _should_preserve_destination_cell(dest_ch, moving_category=moving_category, legend=legend):
            _upsert_entity_placement(map_block, str(token), int(x), int(y))
        else:
            dest_row[int(x)] = token
            grid[int(y)] = "".join(dest_row)
    else:
        raise ValueError(f"Unsupported move kind: {kind}")

    save_map_document(path, data)
    return data


def _terrain_token_char(session, object_type: str) -> str:
    try:
        obj = session.load_object(object_type)
    except Exception:
        obj = {}
    token_spec = obj.get("token")
    if isinstance(token_spec, list) and token_spec:
        candidate = str(token_spec[0])
    elif isinstance(token_spec, str):
        candidate = token_spec
    else:
        candidate = object_type[:1] or "?"
    if len(candidate) != 1:
        fallback = {"water": "^", "difficult_terrain": "~", "briar": "▓"}
        candidate = fallback.get(object_type, "?")
    return candidate


def _allocate_legend_token(legend: dict[str, Any], preferred: str) -> str:
    if preferred and preferred not in legend:
        return preferred
    for ch in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789~^*+":
        if ch not in legend:
            return ch
    raise ValueError("No free legend tokens available for terrain")


def _ensure_legend_token(data: dict[str, Any], session, object_type: str) -> str:
    legend = data.setdefault("legend", {})
    for token, entry in legend.items():
        if isinstance(entry, dict) and entry.get("type") == object_type:
            return str(token)
    preferred = _terrain_token_char(session, object_type)
    token = _allocate_legend_token(legend, preferred)
    try:
        obj = session.load_object(object_type)
    except Exception:
        obj = {}
    legend[token] = {
        "name": obj.get("name", object_type.replace("_", " ").title()),
        "type": object_type,
    }
    return token


def _target_terrain_layer(map_block: dict[str, Any], x: int, y: int) -> tuple[str, list[str]]:
    """Pick the topmost layer with a writable filler cell at (x, y)."""
    for layer_name in ("base_2", "base_1", "base"):
        grid = map_block.get(layer_name)
        if not grid:
            continue
        if y < 0 or y >= len(grid) or x < 0 or x >= len(grid[y]):
            continue
        if grid[y][x] in _FILLER_CHARS:
            return layer_name, grid
    raise ValueError(f"No writable terrain layer at ({x}, {y})")


def place_map_layer_item(
    session,
    map_name: str,
    *,
    object_type: str | None = None,
    token: str | None = None,
    layer: str | None = None,
    x: int,
    y: int,
    placement_id: str | None = None,
    extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Place or replace a layer fixture using map.layer_placements (stable editor ids)."""
    path = resolve_map_yaml_path(session, map_name)
    data = copy.deepcopy(load_map_document(path))
    map_block = _map_block(data)

    if object_type:
        token = _ensure_legend_token(data, session, object_type)
    if not token:
        raise ValueError("token or object_type is required")

    target_layer = layer
    if not target_layer:
        target_layer, _grid = _target_terrain_layer(map_block, int(x), int(y))

    placements = _layer_placements_list(map_block)
    placements[:] = [
        entry
        for entry in placements
        if not (
            isinstance(entry, dict)
            and str(entry.get("layer") or "base_1") == str(target_layer)
            and list(entry.get("pos") or []) == [int(x), int(y)]
        )
    ]

    existing_ids = {
        str(entry.get("id"))
        for entry in placements
        if isinstance(entry, dict) and entry.get("id")
    }
    pid = placement_id or _new_placement_id(
        str(target_layer),
        str(token),
        int(x),
        int(y),
        object_type=object_type,
        existing_ids=existing_ids,
    )

    entry: dict[str, Any] = {
        "id": pid,
        "layer": str(target_layer),
        "token": str(token),
        "pos": [int(x), int(y)],
    }
    if extra_fields:
        for key, value in extra_fields.items():
            if key in {"id", "layer", "token", "pos"}:
                continue
            entry[key] = value

    placements.append(entry)
    materialize_layer_placement(map_block, entry)
    save_map_document(path, data)
    return {
        "id": pid,
        "layer": str(target_layer),
        "token": str(token),
        "x": int(x),
        "y": int(y),
        "object_type": object_type,
    }


def place_map_terrain(
    session,
    map_name: str,
    *,
    object_type: str,
    x: int,
    y: int,
) -> dict[str, Any]:
    """Paint terrain into the campaign map YAML (edit mode)."""
    return place_map_layer_item(
        session,
        map_name,
        object_type=object_type,
        x=int(x),
        y=int(y),
    )


def _yaml_char_to_grid_cell(layer: str, ch: str | None) -> str | None:
    if ch is None:
        return None
    if layer == "base":
        return ch if ch != "_" else None
    if ch in _FILLER_CHARS:
        return None
    return ch


def _terrain_object_type(obj) -> str | None:
    props = getattr(obj, "properties", None) or {}
    obj_type = getattr(obj, "type", None) or props.get("type")
    if obj_type and str(obj_type) in _TERRAIN_OVERLAY_TYPES:
        return str(obj_type)
    return None


def _sync_map_properties_from_disk(battle_map, session, map_name: str) -> dict[str, Any]:
    path = resolve_map_yaml_path(session, map_name)
    data = load_map_document(path)
    battle_map.properties = data
    battle_map.legend = data.get("legend") or {}
    return data


def _sync_layer_from_yaml(battle_map, map_block: dict[str, Any], layer: str) -> None:
    grid_attr = _LAYER_GRID_ATTR.get(layer)
    if not grid_attr:
        return
    grid = getattr(battle_map, grid_attr)
    rows = map_block.get(layer) or []
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if x >= len(grid) or y >= len(grid[x]):
                continue
            grid[x][y] = _yaml_char_to_grid_cell(layer, ch)


def _resync_terrain_tile(battle_map, x: int, y: int) -> None:
    from natural20.npc import Npc
    from natural20.player_character import PlayerCharacter

    for obj in list(battle_map.objects_at(x, y)):
        if isinstance(obj, (PlayerCharacter, Npc)):
            continue
        if obj in battle_map.entities:
            continue
        if _terrain_object_type(obj) is not None:
            battle_map.remove(obj)

    for layer_name in ("base_2", "base_1", "base"):
        grid_attr = _LAYER_GRID_ATTR[layer_name]
        grid = getattr(battle_map, grid_attr)
        if x >= len(grid) or y >= len(grid[x]):
            continue
        ch = grid[x][y]
        if not ch or ch in _FILLER_CHARS or ch == "#":
            continue
        battle_map._setup_object_with_token(ch, (x, y))


def apply_terrain_placement_to_live_map(
    battle_map,
    session,
    map_name: str,
    placement: dict[str, Any],
) -> None:
    """Apply a single layer placement to the in-memory map without a full reload."""
    data = _sync_map_properties_from_disk(battle_map, session, map_name)
    map_block = data.get("map") or {}
    materialize_all_layer_placements(map_block)
    layer = str(placement.get("layer") or "base_1")
    if layer in _LAYER_GRID_ATTR:
        _sync_layer_from_yaml(battle_map, map_block, layer)
    elif layer == "meta" and map_block.get("meta") is not None:
        battle_map.meta_map = [
            [None for _ in range(len(row))] for row in map_block.get("meta") or []
        ]
        for y, row in enumerate(map_block.get("meta") or []):
            for x, ch in enumerate(row):
                if ch not in _FILLER_CHARS:
                    battle_map.meta_map[x][y] = ch
    _resync_terrain_tile(battle_map, int(placement["x"]), int(placement["y"]))
    if hasattr(battle_map, "_compute_lights"):
        battle_map._compute_lights()
