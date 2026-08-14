"""Weapon mastery and D20 Test ruleset integration tests."""

import shutil
from pathlib import Path

import yaml

from natural20.session import Session
from natural20.weapon_mastery import can_use_mastery, weapon_masteries
from natural20.yaml_loader import load_campaign_yaml

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _campaign(tmp_path, ruleset: str):
    dest = tmp_path / "campaign"
    shutil.copytree(
        FIXTURES,
        dest,
        ignore=shutil.ignore_patterns("tmp", "__pycache__", "*.pyc"),
    )
    game_path = dest / "game.yml"
    with game_path.open("r", encoding="utf-8") as fh:
        game = yaml.safe_load(fh) or {}
    game["ruleset"] = ruleset
    with game_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(game, fh)
    return dest


def test_weapons_overlay_adds_push_under_2024(tmp_path):
    root = _campaign(tmp_path, "5e-2024")
    weapons = load_campaign_yaml(root, "items", "weapons")
    assert "push" in weapon_masteries(weapons.get("pike"))
    assert "push" in weapon_masteries(weapons.get("warhammer"))
    assert "sap" in weapon_masteries(weapons.get("longsword"))


def test_weapons_mastery_inert_under_2014(tmp_path):
    root = _campaign(tmp_path, "5e-2014")
    session = Session(str(root))
    weapon = session.load_weapon("longsword")

    class E:
        def __init__(self, sess):
            self.session = sess
            self.properties = {"known_weapon_masteries": ["sap"]}

        def class_feature(self, _):
            return False

    assert can_use_mastery(E(session), weapon, "sap") is False


def test_exhaustion_d20_penalty_2024(tmp_path):
    root = _campaign(tmp_path, "5e-2024")
    session = Session(str(root))
    from natural20.player_character import PlayerCharacter

    fighter = PlayerCharacter.load(session, "high_elf_fighter.yml")
    fighter.set_exhaustion_level(2)
    assert fighter.d20_test_modifier() == -4
    # Saving throw modifier includes exhaustion
    roll = fighter.save_throw("strength")
    # Just ensure roll builds; modifier path exercised
    assert roll is not None


def test_exhaustion_no_penalty_2014(tmp_path):
    root = _campaign(tmp_path, "5e-2014")
    session = Session(str(root))
    from natural20.player_character import PlayerCharacter

    fighter = PlayerCharacter.load(session, "high_elf_fighter.yml")
    fighter.set_exhaustion_level(3)
    assert fighter.d20_test_modifier() == 0


def test_surprise_initiative_disadvantage_flag_2024(tmp_path):
    root = _campaign(tmp_path, "5e-2024")
    session = Session(str(root))
    from natural20.player_character import PlayerCharacter

    fighter = PlayerCharacter.load(session, "high_elf_fighter.yml")
    fighter.set_surprised(True)
    assert session.ruleset.surprise_model() == "initiative_disadvantage"
    # Smoke: rolls without error
    assert fighter.initiative() is not None
