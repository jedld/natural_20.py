"""Shining Smite: post-hit bonus-action smite with a radiant glow rider."""
import random

import pytest

from natural20.actions.attack_action import AttackAction
from natural20.battle import Battle
from natural20.controller import Controller
from natural20.die_roll import DieRoll
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.spell.shining_smite_spell import ShiningSmiteSpell
from natural20.utils.serialization import Serialization
from natural20.weapons import compute_advantages_and_disadvantages


class AlwaysShining(Controller):
    def __init__(self, session):
        super().__init__(session)
        self.offers = []

    def select_reaction(self, entity, battle, map_obj, valid_actions, event):
        if event and event.get('type') == 'shining_smite':
            self.offers.append(valid_actions)
            return valid_actions[0] if valid_actions else None
        return None


@pytest.fixture
def setup():
    random.seed(7)
    session = Session(root_path='tests/fixtures', event_manager=EventManager())
    battle_map = Map(session, 'battle_sim_objects')
    battle = Battle(session, battle_map)
    paladin = PlayerCharacter.load(session, 'goliath_paladin.yml')
    paladin.properties['prepared_spells'] = ['shining_smite']
    paladin.spell_slots['paladin'][2] = 1
    controller = AlwaysShining(session)
    battle.add(paladin, 'heroes', controller=controller, position=[0, 5])
    enemy = session.npc('ogre')
    battle.add(enemy, 'foes', position=[1, 5])
    battle.start()
    paladin.reset_turn(battle)
    enemy.reset_turn(battle)
    return session, battle, battle_map, paladin, enemy, controller


def _hit(session, battle, paladin, enemy):
    attack = AttackAction(session, paladin, 'attack')
    attack.target = enemy
    attack.using = 'warhammer'
    DieRoll.fudge(18)
    try:
        battle.execute_action(attack)
    finally:
        DieRoll.unfudge()
    return attack


def test_hit_offers_smite_and_applies_rider(setup):
    session, battle, battle_map, paladin, enemy, controller = setup
    initial_ba = battle.entity_state_for(paladin)['bonus_action']
    attack = _hit(session, battle, paladin, enemy)

    smite = next((i for i in attack.result if isinstance(i, dict) and i.get('trigger') == 'shining_smite'), None)
    assert smite is not None
    assert smite['damage_type'] == 'radiant'
    assert paladin.spell_slots['paladin'][2] == 0
    assert battle.entity_state_for(paladin)['bonus_action'] == initial_ba - 1
    assert isinstance(paladin.concentration, ShiningSmiteSpell)

    assert enemy.has_effect('targeted_advantage_override')
    assert enemy.has_effect('invisibility_suppressed')
    enemy.statuses.add('invisible') if isinstance(enemy.statuses, set) else enemy.statuses.append('invisible')
    assert not enemy.invisible()
    light = enemy.light_properties()
    assert light and light.get('dim', 0) >= 5

    weapon = session.load_weapon('warhammer')
    advantage, _ = compute_advantages_and_disadvantages(session, paladin, enemy, weapon, battle=battle)
    assert 'shining_smite' in advantage


def test_not_offered_without_slot_of_spell_level(setup):
    session, battle, battle_map, paladin, enemy, controller = setup
    paladin.spell_slots['paladin'][2] = 0
    attack = _hit(session, battle, paladin, enemy)
    assert controller.offers == []
    assert not any(isinstance(i, dict) and i.get('trigger') == 'shining_smite' for i in attack.result)


def test_ending_concentration_clears_target(setup):
    session, battle, battle_map, paladin, enemy, controller = setup
    _hit(session, battle, paladin, enemy)
    assert enemy.has_effect('targeted_advantage_override')
    paladin.dismiss_effect(paladin.concentration)
    assert paladin.concentration is None
    assert not enemy.has_effect('targeted_advantage_override')
    assert not enemy.has_effect('light_override')


def test_damage_dice_scale_with_slot():
    from natural20.spell.shining_smite_spell import ShiningSmiteAction
    session = Session(root_path='tests/fixtures', event_manager=EventManager())
    paladin = PlayerCharacter.load(session, 'goliath_paladin.yml')
    details = session.load_spell('shining_smite')
    assert ShiningSmiteAction(session, paladin, None, 2, details, {}).damage_dice_count() == 2
    assert ShiningSmiteAction(session, paladin, None, 4, details, {}).damage_dice_count() == 4


def test_save_load_keeps_rider(setup):
    session, battle, battle_map, paladin, enemy, controller = setup
    _hit(session, battle, paladin, enemy)
    from natural20.generic_controller import GenericController
    battle.set_controller_for(paladin, GenericController(session))
    dump = Serialization().serialize(session, battle, {'battle_sim_objects': battle_map})
    session2, battle2, maps2 = Serialization().deserialize(dump)
    paladin2 = session2.entity_by_uid(paladin.entity_uid)
    enemy2 = session2.entity_by_uid(enemy.entity_uid)
    assert enemy2.has_effect('targeted_advantage_override')
    assert isinstance(paladin2.concentration, ShiningSmiteSpell)
