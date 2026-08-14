"""Tests for campaign-scoped ruleset factory and Session wiring."""

import shutil
from pathlib import Path

import yaml

from natural20.ruleset import get_ruleset
from natural20.ruleset.factory import normalize_ruleset_id
from natural20.ruleset.ruleset_2014 import Ruleset2014
from natural20.ruleset.ruleset_2024 import Ruleset2024
from natural20.session import Session
from natural20.yaml_loader import campaign_ruleset_id, ruleset_overlay_root

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_normalize_ruleset_id():
    assert normalize_ruleset_id(None) == "5e-2014"
    assert normalize_ruleset_id("2024") == "5e-2024"
    assert normalize_ruleset_id("srd-5.2") == "5e-2024"
    assert normalize_ruleset_id("bogus") == "5e-2014"


def test_factory_defaults():
    r = get_ruleset(None)
    assert isinstance(r, Ruleset2014)
    assert r.name == "5e-2014"
    assert r.weapon_mastery_enabled() is False
    assert r.heroic_inspiration_enabled() is False
    assert r.ability_bonus_source() == "species"
    assert r.d20_test_exhaustion_penalty(3) == 0


def test_factory_2024_hooks():
    r = get_ruleset("5e-2024")
    assert isinstance(r, Ruleset2024)
    assert r.name == "5e-2024"
    assert r.weapon_mastery_enabled() is True
    assert r.heroic_inspiration_enabled() is True
    assert r.ability_bonus_source() == "background"
    assert r.hp_per_level_strategy() == "average"
    assert r.surprise_model() == "initiative_disadvantage"
    assert r.counterspell_resolution() == "caster_con_save"
    assert r.paladin_smite_is_spell() is True
    assert r.phb_2024_grapple_move_cost() is True
    assert r.d20_test_exhaustion_penalty(3) == -6
    assert "grapple" in r.unarmed_strike_modes()


def test_ruleset_overrides():
    r = get_ruleset("5e-2014", overrides={"weapon_mastery_enabled": True})
    assert r.weapon_mastery_enabled() is True
    assert r.name == "5e-2014"


def _campaign_with_ruleset(tmp_path: Path, ruleset: str | None) -> Path:
    """Copy tests/fixtures campaign and optionally set ruleset in game.yml."""
    dest = tmp_path / "campaign"
    shutil.copytree(
        FIXTURES,
        dest,
        ignore=shutil.ignore_patterns("tmp", "__pycache__", "*.pyc"),
    )
    game_path = dest / "game.yml"
    with game_path.open("r", encoding="utf-8") as fh:
        game = yaml.safe_load(fh) or {}
    if ruleset is None:
        game.pop("ruleset", None)
    else:
        game["ruleset"] = ruleset
    with game_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(game, fh)
    return dest


def test_session_default_ruleset_2014(tmp_path):
    root = _campaign_with_ruleset(tmp_path, None)
    assert campaign_ruleset_id(root) == "5e-2014"
    session = Session(str(root))
    assert session.ruleset.name == "5e-2014"
    assert session.ruleset.weapon_mastery_enabled() is False


def test_session_ruleset_from_game_yml(tmp_path):
    root = _campaign_with_ruleset(tmp_path, "5e-2024")
    assert campaign_ruleset_id(root) == "5e-2024"
    session = Session(str(root))
    assert session.ruleset.name == "5e-2024"
    assert session.ruleset.weapon_mastery_enabled() is True


def test_ruleset_overlay_root_exists():
    root = ruleset_overlay_root("5e-2024")
    assert root is not None
    assert root.is_dir()
    assert ruleset_overlay_root("5e-2014") is None


def test_session_to_dict_round_trip_keeps_campaign_ruleset(tmp_path):
    root = _campaign_with_ruleset(tmp_path, "5e-2024")
    session = Session(str(root))
    data = session.to_dict()
    restored = Session.from_dict(data)
    assert restored.ruleset.name == "5e-2024"
