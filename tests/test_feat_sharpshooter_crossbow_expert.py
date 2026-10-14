"""Sharpshooter / Crossbow Expert weapon rules, the Loading property, Archery,
Weapon Mastery (Push / Slow) and feat free casts (Magic Initiate)."""
import json
import random
import shutil
from pathlib import Path

import pytest
import yaml

import natural20.utils.ac_utils as ac_utils
from natural20.actions.attack_action import AttackAction
from natural20.battle import Battle
from natural20.die_roll import DieRoll
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.utils.class_mechanics import extra_prepared_spells, free_cast_pool_for
from natural20.utils.weapon_loading import has_loading, loading_blocked
from natural20.weapon_mastery import can_use_mastery
from natural20.weapons import compute_advantages_and_disadvantages, damage_modifier

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _campaign(tmp_path):
    dest = tmp_path / "campaign"
    shutil.copytree(FIXTURES, dest, ignore=shutil.ignore_patterns("tmp", "__pycache__", "*.pyc"))
    with (dest / "game.yml").open("r", encoding="utf-8") as fh:
        game = yaml.safe_load(fh) or {}
    game["ruleset"] = "5e-2024"
    with (dest / "game.yml").open("w", encoding="utf-8") as fh:
        yaml.safe_dump(game, fh)
    (dest / "index.json").write_text(json.dumps(
        {"expansion_packs": {"players_handbook_2024": "players_handbook_2024"}}))
    return dest


@pytest.fixture
def setup(tmp_path):
    random.seed(11)
    session = Session(root_path=str(_campaign(tmp_path)), event_manager=EventManager())
    battle_map = Map(session, 'maps/empty_map')
    battle = Battle(session, battle_map)
    ranger = PlayerCharacter.load(session, 'elf_ranger.yml')
    ranger.properties['class_features'] = list(ranger.properties.get('class_features') or []) + ['extra_attack']
    ranger.properties['feats'] = []
    goblin = session.npc('goblin')
    battle.add(ranger, 'a', position=[0, 0])
    battle.add(goblin, 'b', position=[1, 0])
    battle.start()
    while battle.current_turn() is not ranger:
        battle.next_turn()
    ranger.reset_turn(battle)
    return session, battle, ranger, goblin


def _feats(entity, *feats):
    entity.properties['feats'] = list(feats)


def _disadvantages(session, battle, ranger, goblin, weapon):
    _adv, dis = compute_advantages_and_disadvantages(session, ranger, goblin, weapon, battle=battle)
    return dis


def _damage_mod(entity, weapon, second_hand=False):
    damage = damage_modifier(entity, weapon, second_hand=second_hand)
    return int(damage.split('d', 1)[1].lstrip('0123456789') or 0)


# --- Sharpshooter ---------------------------------------------------------

def test_sharpshooter_ignores_half_and_three_quarters_cover(setup, monkeypatch):
    session, battle, ranger, goblin = setup
    longbow = session.load_weapon('longbow')
    dagger = session.load_weapon('dagger')
    base_ac = goblin.armor_class()
    for cover in (2, 5):
        monkeypatch.setattr(ac_utils, 'calculate_cover_ac', lambda *_a, c=cover: c)
        _feats(ranger)
        assert ac_utils.effective_ac(battle, ranger, goblin, weapon=longbow) == [base_ac + cover, cover]
        _feats(ranger, 'sharpshooter')
        assert ac_utils.effective_ac(battle, ranger, goblin, weapon=longbow) == [base_ac, 0]
        # melee and thrown attacks keep the cover
        assert ac_utils.effective_ac(battle, ranger, goblin, weapon=dagger) == [base_ac + cover, cover]
        assert ac_utils.effective_ac(battle, ranger, goblin, weapon=dagger, thrown=True)[1] == cover


def test_sharpshooter_ignores_long_range_disadvantage(setup):
    session, battle, ranger, goblin = setup
    battle.map_for(goblin).move_to(goblin, 4, 0, battle)
    short_bow = dict(session.load_weapon('longbow'), range=10, range_max=60)
    assert 'target_long_range' in _disadvantages(session, battle, ranger, goblin, short_bow)
    _feats(ranger, 'sharpshooter')
    assert 'target_long_range' not in _disadvantages(session, battle, ranger, goblin, short_bow)


def test_long_range_compares_feet(setup):
    session, battle, ranger, goblin = setup
    battle.map_for(goblin).move_to(goblin, 3, 0, battle)
    # 15 ft away: inside a 20 ft normal range, beyond a 10 ft one
    assert 'target_long_range' not in _disadvantages(
        session, battle, ranger, goblin, dict(session.load_weapon('longbow'), range=20))
    assert 'target_long_range' in _disadvantages(
        session, battle, ranger, goblin, dict(session.load_weapon('longbow'), range=10))


def test_adjacent_enemy_disadvantage_waivers(setup):
    session, battle, ranger, goblin = setup
    longbow = session.load_weapon('longbow')
    crossbow = session.load_weapon('heavy_crossbow')
    assert 'ranged_with_enemy_in_melee' in _disadvantages(session, battle, ranger, goblin, longbow)
    _feats(ranger, 'crossbow_expert')
    assert 'ranged_with_enemy_in_melee' in _disadvantages(session, battle, ranger, goblin, longbow)
    assert 'ranged_with_enemy_in_melee' not in _disadvantages(session, battle, ranger, goblin, crossbow)
    _feats(ranger, 'sharpshooter')
    assert 'ranged_with_enemy_in_melee' not in _disadvantages(session, battle, ranger, goblin, longbow)


# --- Loading / Crossbow Expert -------------------------------------------

def _fire(session, battle, ranger, goblin, weapon, roll=2):
    attack = AttackAction(session, ranger, 'attack')
    attack.target = goblin
    attack.using = weapon
    DieRoll.fudge(roll)
    try:
        attack.resolve(session, None, {'battle': battle})
    finally:
        DieRoll.unfudge()
    battle.commit(attack)
    return attack


def _loading_issue(session, battle, ranger, goblin, weapon):
    attack = AttackAction(session, ranger, 'attack')
    attack.target = goblin
    attack.using = weapon
    attack.validate(battle_map=battle.map_for(ranger), battle=battle)
    return 'validation.attack.loading' in [str(e) for e in attack.errors]


def test_loading_limits_one_shot_per_attack_action(setup):
    session, battle, ranger, goblin = setup
    assert has_loading(ranger, 'heavy_crossbow')
    assert not has_loading(ranger, 'longbow')
    _fire(session, battle, ranger, goblin, 'heavy_crossbow')
    assert battle.entity_state_for(ranger)['extra_attacks_remaining'] == 1
    assert _loading_issue(session, battle, ranger, goblin, 'heavy_crossbow')
    assert not _loading_issue(session, battle, ranger, goblin, 'longbow')
    # bonus-action / reaction shots are single shots and never blocked
    assert not loading_blocked(ranger, battle, 'heavy_crossbow', as_reaction=True)
    # once the Attack action is used up, a new action (e.g. Action Surge) may fire again
    _fire(session, battle, ranger, goblin, 'longbow')
    assert battle.entity_state_for(ranger)['extra_attacks_remaining'] == 0
    assert not _loading_issue(session, battle, ranger, goblin, 'heavy_crossbow')


def test_loading_after_another_weapon_is_allowed(setup):
    session, battle, ranger, goblin = setup
    _fire(session, battle, ranger, goblin, 'longbow')
    assert not _loading_issue(session, battle, ranger, goblin, 'heavy_crossbow')


def test_crossbow_expert_ignores_loading(setup):
    session, battle, ranger, goblin = setup
    _feats(ranger, 'crossbow_expert')
    assert not has_loading(ranger, 'heavy_crossbow')
    _fire(session, battle, ranger, goblin, 'heavy_crossbow')
    assert not _loading_issue(session, battle, ranger, goblin, 'heavy_crossbow')


def test_npc_attacks_ignore_loading(setup):
    session, _battle, _ranger, goblin = setup
    assert not has_loading(goblin, session.load_weapon('heavy_crossbow'))


def test_crossbow_expert_light_crossbow_extra_attack_adds_modifier(setup):
    session, _battle, ranger, _goblin = setup
    hand = session.load_weapon('hand_crossbow')
    heavy = session.load_weapon('heavy_crossbow')
    dex = ranger.dex_mod()
    assert dex > 0
    assert _damage_mod(ranger, hand, second_hand=True) == 0
    _feats(ranger, 'crossbow_expert')
    assert _damage_mod(ranger, hand, second_hand=True) == dex
    assert _damage_mod(ranger, hand) == dex
    # only Light crossbows
    assert _damage_mod(ranger, heavy, second_hand=True) == 0


# --- Archery -------------------------------------------------------------

def test_archery_adds_two_to_ranged_attack_rolls_not_damage(setup):
    session, _battle, ranger, _goblin = setup
    longbow = session.load_weapon('longbow')
    dagger = session.load_weapon('dagger')
    base_attack = ranger.attack_roll_mod(longbow)
    base_damage = _damage_mod(ranger, longbow)
    melee_attack = ranger.attack_roll_mod(dagger)
    _feats(ranger, 'archery')
    assert ranger.attack_roll_mod(longbow) == base_attack + 2
    assert _damage_mod(ranger, longbow) == base_damage == ranger.dex_mod()
    assert ranger.attack_roll_mod(dagger) == melee_attack


# --- Weapon Mastery ------------------------------------------------------

def test_weapon_mastery_push_and_slow(setup):
    session, battle, ranger, goblin = setup
    _feats(ranger, 'weapon_mastery')
    ranger.properties['known_weapon_masteries'] = ['push', 'slow']
    heavy = session.load_weapon('heavy_crossbow')
    longbow = session.load_weapon('longbow')
    assert can_use_mastery(ranger, heavy, 'push')
    assert can_use_mastery(ranger, longbow, 'slow')
    assert not can_use_mastery(ranger, session.load_weapon('hand_crossbow'), 'vex')

    hit = _fire(session, battle, ranger, goblin, 'heavy_crossbow', roll=19)
    assert any(r['type'] == 'weapon_mastery_push' for r in hit.result)
    ranger.reset_turn(battle)
    goblin.attributes['hp'] = goblin.max_hp()
    if goblin.dead() or goblin.unconscious():
        pytest.skip('goblin dropped')
    hit = _fire(session, battle, ranger, goblin, 'longbow', roll=19)
    assert any(r['type'] == 'weapon_mastery_slow' for r in hit.result)


# --- Magic Initiate free cast / spell abilities --------------------------

def test_magic_initiate_free_cast_from_feat_yaml(setup):
    session, _battle, ranger, _goblin = setup
    _feats(ranger, 'magic_initiate_wizard', 'wayfarer_ability_score_improvements')
    ranger.properties['spell_abilities'] = {'true_strike': 'wisdom', 'shield': 'wisdom'}
    assert ranger.spell_source_ability('shield') in ('wis', 'wisdom')
    assert 'shield' in extra_prepared_spells(ranger)
    assert free_cast_pool_for(ranger, 'shield') == 'magic_initiate_wizard'
    assert free_cast_pool_for(ranger, 'true_strike') is None
    ranger.consume_resource('magic_initiate_wizard')
    assert free_cast_pool_for(ranger, 'shield') is None
    ranger.restore_resources('long_rest')
    assert free_cast_pool_for(ranger, 'shield') == 'magic_initiate_wizard'


def test_inline_cast_without_slot_spends_free_pool(setup):
    session, battle, _ranger, _goblin = setup
    fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
    _feats(fighter, 'magic_initiate_wizard')
    fighter.properties['spell_abilities'] = {'shield': 'intelligence'}
    from natural20.spell.spell import _free_pool_without_slot
    shield = session.load_spell('shield')
    assert _free_pool_without_slot(fighter, shield, 1) == 'magic_initiate_wizard'
    fighter.consume_resource('magic_initiate_wizard')
    assert _free_pool_without_slot(fighter, shield, 1) is None
