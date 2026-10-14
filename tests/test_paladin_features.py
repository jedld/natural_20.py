"""Paladin level 6-11 features: auras, Channel Divinity (Sacred Weapon, Abjure
Foes), Improved Divine Smite / Radiant Strikes, plus the generic frightened
condition they rely on."""
import random

import pytest

from natural20.actions.abjure_foes_action import AbjureFoesAction
from natural20.actions.sacred_weapon_action import SacredWeaponAction
from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.utils.auras import aura_save_bonus
from natural20.utils.fear import (
    apply_fear, enforce_action_limit, is_frightened_of, snapshot_turn_resources,
)
from natural20.utils.feature_hit_riders import feature_hit_riders
from natural20.weapons import compute_advantages_and_disadvantages
from natural20.yaml_loader import load_yaml

PALADIN_OVERRIDE = {
    'classes': {'paladin': 11},
    'level': 11,
    'sacred_oath': 'oath_of_devotion',
    'ability': {'str': 18, 'dex': 12, 'con': 16, 'int': 11, 'wis': 11, 'cha': 18},
}


@pytest.fixture
def setup(monkeypatch):
    import natural20.player_character as pc_module
    real_loader = pc_module.load_campaign_resource_path
    template_paladin = load_yaml('templates/char_classes/paladin.yml')

    def loader(root, relative, *args, **kwargs):
        if relative == 'char_classes/paladin.yml':
            return dict(template_paladin)
        return real_loader(root, relative, *args, **kwargs)

    monkeypatch.setattr(pc_module, 'load_campaign_resource_path', loader)
    random.seed(4242)
    session = Session(root_path='tests/fixtures', event_manager=EventManager())
    battle_map = Map(session, 'battle_sim')
    session.maps = {'battle_sim': battle_map}
    battle = Battle(session, battle_map)
    paladin = PlayerCharacter.load(session, 'goliath_paladin.yml', override=dict(PALADIN_OVERRIDE))
    ally = PlayerCharacter.load(session, 'high_elf_fighter.yml')
    goblin = session.npc('goblin')
    battle.add(paladin, 'heroes', position=[0, 5])
    battle.add(ally, 'heroes', position=[1, 5])
    battle.add(goblin, 'foes', position=[2, 5])
    for entity in (paladin, ally, goblin):
        entity.reset_turn(battle)
    return session, battle_map, battle, paladin, ally, goblin


def test_level_11_devotion_features(setup):
    _, _, _, paladin, _, _ = setup
    for feature in ('aura_of_protection', 'aura_of_courage', 'aura_of_devotion',
                    'improved_divine_smite', 'sacred_weapon', 'channel_divinity'):
        assert paladin.class_feature(feature), feature
    assert not paladin.class_feature('aura_expansion')
    assert paladin.channel_divinity_count == 1


def test_aura_of_protection_save_bonus(setup):
    _, battle_map, battle, paladin, ally, goblin = setup
    assert aura_save_bonus(paladin, battle)[0] == 4
    assert aura_save_bonus(ally, battle) == (4, 'aura_of_protection')
    assert aura_save_bonus(goblin, battle)[0] == 0

    battle_map.move_to(ally, 5, 5, battle)
    assert aura_save_bonus(ally, battle)[0] == 0
    battle_map.move_to(ally, 1, 5, battle)

    paladin.make_unconscious()
    assert aura_save_bonus(ally, battle)[0] == 0


def test_aura_of_courage_and_devotion_immunity(setup):
    _, _, battle, paladin, ally, goblin = setup
    assert ally.immune_to_condition('frightened')
    assert ally.immune_to_condition('charmed')
    assert not ally.immune_to_condition('poisoned')
    assert not goblin.immune_to_condition('frightened')
    assert not apply_fear(ally, goblin)


def test_improved_divine_smite_rider_only_on_melee(setup):
    session, _, _, paladin, ally, _ = setup
    longsword = session.load_weapon('longsword')
    longbow = session.load_weapon('longbow')
    riders = feature_hit_riders(paladin, longsword)
    assert riders == [{'damage_die': '1d8', 'damage_type': 'radiant'}]
    assert feature_hit_riders(paladin, longbow) == []
    assert feature_hit_riders(paladin, longsword, thrown=True) == []
    assert feature_hit_riders(ally, longsword) == []


def test_sacred_weapon(setup):
    session, _, battle, paladin, _, goblin = setup
    assert SacredWeaponAction.can(paladin, battle)
    action = SacredWeaponAction.build(session, paladin)
    battle.action(action)
    battle.commit(action)
    assert paladin.channel_divinity_count == 0
    assert battle.entity_state_for(paladin)['action'] == 0
    weapon = action.result[0]['weapon']
    bonus = paladin.eval_effect('attack_roll_bonus', {'stacked': True, 'value': 0, 'weapon_name': weapon})
    assert bonus == 4
    light = paladin.eval_effect('light_override', {'bright': 0, 'dim': 0})
    assert light == {'bright': 20, 'dim': 40}
    assert not SacredWeaponAction.can(paladin, None)


def test_abjure_foes_frightens_and_limits_turn(setup):
    session, _, battle, paladin, _, goblin = setup
    paladin.properties.setdefault('class_features', []).append('abjure_foes')
    assert AbjureFoesAction.can(paladin, battle)
    action = AbjureFoesAction(session, paladin, 'abjure_foes')
    action.target = [goblin]
    action.resolve(session, None, {'battle': battle})
    item = action.result[0]
    item['success'] = False
    AbjureFoesAction.apply(battle, item, session)

    assert is_frightened_of(goblin, paladin)
    assert 'frightened' in goblin.statuses
    assert paladin.channel_divinity_count == 0

    adv, dis = compute_advantages_and_disadvantages(session, goblin, paladin, 'scimitar', battle=battle)
    assert 'frightened' in dis

    snapshot = snapshot_turn_resources(battle, goblin)
    battle.consume(goblin, 'action')
    enforce_action_limit(battle, goblin, snapshot)
    state = battle.entity_state_for(goblin)
    assert state['bonus_action'] == 0 and state['movement'] == 0

    goblin.take_damage(1, battle=battle, session=session)
    assert not is_frightened_of(goblin, paladin)
    assert 'frightened' not in goblin.statuses


def test_long_rest_restores_pools(setup):
    _, _, _, paladin, _, _ = setup
    paladin.channel_divinity_count = 0
    paladin.lay_on_hands_count = 0
    paladin.long_rest_for_paladin(None)
    assert paladin.channel_divinity_count == 1
    assert paladin.lay_on_hands_count == 55


def test_melee_hit_adds_radiant_damage_and_sacred_weapon_bonus(setup):
    from natural20.actions.attack_action import AttackAction
    from natural20.die_roll import DieRoll
    session, _, battle, paladin, _, goblin = setup
    action = SacredWeaponAction.build(session, paladin)
    battle.action(action)
    battle.commit(action)
    paladin.reset_turn(battle)

    attack = AttackAction(session, paladin, 'attack')
    attack.target = goblin
    attack.using = action.result[0]['weapon']
    DieRoll.fudge(18)
    attack.resolve(session, None, {'battle': battle})
    DieRoll.unfudge()
    types = [r['type'] for r in attack.result]
    assert 'damage' in types
    radiant = [r for r in attack.result if r['type'] == 'additional_damage']
    assert radiant and radiant[0]['damage_type'] == 'radiant'
    # d20 18 + STR 4 + proficiency 4 + Sacred Weapon (CHA) 4
    assert attack.attack_roll.result() == 30
