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
    assert out["xp"] == int(payload.get("currentXp") or 0)
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
    # Polymorph is now a known spell (PolymorphSpell registered in spell_loader)
    # and is marked prepared=true in the dndbeyond_wizard.json fixture
    assert "polymorph" in out["spellbook"]
    assert "polymorph" in out["prepared_spells"]


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
    # Single-class Paladin 5 -> caster level 3 (rounded up) -> 4/2
    assert out["spell_slots"] == {"paladin": {1: 4, 2: 2}}


def test_single_class_ranger_slots_round_up():
    imp = BeyondImporter()
    assert imp._compute_spell_slots({"ranger": 11}, {}) == {"ranger": {1: 4, 2: 3, 3: 3}}
    assert imp._compute_spell_slots({"ranger": 1}, {}) == {}


def test_token_alignment_entity_uid_defaults(importer, payload):
    out = importer.convert_to_yaml(payload)
    assert out["token"] == ["A"]
    assert out["alignment"] == "neutral_good"
    assert out["entity_uid"] == "ddb-999001"
    assert out["group"] == "a"
    assert out["hit_die"] == "inherit"


def test_structured_personality_and_physical_fields(importer, payload):
    payload = dict(payload)
    payload.update({
        "faith": "Corellon",
        "age": "102",
        "hair": "Silver",
        "eyes": "Green",
        "skin": "Pale",
        "height": "5'4\"",
        "weight": "90 lb",
        "traits": {
            "appearance": "A tall elf in blue robes.",
            "personalityTraits": [{"description": "I love arcane mysteries."}],
            "ideals": [{"description": "Knowledge is power."}],
            "bonds": [{"description": "My spellbook is sacred."}],
            "flaws": [{"description": "I hoard secrets."}],
        },
        "notes": {"backstory": "Studied at a tower."},
    })
    out = importer.convert_to_yaml(payload)
    assert out["outward_appearance"] == "A tall elf in blue robes."
    assert out["personality_traits"] == "I love arcane mysteries."
    assert out["ideals"] == "Knowledge is power."
    assert out["bonds"] == "My spellbook is sacred."
    assert out["flaws"] == "I hoard secrets."
    assert out["backstory"] == "Studied at a tower."
    assert out["faith"] == "Corellon"
    assert out["eyes"] == "Green"


def test_extract_avatar_urls_prefers_character_decorations():
    from beyond_importer import extract_avatar_urls, _resize_ddb_avatar_url

    data = {
        "decorations": {
            "avatarUrl": "https://www.dndbeyond.com/avatars/10/83/636339381554374819.png?width=150&height=150&fit=crop",
        },
        "race": {
            "portraitAvatarUrl": "https://www.dndbeyond.com/avatars/9/383/636327460327748907.jpeg?width=1000&height=1000&fit=bounds",
        },
    }
    portrait, token = extract_avatar_urls(data)
    assert portrait == _resize_ddb_avatar_url(
        data["decorations"]["avatarUrl"], width=1000, height=1000, fit="bounds"
    )
    assert token == _resize_ddb_avatar_url(
        data["decorations"]["avatarUrl"], width=256, height=256, fit="crop"
    )


def test_extract_avatar_urls_falls_back_to_race_portrait():
    from beyond_importer import extract_avatar_urls

    data = {
        "decorations": {},
        "race": {
            "portraitAvatarUrl": "https://www.dndbeyond.com/avatars/9/383/portrait.jpeg?width=1000&height=1000&fit=bounds",
        },
    }
    portrait, token = extract_avatar_urls(data)
    assert portrait is not None
    assert "portrait.jpeg" in portrait
    assert token is not None


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
    assert "boots_of_striding_and_springing" in items
    assert "magic_missile" in spells
    assert "booming_blade" in spells


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
    assert "boots_of_striding_and_springing" in types
    assert "instrument_of_illusions" in types
    assert "mawsse" in types
    assert "booming_blade" in out["cantrips"]
    assert out["maneuvers"] == ["disarming_attack", "riposte"]
    assert out["superiority_die"] == "1d6"
    assert out["superiority_dice"] == 1
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


def _inv(name, *, equipped=False, qty=1, armor_type=None, magic=False,
         attuned=False, ac=None):
    definition = {"name": name, "magic": magic}
    if armor_type is not None:
        definition["armorTypeId"] = armor_type
    if ac is not None:
        definition["armorClass"] = ac
    return {"definition": definition, "equipped": equipped, "quantity": qty,
            "isAttuned": attuned}


def test_inventory_resolves_magic_variants_and_merges_stacks(importer):
    payload = {
        "inventory": [
            _inv("Shield, +1", equipped=True, armor_type=4),
            _inv("Dragon Scale Mail (Bronze)", equipped=True, armor_type=2,
                 magic=True, attuned=True, ac=14),
            _inv("Plate Armor", equipped=True, armor_type=3, ac=18),
            _inv("Class Feature: Sacred Weapon"),
            _inv("Rations", qty=18),
            _inv("Rations", qty=5),
            _inv("Oil", qty=7),
        ],
        "currencies": {"cp": 10, "sp": 0, "gp": 1288, "ep": 0, "pp": 0},
    }
    equipped, inventory = importer._extract_inventory(payload)
    stacks = {entry["type"]: entry["qty"] for entry in inventory}

    assert equipped == ["dragon_scale_mail_bronze", "shield_plus_one"]
    assert stacks["plate"] == 1
    assert stacks["rations"] == 23
    assert stacks["oil_flask"] == 7
    assert stacks["gold_piece"] == 1288
    assert stacks["copper_piece"] == 10
    assert not any("sacred_weapon" in w for w in importer.warnings)


def test_item_aliases_for_ddb_crossbow_and_gear_names():
    import beyond_importer as bi

    known = bi._load_known_items()
    assert bi._resolve_item_slug("Crossbow, Light", known) == "light_crossbow"
    assert bi._resolve_item_slug("Crossbow, Heavy", known) == "heavy_crossbow"
    assert bi._resolve_item_slug("Robe", known) == "robes"
    for name, slug in [
        ("Flask", "flask"), ("Shovel", "shovel"), ("Amber", "amber"),
        ("Pearl", "pearl"), ("Alchemist's Fire", "alchemists_fire"),
        ("Alchemist's Supplies", "alchemists_supplies"),
        ("Tinker's Tools", "tinkers_tools"), ("Smith's Tools", "smiths_tools"),
        ("Calligrapher's Supplies", "calligraphers_supplies"),
    ]:
        assert bi._resolve_item_slug(name, known) == slug


def test_mithral_armor_names_map_to_mithral_variants():
    import beyond_importer as bi

    known = bi._load_known_items()
    assert bi._resolve_item_slug("Mithral Breastplate", known) == "mithral_breastplate"
    assert bi._resolve_item_slug("Mithral Plate Armor", known) == "mithral_plate"
    assert bi._resolve_item_slug("Mithral Half Plate Armor", known) == "mithral_half_plate"
    assert bi._resolve_item_slug("Mithral Armor (Chain Mail)", known) == "mithral_chain_mail"
    assert bi._resolve_item_slug("Mithral Splint Armor", known) == "mithral_splint"


def test_mithral_template_drops_stealth_disadvantage():
    from natural20.event_manager import EventManager
    from natural20.session import Session

    session = Session(root_path="tests/fixtures", event_manager=EventManager())
    plate = session.load_equipment("mithral_plate")
    assert plate["ac"] == 18 and plate["subtype"] == "heavy"
    assert plate["stealth_disadvantage"] is False
    assert plate["magical"] is True
    shirt = session.load_equipment("mithral_chain_shirt")
    assert shirt["ac"] == 13 and shirt["subtype"] == "medium"


def test_bracketed_count_prefix_is_stripped_from_item_slug(importer):
    assert _item_slug_from_name("[5] Elixir of Flight") == "elixir_of_flight"
    assert _item_slug_from_name("[12]Potion of Healing") == "healing_potion"
    payload = {"inventory": [_inv("[5] Elixir of Flight", qty=0),
                             _inv("[2] Potion of Healing", qty=2)]}
    _, inventory = importer._extract_inventory(payload)
    stacks = {entry["type"]: entry["qty"] for entry in inventory}
    assert stacks == {"healing_potion": 2}


def test_platinum_and_electrum_currency_imported(importer):
    payload = {"inventory": [],
               "currencies": {"cp": 0, "sp": 1, "gp": 0, "ep": 3, "pp": 124}}
    _, inventory = importer._extract_inventory(payload)
    stacks = {entry["type"]: entry["qty"] for entry in inventory}
    assert stacks == {"silver_piece": 1, "electrum_piece": 3, "platinum_piece": 124}
    assert not any("currency not imported" in w for w in importer.warnings)


def test_equipped_mithral_armor_and_crossbow_stay_equipped(importer):
    payload = {"inventory": [
        _inv("Mithral Breastplate", equipped=True, armor_type=2, magic=True, ac=14),
        _inv("Studded Leather", armor_type=1, ac=12),
        _inv("Shield", equipped=True, armor_type=4),
        _inv("Crossbow, Light", equipped=True),
    ]}
    equipped, _ = importer._extract_inventory(payload)
    assert equipped[0] == "mithral_breastplate"
    assert "light_crossbow" in equipped
    assert "shield" in equipped


def test_weapon_masteries_from_feat_options(importer):
    payload = {"options": {"feat": [
        {"definition": {"name": "Warhammer (Push)"}},
        {"definition": {"name": "Lance (Topple)"}},
        {"definition": {"name": "Hill's Tumble (Hill Giant)"}},
    ]}}
    assert importer._extract_weapon_masteries(payload) == ["push", "topple"]


def test_campaign_root_makes_campaign_items_known(tmp_path):
    import beyond_importer as bi

    items_dir = tmp_path / "items"
    items_dir.mkdir()
    (items_dir / "magic_items.yml").write_text(
        "relic_lance:\n  name: Relic Lance\n  type: melee_attack\n  subtype: weapon\n"
    )
    (tmp_path / "game.yml").write_text("name: t\n")
    known = bi._load_known_items(str(tmp_path))
    assert "relic_lance" in known
    assert "longsword" in known
    assert bi._resolve_item_slug("Relic Lance (Lance)", known) == "relic_lance"


def test_2024_ancestry_read_from_race_options(importer):
    data = {"race": {"fullName": "Goliath", "baseName": "Goliath"},
            "options": {"race": [{"definition": {"name": "Increase two scores (+2 / +1)"}},
                                 {"definition": {"name": "Hill's Tumble (Hill Giant)"}}]}}
    assert importer._extract_race(data) == ("goliath", "hill_giant")


def test_condition_immunities_skip_restricted(importer):
    mods = [
        {"type": "immunity", "subType": "frightened"},
        {"type": "immunity", "subType": "charmed", "restriction": "while within 10 ft"},
        {"type": "immunity", "subType": "poison"},
    ]
    assert importer._extract_condition_immunities(mods) == ["frightened"]


def test_edition_overrides_for_2024_paladin_in_2014_campaign(tmp_path):
    (tmp_path / "game.yml").write_text("name: t\nruleset: 5e-2014\n")
    imp = BeyondImporter(campaign_root=str(tmp_path))
    src_2024 = [{"sourceId": 145}]
    data = {
        "feats": [{"definition": {"name": "Great Weapon Master", "sources": src_2024}},
                  {"definition": {"name": "Alert", "sources": src_2024}}],
        "classes": [{"level": 11, "definition": {"name": "Paladin", "sources": src_2024},
                     "classFeatures": [
                         {"definition": {"name": "Abjure Foes", "requiredLevel": 9}},
                         {"definition": {"name": "Radiant Strikes", "requiredLevel": 11}},
                         {"definition": {"name": "Aura of Courage", "requiredLevel": 10}},
                         {"definition": {"name": "Restoring Touch", "requiredLevel": 14}},
                     ]}],
    }
    out = imp._edition_overrides(data, {"paladin": 11})
    assert out["feat_editions"] == {"great_weapon_master": "5e-2024"}
    assert {"abjure_foes", "radiant_strikes"} <= set(out["class_features"])
    assert out["channel_divinity_uses"] == 3


def test_edition_overrides_noop_on_2024_campaign(tmp_path):
    (tmp_path / "game.yml").write_text("name: t\nruleset: 5e-2024\n")
    imp = BeyondImporter(campaign_root=str(tmp_path))
    data = {"classes": [{"level": 11, "definition": {"name": "Paladin", "sources": [{"sourceId": 145}]}}]}
    assert imp._edition_overrides(data, {"paladin": 11}) == {}


def _artificer_campaign(tmp_path, ruleset="5e-2014"):
    (tmp_path / "game.yml").write_text(f"name: t\nruleset: {ruleset}\n")
    (tmp_path / "index.json").write_text(json.dumps({
        "tile_size": 70, "title": "t", "logins": [], "default_controllers": [],
        "expansion_packs": {"tashas_cauldron": "tashas_cauldron"},
    }))
    return BeyondImporter(campaign_root=str(tmp_path))


def test_2024_gnome_gets_race_edition_and_lineage(tmp_path):
    imp = _artificer_campaign(tmp_path)
    data = {"race": {"fullName": "Gnome", "baseName": "Gnome", "sources": [{"sourceId": 145}]},
            "options": {"race": [{"definition": {"name": "Rock Gnome"}}]}}
    assert imp._extract_race(data) == ("gnome", "rock_gnome")
    assert imp._race_edition(data["race"], "gnome") == "5e-2024"


def test_2024_gnome_has_no_race_edition_in_2024_campaign(tmp_path):
    imp = _artificer_campaign(tmp_path, ruleset="5e-2024")
    assert imp._race_edition({"sources": [{"sourceId": 145}]}, "gnome") is None


def test_spell_abilities_from_race_and_feat_spells(tmp_path):
    imp = _artificer_campaign(tmp_path)
    data = {"spells": {
        "class": [{"definition": {"name": "Fire Bolt"}, "spellCastingAbilityId": 4}],
        "race": [{"definition": {"name": "Prestidigitation"}, "spellCastingAbilityId": 4}],
        "feat": [{"definition": {"name": "Shield"}, "spellCastingAbilityId": 4}],
    }}
    out = imp._extract_spell_abilities(data)
    assert out == {"prestidigitation": "intelligence", "shield": "intelligence"}


def test_data_driven_artificer_slots_round_half_up(tmp_path):
    imp = _artificer_campaign(tmp_path)
    assert imp._class_yaml("artificer").get("subclass_property") == "artificer_specialist"
    assert imp._compute_spell_slots({"artificer": 11}, {}) == {"artificer": {1: 4, 2: 3, 3: 3}}


def test_dancing_sword_ioun_stone_and_gear_names_resolve():
    import beyond_importer as bi

    known = bi._load_known_items()
    for name, slug in [
        ("Dancing Scimitar", "dancing_scimitar"), ("Dancing Longsword", "dancing_longsword"),
        ("Dancing Rapier", "dancing_rapier"), ("Ioun Stone of Insight", "ioun_stone_of_insight"),
        ("Ioun Stone of Mastery", "ioun_stone_of_mastery"), ("Dragonchess Set", "dragonchess_set"),
        ("Three-Dragon Ante Set", "three_dragon_ante_set"), ("Playing Card Set", "playing_card_set"),
        ("Dice Set", "dice_set"), ("Sprig of Mistletoe", "sprig_of_mistletoe"),
        ("Yew Wand", "yew_wand"), ("Wooden Staff", "wooden_staff"), ("Totem", "totem"),
    ]:
        assert bi._resolve_item_slug(name, known) == slug


def test_attuned_items_are_recorded(importer):
    payload = {"inventory": [
        {"definition": {"name": "Ioun Stone of Insight", "canAttune": True, "id": 9228794},
         "equipped": True, "isAttuned": True, "quantity": 1},
        {"definition": {"name": "Dancing Scimitar", "canAttune": True, "id": 4867},
         "equipped": True, "isAttuned": False, "quantity": 1},
    ]}
    equipped, _ = importer._extract_inventory(payload)
    assert equipped == ["ioun_stone_of_insight", "dancing_scimitar"]
    assert importer.attuned_items == ["ioun_stone_of_insight"]


def test_engine_applied_item_ability_bonus_is_not_double_counted(importer):
    data = {
        "stats": [{"id": i, "value": v} for i, v in enumerate([13, 15, 12, 8, 15, 8], start=1)],
        "bonusStats": [], "overrideStats": [],
        "inventory": [
            {"definition": {"name": "Ioun Stone of Insight", "canAttune": True, "id": 9228794},
             "equipped": True, "isAttuned": True, "quantity": 1},
            {"definition": {"name": "Mysterious Charm", "id": 77},
             "equipped": True, "quantity": 1},
        ],
        "modifiers": {
            "item": [
                {"type": "bonus", "subType": "wisdom-score", "value": 2, "componentId": 9228794},
                {"type": "bonus", "subType": "charisma-score", "value": 1, "componentId": 77},
            ],
            "feat": [{"type": "bonus", "subType": "wisdom-score", "value": 2, "componentId": 1}],
        },
    }
    modifiers = importer._iter_modifiers(data)
    sheet = importer._extract_ability_scores(data, modifiers)
    base = importer._extract_ability_scores(
        data, modifiers, skip_item_ids=importer._engine_ability_item_ids(data))
    assert sheet["wis"] == 19
    assert base["wis"] == 17
    assert base["cha"] == 9
