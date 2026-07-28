"""Resolve and persist editable object properties in campaign map YAML."""

from __future__ import annotations

import copy
from typing import Any

from natural20.edit_schema import (
    get_edit_ui_schema,
    normalize_submitted_values,
    object_type_has_editor,
    pick_values_for_schema,
    validate_field_values,
)
from natural20.map_editor import (
    _entry_uid,
    _legend_for,
    _map_block,
    load_map_document,
    resolve_map_yaml_path,
    save_map_document,
)


def _merge_placement_props(legend_entry: dict[str, Any], entity_entry: dict[str, Any] | None = None) -> dict[str, Any]:
    merged = copy.deepcopy(legend_entry or {})
    if entity_entry:
        for key, value in entity_entry.items():
            if key in {"token", "pos", "layer"}:
                continue
            if key == "overrides" and isinstance(value, dict):
                existing = merged.get("overrides")
                if not isinstance(existing, dict):
                    existing = {}
                merged["overrides"] = {**existing, **value}
            else:
                merged[key] = copy.deepcopy(value)
    overrides = merged.pop("overrides", None)
    if isinstance(overrides, dict):
        merged.update(overrides)
    return merged


def _legend_entry_for_token(data: dict[str, Any], token: str) -> dict[str, Any]:
    legend = _legend_for(data)
    entry = legend.get(token)
    if not isinstance(entry, dict):
        entry = {}
        legend[token] = entry
    return entry


def _find_entity_index(
    entities: list[dict[str, Any]],
    *,
    item_id: str,
    index: int | None,
    token: str | None,
    legend: dict[str, Any],
) -> int | None:
    if index is not None and 0 <= index < len(entities):
        return index
    for i, entry in enumerate(entities):
        if not isinstance(entry, dict):
            continue
        tok = entry.get("token")
        if _entry_uid(str(tok or ""), entry, legend) == item_id:
            return i
    return None


def resolve_property_binding(
    session,
    map_name: str,
    *,
    item_id: str,
    kind: str,
    source: str | None = None,
    token: str | None = None,
    index: int | None = None,
    layer: str | None = None,
) -> dict[str, Any]:
    """Locate where editable values live in map YAML for one overlay fixture."""
    path = resolve_map_yaml_path(session, map_name)
    data = load_map_document(path)

    if kind == "spawn_point" or source == "player_spawn_points":
        object_type = "spawn_point"
        if index is None and item_id.startswith("spawn:"):
            index = int(item_id.split(":", 1)[1])
        slots = data.get("player_spawn_points") or []
        if index is None or index < 0 or index >= len(slots):
            raise KeyError(f"Spawn point not found: {item_id}")
        raw = slots[index]
        if isinstance(raw, dict):
            values = {
                "name": raw.get("name"),
                "position": list(raw.get("position") or []),
                "group": raw.get("group"),
            }
        else:
            values = {"name": f"Spawn {index + 1}", "position": list(raw), "group": None}
        return {
            "object_type": object_type,
            "binding": {
                "store": "player_spawn_points",
                "index": index,
            },
            "values": values,
        }

    if not token:
        raise KeyError("token is required for object property binding")

    legend = _legend_for(data)
    legend_entry = copy.deepcopy(legend.get(token) or {})
    object_type = legend_entry.get("type")
    if not object_type:
        raise KeyError(f"Legend token {token!r} has no object type")

    entity_entry: dict[str, Any] | None = None
    entity_index: int | None = None
    store = "legend"

    if source == "entities" or kind in {"entity", "object"}:
        map_block = _map_block(data)
        entities = map_block.get("entities") or []
        entity_index = _find_entity_index(
            entities,
            item_id=item_id,
            index=index,
            token=token,
            legend=legend,
        )
        if entity_index is not None:
            entry = entities[entity_index]
            if isinstance(entry, dict):
                entity_entry = copy.deepcopy(entry)
                store = "entity"

    merged = _merge_placement_props(legend_entry, entity_entry)
    schema = get_edit_ui_schema(session, str(object_type))
    if not schema:
        raise KeyError(f"No editor schema for object type {object_type!r}")

    return {
        "object_type": str(object_type),
        "binding": {
            "store": store,
            "token": str(token),
            "entity_index": entity_index,
            "layer": layer,
        },
        "values": pick_values_for_schema(merged, schema),
    }


def update_property_binding(
    session,
    map_name: str,
    *,
    object_type: str,
    binding: dict[str, Any],
    values: dict[str, Any],
) -> dict[str, Any]:
    schema = get_edit_ui_schema(session, object_type)
    if not schema:
        raise KeyError(f"No editor schema for object type {object_type!r}")

    normalized = normalize_submitted_values(schema, values)
    errors = validate_field_values(session, schema, normalized, current_map=map_name, object_type=object_type)
    if errors:
        raise ValueError("; ".join(errors))

    path = resolve_map_yaml_path(session, map_name)
    data = copy.deepcopy(load_map_document(path))
    map_block = _map_block(data)
    store = binding.get("store")

    if store == "player_spawn_points":
        index = binding.get("index")
        slots = data.setdefault("player_spawn_points", [])
        if index is None or index < 0 or index >= len(slots):
            raise KeyError("Spawn point binding index missing")
        entry = slots[index]
        position = normalized.get("position")
        if not isinstance(entry, dict):
            entry = {"position": list(entry) if isinstance(entry, list) else [0, 0]}
            slots[index] = entry
        if "name" in normalized:
            entry["name"] = normalized["name"]
        if position is not None:
            entry["position"] = position
        if "group" in normalized:
            entry["group"] = normalized["group"]
    elif store == "entity":
        token = binding.get("token")
        entity_index = binding.get("entity_index")
        entities = map_block.setdefault("entities", [])
        if entity_index is None or entity_index < 0 or entity_index >= len(entities):
            raise KeyError("Entity binding index missing")
        entry = entities[entity_index]
        if not isinstance(entry, dict):
            raise KeyError("Invalid entity entry")
        for key, value in normalized.items():
            entry[key] = copy.deepcopy(value)
        entry["token"] = token
    elif store == "legend":
        token = binding.get("token")
        if not token:
            raise KeyError("Legend binding requires token")
        legend_entry = _legend_entry_for_token(data, str(token))
        for key, value in normalized.items():
            legend_entry[key] = copy.deepcopy(value)
        if "type" not in legend_entry:
            legend_entry["type"] = object_type
    else:
        raise ValueError(f"Unsupported property store: {store}")

    save_map_document(path, data)
    return data


def overlay_item_is_editable(session, type_name: str | None) -> bool:
    return bool(type_name) and object_type_has_editor(session, str(type_name))
