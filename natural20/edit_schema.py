"""Editor-only schemas for campaign object properties (not used at runtime)."""

from __future__ import annotations

import copy
from typing import Any

from natural20.yaml_loader import load_campaign_yaml

# Builtin editor schemas for map fixtures that are not object types in items/objects.yml.
_BUILTIN_SCHEMAS: dict[str, dict[str, Any]] = {
    "spawn_point": {
        "label": "Player spawn",
        "scope": ["player_spawn_points"],
        "groups": [
            {
                "id": "placement",
                "label": "Placement",
                "fields": [
                    {"key": "name", "label": "Name", "type": "string"},
                    {
                        "key": "position",
                        "label": "Position",
                        "type": "point",
                        "relative_to": "current_map",
                        "required": True,
                    },
                    {
                        "key": "group",
                        "label": "Team group",
                        "type": "string",
                    },
                ],
            }
        ],
    },
}


def load_objects_catalog(session) -> dict[str, Any]:
    cached = getattr(session, "_objects_catalog_cache", None)
    if cached is None:
        cached = load_campaign_yaml(session.root_path, "items", "objects") or {}
        session._objects_catalog_cache = cached
    return cached


def editable_object_types(session) -> set[str]:
    """Object types with an edit_ui schema — computed once per session."""
    cached = getattr(session, "_editable_object_types_cache", None)
    if cached is not None:
        return cached
    types = set(_BUILTIN_SCHEMAS.keys())
    catalog = load_objects_catalog(session)
    for name, entry in catalog.items():
        if isinstance(entry, dict) and isinstance(entry.get("edit_ui"), dict):
            types.add(str(name))
    session._editable_object_types_cache = types
    return types


def get_object_type_definition(session, object_type: str) -> dict[str, Any] | None:
    if not object_type:
        return None
    if object_type in _BUILTIN_SCHEMAS:
        return {"type": object_type, "edit_ui": copy.deepcopy(_BUILTIN_SCHEMAS[object_type])}
    catalog = load_objects_catalog(session)
    entry = catalog.get(object_type)
    if not isinstance(entry, dict):
        return None
    return copy.deepcopy(entry)


def get_edit_ui_schema(session, object_type: str) -> dict[str, Any] | None:
    if object_type in _BUILTIN_SCHEMAS:
        return copy.deepcopy(_BUILTIN_SCHEMAS[object_type])
    entry = get_object_type_definition(session, object_type)
    if not entry:
        return None
    edit_ui = entry.get("edit_ui")
    return copy.deepcopy(edit_ui) if isinstance(edit_ui, dict) else None


def object_type_has_editor(session, object_type: str) -> bool:
    if not object_type:
        return False
    return str(object_type) in editable_object_types(session)


def _campaign_maps(session) -> list[dict[str, Any]]:
    maps = (session.game_properties or {}).get("maps") or {}
    items: list[dict[str, Any]] = []
    for key in sorted(maps.keys()):
        items.append({"value": key, "label": str(key)})
    return items


def _map_dimensions(session, map_name: str) -> list[int] | None:
    maps = (session.game_properties or {}).get("maps") or {}
    rel = maps.get(map_name)
    if not rel:
        return None
    from natural20.map_editor import load_map_document, resolve_map_yaml_path

    try:
        path = resolve_map_yaml_path(session, map_name)
        data = load_map_document(path)
    except (KeyError, FileNotFoundError, OSError):
        return None
    map_block = data.get("map") or {}
    size = map_block.get("size")
    if isinstance(size, (list, tuple)) and len(size) >= 2:
        return [int(size[0]), int(size[1])]
    for layer in ("base", "meta"):
        grid = map_block.get(layer) or []
        if grid:
            return [len(grid[0]) if grid[0] else 0, len(grid)]
    return None


def _resolve_field_choices(session, field: dict[str, Any], *, current_map: str | None) -> None:
    choices_from = field.get("choices_from")
    if choices_from == "campaign.maps":
        field["choices"] = _campaign_maps(session)
        return
    if choices_from == "field.target_map.tiles":
        target_map = field.get("_context_target_map")
        if target_map:
            dims = _map_dimensions(session, target_map)
            if dims:
                field["bounds"] = {"width": dims[0], "height": dims[1]}
    if field.get("relative_to") == "current_map" and current_map:
        dims = _map_dimensions(session, current_map)
        if dims:
            field["bounds"] = {"width": dims[0], "height": dims[1]}
    if field.get("relative_to") == "target_map":
        field["bounds_map_field"] = "target_map"


def _field_visible(field: dict[str, Any], values: dict[str, Any]) -> bool:
    visible_when = field.get("visible_when")
    if not isinstance(visible_when, dict):
        return True
    for key, expected in visible_when.items():
        actual = values.get(key)
        if isinstance(expected, dict) and expected.get("present"):
            if actual in (None, "", [], {}):
                return False
            continue
        if actual != expected:
            return False
    return True


def resolve_editor_schema(
    session,
    object_type: str,
    *,
    current_map: str | None = None,
    values: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return edit_ui schema with resolved choices/bounds for the editor client."""
    schema = get_edit_ui_schema(session, object_type)
    if not schema:
        return None
    resolved = copy.deepcopy(schema)
    values = values or {}
    target_map = values.get("target_map")
    for group in resolved.get("groups") or []:
        visible_fields = []
        for field in group.get("fields") or []:
            if field.get("relative_to") == "target_map" or field.get("bounds_map_field") == "target_map":
                field["_context_target_map"] = target_map
            _resolve_field_choices(session, field, current_map=current_map)
            if target_map and field.get("key") in {"target_position"}:
                dims = _map_dimensions(session, str(target_map))
                if dims:
                    field["bounds"] = {"width": dims[0], "height": dims[1]}
            if _field_visible(field, values):
                visible_fields.append(field)
        group["fields"] = visible_fields
    return resolved


def iter_schema_fields(schema: dict[str, Any]):
    for group in schema.get("groups") or []:
        for field in group.get("fields") or []:
            key = field.get("key")
            if key:
                yield field


def editable_field_keys(schema: dict[str, Any]) -> list[str]:
    return [str(field["key"]) for field in iter_schema_fields(schema)]


def pick_values_for_schema(merged: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    picked: dict[str, Any] = {}
    for key in editable_field_keys(schema):
        if key in merged:
            picked[key] = copy.deepcopy(merged[key])
    return picked


def _validate_point(value: Any, bounds: dict[str, Any] | None, label: str) -> str | None:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return f"{label} must be a coordinate pair [x, y]"
    try:
        x, y = int(value[0]), int(value[1])
    except (TypeError, ValueError):
        return f"{label} must contain numeric coordinates"
    if bounds:
        width = int(bounds.get("width", 0))
        height = int(bounds.get("height", 0))
        if width and (x < 0 or x >= width):
            return f"{label} x must be between 0 and {width - 1}"
        if height and (y < 0 or y >= height):
            return f"{label} y must be between 0 and {height - 1}"
    return None


def validate_field_values(
    session,
    schema: dict[str, Any],
    values: dict[str, Any],
    *,
    current_map: str | None = None,
    object_type: str | None = None,
) -> list[str]:
    errors: list[str] = []
    resolved = resolve_editor_schema(
        session,
        object_type or "",
        current_map=current_map,
        values=values,
    )
    fields = list(iter_schema_fields(resolved or schema))
    for field in fields:
        key = str(field["key"])
        label = str(field.get("label") or key)
        value = values.get(key)
        if field.get("required") and value in (None, ""):
            errors.append(f"{label} is required")
            continue
        if value in (None, ""):
            continue
        field_type = field.get("type")
        if field_type == "point":
            bounds = field.get("bounds")
            if field.get("relative_to") == "target_map":
                target_map = values.get("target_map")
                if target_map:
                    dims = _map_dimensions(session, str(target_map))
                    if dims:
                        bounds = {"width": dims[0], "height": dims[1]}
            err = _validate_point(value, bounds, label)
            if err:
                errors.append(err)
        elif field_type == "map_ref":
            maps = (session.game_properties or {}).get("maps") or {}
            if str(value) not in maps:
                errors.append(f"{label} must be a registered campaign map")
        elif field_type == "boolean" and not isinstance(value, bool):
            errors.append(f"{label} must be true or false")
    return errors


def normalize_submitted_values(schema: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    allowed = set(editable_field_keys(schema))
    for key, value in values.items():
        if key not in allowed:
            continue
        field = next((f for f in iter_schema_fields(schema) if f.get("key") == key), None)
        if not field:
            continue
        field_type = field.get("type")
        if field_type == "point" and isinstance(value, (list, tuple)):
            normalized[key] = [int(value[0]), int(value[1])]
        elif field_type == "boolean":
            normalized[key] = bool(value)
        elif field_type in {"integer"}:
            normalized[key] = int(value)
        else:
            normalized[key] = value
    return normalized
