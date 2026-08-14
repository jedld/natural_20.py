"""Ruleset-aware Counterspell and Divine Smite tests."""

import shutil
from pathlib import Path
from unittest.mock import MagicMock

import yaml

from natural20.actions.divine_smite_action import DivineSmiteAction
from natural20.controller import Controller
from natural20.session import Session
from natural20.spell.wizard_spells import CounterspellSpell
from natural20.yaml_loader import load_campaign_yaml

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _campaign(tmp_path, ruleset: str, *, drop_local_spells: bool = False):
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
    if drop_local_spells:
        local = dest / "items" / "spells.yml"
        if local.is_file():
            local.unlink()
    return dest


def _spell_action(target, at_level=3, target_spell_level=3, spellcasting_class=None):
    action = MagicMock()
    action.target = target
    action.at_level = at_level
    action.opts = {"target_spell_level": target_spell_level}
    action.spellcasting_class = spellcasting_class
    return action


def test_spells_overlay_updates_counterspell_and_smite(tmp_path):
    root = _campaign(tmp_path, "5e-2024", drop_local_spells=True)
    spells = load_campaign_yaml(root, "items", "spells")
    assert "Constitution saving throw" in (spells["counterspell"].get("description") or "")
    assert spells["divine_smite"].get("casting_time") == "1:bonus"
    assert "verbal" in (spells["divine_smite"].get("components") or [])
    assert spells["counterspell"].get("spell_list_group") == "arcane"


def test_counterspell_2014_auto_succeeds_at_slot(tmp_path):
    root = _campaign(tmp_path, "5e-2014")
    session = Session(str(root))
    caster = MagicMock()
    caster.session = session
    caster.int_mod.return_value = 3
    caster.class_feature.return_value = False
    caster.proficiency_bonus.return_value = 2
    target = MagicMock()
    spell = CounterspellSpell(session, caster, "counterspell", session.load_spell("counterspell"))
    results = spell.resolve(caster, None, _spell_action(target, at_level=3, target_spell_level=3), None)
    assert results[0]["success"] is True
    assert results[0]["resolution"] == "auto_at_or_above"
    assert results[0]["roll"] is None


def test_counterspell_2024_uses_con_save(tmp_path):
    from natural20.die_roll import DieRoll
    from natural20.player_character import PlayerCharacter

    root = _campaign(tmp_path, "5e-2024", drop_local_spells=True)
    session = Session(str(root))
    caster = PlayerCharacter.load(session, "high_elf_fighter.yml")
    target = PlayerCharacter.load(session, "high_elf_fighter.yml")
    spell_meta = dict(session.load_spell("counterspell"))
    spell_meta["id"] = "counterspell"
    spell = CounterspellSpell(session, caster, "counterspell", spell_meta)
    DieRoll.fudge(1)  # target fails CON save → counterspell succeeds
    results = spell.resolve(
        caster, None, _spell_action(target, at_level=3, target_spell_level=9), None
    )
    assert results[0]["resolution"] == "caster_con_save"
    assert results[0]["save_type"] == "constitution"
    assert results[0]["success"] is True  # failed save → interrupted


def test_divine_smite_2024_consumes_bonus_action(tmp_path):
    from natural20.actions.attack_action import AttackAction
    from natural20.battle import Battle
    from natural20.die_roll import DieRoll
    from natural20.map import Map
    from natural20.player_character import PlayerCharacter

    class AlwaysSmite(Controller):
        def select_reaction(self, entity, battle, map_obj, valid_actions, event):
            return valid_actions[0] if valid_actions else None

    root = _campaign(tmp_path, "5e-2024", drop_local_spells=True)
    session = Session(str(root))
    battle_map = Map(session, "battle_sim_objects")
    battle = Battle(session, battle_map)
    paladin = PlayerCharacter.load(session, "goliath_paladin.yml")
    battle.add(paladin, "heroes", controller=AlwaysSmite(session), position=[0, 5])
    enemy = session.npc("goblin")
    battle.add(enemy, "foes", position=[1, 5])
    battle.start()
    paladin.reset_turn(battle)
    enemy.reset_turn(battle)

    initial_ba = battle.entity_state_for(paladin)["bonus_action"]
    initial_slots = paladin.spell_slots["paladin"][1]

    attack = AttackAction(session, paladin, "attack")
    attack.target = enemy
    attack.using = "warhammer"
    DieRoll.fudge(18)
    battle.execute_action(attack)

    smite = next(
        (
            item
            for item in attack.result
            if isinstance(item, dict) and item.get("trigger") == "divine_smite"
        ),
        None,
    )
    assert smite is not None
    assert paladin.spell_slots["paladin"][1] == initial_slots - 1
    assert battle.entity_state_for(paladin)["bonus_action"] == initial_ba - 1


def test_divine_smite_2024_no_dice_cap():
    """2024 removes the 5d8 base dice cap."""
    from natural20.ruleset import get_ruleset

    session = MagicMock()
    session.ruleset = get_ruleset("5e-2024")
    source = MagicMock()
    source.session = session
    target = MagicMock()
    target.properties = {"race": ["human"]}
    target.undead = lambda: False
    spell_details = {"name": "Divine Smite", "damage_type": "radiant"}
    action = DivineSmiteAction(session, source, target, 5, spell_details, {})
    assert action._damage_dice_count() == 6  # 2 + 4, uncapped


def test_divine_smite_2014_keeps_dice_cap():
    from natural20.ruleset import get_ruleset

    session = MagicMock()
    session.ruleset = get_ruleset("5e-2014")
    source = MagicMock()
    source.session = session
    target = MagicMock()
    target.properties = {"race": ["human"]}
    target.undead = lambda: False
    spell_details = {"name": "Divine Smite", "damage_type": "radiant"}
    action = DivineSmiteAction(session, source, target, 5, spell_details, {})
    assert action._damage_dice_count() == 5


def test_spells_overlay_includes_hex_and_searing_smite(tmp_path):
    root = _campaign(tmp_path, "5e-2024", drop_local_spells=True)
    spells = load_campaign_yaml(root, "items", "spells")
    assert spells["hex"].get("concentration") is True
    assert "Necrotic" in (spells["hex"].get("description") or "")
    assert spells["searing_smite"].get("concentration") is False
    assert spells["true_strike"].get("concentration") is False


def test_true_strike_2024_uses_spellcasting_ability(tmp_path):
    from natural20.actions.spell_action import SpellAction
    from natural20.battle import Battle
    from natural20.die_roll import DieRoll
    from natural20.map import Map
    from natural20.player_character import PlayerCharacter

    root = _campaign(tmp_path, "5e-2024", drop_local_spells=True)
    session = Session(str(root))
    battle_map = Map(session, "battle_sim_objects")
    battle = Battle(session, battle_map)
    mage = PlayerCharacter.load(session, "high_elf_mage.yml")
    mage.properties.setdefault("equipped", []).append("dagger")
    mage.properties.setdefault("inventory", []).append({"type": "dagger", "qty": 1})
    mage.properties.setdefault("cantrips", []).append("true_strike")
    mage.properties.setdefault("prepared_spells", []).append("true_strike")
    battle.add(mage, "heroes", position=[0, 5])
    enemy = session.npc("goblin")
    battle.add(enemy, "foes", position=[1, 5])
    battle.start()
    mage.reset_turn(battle)
    enemy.reset_turn(battle)

    spell_meta = dict(session.load_spell("true_strike"))
    spell_meta["id"] = "true_strike"
    from natural20.spell.true_strike_spell import TrueStrikeSpell

    spell = TrueStrikeSpell(session, mage, "true_strike", spell_meta)
    action = SpellAction(session, mage, "spell")
    action.spell_action = spell
    action.using = "dagger"
    action.target = enemy
    spell.chosen_damage_type = "weapon"
    DieRoll.unfudge()
    DieRoll.fudge(18)
    results = spell.resolve(mage, battle, action, battle_map)
    assert any(r.get("type") == "damage" for r in results)
    # INT 18 → +4; dagger is finesse so STR/DEX would be lower without override
    damage = next(r for r in results if r.get("type") == "damage")
    assert damage["attack_roll"].modifier >= 6  # +4 INT + 2 PB


def test_hex_applies_damage_and_ability_disadvantage(tmp_path):
    from natural20.actions.attack_action import AttackAction
    from natural20.actions.spell_action import SpellAction
    from natural20.battle import Battle
    from natural20.die_roll import DieRoll
    from natural20.map import Map
    from natural20.player_character import PlayerCharacter
    from natural20.spell.hex_spell import HexSpell

    root = _campaign(tmp_path, "5e-2024", drop_local_spells=True)
    session = Session(str(root))
    battle_map = Map(session, "battle_sim_objects")
    battle = Battle(session, battle_map)
    warlock = PlayerCharacter.load(session, "tiefling_warlock.yml")
    warlock.properties.setdefault("prepared_spells", []).append("hex")
    battle.add(warlock, "heroes", position=[0, 5])
    enemy = session.npc("goblin")
    battle.add(enemy, "foes", position=[1, 5])
    battle.start()
    warlock.reset_turn(battle)
    enemy.reset_turn(battle)

    spell_meta = dict(session.load_spell("hex"))
    spell_meta["id"] = "hex"
    spell = HexSpell(session, warlock, "hex", spell_meta)
    spell.hexed_ability = "str"
    action = SpellAction(session, warlock, "spell")
    action.spell_action = spell
    action.target = enemy
    action.at_level = 1
    results = spell.resolve(warlock, battle, action, battle_map)
    HexSpell.apply(battle, results[0], session)

    assert enemy.has_effect("ability_check_advantage_modifier")
    adv, dis = enemy.eval_effect(
        "ability_check_advantage_modifier",
        {"value": [[], []], "skill": "athletics", "ability": "str"},
    )
    assert "hex" in (dis or [])

    attack = AttackAction(session, warlock, "attack")
    attack.target = enemy
    attack.using = "dagger"
    DieRoll.unfudge()
    DieRoll.fudge(18)
    DieRoll.fudge(4, die_sides=6)
    battle.execute_action(attack)
    # Hex should have contributed; goblin starts ~7 HP, dagger+hex should hurt
    assert enemy.hp() < enemy.max_hp()


def test_searing_smite_2024_consumes_bonus_and_ignites(tmp_path):
    from natural20.actions.attack_action import AttackAction
    from natural20.battle import Battle
    from natural20.die_roll import DieRoll
    from natural20.map import Map
    from natural20.player_character import PlayerCharacter

    class AlwaysSearing(Controller):
        def select_reaction(self, entity, battle, map_obj, valid_actions, event):
            if event and event.get("type") == "searing_smite":
                return valid_actions[0] if valid_actions else None
            return None  # decline divine smite so BA stays for searing

    root = _campaign(tmp_path, "5e-2024", drop_local_spells=True)
    session = Session(str(root))
    battle_map = Map(session, "battle_sim_objects")
    battle = Battle(session, battle_map)
    paladin = PlayerCharacter.load(session, "goliath_paladin.yml")
    paladin.properties["prepared_spells"] = ["searing_smite"]
    battle.add(paladin, "heroes", controller=AlwaysSearing(session), position=[0, 5])
    enemy = session.npc("goblin")
    battle.add(enemy, "foes", position=[1, 5])
    battle.start()
    paladin.reset_turn(battle)
    enemy.reset_turn(battle)

    initial_ba = battle.entity_state_for(paladin)["bonus_action"]
    initial_slots = paladin.spell_slots["paladin"][1]

    attack = AttackAction(session, paladin, "attack")
    attack.target = enemy
    attack.using = "warhammer"
    DieRoll.fudge(18)
    battle.execute_action(attack)

    searing = next(
        (
            item
            for item in attack.result
            if isinstance(item, dict) and item.get("trigger") == "searing_smite"
        ),
        None,
    )
    assert searing is not None
    assert paladin.spell_slots["paladin"][1] == initial_slots - 1
    assert battle.entity_state_for(paladin)["bonus_action"] == initial_ba - 1
    assert paladin.has_effect("searing_smite")
