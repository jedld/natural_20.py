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
