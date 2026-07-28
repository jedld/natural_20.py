"""Tests for editor-only object property schemas."""

from __future__ import annotations

from pathlib import Path

from natural20.edit_schema import (
    editable_object_types,
    get_edit_ui_schema,
    object_type_has_editor,
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


def test_editable_object_types_cached(tmp_path: Path):
    session = _make_session(tmp_path)
    first = editable_object_types(session)
    second = editable_object_types(session)
    assert first is second
    assert "spawn_point" in first
