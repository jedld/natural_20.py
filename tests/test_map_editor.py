"""Tests for campaign map YAML edit helpers."""

from __future__ import annotations

from pathlib import Path

import yaml

from natural20.map_editor import (
    apply_terrain_placement_to_live_map,
    build_edit_overlay,
    move_map_item,
    place_map_terrain,
    place_npc_in_map,
    place_player_in_map,
    remove_map_item,
    save_map_document,
)


def _write_map(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    save_map_document(path, data)


def test_build_edit_overlay_includes_entities_and_spawns(tmp_path: Path):
    campaign = tmp_path / "demo"
    maps_dir = campaign / "maps"
    maps_dir.mkdir(parents=True)
    (campaign / "game.yml").write_text(
        "name: Demo\nmaps:\n  hub: maps/hub\n",
        encoding="utf-8",
    )
    map_data = {
        "name": "Hub",
        "player_spawn_points": [{"position": [2, 3], "name": "Start"}],
        "map": {
            "size": [5, 5],
            "base": ["#####", "#...#", "#...#", "#...#", "#####"],
            "meta": [".....", ".....", "..@..", ".....", "....."],
            "entities": [
                {"token": "G", "pos": [1, 1]},
                {"token": "EXIT", "layer": "object", "pos": [3, 3]},
            ],
        },
        "legend": {
            "G": {
                "name": "Guz",
                "type": "npc",
                "sub_type": "guz",
                "overrides": {"entity_uid": "guz"},
            },
            "@": {
                "name": "Sheep",
                "type": "npc",
                "sub_type": "finethir_sheep",
                "overrides": {"entity_uid": "finethir_shinebright"},
            },
            "EXIT": {
                "name": "Exit",
                "type": "teleporter",
                "entity_uid": "road_out",
            },
        },
    }
    _write_map(maps_dir / "hub.yml", map_data)

    overlay = build_edit_overlay(map_data)
    kinds = {item["id"]: item["kind"] for item in overlay["items"]}
    assert kinds["guz"] == "entity"
    assert kinds["road_out"] == "object"
    assert kinds["finethir_shinebright"] == "entity"
    assert any(item["kind"] == "spawn_point" for item in overlay["items"])
    assert any(item["id"] == "road_out" and item["kind"] == "object" for item in overlay["items"])
    assert any(
        item.get("category") == "teleporter"
        for item in overlay["items"] + overlay["terrain"]
    )


def test_build_edit_overlay_allows_multiple_fixtures_per_tile():
    map_data = {
        "player_spawn_points": [{"position": [2, 2], "name": "Party Start"}],
        "map": {
            "size": [5, 5],
            "base": ["#####", "#...#", "#.T.#", "#...#", "#####"],
            "entities": [
                {"token": "BAR", "layer": "object", "pos": [2, 2]},
            ],
        },
        "legend": {
            "T": {"name": "Town Gate", "type": "teleporter", "entity_uid": "gate"},
            "BAR": {"name": "Bar Counter", "type": "chest", "entity_uid": "tavern_bar"},
        },
    }
    overlay = build_edit_overlay(map_data)
    at_22 = [
        item
        for item in overlay["items"] + overlay["terrain"]
        if item["x"] == 2 and item["y"] == 2
    ]
    categories = {item["category"] for item in at_22}
    assert "teleporter" in categories
    assert "object" in categories or any(item["kind"] == "object" for item in at_22)
    assert "spawn_point" in categories


def test_move_map_item_updates_entities_and_spawn_points(tmp_path: Path):
    campaign = tmp_path / "demo"
    maps_dir = campaign / "maps"
    maps_dir.mkdir(parents=True)
    (campaign / "game.yml").write_text(
        "name: Demo\nmaps:\n  hub: maps/hub\n",
        encoding="utf-8",
    )
    map_data = {
        "player_spawn_points": [{"position": [1, 1]}],
        "map": {
            "entities": [
                {"token": "G", "pos": [1, 1]},
            ],
        },
        "legend": {
            "G": {
                "type": "npc",
                "sub_type": "guz",
                "overrides": {"entity_uid": "guz"},
            }
        },
    }
    map_path = maps_dir / "hub.yml"
    _write_map(map_path, map_data)

    class _Session:
        root_path = str(campaign)
        game_properties = {"maps": {"hub": "maps/hub"}}

    move_map_item(
        _Session(),
        "hub",
        item_id="guz",
        kind="entity",
        source="entities",
        x=3,
        y=2,
    )
    saved = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    assert saved["map"]["entities"][0]["pos"] == [3, 2]

    move_map_item(
        _Session(),
        "hub",
        item_id="spawn:0",
        kind="spawn_point",
        source="player_spawn_points",
        index=0,
        x=4,
        y=4,
    )
    saved = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    assert saved["player_spawn_points"][0]["position"] == [4, 4]


def test_move_map_item_updates_terrain(tmp_path: Path):
    campaign = tmp_path / "demo"
    maps_dir = campaign / "maps"
    maps_dir.mkdir(parents=True)
    (campaign / "game.yml").write_text(
        "name: Demo\nmaps:\n  hub: maps/hub\n",
        encoding="utf-8",
    )
    map_data = {
        "map": {
            "size": [5, 5],
            "base": ["#####", "#...#", "#.T.#", "#...#", "#####"],
        },
        "legend": {
            "T": {"name": "Gate", "type": "teleporter", "entity_uid": "gate_out"},
        },
    }
    map_path = maps_dir / "hub.yml"
    _write_map(map_path, map_data)

    class _Session:
        root_path = str(campaign)
        game_properties = {"maps": {"hub": "maps/hub"}}

    move_map_item(
        _Session(),
        "hub",
        item_id="terrain:base:2:2",
        kind="terrain",
        layer="base",
        token="T",
        x=1,
        y=1,
    )
    saved = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    assert saved["map"]["base"][2][2] == "."
    assert saved["map"]["base"][1][1] == "T"


def test_move_terrain_teleporter_onto_wall_preserves_wall(tmp_path: Path):
    campaign = tmp_path / "demo"
    maps_dir = campaign / "maps"
    maps_dir.mkdir(parents=True)
    (campaign / "game.yml").write_text(
        "name: Demo\nmaps:\n  hub: maps/hub\n",
        encoding="utf-8",
    )
    map_data = {
        "map": {
            "size": [5, 5],
            "base": ["#####", "#.T.#", "#...#", "#...#", "#####"],
            "entities": [],
        },
        "legend": {
            "T": {"name": "Gate", "type": "teleporter", "entity_uid": "gate_out"},
        },
    }
    map_path = maps_dir / "hub.yml"
    _write_map(map_path, map_data)

    class _Session:
        root_path = str(campaign)
        game_properties = {"maps": {"hub": "maps/hub"}}

    move_map_item(
        _Session(),
        "hub",
        item_id="terrain:base:2:1",
        kind="terrain",
        layer="base",
        token="T",
        x=0,
        y=1,
    )
    saved = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    assert saved["map"]["base"][1][0] == "#"
    assert saved["map"]["base"][1][2] == "."
    assert saved["map"]["entities"] == [
        {"token": "T", "pos": [0, 1], "layer": "object"},
    ]


def test_move_map_item_resolves_entities_index_id_without_entity_uid(tmp_path: Path):
    campaign = tmp_path / "demo"
    maps_dir = campaign / "maps"
    maps_dir.mkdir(parents=True)
    (campaign / "game.yml").write_text(
        "name: Demo\nmaps:\n  hub: maps/hub\n",
        encoding="utf-8",
    )
    map_data = {
        "map": {
            "entities": [
                {"token": "G", "pos": [1, 1]},
                {"token": "w1", "pos": [8, 1]},
            ],
        },
        "legend": {
            "G": {"type": "npc", "sub_type": "guz", "overrides": {"entity_uid": "guz"}},
            "w1": {"type": "npc", "sub_type": "polymorph_wolf"},
        },
    }
    map_path = maps_dir / "hub.yml"
    _write_map(map_path, map_data)

    class _Session:
        root_path = str(campaign)
        game_properties = {"maps": {"hub": "maps/hub"}}

    move_map_item(
        _Session(),
        "hub",
        item_id="entities:1",
        kind="entity",
        source="entities",
        index=1,
        x=4,
        y=24,
    )
    saved = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    assert saved["map"]["entities"][1]["pos"] == [4, 24]


def test_move_map_item_resolves_entity_by_token_and_source_position(tmp_path: Path):
    campaign = tmp_path / "demo"
    maps_dir = campaign / "maps"
    maps_dir.mkdir(parents=True)
    (campaign / "game.yml").write_text(
        "name: Demo\nmaps:\n  hub: maps/hub\n",
        encoding="utf-8",
    )
    map_data = {
        "map": {
            "entities": [
                {"token": "w1", "pos": [8, 1]},
            ],
        },
        "legend": {
            "w1": {"type": "npc", "sub_type": "polymorph_wolf"},
        },
    }
    map_path = maps_dir / "hub.yml"
    _write_map(map_path, map_data)

    class _Session:
        root_path = str(campaign)
        game_properties = {"maps": {"hub": "maps/hub"}}

    move_map_item(
        _Session(),
        "hub",
        item_id="6a6bf55f-7cf4-42b3-96fe-1b1449c15220",
        kind="entity",
        source="entities",
        token="w1",
        from_x=8,
        from_y=1,
        x=10,
        y=2,
    )
    saved = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    assert saved["map"]["entities"][0]["pos"] == [10, 2]


def test_build_edit_overlay_uses_entities_index_when_entity_uid_missing():
    map_data = {
        "map": {
            "entities": [
                {"token": "w1", "pos": [8, 1]},
            ],
        },
        "legend": {
            "w1": {"type": "npc", "sub_type": "polymorph_wolf"},
        },
    }
    overlay = build_edit_overlay(map_data)
    wolf = next(item for item in overlay["items"] if item["token"] == "w1")
    assert wolf["id"] == "entities:0"
    assert wolf["index"] == 0


def test_place_map_terrain_writes_base_overlay_layer(tmp_path: Path):
    campaign = tmp_path / "demo"
    maps_dir = campaign / "maps"
    maps_dir.mkdir(parents=True)
    (campaign / "game.yml").write_text(
        "name: Demo\nmaps:\n  hub: maps/hub\n",
        encoding="utf-8",
    )
    map_data = {
        "map": {
            "size": [5, 5],
            "base": ["#####", "#...#", "#...#", "#...#", "#####"],
            "base_1": [".....", ".....", ".....", ".....", "....."],
        },
        "legend": {},
    }
    map_path = maps_dir / "hub.yml"
    _write_map(map_path, map_data)

    class _Session:
        root_path = str(campaign)
        game_properties = {"maps": {"hub": "maps/hub"}}

        def load_object(self, object_type):
            return {
                "water": {"name": "Water", "token": ["^"]},
                "difficult_terrain": {"name": "Difficult Terrain", "token": ["~"]},
            }[object_type]

    placed = place_map_terrain(_Session(), "hub", object_type="water", x=2, y=2)
    saved = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    assert placed["layer"] == "base_1"
    assert placed["token"] == "^"
    assert saved["map"]["base_1"][2][2] == "^"
    assert saved["legend"]["^"]["type"] == "water"
    assert saved["map"]["layer_placements"]
    assert saved["map"]["layer_placements"][0]["id"].startswith("lp_")


def test_place_map_terrain_writes_directional_wall_token(tmp_path: Path):
    campaign = tmp_path / "demo"
    maps_dir = campaign / "maps"
    maps_dir.mkdir(parents=True)
    (campaign / "game.yml").write_text(
        "name: Demo\nmaps:\n  hub: maps/hub\n",
        encoding="utf-8",
    )
    map_data = {
        "map": {
            "base": ["...", "...", "..."],
        },
        "legend": {},
    }
    map_path = maps_dir / "hub.yml"
    _write_map(map_path, map_data)

    class _Session:
        root_path = str(campaign)
        game_properties = {"maps": {"hub": "maps/hub"}}

        def load_object(self, object_type):
            return {
                "stone_wall_tl": {
                    "name": "Stone Wall Thin Top Left",
                    "item_class": "StoneWallDirectional",
                    "token": ["┌"],
                },
                "stone_wall": {
                    "name": "Stone Wall",
                    "item_class": "StoneWall",
                    "token": [None],
                },
            }[object_type]

    placed = place_map_terrain(_Session(), "hub", object_type="stone_wall_tl", x=1, y=1)
    saved = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    assert placed["token"] == "┌"
    assert saved["map"]["base"][1][1] == "┌"
    assert saved["legend"]["┌"]["type"] == "stone_wall_tl"

    placed_wall = place_map_terrain(_Session(), "hub", object_type="stone_wall", x=0, y=0)
    saved = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    assert placed_wall["token"] == "#"
    assert saved["map"]["base"][0][0] == "#"


def test_place_wall_overwrites_occupied_base_cell(tmp_path: Path):
    """Walls/doors may replace non-filler terrain (e.g. teleporter token on stairs)."""
    campaign = tmp_path / "demo"
    maps_dir = campaign / "maps"
    maps_dir.mkdir(parents=True)
    (campaign / "game.yml").write_text(
        "name: Demo\nmaps:\n  upstairs: maps/upstairs\n",
        encoding="utf-8",
    )
    map_data = {
        "map": {
            "base": ["T......", "......."],
        },
        "legend": {
            "T": {"name": "Stairs", "type": "teleporter"},
        },
    }
    map_path = maps_dir / "upstairs.yml"
    _write_map(map_path, map_data)

    class _Session:
        root_path = str(campaign)
        game_properties = {"maps": {"upstairs": "maps/upstairs"}}

        def load_object(self, object_type):
            return {
                "stone_wall_tl": {
                    "name": "Stone Wall Thin Top Left",
                    "item_class": "StoneWallDirectional",
                    "token": ["┌"],
                },
            }[object_type]

    placed = place_map_terrain(_Session(), "upstairs", object_type="stone_wall_tl", x=0, y=0)
    saved = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    assert placed["token"] == "┌"
    assert saved["map"]["base"][0][0] == "┌"


def test_place_teleporter_on_wall_preserves_terrain(tmp_path: Path):
    campaign = tmp_path / "demo"
    maps_dir = campaign / "maps"
    maps_dir.mkdir(parents=True)
    (campaign / "game.yml").write_text(
        "name: Demo\nmaps:\n  hub: maps/hub\n",
        encoding="utf-8",
    )
    map_data = {
        "map": {
            "size": [3, 3],
            "base": [".┌.", "...", "..."],
            "layer_placements": [
                {"id": "lp_wall", "layer": "base", "token": "┌", "pos": [1, 0]},
            ],
            "entities": [],
        },
        "legend": {
            "┌": {"name": "Wall", "type": "stone_wall_tl"},
        },
    }
    map_path = maps_dir / "hub.yml"
    _write_map(map_path, map_data)

    class _Session:
        root_path = str(campaign)
        game_properties = {"maps": {"hub": "maps/hub"}}

        def load_object(self, object_type):
            return {
                "teleporter": {
                    "name": "Teleporter",
                    "item_class": "Teleporter",
                    "token": ["T"],
                },
            }[object_type]

    placed = place_map_terrain(_Session(), "hub", object_type="teleporter", x=1, y=0)
    saved = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    assert placed["placement_kind"] == "object"
    assert saved["map"]["base"][0][1] == "┌"
    assert saved["map"]["layer_placements"]
    assert saved["map"]["entities"] == [
        {"token": "T", "pos": [1, 0], "layer": "object"},
    ]
    assert saved["legend"]["T"]["type"] == "teleporter"
    assert saved["legend"]["T"]["target_map"] == "hub"
    assert saved["legend"]["T"]["target_position"] == [1, 0]


def test_place_note_uses_unique_token_and_entity_notes(tmp_path: Path):
    campaign = tmp_path / "demo"
    maps_dir = campaign / "maps"
    maps_dir.mkdir(parents=True)
    (campaign / "game.yml").write_text(
        "name: Demo\nmaps:\n  hub: maps/hub\n",
        encoding="utf-8",
    )
    map_data = {
        "map": {
            "size": [4, 4],
            "base": ["....", "....", "....", "...."],
            "entities": [],
        },
        "legend": {},
    }
    map_path = maps_dir / "hub.yml"
    _write_map(map_path, map_data)

    class _Session:
        root_path = str(campaign)
        game_properties = {"maps": {"hub": "maps/hub"}}

        def load_object(self, object_type):
            return {
                "note": {
                    "name": "Note",
                    "placeable": True,
                    "token": ["N"],
                },
            }[object_type]

    session = _Session()
    first = place_map_terrain(session, "hub", object_type="note", x=1, y=1)
    second = place_map_terrain(session, "hub", object_type="note", x=2, y=2)
    saved = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    assert first["token"] != second["token"]
    assert len(saved["map"]["entities"]) == 2
    for entry in saved["map"]["entities"]:
        assert entry["layer"] == "object"
        assert entry["notes"][0]["note"] == ""
        assert entry["image_offset_px"] == [0, 0]
        assert entry["hide_map_token"] is True
    assert saved["legend"][first["token"]]["type"] == "note"
    assert saved["legend"][second["token"]]["type"] == "note"
    overlay = build_edit_overlay(saved)
    inline_notes = [item for item in overlay["items"] if item.get("source") == "inline_note"]
    assert len(inline_notes) == 2
    assert all(item["label"] == "Note (empty)" for item in inline_notes)


def test_build_edit_overlay_includes_chest_note_trigger_and_inline_notes():
    map_data = {
        "map": {
            "size": [3, 3],
            "base": ["...", ".c.", "..."],
            "meta": ["...", ".p.", ".W."],
        },
        "legend": {
            "c": {"name": "Chest", "type": "chest"},
            "p": {
                "name": "Ambush",
                "type": "proximity_trigger",
                "events": [{"event": "activate", "message": "Surprise!"}],
            },
            "W": {
                "name": "Footprints",
                "type": "note",
                "notes": [{"note": "You notice an absence of footprints in the dust."}],
            },
        },
    }
    overlay = build_edit_overlay(map_data)
    combined = (overlay.get("items") or []) + (overlay.get("terrain") or [])
    object_types = {item.get("object_type") for item in combined}
    categories = {item.get("category") for item in combined}
    assert "chest" in object_types
    assert "proximity_trigger" in object_types
    assert "note" in object_types
    assert "container" in categories
    assert "trigger" in categories
    inline_notes = [item for item in overlay["items"] if item.get("source") == "inline_note"]
    assert len(inline_notes) == 1
    assert "footprints" in inline_notes[0]["label"].lower()
    assert inline_notes[0]["parent_object_type"] == "note"
    assert inline_notes[0]["parent_id"]


def test_build_edit_overlay_prefers_layer_placements_over_grid_scan():
    map_data = {
        "map": {
            "size": [3, 3],
            "base_1": ["...", ".^.", "..."],
            "layer_placements": [
                {"id": "lp_water_feature", "layer": "base_1", "token": "^", "pos": [1, 1]},
            ],
        },
        "legend": {
            "^": {"name": "Water", "type": "water"},
        },
    }
    overlay = build_edit_overlay(map_data)
    water = [item for item in overlay["terrain"] if item.get("object_type") == "water"]
    assert len(water) == 1
    assert water[0]["id"] == "lp_water_feature"
    assert water[0]["source"] == "layer_placements"


def test_move_layer_placement_updates_list_and_grid(tmp_path: Path):
    campaign = tmp_path / "demo"
    maps_dir = campaign / "maps"
    maps_dir.mkdir(parents=True)
    (campaign / "game.yml").write_text(
        "name: Demo\nmaps:\n  hub: maps/hub\n",
        encoding="utf-8",
    )
    map_data = {
        "map": {
            "size": [5, 5],
            "base_1": [".....", ".....", "..^..", ".....", "....."],
            "layer_placements": [
                {"id": "lp_water_pool", "layer": "base_1", "token": "^", "pos": [2, 2]},
            ],
        },
        "legend": {"^": {"name": "Water", "type": "water"}},
    }
    map_path = maps_dir / "hub.yml"
    _write_map(map_path, map_data)

    class _Session:
        root_path = str(campaign)
        game_properties = {"maps": {"hub": "maps/hub"}}

    move_map_item(
        _Session(),
        "hub",
        item_id="lp_water_pool",
        kind="terrain",
        source="layer_placements",
        layer="base_1",
        token="^",
        x=1,
        y=1,
    )
    saved = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    assert saved["map"]["layer_placements"][0]["pos"] == [1, 1]
    assert saved["map"]["base_1"][2][2] == "."
    assert saved["map"]["base_1"][1][1] == "^"


def test_remove_layer_placement_clears_list_and_grid(tmp_path: Path):
    campaign = tmp_path / "demo"
    maps_dir = campaign / "maps"
    maps_dir.mkdir(parents=True)
    (campaign / "game.yml").write_text(
        "name: Demo\nmaps:\n  hub: maps/hub\n",
        encoding="utf-8",
    )
    map_data = {
        "map": {
            "size": [5, 5],
            "base_1": [".....", ".....", "..^..", ".....", "....."],
            "layer_placements": [
                {"id": "lp_water_pool", "layer": "base_1", "token": "^", "pos": [2, 2]},
            ],
        },
        "legend": {"^": {"name": "Water", "type": "water"}},
    }
    map_path = maps_dir / "hub.yml"
    _write_map(map_path, map_data)

    class _Session:
        root_path = str(campaign)
        game_properties = {"maps": {"hub": "maps/hub"}}

    removed = remove_map_item(
        _Session(),
        "hub",
        item_id="lp_water_pool",
        kind="terrain",
        source="layer_placements",
        layer="base_1",
        token="^",
        x=2,
        y=2,
    )
    saved = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    assert removed["x"] == 2
    assert removed["y"] == 2
    assert saved["map"]["layer_placements"] == []
    assert saved["map"]["base_1"][2][2] == "."


def test_remove_grid_terrain_clears_ascii_cell(tmp_path: Path):
    campaign = tmp_path / "demo"
    maps_dir = campaign / "maps"
    maps_dir.mkdir(parents=True)
    (campaign / "game.yml").write_text(
        "name: Demo\nmaps:\n  hub: maps/hub\n",
        encoding="utf-8",
    )
    map_data = {
        "map": {
            "size": [3, 3],
            "base": [".┌.", "...", "..."],
        },
        "legend": {"┌": {"name": "Wall", "type": "stone_wall_tl"}},
    }
    map_path = maps_dir / "hub.yml"
    _write_map(map_path, map_data)

    class _Session:
        root_path = str(campaign)
        game_properties = {"maps": {"hub": "maps/hub"}}

    remove_map_item(
        _Session(),
        "hub",
        item_id="terrain:base:1:0",
        kind="terrain",
        layer="base",
        token="┌",
        x=1,
        y=0,
    )
    saved = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    assert saved["map"]["base"][0][1] == "."


def test_remove_fixture_at_position_clears_layer_placement(tmp_path: Path):
    campaign = tmp_path / "demo"
    maps_dir = campaign / "maps"
    maps_dir.mkdir(parents=True)
    (campaign / "game.yml").write_text(
        "name: Demo\nmaps:\n  hub: maps/hub\n",
        encoding="utf-8",
    )
    map_data = {
        "map": {
            "size": [3, 3],
            "base": [".┌.", "...", "..."],
            "layer_placements": [
                {"id": "lp_wall", "layer": "base", "token": "┌", "pos": [1, 0]},
            ],
        },
        "legend": {"┌": {"name": "Wall", "type": "stone_wall_tl"}},
    }
    map_path = maps_dir / "hub.yml"
    _write_map(map_path, map_data)

    class _Session:
        root_path = str(campaign)
        game_properties = {"maps": {"hub": "maps/hub"}}

    remove_map_item(
        _Session(),
        "hub",
        item_id="pos:1:0",
        kind="terrain",
        x=1,
        y=0,
    )
    saved = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    assert saved["map"]["layer_placements"] == []
    assert saved["map"]["base"][0][1] == "."


def test_build_edit_overlay_includes_water_terrain(tmp_path: Path):
    map_data = {
        "map": {
            "size": [3, 3],
            "base_1": ["...", ".^.", "..."],
        },
        "legend": {
            "^": {"name": "Water", "type": "water"},
        },
    }
    overlay = build_edit_overlay(map_data)
    terrain = overlay["terrain"]
    assert any(item["object_type"] == "water" for item in terrain)


def test_build_edit_overlay_includes_wall_and_door_edges():
    map_data = {
        "map": {
            "size": [4, 4],
            "base": [
                "....",
                ".┌.",
                ".╒.",
                "....",
            ],
        },
        "legend": {
            "┌": {"name": "stone_wall", "type": "stone_wall_lt"},
            "╒": {
                "name": "Corner Door Top Left",
                "type": "corner_door_tl",
            },
        },
    }
    overlay = build_edit_overlay(map_data)
    wall_tile = next(item for item in overlay["terrain"] if item["token"] == "┌")
    door_tile = next(item for item in overlay["terrain"] if item["token"] == "╒")

    assert wall_tile["wall_edges"] == {
        "top": True,
        "right": False,
        "bottom": False,
        "left": True,
    }
    assert door_tile["wall_edges"] == {
        "top": False,
        "right": False,
        "bottom": False,
        "left": True,
    }
    assert door_tile["door_edges"] == {
        "top": True,
        "right": False,
        "bottom": False,
        "left": False,
    }


def test_build_edit_overlay_corner_door_tr_edges():
    """Top-right corner door: door on top edge, solid wall on right."""
    map_data = {
        "map": {
            "size": [4, 4],
            "base": [
                "....",
                ".╗..",
                "....",
                "....",
            ],
        },
        "legend": {
            "╗": {
                "name": "Corner Door Top Right",
                "type": "corner_door_tr",
            },
        },
    }
    overlay = build_edit_overlay(map_data)
    door_tile = next(item for item in overlay["terrain"] if item["token"] == "╗")
    assert door_tile["wall_edges"] == {
        "top": False,
        "right": True,
        "bottom": False,
        "left": False,
    }
    assert door_tile["door_edges"] == {
        "top": True,
        "right": False,
        "bottom": False,
        "left": False,
    }


def test_build_edit_overlay_merges_object_catalog_for_fixture_edges():
    """Legend-only types (e.g. bottom_storage_room) get border/door_pos from objects.yml."""
    from natural20.session import Session

    session = Session(root_path="user_levels/death_house")
    map_data = {
        "map": {
            "size": [4, 4],
            "base": [
                "....",
                ".*..",
                "....",
                "....",
            ],
        },
        "legend": {
            "*": {
                "name": "bottom storage room",
                "type": "bottom_storage_room",
            },
        },
    }
    overlay_without = build_edit_overlay(map_data)
    tile_without = next(item for item in overlay_without["terrain"] if item["token"] == "*")
    assert "wall_edges" not in tile_without
    assert "door_edges" not in tile_without

    overlay_with = build_edit_overlay(map_data, session=session)
    tile_with = next(item for item in overlay_with["terrain"] if item["token"] == "*")
    assert tile_with["wall_edges"] == {
        "top": True,
        "right": True,
        "bottom": False,
        "left": True,
    }
    assert tile_with["door_edges"] == {
        "top": False,
        "right": False,
        "bottom": True,
        "left": False,
    }


def test_build_edit_overlay_skips_object_catalog_for_npcs():
    """NPC legend types are not objects.yml entries; do not probe the catalog."""
    class _Session:
        root_path = None
        load_calls = 0

        def load_object(self, object_type):
            self.load_calls += 1
            raise AssertionError(f"unexpected catalog lookup for {object_type}")

    map_data = {
        "map": {
            "size": [3, 3],
            "base": ["...", "...", "..."],
            "entities": [
                {"token": "A", "pos": [0, 0]},
                {"token": "B", "pos": [1, 1]},
                {"token": "C", "pos": [2, 2]},
            ],
        },
        "legend": {
            "A": {"name": "Alice", "type": "npc", "overrides": {"backstory": "x" * 200}},
            "B": {"name": "Bob", "type": "npc"},
            "C": {"name": "Cara", "type": "npc"},
        },
    }
    session = _Session()
    overlay = build_edit_overlay(map_data, session=session)
    assert session.load_calls == 0
    labels = {item["label"] for item in overlay["items"] if item.get("source") == "entities"}
    assert labels == {"Alice", "Bob", "Cara"}


def test_load_object_does_not_reload_yaml_on_missing_name():
    from natural20.session import Session

    session = Session(root_path="tests/fixtures")
    session.objects.clear()
    session._objects_catalog_loaded = False
    loads = {"n": 0}
    original = session.load_yaml_file

    def counted(category, resource):
        loads["n"] += 1
        return original(category, resource)

    session.load_yaml_file = counted
    for _ in range(3):
        try:
            session.load_object("definitely_not_an_object")
        except AssertionError:
            pass
    assert loads["n"] == 1


def test_build_edit_overlay_includes_hash_wall_edges():
    map_data = {
        "map": {
            "size": [3, 3],
            "base": [
                "###",
                "#.#",
                "###",
            ],
        },
        "legend": {},
    }
    overlay = build_edit_overlay(map_data)
    wall_tiles = [item for item in overlay["terrain"] if item["token"] == "#"]
    assert len(wall_tiles) == 8
    for tile in wall_tiles:
        assert tile["category"] == "wall"
        assert tile["wall_edges"] == {
            "top": True,
            "right": True,
            "bottom": True,
            "left": True,
        }


def test_build_edit_overlay_includes_barrier_edges():
    map_data = {
        "map": {
            "size": [4, 4],
            "base": [
                "....",
                ".┏.",
                ".┫.",
                "....",
            ],
        },
        "legend": {
            "┏": {
                "name": "lt_corner_barrier",
                "type": "barrier",
                "border": [1, 0, 0, 1],
            },
            "┫": {
                "name": "r_corner_barrier",
                "type": "barrier",
                "border": [0, 1, 0, 0],
            },
        },
    }
    overlay = build_edit_overlay(map_data)
    lt_tile = next(item for item in overlay["terrain"] if item["token"] == "┏")
    right_tile = next(item for item in overlay["terrain"] if item["token"] == "┫")

    assert lt_tile["category"] == "wall"
    assert lt_tile["wall_edges"] == {
        "top": True,
        "right": False,
        "bottom": False,
        "left": True,
    }
    assert right_tile["category"] == "wall"
    assert right_tile["wall_edges"] == {
        "top": False,
        "right": True,
        "bottom": False,
        "left": False,
    }


def test_apply_terrain_placement_to_live_map(tmp_path: Path):
    campaign = tmp_path / "demo"
    maps_dir = campaign / "maps"
    maps_dir.mkdir(parents=True)
    (campaign / "game.yml").write_text(
        "name: Demo\nmaps:\n  hub: maps/hub\n",
        encoding="utf-8",
    )
    map_data = {
        "map": {
            "size": [5, 5],
            "base": ["#####", "#...#", "#...#", "#...#", "#####"],
            "base_1": [".....", ".....", ".....", ".....", "....."],
        },
        "legend": {},
    }
    map_path = maps_dir / "hub.yml"
    _write_map(map_path, map_data)

    class _Session:
        root_path = str(campaign)
        game_properties = {"maps": {"hub": "maps/hub"}}

        def load_object(self, object_type):
            return {
                "water": {"name": "Water", "token": ["^"], "type": "water"},
            }[object_type]

    from natural20.map import Map
    from natural20.session import Session

    (campaign / "items").mkdir()
    (campaign / "items" / "objects.yml").write_text(
        "water:\n  name: Water\n  token:\n    - ^\n",
        encoding="utf-8",
    )
    session = Session(str(campaign))
    battle_map = Map(session, str(map_path), name="hub", skip_setup=True)
    placed = place_map_terrain(session, "hub", object_type="water", x=2, y=2)
    apply_terrain_placement_to_live_map(battle_map, session, "hub", placed)
    assert battle_map.base_map_1[2][2] == "^"
    assert any(
        getattr(obj, "type", None) == "water"
        for obj in battle_map.objects_at(2, 2)
    )


def test_resync_terrain_tile_replaces_directional_wall(tmp_path: Path):
    from natural20.item_library.common import StoneWallDirectional
    from natural20.map import Map
    from natural20.map_editor import _resync_terrain_tile
    from natural20.session import Session

    campaign = tmp_path / "demo"
    maps_dir = campaign / "maps"
    maps_dir.mkdir(parents=True)
    (campaign / "game.yml").write_text(
        "name: Demo\nmaps:\n  hub: maps/hub\n",
        encoding="utf-8",
    )
    map_data = {
        "map": {
            "size": [3, 3],
            "base": ["...", ".┌.", "..."],
        },
        "legend": {
            "┌": {"name": "Wall TL", "type": "stone_wall_tl"},
            "┐": {"name": "Wall TR", "type": "stone_wall_tr"},
        },
    }
    map_path = maps_dir / "hub.yml"
    _write_map(map_path, map_data)

    session = Session(str(campaign))
    battle_map = Map(session, str(map_path), name="hub")
    walls = [obj for obj in battle_map.objects_at(1, 1) if isinstance(obj, StoneWallDirectional)]
    assert len(walls) == 1
    assert walls[0].wall_direction == "stone_wall_tl"

    battle_map.properties["map"]["base"][1] = ".┐."
    _resync_terrain_tile(battle_map, 1, 1)
    walls = [obj for obj in battle_map.objects_at(1, 1) if isinstance(obj, StoneWallDirectional)]
    assert len(walls) == 1
    assert walls[0].wall_direction == "stone_wall_tr"


def test_place_npc_in_map_creates_legend_and_entity(tmp_path: Path):
    campaign = tmp_path / "demo"
    maps_dir = campaign / "maps"
    maps_dir.mkdir(parents=True)
    (campaign / "game.yml").write_text(
        "name: Demo\nmaps:\n  hub: maps/hub\n",
        encoding="utf-8",
    )
    map_data = {
        "map": {
            "size": [5, 5],
            "base": ["#####", "#...#", "#...#", "#...#", "#####"],
        },
        "legend": {},
    }
    map_path = maps_dir / "hub.yml"
    _write_map(map_path, map_data)

    class _Session:
        root_path = str(campaign)
        game_properties = {"maps": {"hub": "maps/hub"}}

    result = place_npc_in_map(_Session(), "hub", npc_type="goblin", x=2, y=2)
    assert result["npc_type"] == "goblin"
    assert result["x"] == 2
    assert result["y"] == 2
    assert result["placement_kind"] == "entity"

    saved = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    # Legend should have an entry for goblin
    goblin_token = result["token"]
    assert goblin_token in saved["legend"]
    assert saved["legend"][goblin_token]["type"] == "npc"
    assert saved["legend"][goblin_token]["sub_type"] == "goblin"
    # Entity placement should exist
    entities = saved["map"]["entities"]
    assert any(e["token"] == goblin_token and e["pos"] == [2, 2] for e in entities)


def test_place_npc_in_map_reuses_existing_legend_entry(tmp_path: Path):
    campaign = tmp_path / "demo"
    maps_dir = campaign / "maps"
    maps_dir.mkdir(parents=True)
    (campaign / "game.yml").write_text(
        "name: Demo\nmaps:\n  hub: maps/hub\n",
        encoding="utf-8",
    )
    map_data = {
        "map": {
            "size": [5, 5],
            "base": ["#####", "#...#", "#...#", "#...#", "#####"],
            "entities": [{"token": "G", "pos": [1, 1]}],
        },
        "legend": {
            "G": {"name": "Goblin", "type": "npc", "sub_type": "goblin"},
        },
    }
    map_path = maps_dir / "hub.yml"
    _write_map(map_path, map_data)

    class _Session:
        root_path = str(campaign)
        game_properties = {"maps": {"hub": "maps/hub"}}

    result = place_npc_in_map(_Session(), "hub", npc_type="goblin", x=3, y=3)
    assert result["token"] == "G"

    saved = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    entities = saved["map"]["entities"]
    assert any(e["token"] == "G" and e["pos"] == [3, 3] for e in entities)
    assert len(entities) == 2


def test_place_npc_in_map_preserves_overrides(tmp_path: Path):
    campaign = tmp_path / "demo"
    maps_dir = campaign / "maps"
    maps_dir.mkdir(parents=True)
    (campaign / "game.yml").write_text(
        "name: Demo\nmaps:\n  hub: maps/hub\n",
        encoding="utf-8",
    )
    map_data = {
        "map": {
            "size": [5, 5],
            "base": ["#####", "#...#", "#...#", "#...#", "#####"],
        },
        "legend": {},
    }
    map_path = maps_dir / "hub.yml"
    _write_map(map_path, map_data)

    class _Session:
        root_path = str(campaign)
        game_properties = {"maps": {"hub": "maps/hub"}}

    place_npc_in_map(
        _Session(), "hub", npc_type="goblin", x=2, y=2,
        overrides={"entity_uid": "my_goblin"}
    )

    saved = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    entities = saved["map"]["entities"]
    placed_entry = [e for e in entities if e["pos"] == [2, 2]][0]
    assert placed_entry.get("overrides", {}).get("entity_uid") == "my_goblin"


def test_place_player_in_map_updates_existing_position(tmp_path: Path):
    campaign = tmp_path / "demo"
    maps_dir = campaign / "maps"
    maps_dir.mkdir(parents=True)
    (campaign / "game.yml").write_text(
        "name: Demo\nmaps:\n  hub: maps/hub\n",
        encoding="utf-8",
    )
    map_data = {
        "map": {
            "size": [5, 5],
            "base": ["#####", "#...#", "#...#", "#...#", "#####"],
        },
        "player": [
            {"position": [1, 1], "overrides": {"entity_uid": "hero_1"}},
        ],
    }
    map_path = maps_dir / "hub.yml"
    _write_map(map_path, map_data)

    class _Session:
        root_path = str(campaign)
        game_properties = {"maps": {"hub": "maps/hub"}}

    result = place_player_in_map(_Session(), "hub", entity_uid="hero_1", x=3, y=3)
    assert result["entity_uid"] == "hero_1"
    assert result["placement_kind"] == "player"

    saved = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    player_list = saved["player"]
    assert len(player_list) == 1
    assert player_list[0]["position"] == [3, 3]


def test_place_player_in_map_adds_new_entry(tmp_path: Path):
    campaign = tmp_path / "demo"
    maps_dir = campaign / "maps"
    maps_dir.mkdir(parents=True)
    (campaign / "game.yml").write_text(
        "name: Demo\nmaps:\n  hub: maps/hub\n",
        encoding="utf-8",
    )
    map_data = {
        "map": {
            "size": [5, 5],
            "base": ["#####", "#...#", "#...#", "#...#", "#####"],
        },
        "player": [],
    }
    map_path = maps_dir / "hub.yml"
    _write_map(map_path, map_data)

    class _Session:
        root_path = str(campaign)
        game_properties = {"maps": {"hub": "maps/hub"}}

    result = place_player_in_map(_Session(), "hub", entity_uid="hero_2", x=4, y=4)
    assert result["entity_uid"] == "hero_2"

    saved = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    player_list = saved["player"]
    assert len(player_list) == 1
    assert player_list[0]["position"] == [4, 4]
    assert player_list[0]["overrides"]["entity_uid"] == "hero_2"


def test_place_player_in_map_matches_by_sheet(tmp_path: Path):
    campaign = tmp_path / "demo"
    maps_dir = campaign / "maps"
    maps_dir.mkdir(parents=True)
    (campaign / "game.yml").write_text(
        "name: Demo\nmaps:\n  hub: maps/hub\n",
        encoding="utf-8",
    )
    map_data = {
        "map": {
            "size": [5, 5],
            "base": ["#####", "#...#", "#...#", "#...#", "#####"],
        },
        "player": [
            {"position": [1, 1], "sheet": "characters/hero_3.yml"},
        ],
    }
    map_path = maps_dir / "hub.yml"
    _write_map(map_path, map_data)

    class _Session:
        root_path = str(campaign)
        game_properties = {"maps": {"hub": "maps/hub"}}

    place_player_in_map(_Session(), "hub", entity_uid="characters/hero_3.yml", x=3, y=3)

    saved = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    assert saved["player"][0]["position"] == [3, 3]


def test_place_player_in_map_creates_player_list(tmp_path: Path):
    campaign = tmp_path / "demo"
    maps_dir = campaign / "maps"
    maps_dir.mkdir(parents=True)
    (campaign / "game.yml").write_text(
        "name: Demo\nmaps:\n  hub: maps/hub\n",
        encoding="utf-8",
    )
    map_data = {
        "map": {
            "size": [5, 5],
            "base": ["#####", "#...#", "#...#", "#...#", "#####"],
        },
    }
    map_path = maps_dir / "hub.yml"
    _write_map(map_path, map_data)

    class _Session:
        root_path = str(campaign)
        game_properties = {"maps": {"hub": "maps/hub"}}

    result = place_player_in_map(_Session(), "hub", entity_uid="hero_new", x=2, y=2)
    assert result["entity_uid"] == "hero_new"

    saved = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    assert "player" in saved
    assert len(saved["player"]) == 1
    assert saved["player"][0]["position"] == [2, 2]


def test_place_npc_in_map_moves_unique_on_same_map(tmp_path: Path):
    campaign = tmp_path / "demo"
    maps_dir = campaign / "maps"
    maps_dir.mkdir(parents=True)
    (campaign / "game.yml").write_text(
        "name: Demo\nmaps:\n  hub: maps/hub\n",
        encoding="utf-8",
    )
    map_data = {
        "map": {
            "size": [5, 5],
            "base": ["#####", "#...#", "#...#", "#...#", "#####"],
        },
        "legend": {},
    }
    map_path = maps_dir / "hub.yml"
    _write_map(map_path, map_data)

    class _Session:
        root_path = str(campaign)
        game_properties = {"maps": {"hub": "maps/hub"}}

    first = place_npc_in_map(
        _Session(), "hub", npc_type="goblin", x=1, y=1,
        overrides={"entity_uid": "named_scout"},
    )
    second = place_npc_in_map(
        _Session(), "hub", npc_type="goblin", x=3, y=3,
        overrides={"entity_uid": "named_scout"},
    )
    assert second["moved"] is True
    assert second["entity_uid"] == "named_scout"
    saved = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    entities = saved["map"]["entities"]
    matching = [e for e in entities if (e.get("overrides") or {}).get("entity_uid") == "named_scout"]
    assert len(matching) == 1
    assert matching[0]["pos"] == [3, 3]
    assert first["token"] == second["token"]


def test_place_npc_in_map_moves_unique_across_map_set(tmp_path: Path):
    campaign = tmp_path / "demo"
    maps_dir = campaign / "maps"
    maps_dir.mkdir(parents=True)
    (campaign / "game.yml").write_text(
        "name: Demo\nmaps:\n  hub: maps/hub\n  cellar: maps/cellar\n",
        encoding="utf-8",
    )
    map_data = {
        "map": {
            "size": [5, 5],
            "base": ["#####", "#...#", "#...#", "#...#", "#####"],
        },
        "legend": {},
    }
    hub_path = maps_dir / "hub.yml"
    cellar_path = maps_dir / "cellar.yml"
    _write_map(hub_path, map_data)
    _write_map(cellar_path, map_data)

    class _Session:
        root_path = str(campaign)
        game_properties = {"maps": {"hub": "maps/hub", "cellar": "maps/cellar"}}

    place_npc_in_map(
        _Session(), "hub", npc_type="goblin", x=1, y=1,
        overrides={"entity_uid": "named_scout"},
    )
    result = place_npc_in_map(
        _Session(), "cellar", npc_type="goblin", x=2, y=2,
        overrides={"entity_uid": "named_scout"},
    )
    assert result["moved"] is True
    assert result["from_map"] == "hub"
    hub = yaml.safe_load(hub_path.read_text(encoding="utf-8"))
    cellar = yaml.safe_load(cellar_path.read_text(encoding="utf-8"))
    hub_uids = [
        (e.get("overrides") or {}).get("entity_uid")
        for e in (hub.get("map") or {}).get("entities") or []
    ]
    cellar_uids = [
        (e.get("overrides") or {}).get("entity_uid")
        for e in (cellar.get("map") or {}).get("entities") or []
    ]
    assert "named_scout" not in hub_uids
    assert "named_scout" in cellar_uids

