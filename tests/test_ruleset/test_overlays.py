"""Ruleset YAML overlay loading for classes and backgrounds."""

import shutil
from pathlib import Path

import yaml

from natural20.session import Session

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


def test_fighter_overlay_adds_weapon_mastery(tmp_path):
    root = _campaign(tmp_path, "5e-2024")
    # Campaign-local class files shadow overlays; remove so SRD overlay applies.
    fighter_local = root / "char_classes" / "fighter.yml"
    if fighter_local.is_file():
        fighter_local.unlink()
    session = Session(str(root))
    fighter = session.load_class("fighter")
    assert "weapon_mastery" in (fighter.get("class_features") or [])


def test_soldier_background_has_attribute_bonus_2024(tmp_path):
    root = _campaign(tmp_path, "5e-2024")
    soldier_local = root / "backgrounds" / "soldier.yml"
    if soldier_local.is_file():
        soldier_local.unlink()
    session = Session(str(root))
    backgrounds = session.load_backgrounds()
    soldier = backgrounds.get("soldier") or {}
    assert soldier.get("attribute_bonus", {}).get("str") == 2
    assert soldier.get("origin_feat") == "alert"


def test_soldier_background_no_asi_2014(tmp_path):
    root = _campaign(tmp_path, "5e-2014")
    soldier_local = root / "backgrounds" / "soldier.yml"
    if soldier_local.is_file():
        soldier_local.unlink()
    session = Session(str(root))
    backgrounds = session.load_backgrounds()
    soldier = backgrounds.get("soldier") or {}
    assert not soldier.get("attribute_bonus")
