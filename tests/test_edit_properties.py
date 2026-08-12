"""Tests for editable object property persistence."""

from __future__ import annotations

from pathlib import Path

import yaml

from natural20.edit_properties import resolve_property_binding, update_property_binding
from natural20.map_editor import save_map_document


def _write_map(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    save_map_document(path, data)


def _campaign(tmp_path: Path):
    campaign = tmp_path / "demo"
    maps_dir = campaign / "maps"
    maps_dir.mkdir(parents=True)
    (campaign / "game.yml").write_text(
        "name: Demo\nmaps:\n  hub: maps/hub\n  other: maps/other\n",
        encoding="utf-8",
    )
    map_data = {
        "map": {
            "size": [5, 5],
            "base": ["#####", "#.T.#", "#...#", "#...#", "#####"],
            "entities": [],
        },
        "legend": {
            "T": {
                "name": "Gate",
                "type": "teleporter",
                "entity_uid": "gate_out",
                "target_map": "other",
                "target_position": [1, 1],
            },
        },
    }
    map_path = maps_dir / "hub.yml"
    _write_map(map_path, map_data)
    _write_map(
        maps_dir / "other.yml",
        {
            "map": {"size": [6, 6], "base": ["......"] * 6},
        },
    )

    class _Session:
        root_path = str(campaign)
        game_properties = {"maps": {"hub": "maps/hub", "other": "maps/other"}}

    return _Session(), map_path


def test_resolve_legend_teleporter_properties(tmp_path: Path):
    session, _map_path = _campaign(tmp_path)
    resolved = resolve_property_binding(
        session,
        "hub",
        item_id="gate_out",
        kind="terrain",
        token="T",
        source="legend",
    )
    assert resolved["object_type"] == "teleporter"
    assert resolved["binding"]["store"] == "legend"
    assert resolved["values"]["target_map"] == "other"
    assert resolved["values"]["target_position"] == [1, 1]


def test_update_legend_teleporter_properties(tmp_path: Path):
    session, map_path = _campaign(tmp_path)
    resolved = resolve_property_binding(
        session,
        "hub",
        item_id="gate_out",
        kind="terrain",
        token="T",
        source="legend",
    )
    update_property_binding(
        session,
        "hub",
        object_type="teleporter",
        binding=resolved["binding"],
        values={
            "target_map": "other",
            "target_position": [3, 4],
            "label": "South gate",
            "visible": True,
        },
    )
    saved = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    legend = saved["legend"]["T"]
    assert legend["target_map"] == "other"
    assert legend["target_position"] == [3, 4]
    assert legend["label"] == "South gate"
    assert legend["visible"] is True


def test_resolve_entity_layer_teleporter_properties(tmp_path: Path):
    session, map_path = _campaign(tmp_path)
    saved = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    saved["map"]["entities"] = [{"token": "T", "pos": [0, 1], "layer": "object", "target_map": "hub"}]
    map_path.write_text(yaml.safe_dump(saved, sort_keys=False), encoding="utf-8")

    resolved = resolve_property_binding(
        session,
        "hub",
        item_id="gate_out",
        kind="object",
        token="T",
        source="entities",
        index=0,
    )
    assert resolved["binding"]["store"] == "entity"
    assert resolved["values"]["target_map"] == "hub"
    assert resolved["values"]["target_position"] == [1, 1]


def test_update_spawn_point_properties(tmp_path: Path):
    session, map_path = _campaign(tmp_path)
    saved = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    saved["player_spawn_points"] = [{"position": [2, 2], "name": "Start"}]
    map_path.write_text(yaml.safe_dump(saved, sort_keys=False), encoding="utf-8")

    resolved = resolve_property_binding(
        session,
        "hub",
        item_id="spawn:0",
        kind="spawn_point",
        source="player_spawn_points",
        index=0,
    )
    assert resolved["object_type"] == "spawn_point"
    update_property_binding(
        session,
        "hub",
        object_type="spawn_point",
        binding=resolved["binding"],
        values={"name": "Party", "position": [1, 3], "group": "heroes"},
    )
    saved = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    assert saved["player_spawn_points"][0] == {
        "position": [1, 3],
        "name": "Party",
        "group": "heroes",
    }


def test_update_note_contents_and_offset(tmp_path: Path):
    session, map_path = _campaign(tmp_path)
    saved = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    saved["legend"]["N"] = {
        "name": "Clue",
        "type": "note",
        "notes": [{"note": "Old text", "perception_dc": 5}],
        "image_offset_px": [0, 0],
    }
    saved["map"]["entities"] = [{"token": "N", "pos": [2, 2], "layer": "object"}]
    map_path.write_text(yaml.safe_dump(saved, sort_keys=False), encoding="utf-8")

    resolved = resolve_property_binding(
        session,
        "hub",
        item_id="entities:0",
        kind="object",
        token="N",
        source="entities",
        index=0,
    )
    assert resolved["object_type"] == "note"
    update_property_binding(
        session,
        "hub",
        object_type="note",
        binding=resolved["binding"],
        values={
            "label": "Wall carving",
            "hide_map_token": True,
            "image_offset_px": [12, 8],
            "notes": [
                {
                    "note": "Vines and skulls.",
                    "perception_dc": 12,
                    "religion_dc": 14,
                    "image": "wall_detail",
                },
            ],
        },
    )
    saved = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    entity = saved["map"]["entities"][0]
    assert entity["label"] == "Wall carving"
    assert entity["image_offset_px"] == [12, 8]
    assert entity["notes"][0]["note"] == "Vines and skulls."
    assert entity["notes"][0]["perception_dc"] == 12
    assert entity["notes"][0]["religion_dc"] == 14
    assert entity["notes"][0]["image"] == "wall_detail"


def test_update_chest_inventory(tmp_path: Path):
    session, map_path = _campaign(tmp_path)
    items_dir = Path(session.root_path) / "items"
    items_dir.mkdir(parents=True, exist_ok=True)
    (items_dir / "equipment.yml").write_text(
        "healing_potion:\n  name: Healing Potion\narrows:\n  name: Arrows\n",
        encoding="utf-8",
    )
    saved = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    saved["legend"]["C"] = {
        "name": "Treasure Chest",
        "type": "chest",
        "inventory": [{"type": "arrows", "qty": 5}],
    }
    saved["map"]["entities"] = [{"token": "C", "pos": [2, 2], "layer": "object"}]
    map_path.write_text(yaml.safe_dump(saved, sort_keys=False), encoding="utf-8")

    resolved = resolve_property_binding(
        session,
        "hub",
        item_id="entities:0",
        kind="object",
        token="C",
        source="entities",
        index=0,
    )
    assert resolved["object_type"] == "chest"
    assert resolved["values"]["inventory"] == [{"type": "arrows", "qty": 5}]

    update_property_binding(
        session,
        "hub",
        object_type="chest",
        binding=resolved["binding"],
        values={
            "inventory": [
                {"type": "healing_potion", "qty": 2},
                {"type": "arrows", "qty": 20},
            ],
            "notes": [],
            "image_offset_px": [0, 0],
        },
    )
    saved = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    entity = saved["map"]["entities"][0]
    assert entity["inventory"] == [
        {"type": "healing_potion", "qty": 2},
        {"type": "arrows", "qty": 20},
    ]
