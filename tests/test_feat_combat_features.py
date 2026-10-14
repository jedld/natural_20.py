"""Feat combat features: YAML attack options (before-attack / on-hit), Great
Weapon Master (Heavy Weapon Mastery, Hew) and Blind Fighting."""
import random

import pytest

from natural20.actions.attack_action import AttackAction
from natural20.actions.attack_option_action import (
    AttackOptionAction, AttackOptionHitOffer, install_attack_option_hooks,
)
from natural20.actions.hew_attack_action import HewAttackAction
from natural20.battle import Battle
from natural20.die_roll import DieRoll
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.utils.fear import is_frightened_of
from natural20.utils.great_weapon_master import gwm_hit_riders

PRECISE = {
    'id': 'precise_strike', 'name': 'Precise Strike', 'timing': 'before_attack',
    'advantage': True, 'extra_damage': '1d8', 'uses': 'proficiency_bonus',
    'expend': 'on_hit', 'once_per_turn': True,
}
DEMORALIZE = {
    'id': 'demoralizing_strike', 'name': 'Demoralizing Strike', 'timing': 'on_hit',
    'uses': 2, 'once_per_turn': True,
    'save': {'ability': 'wisdom', 'dc_abilities': ['cha']},
    'on_fail': {'condition': 'frightened', 'rounds': 1},
    'on_success': {'next_attack_disadvantage': True},
}


@pytest.fixture
def setup():
    random.seed(1234)
    session = Session(root_path='tests/fixtures', event_manager=EventManager())
    battle_map = Map(session, 'battle_sim')
    battle = Battle(session, battle_map)
    fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
    goblin = session.npc('goblin')
    battle.add(fighter, 'heroes', position=[0, 5])
    battle.add(goblin, 'foes', position=[1, 5])
    battle.start()
    while battle.current_turn() is not fighter:
        battle.next_turn()
    fighter.reset_turn(battle)
    goblin.reset_turn(battle)
    return session, battle, fighter, goblin


def _melee(session, fighter, goblin, roll, weapon='vicious_rapier', action_class=AttackAction):
    attack = action_class(session, fighter, 'attack')
    attack.target = goblin
    attack.using = weapon
    DieRoll.fudge(roll)
    try:
        attack.resolve(session, None, {'battle': attack.session and fighter_battle(fighter)})
    finally:
        DieRoll.unfudge()
    return attack


_BATTLES = {}


def fighter_battle(entity):
    return _BATTLES[entity.entity_uid]


def test_precise_strike_advantage_and_damage_spent_only_on_hit(setup):
    session, battle, fighter, goblin = setup
    _BATTLES[fighter.entity_uid] = battle
    fighter.properties['attack_options'] = [PRECISE]
    actions = [a for a in fighter.available_actions(session, battle) if isinstance(a, AttackOptionAction)]
    assert len(actions) == 1
    battle.action(actions[0])
    battle.commit(actions[0])
    pb = fighter.proficiency_bonus()

    adv, _ = fighter.eval_effect('attack_advantage_modifier', {'target': goblin})
    assert 'precise_strike' in adv

    miss = _melee(session, fighter, goblin, 1)
    assert miss.result[-1]['type'] == 'miss'
    assert fighter.resource_value('precise_strike') == pb
    assert not fighter.eval_effect('attack_advantage_modifier', {'target': goblin})[0]

    actions = [a for a in fighter.available_actions(session, battle) if isinstance(a, AttackOptionAction)]
    battle.action(actions[0])
    battle.commit(actions[0])
    hit = _melee(session, fighter, goblin, 19)
    extra = [r for r in hit.result if r['type'] == 'additional_damage' and r['attack_name'] == 'Precise Strike']
    assert extra
    assert fighter.resource_value('precise_strike') == pb - 1
    assert not [a for a in fighter.available_actions(session, battle) if isinstance(a, AttackOptionAction)]


def test_demoralizing_strike_offer_frightens_on_failed_save(setup):
    session, battle, fighter, goblin = setup
    _BATTLES[fighter.entity_uid] = battle
    fighter.properties['attack_options'] = [DEMORALIZE]
    install_attack_option_hooks(fighter)
    install_attack_option_hooks(fighter)
    offers = [h for h in fighter.entity_event_hooks['on_attack_hit'] if isinstance(h['handler'], AttackOptionHitOffer)]
    assert len(offers) == 1

    goblin.properties['ability'] = dict(goblin.properties.get('ability', {}), wis=1)
    random.seed(1)
    hit = _melee(session, fighter, goblin, 19)
    option_items = [r for r in hit.result if r['type'] == 'attack_option_hit']
    assert option_items
    option_items[0]['success'] = False
    from natural20.actions.attack_option_action import AttackOptionHitAction
    AttackOptionHitAction.apply(battle, option_items[0], session)
    assert is_frightened_of(goblin, fighter)
    assert fighter.resource_value('demoralizing_strike') == 1


def test_gwm_heavy_weapon_mastery_is_2024_and_own_turn_only(setup):
    session, battle, fighter, goblin = setup
    greatsword = {'name': 'Greatsword', 'type': 'melee_attack', 'damage': '2d6',
                  'damage_type': 'slashing', 'properties': ['heavy', 'two_handed']}
    longsword = {'name': 'Longsword', 'type': 'melee_attack', 'damage': '1d8',
                 'damage_type': 'slashing', 'properties': ['versatile']}
    fighter.properties.setdefault('feats', []).append('great_weapon_master')
    assert gwm_hit_riders(fighter, greatsword, battle) == []
    fighter.properties['feat_editions'] = {'great_weapon_master': '5e-2024'}
    pb = fighter.proficiency_bonus()
    assert gwm_hit_riders(fighter, greatsword, battle) == [{'damage_die': str(pb), 'damage_type': 'slashing'}]
    assert gwm_hit_riders(fighter, longsword, battle) == []
    assert gwm_hit_riders(fighter, greatsword, battle, as_reaction=True) == []


def test_hew_bonus_attack_after_critical_hit(setup):
    session, battle, fighter, goblin = setup
    _BATTLES[fighter.entity_uid] = battle
    fighter.properties.setdefault('feats', []).append('great_weapon_master')
    goblin.attributes['hp'] = 500
    attack = _melee(session, fighter, goblin, 20)
    battle.commit(attack)
    assert battle.entity_state_for(fighter)['hew_pending'] == 'vicious_rapier'
    assert HewAttackAction.can(fighter, battle)
    hews = [a for a in fighter.available_actions(session, battle) if isinstance(a, HewAttackAction)]
    assert hews and hews[0].using == 'vicious_rapier'

    hew = _melee(session, fighter, goblin, 5, action_class=HewAttackAction)
    battle.commit(hew)
    state = battle.entity_state_for(fighter)
    assert state['hew_pending'] is None
    assert state['bonus_action'] == 0


def test_blind_fighting_grants_blindsight(setup):
    _, _, fighter, _ = setup
    assert not fighter.has_blindsight()
    fighter.properties.setdefault('feats', []).append('blind_fighting')
    assert fighter.blindsight_range() == 10
    assert fighter.blindsight(10) and not fighter.blindsight(15)
    fighter.properties['blindsight'] = 30
    assert fighter.blindsight_range() == 30
