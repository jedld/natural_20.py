"""Tests for campaign map YAML edit helpers."""

from __future__ import annotations

from pathlib import Path

import yaml

from natural20.map_editor import (
    apply_terrain_placement_to_live_map,
    build_edit_overlay,
    move_map_item,
    place_map_terrain,
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
