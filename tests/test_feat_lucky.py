"""2024 Lucky feat (luck points) and the separate halfling reroll-1s trait."""
import json
import random
import shutil
from pathlib import Path

import pytest
import yaml

from natural20.actions.attack_action import AttackAction
from natural20.battle import Battle
from natural20.die_roll import DieRoll
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.utils.luck_points import (
    has_reroll_ones_trait, luck_against_attack, luck_on_own_roll, luck_points,
)

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
    random.seed(7)
    events = []
    manager = EventManager()
    manager.register_event_listener(['luck_point'], lambda e: events.append(e))
    session = Session(root_path=str(_campaign(tmp_path)), event_manager=manager)
    battle_map = Map(session, 'maps/empty_map')
    battle = Battle(session, battle_map)
    ranger = PlayerCharacter.load(session, 'elf_ranger.yml')
    ranger.properties['feats'] = ['lucky']
    goblin = session.npc('goblin')
    battle.add(ranger, 'a', position=[0, 0])
    battle.add(goblin, 'b', position=[1, 0])
    battle.start()
    return session, battle, ranger, goblin, events


def _d20(face, modifier=0, **kw):
    return DieRoll([face], modifier, 20, **kw)


def test_pool_equals_proficiency_bonus_and_restores_on_long_rest(setup):
    _session, battle, ranger, _goblin, _events = setup
    pb = ranger.proficiency_bonus()
    assert luck_points(ranger) == pb
    assert ranger.get_resource('luck_points').restore_on == 'long_rest'
    ranger.consume_resource('luck_points', pb)
    assert luck_points(ranger) == 0
    ranger.restore_resources('short_rest')
    assert luck_points(ranger) == 0
    ranger.restore_resources('long_rest')
    assert luck_points(ranger) == pb


def test_self_advantage_after_failed_attack_roll(setup):
    _session, battle, ranger, goblin, events = setup
    pb = ranger.proficiency_bonus()
    DieRoll.fudge(18)
    try:
        new_roll = luck_on_own_roll(ranger, _d20(3, 5), 15, battle=battle, target=goblin)
    finally:
        DieRoll.unfudge()
    assert new_roll.advantage
    assert new_roll.result() == 23
    assert luck_points(ranger) == pb - 1
    assert events and events[-1]['mode'] == 'advantage'
    assert events[-1]['remaining'] == pb - 1


def test_successful_or_hopeless_roll_does_not_spend(setup):
    _session, battle, ranger, goblin, _events = setup
    pb = ranger.proficiency_bonus()
    hit = _d20(15, 5)
    assert luck_on_own_roll(ranger, hit, 15, battle=battle, target=goblin) is hit
    # needs a natural 20+: 1/20 chance to matter, below the AI threshold
    hopeless = _d20(2, 0)
    assert luck_on_own_roll(ranger, hopeless, 25, battle=battle, roll_kind='wisdom_saving_throw') is hopeless
    assert luck_points(ranger) == pb


def test_no_luck_out_of_combat(setup):
    session, _battle, ranger, _goblin, _events = setup
    roll = _d20(3, 5)
    assert luck_on_own_roll(ranger, roll, 15, battle=None) is roll


def test_luck_on_failed_saving_throw(setup):
    _session, battle, ranger, _goblin, events = setup
    pb = ranger.proficiency_bonus()
    modifier = ranger.wis_mod()
    DieRoll.fudge(2)
    try:
        roll = ranger.save_throw('wisdom', battle, {'dc': 2 + modifier + 5})
    finally:
        DieRoll.unfudge()
    assert luck_points(ranger) == pb - 1
    assert events[-1]['old_roll'] is not roll
    assert events[-1]['roll_kind'] == 'wisdom_saving_throw'


def test_impose_disadvantage_on_hit_against_lucky_creature(setup):
    _session, battle, ranger, goblin, events = setup
    pb = ranger.proficiency_bonus()
    DieRoll.fudge(2)
    try:
        new_roll = luck_against_attack(ranger, goblin, _d20(14, 4), 15, battle=battle)
    finally:
        DieRoll.unfudge()
    assert new_roll.disadvantage
    assert new_roll.result() == 6
    assert luck_points(ranger) == pb - 1
    assert events[-1]['mode'] == 'disadvantage'

    # a miss is never rerolled
    miss = _d20(5, 4)
    assert luck_against_attack(ranger, goblin, miss, 15, battle=battle) is miss


def test_attack_action_offers_luck_to_defender(setup):
    session, battle, ranger, goblin, _events = setup
    pb = ranger.proficiency_bonus()
    attack = AttackAction(session, goblin, 'attack')
    attack.target = ranger
    attack.npc_action = goblin.npc_actions[0]
    DieRoll.fudge(18)
    try:
        attack.resolve(session, None, {'battle': battle})
    finally:
        DieRoll.unfudge()
    # 18 + goblin bonus always hits; the extra d20 is random, the point is spent
    assert luck_points(ranger) == pb - 1


def test_luck_points_round_trip_through_save_load(setup):
    session, _battle, ranger, _goblin, _events = setup
    pb = ranger.proficiency_bonus()
    luck_points(ranger)
    ranger.consume_resource('luck_points', 1)
    data = ranger.to_dict()
    data.setdefault('session', session)
    restored = PlayerCharacter.from_dict(data)
    restored.session = session
    assert restored.get_resource('luck_points').current == pb - 1
    assert luck_points(restored) == pb - 1


def test_halfling_still_rerolls_ones():
    session = Session(root_path='tests/fixtures', event_manager=EventManager())
    halfling = PlayerCharacter.load(session, 'halfling_rogue.yml')
    assert has_reroll_ones_trait(halfling)
    halfling.properties['feats'] = ['lucky']
    assert has_reroll_ones_trait(halfling)
    DieRoll.fudge(1)
    try:
        roll = DieRoll.roll_with_lucky(halfling, '1d20')
    finally:
        DieRoll.unfudge()
    assert roll.prev_roll is not None


def test_lucky_feat_alone_does_not_reroll_ones(setup):
    _session, _battle, ranger, _goblin, _events = setup
    assert ranger.class_feature('lucky')
    assert not has_reroll_ones_trait(ranger)
    DieRoll.fudge(1)
    try:
        roll = DieRoll.roll_with_lucky(ranger, '1d20')
    finally:
        DieRoll.unfudge()
    assert roll.prev_roll is None
    assert roll.result() == 1


def test_unknown_feat_ids_are_no_ops(setup):
    session, battle, ranger, goblin, _events = setup
    ranger.properties['feats'] = ['wayfarer_ability_score_improvements', 'definitely_not_a_feat']
    roll = _d20(3, 5)
    assert luck_on_own_roll(ranger, roll, 15, battle=battle, target=goblin) is roll
    assert ranger.get_resource('luck_points') is None
    attack = AttackAction(session, ranger, 'attack')
    attack.target = goblin
    attack.using = 'longbow'
    attack.validate(battle_map=battle.map_for(ranger), battle=battle)
    assert 'validation.attack.loading' not in [str(i) for i in attack.errors]
