"""Tests for the D&D Beyond importer."""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from beyond_importer import (  # noqa: E402
    BeyondImporter,
    _item_slug_from_name,
    _load_known_items,
    _load_known_spells,
    _normalize_background,
    _slug,
    parse_character_id_from_url,
)

FIXTURE = ROOT / "tests" / "fixtures" / "dndbeyond_wizard.json"
FULL_FIXTURE = ROOT / "tests" / "fixtures" / "dndbeyond.json"


@pytest.fixture
def payload():
    return json.loads(FIXTURE.read_text())


@pytest.fixture
def importer():
    import beyond_importer as bi

    bi._ITEM_CACHE = None
    bi._SPELL_CACHE = None
    return BeyondImporter()


def test_parse_character_id_from_url_accepts_common_links():
    assert parse_character_id_from_url(
        'https://www.dndbeyond.com/characters/14191568'
    ) == 14191568
    assert parse_character_id_from_url(
        'https://dndbeyond.com/characters/999001/'
    ) == 999001
    assert parse_character_id_from_url('not-a-url') is None


def test_slug_handles_apostrophes_and_punctuation():
    assert _slug("Thieves' Tools") == "thieves_tools"
    assert _slug("Cook's Utensils") == "cooks_utensils"
    assert _slug("High Elf") == "high_elf"
    assert _slug("  Multi   space  ") == "multi_space"


def test_race_split(importer, payload):
    out = importer.convert_to_yaml(payload)
    assert out["race"] == "elf"
    assert out["subrace"] == "high_elf"


def test_classes_and_subclass(importer, payload):
    out = importer.convert_to_yaml(payload)
    assert out["classes"] == {"wizard": 2}
    assert out["level"] == 2
    assert out["arcane_tradition"] == "school_of_evocation"
    assert out["background"] == "sage"


def test_multiclass_levels_are_summed(importer, payload):
    payload["classes"].append({
        "id": 2,
        "level": 3,
        "definition": {"name": "Fighter"},
    })
    out = importer.convert_to_yaml(payload)
    assert out["classes"] == {"wizard": 2, "fighter": 3}
    assert out["level"] == 5


def test_ability_scores(importer, payload):
    out = importer.convert_to_yaml(payload)
    assert out["ability"] == {"str": 10, "dex": 14, "con": 14,
                              "int": 17, "wis": 12, "cha": 8}


def test_hp_math_uses_con_and_excludes_temp(importer, payload):
    out = importer.convert_to_yaml(payload)
    # con 14 -> +2; level 2 -> +4; base 12 + 0 + 4 = 16
    assert out["max_hp"] == 16
    assert out["hp"] == 16 - 3
    assert out["temporary_hp"] == 2


def test_skills_languages_saves_from_modifiers(importer, payload):
    out = importer.convert_to_yaml(payload)
    assert "perception" in out["skills"]
    assert "arcana" in out["skills"]
    assert "history" in out["skills"]
    assert "investigation" in out["skills"]
    assert sorted(out["languages"]) == ["common", "elvish", "goblin"]
    assert out["saving_throw_proficiencies"] == ["int", "wis"]
    assert "light_armor" in out["weapon_proficiencies"]


def test_inventory_filters_unknown_items_and_aliases(importer, payload):
    out = importer.convert_to_yaml(payload)
    types = sorted(i["type"] for i in out["inventory"])
    # Mysterious Trinket should be dropped, Potion of Healing aliased.
    assert "healing_potion" in types
    assert "spellbook" in types
    assert "dagger" in types
    assert "arcane_focus" in types
    assert "mysterious_trinket" not in types
    # Equipped only contains items flagged equipped in payload.
    assert out["equipped"] == ["dagger"]
    # Warning surfaced for the dropped item.
    assert any("mysterious_trinket" in w for w in importer.warnings)


def test_spell_buckets(importer, payload):
    out = importer.convert_to_yaml(payload)
    # Cantrips present
    assert "firebolt" in out["cantrips"]
    assert "mage_hand" in out["cantrips"]
    assert "true_strike" in out["cantrips"]  # from spells.race always-prepared
    # Prepared list only includes prepared leveled spells the engine knows
    assert "magic_missile" in out["prepared_spells"]
    assert "shield" in out["prepared_spells"]
    assert "mage_armor" not in out["prepared_spells"]  # not prepared in fixture
    # Spellbook holds all wizard spells regardless of prepared state
    assert "magic_missile" in out["spellbook"]
    assert "mage_armor" in out["spellbook"]
    # Polymorph is unknown to this engine build → dropped silently
    assert "polymorph" not in out["spellbook"]
    assert "polymorph" not in out["prepared_spells"]
    # And a warning was emitted for it
    assert any("polymorph" in w.lower() for w in importer.warnings)


def test_spell_slots_from_caster_level(importer, payload):
    out = importer.convert_to_yaml(payload)
    # Wizard 2 -> 3 first-level slots
    assert out["spell_slots"] == {"wizard": {1: 3}}


def test_warlock_pact_slots():
    importer = BeyondImporter()
    payload = {
        "name": "Pact",
        "stats": [{"id": i, "value": 10} for i in range(1, 7)],
        "bonusStats": [], "overrideStats": [],
        "race": {"fullName": "Human", "baseRaceName": "Human"},
        "classes": [
            {"id": 1, "level": 5, "definition": {"name": "Warlock"},
             "subclassDefinition": {"name": "The Fiend"}}
        ],
        "modifiers": {},
        "inventory": [],
        "classSpells": [],
        "spells": {},
        "baseHitPoints": 8,
    }
    out = importer.convert_to_yaml(payload)
    # Warlock 5 -> 2 third-level pact slots
    assert out["spell_slots"] == {"warlock": {3: 2}}
    assert out["otherworldly_patron"] == "the_fiend"


def test_paladin_half_caster_slots():
    importer = BeyondImporter()
    payload = {
        "name": "Pal",
        "stats": [{"id": i, "value": 10} for i in range(1, 7)],
        "bonusStats": [], "overrideStats": [],
        "race": {"fullName": "Human", "baseRaceName": "Human"},
        "classes": [
            {"id": 1, "level": 5, "definition": {"name": "Paladin"}}
        ],
        "modifiers": {}, "inventory": [], "classSpells": [], "spells": {},
        "baseHitPoints": 10,
    }
    out = importer.convert_to_yaml(payload)
    # Paladin 5 -> caster level 2 -> 3 first-level slots
    assert out["spell_slots"] == {"paladin": {1: 3}}


def test_token_alignment_entity_uid_defaults(importer, payload):
    out = importer.convert_to_yaml(payload)
    assert out["token"] == ["A"]
    assert out["alignment"] == "neutral_good"
    assert out["entity_uid"] == "ddb-999001"
    assert out["group"] == "a"
    assert out["hit_die"] == "inherit"


def test_load_character_accepts_dict_path_and_file(tmp_path, importer, payload):
    # dict
    assert importer.load_character(payload)["name"] == payload["name"]
    # path
    assert importer.load_character(str(FIXTURE))["name"] == payload["name"]
    # wrapped {"data": ...}
    wrapped = tmp_path / "wrapped.json"
    wrapped.write_text(json.dumps({"data": payload}))
    assert importer.load_character(str(wrapped))["name"] == payload["name"]


def test_unknown_item_warning_surfaces_via_warnings(payload):
    imp = BeyondImporter()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        imp.convert_to_yaml(payload)
    messages = " ".join(str(w.message) for w in caught)
    assert "mysterious_trinket" in messages


def test_known_items_and_spells_caches_populate():
    items = _load_known_items()
    spells = _load_known_spells()
    assert "dagger" in items
    assert "spellbook" in items
    assert "magic_missile" in spells


def test_item_slug_strips_magic_bonus_and_aliases_leather():
    assert _item_slug_from_name("Leather, +2") == "leather_armor"
    assert _item_slug_from_name("Scimitar, +1") == "scimitar"
    assert _item_slug_from_name("Rations (1 day)") == "rations"


def test_background_alias_maps_criminal_spy():
    assert _normalize_background("criminal_spy") == "criminal"


def test_full_fixture_imports_flavor_and_gear(tmp_path):
    importer = BeyondImporter()
    payload = json.loads(FULL_FIXTURE.read_text())["data"]
    out = importer.convert_to_yaml(payload)

    assert out["race"] == "halfling"
    assert out["subrace"] == "lightfoot"
    assert out["background"] == "criminal"
    assert out["roguish_archetype"] == "swashbuckler"
    assert "backstory" in out
    assert "Phandalin" in out["backstory"]
    assert "description" in out
    assert "Appearance: Cute" in out["description"]

    types = {entry["type"] for entry in out["inventory"]}
    assert "leather_armor" in types
    assert "scimitar" in types
    assert "crowbar" in types
    assert "waterskin" in types
    assert out["tool_proficiencies"] == out["tools"]


def test_sorcerer_known_spells_are_treated_as_prepared():
    importer = BeyondImporter()
    payload = {
        "name": "Sorcerer",
        "stats": [{"id": i, "value": 10} for i in range(1, 7)],
        "bonusStats": [], "overrideStats": [],
        "race": {"fullName": "Human", "baseRaceName": "Human"},
        "classes": [
            {"id": 1, "level": 3, "definition": {"name": "Sorcerer"}}
        ],
        "modifiers": {},
        "inventory": [],
        "classSpells": [{
            "characterClassId": 1,
            "spells": [
                {"prepared": False, "definition": {"name": "Fire Bolt", "level": 0}},
                {"prepared": False, "definition": {"name": "Magic Missile", "level": 1}},
            ],
        }],
        "spells": {},
        "baseHitPoints": 10,
    }
    out = importer.convert_to_yaml(payload)
    assert "firebolt" in out["cantrips"]
    assert "magic_missile" in out["prepared_spells"]


def test_cli_writes_yaml(tmp_path):
    from beyond_importer import main
    out = tmp_path / "char.yml"
    rc = main(["--input", str(FIXTURE), "--output", str(out)])
    assert rc == 0
    text = out.read_text()
    assert "race: elf" in text
    assert "subrace: high_elf" in text
    assert "wizard: 2" in text
