"""Tests for editor-only object property schemas."""

from __future__ import annotations

from pathlib import Path

from natural20.edit_schema import (
    editable_object_types,
    get_edit_ui_schema,
    object_type_has_editor,
    pick_values_for_schema,
    resolve_editor_schema,
    validate_field_values,
)
from natural20.map_editor import save_map_document


def _write_map(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    save_map_document(path, data)


def _make_session(tmp_path: Path):
    campaign = tmp_path / "demo"
    maps_dir = campaign / "maps"
    maps_dir.mkdir(parents=True)
    (campaign / "game.yml").write_text(
        "name: Demo\nmaps:\n  hub: maps/hub\n  other: maps/other\n",
        encoding="utf-8",
    )
    _write_map(
        maps_dir / "hub.yml",
        {
            "map": {"size": [6, 4], "base": ["......"] * 4},
        },
    )
    _write_map(
        maps_dir / "other.yml",
        {
            "map": {"size": [10, 8], "base": [".........."] * 8},
        },
    )

    class Session:
        root_path = str(campaign)
        game_properties = {"maps": {"hub": "maps/hub", "other": "maps/other"}}

    return Session()


def test_teleporter_edit_ui_loaded_from_templates(tmp_path: Path):
    session = _make_session(tmp_path)
    assert object_type_has_editor(session, "teleporter")
    schema = get_edit_ui_schema(session, "teleporter")
    assert schema is not None
    assert schema["label"] == "Teleporter"
    field_keys = [
        field["key"]
        for group in schema["groups"]
        for field in group["fields"]
    ]
    assert "target_map" in field_keys
    assert "target_position" in field_keys


def test_resolve_editor_schema_includes_map_choices(tmp_path: Path):
    session = _make_session(tmp_path)
    schema = resolve_editor_schema(session, "teleporter", current_map="hub")
    destination = next(group for group in schema["groups"] if group["id"] == "destination")
    target_map_field = next(field for field in destination["fields"] if field["key"] == "target_map")
    choice_values = {item["value"] for item in target_map_field["choices"]}
    assert choice_values == {"hub", "other"}


def test_resolve_editor_schema_sets_target_position_bounds(tmp_path: Path):
    session = _make_session(tmp_path)
    schema = resolve_editor_schema(
        session,
        "teleporter",
        current_map="hub",
        values={"target_map": "other"},
    )
    destination = next(group for group in schema["groups"] if group["id"] == "destination")
    target_position = next(field for field in destination["fields"] if field["key"] == "target_position")
    assert target_position["bounds"] == {"width": 10, "height": 8}


def test_validate_field_values_rejects_out_of_bounds_target(tmp_path: Path):
    session = _make_session(tmp_path)
    schema = get_edit_ui_schema(session, "teleporter")
    errors = validate_field_values(
        session,
        schema,
        {"target_map": "other", "target_position": [99, 99]},
        current_map="hub",
        object_type="teleporter",
    )
    assert errors
    assert any("x must be" in err or "y must be" in err for err in errors)


def test_spawn_point_builtin_schema(tmp_path: Path):
    session = _make_session(tmp_path)
    assert object_type_has_editor(session, "spawn_point")
    schema = get_edit_ui_schema(session, "spawn_point")
    assert schema["scope"] == ["player_spawn_points"]


def test_note_builtin_schema_includes_note_list(tmp_path: Path):
    session = _make_session(tmp_path)
    assert object_type_has_editor(session, "note")
    schema = get_edit_ui_schema(session, "note")
    field_keys = [
        field["key"]
        for group in schema["groups"]
        for field in group["fields"]
    ]
    assert "notes" in field_keys
    assert "image_offset_px" in field_keys
    assert "label" in field_keys


def test_teleporter_schema_merges_notes_group(tmp_path: Path):
    session = _make_session(tmp_path)
    schema = get_edit_ui_schema(session, "teleporter")
    field_keys = [
        field["key"]
        for group in schema["groups"]
        for field in group["fields"]
    ]
    assert "target_map" in field_keys
    assert "notes" in field_keys
    assert "image_offset_px" in field_keys


def test_editable_object_types_cached(tmp_path: Path):
    session = _make_session(tmp_path)
    first = editable_object_types(session)
    second = editable_object_types(session)
    assert first is second
    assert "spawn_point" in first
    assert "note" in first
    assert "teleporter" in first


def test_edit_fixtures_loaded_from_templates(tmp_path: Path):
    session = _make_session(tmp_path)
    schema = get_edit_ui_schema(session, "spawn_point")
    assert schema is not None
    assert schema["label"] == "Player spawn"
    field_keys = [field["key"] for group in schema["groups"] for field in group["fields"]]
    assert field_keys == ["name", "position", "group"]


def test_campaign_can_override_edit_fixtures(tmp_path: Path):
    campaign = tmp_path / "demo"
    edit_dir = campaign / "edit"
    edit_dir.mkdir(parents=True)
    maps_dir = campaign / "maps"
    maps_dir.mkdir(parents=True)
    (campaign / "game.yml").write_text(
        "name: Demo\nmaps:\n  hub: maps/hub\n",
        encoding="utf-8",
    )
    _write_map(
        maps_dir / "hub.yml",
        {"map": {"size": [4, 4], "base": ["...."] * 4}},
    )
    (edit_dir / "fixtures.yml").write_text(
        """
fixtures:
  spawn_point:
    label: Custom spawn
    scope: [player_spawn_points]
    groups:
      - id: placement
        label: Placement
        fields:
          - key: name
            label: Spawn name
            type: string
""".strip(),
        encoding="utf-8",
    )

    class Session:
        root_path = str(campaign)
        game_properties = {"maps": {"hub": "maps/hub"}}

    schema = get_edit_ui_schema(Session(), "spawn_point")
    assert schema["label"] == "Custom spawn"


def test_pick_values_coerces_corrupted_notes_string(tmp_path: Path):
    session = _make_session(tmp_path)
    schema = get_edit_ui_schema(session, "note")
    picked = pick_values_for_schema(
        {"notes": "[object Object],[object Object]", "hide_map_token": True},
        schema,
    )
    assert picked["notes"] == [{"note": "", "perception_dc": 0}]


def test_chest_schema_includes_inventory_list(tmp_path: Path):
    session = _make_session(tmp_path)
    assert object_type_has_editor(session, "chest")
    schema = get_edit_ui_schema(session, "chest")
    field_by_key = {
        field["key"]: field
        for group in schema["groups"]
        for field in group["fields"]
    }
    assert field_by_key["inventory"]["type"] == "inventory_list"
    assert "notes" in field_by_key


def test_resolve_inventory_field_marks_autocomplete(tmp_path: Path):
    session = _make_session(tmp_path)
    schema = resolve_editor_schema(session, "chest")
    inventory = next(
        field
        for group in schema["groups"]
        for field in group["fields"]
        if field["key"] == "inventory"
    )
    assert inventory.get("autocomplete") is True
    assert inventory.get("catalog_url") == "/edit/catalog/items"


def test_list_item_catalog_filters_by_query(tmp_path: Path):
    from natural20.edit_schema import list_item_catalog

    campaign = tmp_path / "demo"
    items_dir = campaign / "items"
    items_dir.mkdir(parents=True)
    (campaign / "game.yml").write_text("name: Demo\nmaps: {}\n", encoding="utf-8")
    (items_dir / "equipment.yml").write_text(
        "healing_potion:\n  name: Healing Potion\n  type: potion\narrows:\n  name: Arrows\n  type: ammunition\n",
        encoding="utf-8",
    )
    (items_dir / "weapons.yml").write_text(
        "longsword:\n  name: Longsword\n  type: weapon\n",
        encoding="utf-8",
    )

    class Session:
        root_path = str(campaign)
        game_properties = {"maps": {}}

    rows = list_item_catalog(Session(), query="heal", limit=10)
    assert any(row["value"] == "healing_potion" for row in rows)
    assert all("heal" in row["value"] or "heal" in row["label"].lower() for row in rows)


def test_validate_inventory_rejects_unknown_item(tmp_path: Path):
    from natural20.edit_schema import normalize_submitted_values

    campaign = tmp_path / "demo"
    items_dir = campaign / "items"
    items_dir.mkdir(parents=True)
    (campaign / "game.yml").write_text("name: Demo\nmaps: {}\n", encoding="utf-8")
    (items_dir / "equipment.yml").write_text(
        "healing_potion:\n  name: Healing Potion\n",
        encoding="utf-8",
    )

    class Session:
        root_path = str(campaign)
        game_properties = {"maps": {}}

    session = Session()
    schema = get_edit_ui_schema(session, "chest")
    errors = validate_field_values(
        session,
        schema,
        {"inventory": [{"type": "not_a_real_item", "qty": 1}]},
        object_type="chest",
    )
    assert errors
    assert any("unknown item" in err for err in errors)

    normalized = normalize_submitted_values(
        schema,
        {"inventory": [{"type": "healing_potion", "qty": 2}, {"type": "healing_potion", "qty": 1}]},
    )
    assert normalized["inventory"] == [{"type": "healing_potion", "qty": 3}]
