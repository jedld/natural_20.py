"""Undead Fortitude, heal-blocking on-hit riders, any-combination multiattack, cannot_speak."""
import random

import pytest

from natural20.actions.attack_action import AttackAction
from natural20.battle import Battle
from natural20.die_roll import DieRoll
from natural20.event_manager import EventManager
from natural20.generic_controller import GenericController
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.utils.combat_comms import speech_block_reason
from natural20.utils.multiattack import expand_multiattack_entries, multiattack_combos


@pytest.fixture
def setup():
    random.seed(7)
    session = Session(root_path='tests/fixtures', event_manager=EventManager())
    battle_map = Map(session, 'tests/fixtures/jev_arena.yml')
    session.register_map('arena', battle_map)
    battle = Battle(session, battle_map)
    pc = PlayerCharacter.load(session, 'high_elf_fighter.yml')
    battle.add(pc, 'a', position=[5, 4], add_to_initiative=True)
    knight = session.npc('bone_sentinel')
    battle_map.add(knight, 5, 5)
    battle.add(knight, 'b', controller=GenericController(session), add_to_initiative=True)
    battle.start()
    battle.set_current_turn(knight)
    knight.reset_turn(battle)
    pc.reset_turn(battle)
    yield session, battle, pc, knight
    DieRoll.unfudge(20)


def _attack(session, battle, source, target, name, d20=15):
    action = AttackAction(session, source, 'attack')
    action.npc_action = next(a for a in source.npc_actions if a['name'] == name)
    action.target = target
    DieRoll.fudge(d20)
    try:
        battle.action(action)
        battle.commit(action)
    finally:
        DieRoll.unfudge(20)
    return action


def test_any_of_expands_to_combinations():
    combos = expand_multiattack_entries([{'any_of': ['a', 'b'], 'count': 3}])
    assert sorted(combos) == [['a', 'a', 'a'], ['a', 'a', 'b'], ['a', 'b', 'b'], ['b', 'b', 'b']]


def test_any_combination_multiattack_allows_three_attacks(setup):
    session, battle, pc, knight = setup
    assert len(multiattack_combos(knight)) == 4
    state = battle.entity_state_for(knight)
    assert sorted(state['multiattack'][1]) == ['axe'] * 3 + ['draining_blade'] * 3

    pc.attributes['hp'] = 500
    pc.properties['max_hp'] = 500
    _attack(session, battle, knight, pc, 'draining_blade')
    assert sorted(state['multiattack'][1]) == ['axe'] * 2 + ['draining_blade'] * 2
    _attack(session, battle, knight, pc, 'draining_blade')
    assert sorted(state['multiattack'][1]) == ['axe', 'draining_blade']
    _attack(session, battle, knight, pc, 'axe')
    assert not any(state['multiattack'].values())


def test_blade_hit_blocks_healing_until_attackers_next_turn(setup):
    session, battle, pc, knight = setup
    pc.attributes['hp'] = 500
    pc.properties['max_hp'] = 500
    _attack(session, battle, knight, pc, 'draining_blade', d20=19)
    hp = pc.hp()
    pc.heal(10)
    assert pc.hp() == hp

    knight.resolve_trigger('start_of_turn', {'battle': battle})
    pc.heal(10)
    assert pc.hp() == hp + 10


def test_undead_fortitude_save_keeps_it_at_one_hp(setup):
    session, battle, pc, knight = setup
    knight.attributes['hp'] = 5
    DieRoll.fudge(20)
    try:
        knight.take_damage(8, battle=battle, damage_type='slashing')
    finally:
        DieRoll.unfudge(20)
    assert knight.hp() == 1
    assert not knight.dead()


def test_undead_fortitude_failed_save(setup):
    session, battle, pc, knight = setup
    knight.attributes['hp'] = 5
    DieRoll.fudge(1)
    try:
        knight.take_damage(8, battle=battle, damage_type='slashing')
    finally:
        DieRoll.unfudge(20)
    assert knight.hp() <= 0


@pytest.mark.parametrize('damage_type,critical', [('bludgeoning', False), ('slashing', True)])
def test_undead_fortitude_bypass(setup, damage_type, critical):
    session, battle, pc, knight = setup
    knight.attributes['hp'] = 5
    DieRoll.fudge(20)
    try:
        knight.take_damage(8, battle=battle, damage_type=damage_type, critical=critical)
    finally:
        DieRoll.unfudge(20)
    assert knight.hp() <= 0


def test_zombie_attribute_defaults_to_radiant_bypass():
    from natural20.utils.monster_traits import undead_fortitude_config
    session = Session(root_path='tests/fixtures', event_manager=EventManager())
    zombie = session.npc('bone_sentinel')
    zombie.properties.pop('undead_fortitude')
    assert undead_fortitude_config(zombie)['bypass'] == ['radiant']


def test_cannot_speak_blocks_callouts(setup):
    _, _, _, knight = setup
    assert speech_block_reason(knight) == 'cannot_speak'
