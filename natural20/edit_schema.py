"""Editor-only schemas for campaign object properties (not used at runtime)."""

from __future__ import annotations

import copy
import re
from typing import Any

from natural20.yaml_loader import load_campaign_yaml, load_edit_fixtures

_NOTE_DC_KEYS = (
    "perception_dc",
    "investigation_dc",
    "religion_dc",
    "arcana_dc",
    "medicine_dc",
    "nature_dc",
    "insight_dc",
)

_CONTAINER_ITEM_CLASSES = frozenset({"Chest", "Fireplace"})
_CONTAINER_OBJECT_TYPES = frozenset(
    {
        "chest",
        "fireplace",
        "barrel",
        "tavern_bar_counter",
        "tavern_till_safe",
        "tavern_guest_chest",
    }
)
_ITEM_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]*$", re.IGNORECASE)

# Fallback when templates/edit/fixtures.yml is missing (e.g. broken install).
_FALLBACK_NOTES_GROUP: dict[str, Any] = {
    "id": "notes",
    "label": "Notes",
    "fields": [
        {
            "key": "notes",
            "label": "Discoverable notes",
            "type": "note_list",
        },
        {
            "key": "image_offset_px",
            "label": "Note indicator offset",
            "type": "offset_px",
        },
    ],
}

_FALLBACK_INVENTORY_GROUP: dict[str, Any] = {
    "id": "inventory",
    "label": "Container contents",
    "fields": [
        {
            "key": "inventory",
            "label": "Items in container",
            "type": "inventory_list",
            "choices_from": "campaign.items",
        },
    ],
}


def load_objects_catalog(session) -> dict[str, Any]:
    cached = getattr(session, "_objects_catalog_cache", None)
    if cached is None:
        cached = load_campaign_yaml(session.root_path, "items", "objects") or {}
        session._objects_catalog_cache = cached
    return cached


def _load_edit_fixtures(session) -> dict[str, Any]:
    cached = getattr(session, "_edit_fixtures_cache", None)
    if cached is None:
        cached = load_edit_fixtures(session.root_path)
        if not isinstance(cached, dict):
            cached = {}
        session._edit_fixtures_cache = cached
    return cached


def _notes_group(session) -> dict[str, Any]:
    mixins = _load_edit_fixtures(session).get("mixins") or {}
    notes = mixins.get("notes")
    if isinstance(notes, dict) and notes.get("fields"):
        return copy.deepcopy(notes)
    return copy.deepcopy(_FALLBACK_NOTES_GROUP)


def _inventory_group(session) -> dict[str, Any]:
    mixins = _load_edit_fixtures(session).get("mixins") or {}
    inventory = mixins.get("inventory")
    if isinstance(inventory, dict) and inventory.get("fields"):
        return copy.deepcopy(inventory)
    return copy.deepcopy(_FALLBACK_INVENTORY_GROUP)


def _notes_only_schema(session) -> dict[str, Any]:
    return {
        "label": "Notes",
        "scope": ["legend", "entity"],
        "groups": [_notes_group(session)],
    }


def object_definition_supports_inventory(entry: dict[str, Any] | None, object_type: str | None = None) -> bool:
    """True when this object type can hold map YAML ``inventory`` stacks."""
    if not isinstance(entry, dict):
        entry = {}
    type_name = str(object_type or entry.get("type") or "").strip()
    if type_name in _CONTAINER_OBJECT_TYPES:
        return True
    item_class = entry.get("item_class")
    if item_class in _CONTAINER_ITEM_CLASSES:
        return True
    if "inventory" in entry:
        return True
    edit_ui = entry.get("edit_ui")
    if isinstance(edit_ui, dict):
        mixins = edit_ui.get("mixins") or []
        if "inventory" in mixins:
            return True
        for field in iter_schema_fields(edit_ui):
            if field.get("key") == "inventory" or field.get("type") == "inventory_list":
                return True
    return False


def _fixture_schemas(session) -> dict[str, Any]:
    fixtures = _load_edit_fixtures(session).get("fixtures") or {}
    if not isinstance(fixtures, dict):
        return {}
    return fixtures


def editable_object_types(session) -> set[str]:
    """Object types with an edit_ui schema — computed once per session."""
    cached = getattr(session, "_editable_object_types_cache", None)
    if cached is not None:
        return cached
    types = {str(key) for key in _fixture_schemas(session).keys()}
    catalog = load_objects_catalog(session)
    for name, entry in catalog.items():
        if not isinstance(entry, dict):
            continue
        if isinstance(entry.get("edit_ui"), dict) or object_definition_supports_inventory(entry, name):
            types.add(str(name))
    session._editable_object_types_cache = types
    return types


def get_object_type_definition(session, object_type: str) -> dict[str, Any] | None:
    if not object_type:
        return None
    fixture = _fixture_schemas(session).get(object_type)
    if isinstance(fixture, dict):
        return {"type": object_type, "edit_ui": copy.deepcopy(fixture)}
    catalog = load_objects_catalog(session)
    entry = catalog.get(object_type)
    if not isinstance(entry, dict):
        return None
    return copy.deepcopy(entry)


def _schema_has_notes_fields(schema: dict[str, Any]) -> bool:
    for field in iter_schema_fields(schema):
        if field.get("key") in {"notes", "image_offset_px"}:
            return True
    return False


def _schema_has_inventory_fields(schema: dict[str, Any]) -> bool:
    for field in iter_schema_fields(schema):
        if field.get("key") == "inventory" or field.get("type") == "inventory_list":
            return True
    return False


def _with_notes_group(session, schema: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(schema)
    if _schema_has_notes_fields(merged):
        return merged
    groups = merged.setdefault("groups", [])
    groups.append(_notes_group(session))
    return merged


def _with_standard_groups(
    session,
    schema: dict[str, Any],
    *,
    entry: dict[str, Any] | None = None,
    object_type: str | None = None,
) -> dict[str, Any]:
    merged = _with_notes_group(session, schema)
    if object_definition_supports_inventory(entry, object_type) and not _schema_has_inventory_fields(merged):
        groups = merged.setdefault("groups", [])
        groups.insert(0, _inventory_group(session))
    return merged


def get_edit_ui_schema(session, object_type: str) -> dict[str, Any] | None:
    fixture = _fixture_schemas(session).get(object_type)
    if isinstance(fixture, dict):
        return copy.deepcopy(fixture)
    entry = get_object_type_definition(session, object_type)
    if not entry:
        return None
    edit_ui = entry.get("edit_ui")
    if isinstance(edit_ui, dict):
        return _with_standard_groups(session, edit_ui, entry=entry, object_type=object_type)
    if object_definition_supports_inventory(entry, object_type):
        return _with_standard_groups(
            session,
            {
                "label": entry.get("name") or str(object_type).replace("_", " ").title(),
                "scope": ["legend", "entity"],
                "groups": [],
            },
            entry=entry,
            object_type=object_type,
        )
    return _notes_only_schema(session)


def object_type_has_editor(session, object_type: str) -> bool:
    if not object_type:
        return False
    return str(object_type) in editable_object_types(session)


def _campaign_maps(session, current_map: str | None = None, *, all_sets: bool = False) -> list[dict[str, Any]]:
    maps = (session.game_properties or {}).get("maps") or {}
    items: list[dict[str, Any]] = []
    allowed = None
    if not all_sets and current_map and hasattr(session, "maps_in_set"):
        try:
            allowed = set(session.maps_in_set(session.map_set_for(current_map)))
        except Exception:
            allowed = None
    for key in sorted(maps.keys()):
        if allowed is not None and key not in allowed:
            continue
        items.append({"value": key, "label": str(key)})
    return items


def _load_item_catalog(session) -> dict[str, dict[str, Any]]:
    cached = getattr(session, "_edit_item_catalog_cache", None)
    if cached is not None:
        return cached
    catalog: dict[str, dict[str, Any]] = {}
    for category in ("equipment", "weapons", "magic_items"):
        data = load_campaign_yaml(session.root_path, "items", category) or {}
        if not isinstance(data, dict):
            continue
        for slug, entry in data.items():
            if not isinstance(entry, dict):
                continue
            key = str(slug)
            if key in catalog:
                continue
            label = entry.get("name") or key.replace("_", " ").title()
            catalog[key] = {
                "value": key,
                "label": str(label),
                "category": category,
                "type": entry.get("type"),
            }
    session._edit_item_catalog_cache = catalog
    return catalog


def list_item_catalog(
    session,
    *,
    query: str | None = None,
    limit: int = 40,
) -> list[dict[str, Any]]:
    """Return item catalog rows for edit-mode autocomplete."""
    catalog = _load_item_catalog(session)
    needle = str(query or "").strip().lower()
    rows = list(catalog.values())
    if needle:
        scored: list[tuple[int, dict[str, Any]]] = []
        for row in rows:
            value = str(row.get("value") or "").lower()
            label = str(row.get("label") or "").lower()
            if needle == value:
                score = 0
            elif value.startswith(needle):
                score = 1
            elif needle in value:
                score = 2
            elif needle in label:
                score = 3
            else:
                continue
            scored.append((score, row))
        scored.sort(key=lambda item: (item[0], str(item[1].get("label") or "").lower()))
        rows = [row for _score, row in scored]
    else:
        rows.sort(key=lambda row: str(row.get("label") or "").lower())
    if limit and limit > 0:
        rows = rows[: int(limit)]
    return copy.deepcopy(rows)


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


def _resolve_field_choices(session, field: dict[str, Any], *, current_map: str | None, values: dict[str, Any] | None = None) -> None:
    choices_from = field.get("choices_from")
    values = values or {}
    if choices_from == "campaign.maps":
        all_sets = bool(field.get("all_map_sets") or values.get("party_travel") or values.get("party"))
        field["choices"] = _campaign_maps(session, current_map=current_map, all_sets=all_sets)
        return
    if choices_from == "campaign.all_maps":
        field["choices"] = _campaign_maps(session, current_map=current_map, all_sets=True)
        return
    if choices_from == "campaign.items":
        # Full catalogs are large; the client loads suggestions via /edit/catalog/items.
        field["autocomplete"] = True
        field["catalog_url"] = "/edit/catalog/items"
        field["choices"] = []
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
            _resolve_field_choices(session, field, current_map=current_map, values=values)
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


def _coerce_note_list_value(value: Any) -> list[Any]:
    if isinstance(value, list):
        return copy.deepcopy(value)
    if value in (None, ""):
        return []
    if isinstance(value, str):
        if "[object Object]" in value:
            return [{"note": "", "perception_dc": 0}]
        return [{"note": value}]
    if isinstance(value, dict):
        return [copy.deepcopy(value)]
    return []


def _coerce_inventory_list_value(value: Any) -> list[dict[str, Any]]:
    if value in (None, ""):
        return []
    if isinstance(value, dict):
        rows = []
        for item_type, entry in value.items():
            if isinstance(entry, dict):
                qty = entry.get("qty", 1)
                row = {"type": str(item_type), "qty": max(1, _safe_int(qty, 1))}
                if entry.get("contents") is not None:
                    row["contents"] = _coerce_inventory_list_value(entry.get("contents"))
                    row["is_container"] = True
                elif entry.get("is_container"):
                    row["contents"] = []
                    row["is_container"] = True
                rows.append(row)
            else:
                rows.append({"type": str(item_type), "qty": max(1, _safe_int(entry, 1))})
        return rows
    if not isinstance(value, list):
        return []
    rows = []
    for entry in value:
        if isinstance(entry, str):
            rows.append({"type": entry, "qty": 1})
            continue
        if not isinstance(entry, dict):
            continue
        item_type = entry.get("type") or entry.get("item") or entry.get("name")
        if not item_type:
            continue
        row = {"type": str(item_type), "qty": max(1, _safe_int(entry.get("qty", 1), 1))}
        if entry.get("contents") is not None:
            row["contents"] = _coerce_inventory_list_value(entry.get("contents"))
            row["is_container"] = True
        elif entry.get("is_container"):
            row["contents"] = []
            row["is_container"] = True
        rows.append(row)
    return rows


def _safe_int(value: Any, default: int = 1) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def pick_values_for_schema(merged: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    picked: dict[str, Any] = {}
    for field in iter_schema_fields(schema):
        key = str(field["key"])
        if key in merged:
            value = copy.deepcopy(merged[key])
            if field.get("type") == "note_list" or key == "notes":
                picked[key] = _coerce_note_list_value(value)
            elif field.get("type") == "inventory_list" or key == "inventory":
                picked[key] = _coerce_inventory_list_value(value)
            elif field.get("type") == "point_list":
                picked[key] = _normalize_point_list(value)
            else:
                picked[key] = value
        elif field.get("type") == "note_list" or key == "notes":
            picked[key] = []
        elif field.get("type") == "inventory_list" or key == "inventory":
            picked[key] = []
        elif field.get("type") == "offset_px":
            picked[key] = [0, 0]
        elif field.get("type") == "point_list":
            picked[key] = []
        elif "default" in field:
            picked[key] = copy.deepcopy(field["default"])
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


def _normalize_point_list(value: Any) -> list[list[int]]:
    points: list[list[int]] = []
    if not isinstance(value, (list, tuple)):
        return points
    seen: set[tuple[int, int]] = set()
    for item in value:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        try:
            pt = [int(item[0]), int(item[1])]
        except (TypeError, ValueError):
            continue
        key = (pt[0], pt[1])
        if key in seen:
            continue
        seen.add(key)
        points.append(pt)
    return points


def _validate_point_list(value: Any, bounds: dict[str, Any] | None, label: str) -> str | None:
    points = _normalize_point_list(value)
    if not points:
        return f"{label} must include at least the base square"
    for idx, pt in enumerate(points):
        err = _validate_point(pt, bounds, f"{label} square {idx + 1}")
        if err:
            return err
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
        elif field_type == "point_list":
            bounds = field.get("bounds")
            if field.get("relative_to") == "current_map":
                dims = _map_dimensions(session, current_map)
                if dims:
                    bounds = {"width": dims[0], "height": dims[1]}
            err = _validate_point_list(value, bounds, label)
            if err:
                errors.append(err)
        elif field_type == "map_ref":
            maps = (session.game_properties or {}).get("maps") or {}
            if str(value) not in maps:
                errors.append(f"{label} must be a registered campaign map")
        elif field_type == "boolean" and not isinstance(value, bool):
            errors.append(f"{label} must be true or false")
        elif field_type == "offset_px":
            err = _validate_offset_px(value, label)
            if err:
                errors.append(err)
        elif field_type == "note_list":
            err = _validate_note_list(value, label)
            if err:
                errors.append(err)
        elif field_type == "inventory_list":
            err = _validate_inventory_list(session, value, label)
            if err:
                errors.append(err)
    return errors


def _validate_offset_px(value: Any, label: str) -> str | None:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return f"{label} must be a pixel pair [top, left]"
    try:
        int(value[0])
        int(value[1])
    except (TypeError, ValueError):
        return f"{label} must contain integer pixel offsets"
    return None


def _validate_note_list(value: Any, label: str) -> str | None:
    if not isinstance(value, list):
        return f"{label} must be a list of notes"
    for idx, entry in enumerate(value):
        if not isinstance(entry, dict):
            return f"{label} entry {idx + 1} must be an object"
        text = entry.get("note")
        if text is None:
            text = entry.get("content") or entry.get("message")
        if text is None:
            return f"{label} entry {idx + 1} needs note text"
        for dc_key in _NOTE_DC_KEYS:
            if dc_key in entry and entry[dc_key] not in (None, ""):
                try:
                    int(entry[dc_key])
                except (TypeError, ValueError):
                    return f"{label} entry {idx + 1} {dc_key} must be an integer"
    return None


def _validate_inventory_list(session, value: Any, label: str, *, depth: int = 0) -> str | None:
    if not isinstance(value, list):
        return f"{label} must be a list of items"
    if depth > 3:
        return f"{label} nesting is too deep"
    catalog = _load_item_catalog(session)
    for idx, entry in enumerate(value):
        if not isinstance(entry, dict):
            return f"{label} entry {idx + 1} must be an object with type and qty"
        item_type = entry.get("type") or entry.get("item")
        if not item_type or not str(item_type).strip():
            return f"{label} entry {idx + 1} needs an item type"
        slug = str(item_type).strip()
        if not _ITEM_SLUG_RE.match(slug):
            return f"{label} entry {idx + 1} has an invalid item id"
        if catalog and slug not in catalog:
            return f"{label} entry {idx + 1}: unknown item '{slug}'"
        qty = entry.get("qty", 1)
        try:
            qty_int = int(qty)
        except (TypeError, ValueError):
            return f"{label} entry {idx + 1} qty must be an integer"
        if qty_int < 1:
            return f"{label} entry {idx + 1} qty must be at least 1"
        if entry.get("contents") is not None:
            nested_err = _validate_inventory_list(
                session,
                entry.get("contents"),
                f"{label} entry {idx + 1} contents",
                depth=depth + 1,
            )
            if nested_err:
                return nested_err
    return None


def _normalize_note_entry(entry: Any) -> dict[str, Any] | None:
    if isinstance(entry, str):
        text = entry.strip()
        return {"note": text} if text else None
    if not isinstance(entry, dict):
        return None
    text = entry.get("note")
    if text is None:
        text = entry.get("content") or entry.get("message") or ""
    text = str(text)
    normalized: dict[str, Any] = {"note": text}
    for dc_key in _NOTE_DC_KEYS:
        raw = entry.get(dc_key)
        if raw in (None, ""):
            continue
        try:
            normalized[dc_key] = int(raw)
        except (TypeError, ValueError):
            continue
    image = entry.get("image")
    if image:
        normalized["image"] = str(image).strip()
    language = entry.get("language")
    if language:
        normalized["language"] = str(language).strip()
    if entry.get("highlight"):
        normalized["highlight"] = True
    offset = entry.get("image_offset_px")
    if isinstance(offset, (list, tuple)) and len(offset) >= 2:
        try:
            normalized["image_offset_px"] = [int(offset[0]), int(offset[1])]
        except (TypeError, ValueError):
            pass
    return normalized


def _normalize_inventory_entry(entry: Any) -> dict[str, Any] | None:
    if isinstance(entry, str):
        slug = entry.strip()
        return {"type": slug, "qty": 1} if slug else None
    if not isinstance(entry, dict):
        return None
    item_type = entry.get("type") or entry.get("item") or entry.get("name")
    if not item_type:
        return None
    slug = str(item_type).strip()
    if not slug:
        return None
    try:
        qty = int(entry.get("qty", 1))
    except (TypeError, ValueError):
        qty = 1
    if qty < 1:
        return None
    normalized: dict[str, Any] = {"type": slug, "qty": qty}
    if entry.get("contents") is not None:
        nested = []
        for child in entry.get("contents") or []:
            parsed_child = _normalize_inventory_entry(child)
            if parsed_child is not None:
                nested.append(parsed_child)
        normalized["contents"] = nested
        normalized["is_container"] = True
    elif entry.get("is_container"):
        normalized["contents"] = []
        normalized["is_container"] = True
    return normalized


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
        if field_type in {"point", "offset_px"} and isinstance(value, (list, tuple)):
            normalized[key] = [int(value[0]), int(value[1])]
        elif field_type == "point_list":
            normalized[key] = _normalize_point_list(value)
        elif field_type == "boolean":
            normalized[key] = bool(value)
        elif field_type in {"integer"}:
            try:
                normalized[key] = int(value)
            except (TypeError, ValueError):
                default = field.get("default")
                try:
                    normalized[key] = int(default)
                except (TypeError, ValueError):
                    normalized[key] = 0
        elif field_type == "note_list":
            entries = value if isinstance(value, list) else []
            notes = []
            for entry in entries:
                parsed = _normalize_note_entry(entry)
                if parsed is not None:
                    notes.append(parsed)
            normalized[key] = notes
        elif field_type == "inventory_list":
            entries = value if isinstance(value, list) else []
            # Preserve per-instance container contents; do not merge stacks that
            # carry nested contents (e.g. two pouches with different loot).
            merged_plain: dict[str, int] = {}
            plain_order: list[str] = []
            rows: list[dict[str, Any]] = []
            for entry in entries:
                parsed = _normalize_inventory_entry(entry)
                if parsed is None:
                    continue
                if parsed.get("contents") is not None or parsed.get("is_container"):
                    rows.append(parsed)
                    continue
                item_type = parsed["type"]
                if item_type not in merged_plain:
                    plain_order.append(item_type)
                    merged_plain[item_type] = 0
                merged_plain[item_type] += int(parsed["qty"])
            for item_type in plain_order:
                rows.append({"type": item_type, "qty": merged_plain[item_type]})
            normalized[key] = rows
        else:
            normalized[key] = value
    return normalized
