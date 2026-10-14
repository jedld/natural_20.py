"""Generic item mechanics: skill advantage, item resistances, creature-type
damage riders, bonus-action activation and next-attack advantage."""
import random

import pytest

from natural20.actions.attack_action import AttackAction
from natural20.actions.use_item_action import UseItemAction
from natural20.battle import Battle
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
    battle.add(pc, 'a', position=[0, 5], token='G')
    pc.reset_turn(battle)
    return session, battle_map, battle, pc


def _equip(pc, item):
    pc.add_item(item, 1)
    pc.equip(item, ignore_inventory=True)


def test_skill_advantage_from_equipped_item(setup):
    session, _, _, pc = setup
    assert pc.equipped_skill_modifiers('stealth') == ([], [])
    _equip(pc, 'test_shadow_cloak')
    adv, _ = pc.equipped_skill_modifiers('stealth')
    assert adv
    assert pc.equipped_skill_modifiers('perception') == ([], [])


def test_dragon_scale_mail_variant_grants_resistance(setup):
    session, _, _, pc = setup
    props = session.load_equipment('dragon_scale_mail_red')
    assert props['resistances'] == ['fire']
    assert props['save_advantage_against']
    pc.equip("dragon_scale_mail_red", ignore_inventory=True)
    assert 'fire' in pc.effective_resistances()


def test_creature_type_damage_rider_only_vs_matching_type(setup):
    from natural20.utils.monster_traits import additional_damage_entries
    session, _, _, pc = setup
    spear = session.load_weapon('test_wyrmbane_spear')
    goblin = session.npc('goblin')
    assert additional_damage_entries(spear, target=goblin) == []
    goblin.properties['kind'] = 'dragon'
    assert len(additional_damage_entries(spear, target=goblin)) == 1
    goblin.properties['kind'] = 'dragonborn'
    assert additional_damage_entries(spear, target=goblin) == []


def test_bonus_action_item_and_next_attack_advantage(setup):
    session, battle_map, battle, pc = setup
    _equip(pc, 'test_shadow_cloak')
    state = battle.entity_state_for(pc)
    state['action'] = 0
    assert UseItemAction.can(pc, battle)

    action = UseItemAction.build(session, pc)['next']('test_shadow_cloak')
    while isinstance(action, dict):
        param = action['param'][0]
        if param['type'] == 'select_empty_space':
            action = action['next']([1, 5])
        else:
            action = action['next'](pc)
    assert action.can_use_on(pc, battle)
    battle.action(action)
    battle.commit(action)

    assert state['bonus_action'] == 0
    assert battle_map.position_of(pc) == [1, 5]
    assert pc.resource_value('test_shadow_cloak_charges') == 0
    assert pc.eval_effect('attack_advantage_modifier')

    pc.resolve_trigger('attack_resolved', {'target': None})
    assert not pc.eval_effect('attack_advantage_modifier')


def test_next_attack_advantage_expires_at_end_of_turn(setup):
    from natural20.effects.next_attack_advantage_effect import NextAttackAdvantageEffect
    _, _, battle, pc = setup
    NextAttackAdvantageEffect.grant(pc)
    assert pc.has_effect('attack_advantage_modifier')
    pc.resolve_trigger('end_of_turn', {'battle': battle})
    assert not pc.has_effect('attack_advantage_modifier')


def test_dragon_scale_mail_advantage_on_tagged_saves(setup):
    _, _, battle, pc = setup
    pc.equip('dragon_scale_mail_red', ignore_inventory=True)
    tagged = pc.save_throw('dexterity', battle=battle, opts={'dc': 15, 'save_tags': ['dragon_breath']})
    plain = pc.save_throw('dexterity', battle=battle, opts={'dc': 15})
    assert tagged.advantage
    assert not plain.advantage
