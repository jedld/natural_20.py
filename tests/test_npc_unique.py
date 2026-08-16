"""Unique NPC detection and spawn-or-move on a map set."""

from __future__ import annotations

from pathlib import Path

import yaml

from natural20.map_set import spawn_or_move_npc, unique_npc_uid_for_type
from natural20.npc import authored_unique_entity_uid, is_unique_npc_properties
from natural20.session import Session

from tests.test_map_set import _write_campaign


def test_authored_unique_entity_uid_requires_stable_id():
    assert authored_unique_entity_uid({"entity_uid": "npc_ireena"}) == "npc_ireena"
    assert authored_unique_entity_uid({"uid": "npc_strahd_zombie"}) is None
    assert authored_unique_entity_uid({"unique": True, "uid": "npc_mayor"}) == "npc_mayor"
    assert authored_unique_entity_uid(
        {"entity_uid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}
    ) is None
    assert is_unique_npc_properties({"unique": True}) is True
    assert is_unique_npc_properties({"kind": "Goblin"}) is False


def _write_unique_npc(root: Path, name: str = "named_scout", uid: str = "named_scout"):
    npc_dir = root / "npcs"
    npc_dir.mkdir(exist_ok=True)
    (npc_dir / f"{name}.yml").write_text(
        yaml.safe_dump(
            {
                "kind": "Named Scout",
                "entity_uid": uid,
                "label": "Named Scout",
                "size": "medium",
                "default_ac": 13,
                "max_hp": 7,
                "hp_die": "2d6",
                "speed": 30,
                "cr": 0.125,
                "ability": {
                    "str": 8,
                    "dex": 14,
                    "con": 10,
                    "int": 10,
                    "wis": 8,
                    "cha": 8,
                },
                "actions": [
                    {
                        "name": "scimitar",
                        "type": "melee_attack",
                        "range": 5,
                        "targets": 1,
                        "attack": 4,
                        "damage": 5,
                        "damage_die": "1d6+2",
                        "damage_type": "slashing",
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_spawn_or_move_unique_npc_moves_within_map_set(tmp_path: Path):
    _write_campaign(
        tmp_path,
        map_sets={
            "root": {"label": "Town", "maps": ["town", "woods"]},
        },
    )
    _write_unique_npc(tmp_path)
    session = Session(root_path=str(tmp_path))
    assert unique_npc_uid_for_type(session, "named_scout") == "named_scout"

    first = spawn_or_move_npc(session, "named_scout", session.maps["town"], 1, 1)
    assert first["moved"] is False
    npc = session.entity_by_uid("named_scout")
    assert npc in session.maps["town"].entities
    assert list(session.maps["town"].position_of(npc)) == [1, 1]

    moved = spawn_or_move_npc(session, "named_scout", session.maps["woods"], 2, 2)
    assert moved["moved"] is True
    assert moved["from_map"] == "town"
    assert moved["entity_uid"] == "named_scout"
    assert npc not in session.maps["town"].entities
    assert npc in session.maps["woods"].entities
    assert list(session.maps["woods"].position_of(npc)) == [2, 2]


def test_generic_npc_spawn_creates_new_instance(tmp_path: Path):
    _write_campaign(tmp_path)
    session = Session(root_path=str(tmp_path))
    first = spawn_or_move_npc(session, "goblin", session.maps["town"], 1, 1)
    second = spawn_or_move_npc(session, "goblin", session.maps["town"], 2, 2)
    assert first["moved"] is False
    assert second["moved"] is False
    assert first["entity_uid"] != second["entity_uid"]
    assert len([e for e in session.maps["town"].entities]) >= 2
