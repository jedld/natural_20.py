"""Alchemist's Fire: thrown flask attack, ongoing burning, and putting it out."""
import random

import pytest
import yaml

from natural20.actions.extinguish_flames_action import ExtinguishFlamesAction
from natural20.actions.use_item_action import UseItemAction
from natural20.battle import Battle
from natural20.effects.burning_effect import BurningEffect
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session


@pytest.fixture
def setup():
    random.seed(7000)
    session = Session(root_path='tests/fixtures', event_manager=EventManager())
    battle_map = Map(session, 'battle_sim')
    battle = Battle(session, battle_map)
    pc = PlayerCharacter.load(session, 'high_elf_fighter.yml')
    goblin = session.npc('goblin')
    battle.add(pc, 'a', position=[0, 5], token='G')
    battle.add(goblin, 'b', position=[2, 5], token='g')
    pc.reset_turn(battle)
    goblin.reset_turn(battle)
    return session, battle_map, battle, pc, goblin


def _throw(session, battle, pc, target):
    pc.add_item('alchemists_fire', 1)
    action = UseItemAction.build(session, pc)['next']('alchemists_fire')
    action = action['next'](target)
    return action


def test_alchemists_fire_template():
    session = Session(root_path='tests/fixtures', event_manager=EventManager())
    props = session.load_equipment('alchemists_fire')
    assert props['item_class'] == 'ThrownFlaskItem'
    assert props['burning']['damage'] == '1d4'
    assert props['burning']['extinguish_dc'] == 10
    assert props['thrown_range'] == 20


def test_hit_sets_target_burning_and_consumes_flask(setup, monkeypatch):
    session, _, battle, pc, goblin = setup
    action = _throw(session, battle, pc, goblin)
    monkeypatch.setattr(goblin, 'armor_class', lambda *a, **k: 1)
    battle.action(action)
    assert action.result[0]['hit'] or action.result[0]['attack_roll'].nat_1()
    if not action.result[0]['hit']:
        pytest.skip('natural 1 with this seed')
    battle.commit(action)
    assert pc.item_count('alchemists_fire') == 0
    effect = BurningEffect.active_on(goblin)
    assert effect is not None
    assert effect.damage == '1d4' and effect.extinguish_dc == 10


def test_miss_does_not_burn(setup, monkeypatch):
    session, _, battle, pc, goblin = setup
    action = _throw(session, battle, pc, goblin)
    monkeypatch.setattr(goblin, 'armor_class', lambda *a, **k: 99)
    battle.action(action)
    if action.result[0]['attack_roll'].nat_20():
        pytest.skip('natural 20 with this seed')
    battle.commit(action)
    assert BurningEffect.active_on(goblin) is None
    assert pc.item_count('alchemists_fire') == 0


def test_burning_deals_fire_damage_each_start_of_turn(setup):
    session, _, battle, pc, goblin = setup
    goblin.attributes['hp'] = 50
    goblin.properties['max_hp'] = 50
    BurningEffect.apply_to(goblin, pc, damage='1d4', damage_type='fire', extinguish_dc=10)
    hp = goblin.hp()
    goblin.resolve_trigger('start_of_turn', {'battle': battle})
    after_first = goblin.hp()
    assert 1 <= hp - after_first <= 4
    goblin.resolve_trigger('start_of_turn', {'battle': battle})
    assert goblin.hp() < after_first


def test_burning_does_not_stack(setup):
    _, _, _, pc, goblin = setup
    first = BurningEffect.apply_to(goblin, pc)
    second = BurningEffect.apply_to(goblin, pc)
    assert first is second
    assert len(goblin.effects['burning']) == 1
    assert len(goblin.entity_event_hooks['start_of_turn']) == 1


def test_extinguish_success_removes_burning(setup, monkeypatch):
    session, _, battle, pc, goblin = setup
    BurningEffect.apply_to(pc, goblin)
    assert ExtinguishFlamesAction.can(pc, battle)
    options = ExtinguishFlamesAction.options_for(session, pc, battle)
    assert [o.target for o in options] == [pc]

    from natural20.die_roll import DieRoll
    monkeypatch.setattr(pc, 'dexterity_check', lambda **kw: DieRoll.roll('20'))
    action = options[0]
    battle.action(action)
    battle.commit(action)
    assert BurningEffect.active_on(pc) is None
    assert 'start_of_turn' not in pc.entity_event_hooks or not any(
        isinstance(h.get('effect'), BurningEffect) for h in pc.entity_event_hooks['start_of_turn'])
    assert battle.entity_state_for(pc)['action'] == 0


def test_extinguish_failure_keeps_burning(setup, monkeypatch):
    session, _, battle, pc, goblin = setup
    BurningEffect.apply_to(pc, goblin)
    from natural20.die_roll import DieRoll
    monkeypatch.setattr(pc, 'dexterity_check', lambda **kw: DieRoll.roll('1'))
    action = ExtinguishFlamesAction.options_for(session, pc, battle)[0]
    battle.action(action)
    battle.commit(action)
    assert BurningEffect.active_on(pc) is not None


def test_npc_offers_extinguish_only_while_burning(setup):
    session, _, battle, pc, goblin = setup
    assert not ExtinguishFlamesAction.can(goblin, battle)
    BurningEffect.apply_to(goblin, pc)
    assert ExtinguishFlamesAction.can(goblin, battle)
    assert ExtinguishFlamesAction.options_for(session, goblin, battle)[0].target is goblin


def test_pc_offers_extinguish_only_while_burning(setup):
    session, _, battle, pc, goblin = setup
    battle.start(combat_order=[pc, goblin])
    pc.reset_turn(battle)
    assert not any(isinstance(a, ExtinguishFlamesAction) for a in pc.available_actions(session, battle))
    BurningEffect.apply_to(pc, goblin)
    offered = [a for a in pc.available_actions(session, battle) if isinstance(a, ExtinguishFlamesAction)]
    assert offered and offered[0].target is pc


def test_burning_effect_round_trips_through_yaml(setup):
    from natural20.utils.serialization import SafeLoaderWithConstructors
    _, _, _, pc, goblin = setup
    effect = BurningEffect.apply_to(goblin, pc, damage='2d4')
    dumped = yaml.safe_dump({'effect': effect})
    loaded = yaml.load(dumped, Loader=SafeLoaderWithConstructors)['effect']
    assert isinstance(loaded, BurningEffect)
    assert loaded.damage == '2d4'
    assert loaded.extinguish_dc == 10
    assert loaded.target == goblin.entity_uid
