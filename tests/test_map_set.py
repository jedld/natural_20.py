"""Map sets: implicit root, dual-set placements, same-set teleporter guards."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from natural20.campaign_validator import ValidateOptions, validate_campaign
from natural20.item_library.teleporter import Teleporter
from natural20.map_set import (
    ROOT_MAP_SET_ID,
    MapSetRegistry,
    place_entity_instance,
    place_party_on_map,
)
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.utils.serialization import Serialization


MIN_MAP = """
name: {name}
map:
  illumination: 1.0
  base:
    - "...."
    - "...."
    - "...."
    - "...."
legend: {{}}
player: []
npc: []
"""

MIN_GAME = """
name: Map Set Fixture
starting_map: maps/town
maps:
  town: maps/town
  woods: maps/woods
groups:
  a:
    default: true
    enemies: []
    allies: []
    neutral: []
"""

MIN_INDEX = """
{
  "tile_size": 70,
  "title": "Map Set Fixture",
  "login_background": "assets/login.png",
  "map": "maps/town",
  "soundtracks": [],
  "logins": [],
  "default_controllers": []
}
"""


def _write_campaign(root: Path, *, map_sets=None, extra_town=None, extra_woods=None):
    (root / "maps").mkdir(parents=True)
    (root / "characters").mkdir()
    game = yaml.safe_load(MIN_GAME)
    if map_sets is not None:
        game["map_sets"] = map_sets
    (root / "game.yml").write_text(yaml.safe_dump(game, sort_keys=False), encoding="utf-8")
    (root / "index.json").write_text(MIN_INDEX.strip() + "\n", encoding="utf-8")
    town = MIN_MAP.format(name="town")
    woods = MIN_MAP.format(name="woods")
    if extra_town:
        town = extra_town
    if extra_woods:
        woods = extra_woods
    (root / "maps" / "town.yml").write_text(town, encoding="utf-8")
    (root / "maps" / "woods.yml").write_text(woods, encoding="utf-8")
    fixture_pc = Path("tests/fixtures/characters/high_elf_fighter.yml")
    if fixture_pc.is_file():
        shutil.copy(fixture_pc, root / "characters" / "high_elf_fighter.yml")
    return root


def test_implicit_root_set_contains_all_maps():
    session = Session(root_path="tests/fixtures")
    assert session.map_set_for("index") == ROOT_MAP_SET_ID
    assert session.active_map_set == ROOT_MAP_SET_ID
    assert "index" in session.maps_in_set(ROOT_MAP_SET_ID)
    assert session.same_map_set("index", "index")


def test_map_sets_from_game_yml(tmp_path: Path):
    _write_campaign(
        tmp_path,
        map_sets={
            "root": {"label": "Town", "maps": ["town"]},
            "wilds": {"label": "Wilds", "maps": ["woods"]},
        },
    )
    session = Session(root_path=str(tmp_path))
    assert session.map_set_for("town") == "root"
    assert session.map_set_for("woods") == "wilds"
    assert session.same_map_set("town", "woods") is False
    assert "woods" not in session.maps["town"].linked_maps
    assert "town" not in session.maps["woods"].linked_maps
    assert session.active_map_set == "root"


def test_unlisted_maps_fall_back_to_root(tmp_path: Path):
    _write_campaign(
        tmp_path,
        map_sets={"wilds": {"label": "Wilds", "maps": ["woods"]}},
    )
    session = Session(root_path=str(tmp_path))
    assert session.map_set_for("town") == ROOT_MAP_SET_ID
    assert session.map_set_for("woods") == "wilds"


def test_dual_placement_map_for_entity_prefers_active_set(tmp_path: Path):
    _write_campaign(
        tmp_path,
        map_sets={
            "root": {"label": "Town", "maps": ["town"]},
            "wilds": {"label": "Wilds", "maps": ["woods"]},
        },
    )
    session = Session(root_path=str(tmp_path))
    pc = PlayerCharacter.load(session, "characters/high_elf_fighter")
    session.maps["town"].add(pc, 1, 1, group="a")
    place_entity_instance(session, pc, session.maps["woods"], 2, 2, group="a")

    assert pc in session.maps["town"].entities
    assert pc in session.maps["woods"].entities
    session.active_map_set = "root"
    assert session.map_for_entity(pc).name == "town"
    session.active_map_set = "wilds"
    assert session.map_for_entity(pc).name == "woods"
    maps = {m.name for m in session.maps_for_entity(pc)}
    assert maps == {"town", "woods"}


def test_teleporter_refuses_cross_set(tmp_path: Path):
    _write_campaign(
        tmp_path,
        map_sets={
            "root": {"label": "Town", "maps": ["town"]},
            "wilds": {"label": "Wilds", "maps": ["woods"]},
        },
    )
    session = Session(root_path=str(tmp_path))
    pc = PlayerCharacter.load(session, "characters/high_elf_fighter")
    town = session.maps["town"]
    town.add(pc, 0, 0, group="a")
    tp = Teleporter(session, town, {
        "name": "gate",
        "label": "Bad Gate",
        "target_map": "woods",
        "target_position": [1, 1],
    })
    tp.on_enter(pc, town)
    assert pc in town.entities
    assert pc not in session.maps["woods"].entities


def test_place_party_does_not_remove_other_set_instance(tmp_path: Path):
    _write_campaign(
        tmp_path,
        map_sets={
            "root": {"label": "Town", "maps": ["town"]},
            "wilds": {"label": "Wilds", "maps": ["woods"]},
        },
    )
    session = Session(root_path=str(tmp_path))
    pc = PlayerCharacter.load(session, "characters/high_elf_fighter")
    session.maps["town"].add(pc, 1, 1, group="a")
    placed = place_party_on_map(session, "woods", x=2, y=2, players=[pc], include_companions=False)
    assert placed
    assert pc in session.maps["town"].entities
    assert list(session.maps["town"].position_of(pc)) == [1, 1]
    assert pc in session.maps["woods"].entities


def test_serialize_duplicate_uid_as_stub(tmp_path: Path):
    _write_campaign(
        tmp_path,
        map_sets={
            "root": {"label": "Town", "maps": ["town"]},
            "wilds": {"label": "Wilds", "maps": ["woods"]},
        },
    )
    session = Session(root_path=str(tmp_path))
    pc = PlayerCharacter.load(session, "characters/high_elf_fighter")
    session.maps["town"].add(pc, 1, 1, group="a")
    place_entity_instance(session, pc, session.maps["woods"], 2, 2, group="a")
    blob = Serialization().serialize(session, None, session.maps)
    assert "_entity_uid" in blob or str(pc.entity_uid) in blob
    new_session, _battle, maps = Serialization().deserialize(blob)
    new_session.active_map_set = "root"
    restored = None
    for battle_map in maps.values():
        for ent in battle_map.entities:
            if str(getattr(ent, "entity_uid", "")) == str(pc.entity_uid):
                restored = ent
                break
    assert restored is not None
    assert restored in maps["town"].entities
    assert restored in maps["woods"].entities


def test_validator_cross_map_set_teleporter(tmp_path: Path):
    town = MIN_MAP.format(name="town").replace(
        "legend: {}",
        """legend:
  T:
    type: teleporter
    name: Gate
    target_map: woods
    target_position: [1, 1]
""",
    )
    town += """
map:
  illumination: 1.0
  base:
    - "T..."
    - "...."
    - "...."
    - "...."
"""
    # The replace above may have duplicated map: — write a clean town file instead.
    town = """
name: town
map:
  illumination: 1.0
  base:
    - "T..."
    - "...."
    - "...."
    - "...."
legend:
  T:
    type: teleporter
    name: Gate
    target_map: woods
    target_position: [1, 1]
player: []
npc: []
"""
    _write_campaign(
        tmp_path,
        map_sets={
            "root": {"label": "Town", "maps": ["town"]},
            "wilds": {"label": "Wilds", "maps": ["woods"]},
        },
        extra_town=town,
    )
    report = validate_campaign(tmp_path, ValidateOptions(static_only=True, skip_formatting=True))
    codes = [issue.code for issue in report.issues]
    assert "cross_map_set" in codes


def test_registry_assign_and_config_roundtrip():
    registry = MapSetRegistry.from_game_config(
        {"map_sets": {"root": {"maps": ["a"]}}},
        {"a": object(), "b": object()},
    )
    assert registry.set_for_map("b") == ROOT_MAP_SET_ID
    registry.ensure_set("wilds", label="Wilds")
    registry.assign_map("b", "wilds")
    cfg = registry.to_game_config()
    assert "b" in cfg["wilds"]["maps"]
    assert "b" not in cfg["root"]["maps"]


def test_event_teleport_refuses_cross_set(tmp_path: Path):
    from natural20.concern.generic_event_handler import GenericEventHandler

    _write_campaign(
        tmp_path,
        map_sets={
            "root": {"label": "Town", "maps": ["town"]},
            "wilds": {"label": "Wilds", "maps": ["woods"]},
        },
    )
    session = Session(root_path=str(tmp_path))
    pc = PlayerCharacter.load(session, "characters/high_elf_fighter")
    town = session.maps["town"]
    town.add(pc, 1, 1, group="a")
    handler = GenericEventHandler(session, town, {
        "teleport": {"map": "woods", "pos": [2, 2]},
    })
    handler.handle(pc)
    assert pc in town.entities
    assert pc not in session.maps["woods"].entities


def test_validator_split_map_stack(tmp_path: Path):
    _write_campaign(
        tmp_path,
        map_sets={
            "root": {"label": "Town", "maps": ["town"]},
            "wilds": {"label": "Wilds", "maps": ["woods"]},
        },
    )
    game_path = tmp_path / "game.yml"
    game = yaml.safe_load(game_path.read_text(encoding="utf-8"))
    game["map_stacks"] = {
        "bad_stack": {
            "base": "town",
            "floors": [{"map": "woods", "anchor": [0, 0]}],
        }
    }
    game_path.write_text(yaml.safe_dump(game, sort_keys=False), encoding="utf-8")
    report = validate_campaign(tmp_path, ValidateOptions(static_only=True, skip_formatting=True))
    codes = [issue.code for issue in report.issues]
    assert "cross_map_set" in codes


def test_validator_floor_stack_other_set(tmp_path: Path):
    woods = """
name: woods
floor:
  stack: town_stack
  role: overlay
map:
  illumination: 1.0
  base:
    - "...."
    - "...."
    - "...."
    - "...."
legend: {}
player: []
npc: []
"""
    _write_campaign(
        tmp_path,
        map_sets={
            "root": {"label": "Town", "maps": ["town"]},
            "wilds": {"label": "Wilds", "maps": ["woods"]},
        },
        extra_woods=woods,
    )
    game_path = tmp_path / "game.yml"
    game = yaml.safe_load(game_path.read_text(encoding="utf-8"))
    game["map_stacks"] = {
        "town_stack": {
            "base": "town",
            "floors": [],
        }
    }
    game_path.write_text(yaml.safe_dump(game, sort_keys=False), encoding="utf-8")
    report = validate_campaign(tmp_path, ValidateOptions(static_only=True, skip_formatting=True))
    codes = [issue.code for issue in report.issues]
    assert "cross_map_set" in codes


def test_unique_npc_map_for_entity_uses_active_set(tmp_path: Path):
    _write_campaign(
        tmp_path,
        map_sets={
            "root": {"label": "Town", "maps": ["town"]},
            "wilds": {"label": "Wilds", "maps": ["woods"]},
        },
    )
    session = Session(root_path=str(tmp_path))
    npc = session.npc("goblin", {"name": "Rose", "overrides": {"entity_uid": "rose_durst"}})
    npc.entity_uid = "rose_durst"
    session.register_entity(npc)
    session.maps["town"].add(npc, 1, 1, group="b")
    place_entity_instance(session, npc, session.maps["woods"], 2, 2, group="b")
    session.active_map_set = "root"
    assert session.map_for_entity(npc).name == "town"
    session.active_map_set = "wilds"
    assert session.map_for_entity(npc).name == "woods"


def test_companion_place_party_stays_in_set(tmp_path: Path):
    _write_campaign(
        tmp_path,
        map_sets={
            "root": {"label": "Town", "maps": ["town"]},
            "wilds": {"label": "Wilds", "maps": ["woods"]},
        },
    )
    session = Session(root_path=str(tmp_path))
    pc = PlayerCharacter.load(session, "characters/high_elf_fighter")
    companion = session.npc("goblin", {"name": "Sheep", "overrides": {"entity_uid": "party_sheep"}})
    companion.entity_uid = "party_sheep"
    session.register_entity(companion)
    session.maps["town"].add(pc, 1, 1, group="a")
    session.maps["town"].add(companion, 2, 1, group="a")
    session.game_properties = dict(session.game_properties or {})
    session.game_properties["companions"] = [{"entity_uid": "party_sheep"}]
    place_party_on_map(session, "woods", x=2, y=2, players=[pc], include_companions=True)
    assert companion in session.maps["town"].entities
    assert companion in session.maps["woods"].entities
    assert pc in session.maps["town"].entities


def test_battle_maps_from_session_dict_are_active_set(tmp_path: Path):
    from natural20.battle import Battle

    _write_campaign(
        tmp_path,
        map_sets={
            "root": {"label": "Town", "maps": ["town"]},
            "wilds": {"label": "Wilds", "maps": ["woods"]},
        },
    )
    session = Session(root_path=str(tmp_path))
    session.active_map_set = "root"
    battle = Battle(session, session.maps)
    names = {getattr(m, "name", None) for m in battle.maps}
    assert "town" in names
    assert "woods" not in names


def test_active_map_set_roundtrips_in_session_dict(tmp_path: Path):
    _write_campaign(
        tmp_path,
        map_sets={
            "root": {"label": "Town", "maps": ["town"]},
            "wilds": {"label": "Wilds", "maps": ["woods"]},
        },
    )
    session = Session(root_path=str(tmp_path))
    session.active_map_set = "wilds"
    blob = session.to_dict()
    assert blob["active_map_set"] == "wilds"
    restored = Session.from_dict(blob)
    assert restored.active_map_set == "wilds"
