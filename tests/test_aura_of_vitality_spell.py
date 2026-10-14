"""Aura of Vitality: concentration aura with a once-per-turn bonus-action heal."""
import random
import shutil
from pathlib import Path

import yaml

from natural20.actions.aura_of_vitality_heal_action import AuraOfVitalityHealAction
from natural20.actions.spell_action import SpellAction
from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.spell.aura_of_vitality_spell import AuraOfVitalityEffect
from natural20.utils.serialization import Serialization

FIXTURES = Path('tests/fixtures')


def _root(tmp_path, ruleset):
    if ruleset is None:
        return str(FIXTURES)
    dest = tmp_path / 'campaign'
    shutil.copytree(FIXTURES, dest, ignore=shutil.ignore_patterns('tmp', '__pycache__', '*.pyc'))
    game_path = dest / 'game.yml'
    game = yaml.safe_load(game_path.read_text()) or {}
    game['ruleset'] = ruleset
    game_path.write_text(yaml.safe_dump(game))
    return str(dest)


def _setup(tmp_path, ruleset=None):
    random.seed(3)
    session = Session(root_path=_root(tmp_path, ruleset), event_manager=EventManager())
    battle_map = session.register_map('empty_map', Map(session, 'maps/empty_map'))
    battle = Battle(session, battle_map)
    paladin = PlayerCharacter.load(session, 'goliath_paladin.yml')
    ally = PlayerCharacter.load(session, 'high_elf_fighter.yml')
    goblin = session.npc('goblin', {'name': 'Goblin'})
    battle_map.add(paladin, 1, 1)
    battle_map.add(ally, 1, 2)
    battle_map.add(goblin, 5, 6)
    battle.add(paladin, 'a', add_to_initiative=True)
    battle.add(ally, 'a', add_to_initiative=True)
    battle.add(goblin, 'b', add_to_initiative=True)
    battle.start(combat_order=[paladin, ally, goblin])
    paladin.reset_turn(battle)
    paladin.spell_slots['paladin'][3] = 2
    paladin.properties['prepared_spells'] = ['aura_of_vitality']
    ally.take_damage(ally.hp() - 1, battle=battle)
    return session, battle, battle_map, paladin, ally


def _cast(session, battle, battle_map, paladin, target):
    action = SpellAction.build(session, paladin)['next'](['aura_of_vitality', 3])['next'](target)
    action.resolve(session, battle_map, {'battle': battle})
    battle.commit(action)
    return action


def _pulse(session, battle, battle_map, paladin, target):
    action = AuraOfVitalityHealAction.build(session, paladin)['next'](target)
    action.validate(battle_map)
    assert not action.errors, action.errors
    action.resolve(session, battle_map, {'battle': battle})
    battle.commit(action)
    return action


def test_2014_cast_then_bonus_action_heal_once_per_turn(tmp_path):
    session, battle, battle_map, paladin, ally = _setup(tmp_path)
    assert not AuraOfVitalityHealAction.can(paladin, battle)
    _cast(session, battle, battle_map, paladin, [1, 1])
    assert isinstance(paladin.concentration, AuraOfVitalityEffect)
    assert ally.hp() == 1  # 2014: casting doesn't heal

    assert AuraOfVitalityHealAction.can(paladin, battle)
    _pulse(session, battle, battle_map, paladin, ally)
    assert 3 <= ally.hp() - 1 <= 12
    assert not AuraOfVitalityHealAction.can(paladin, battle)

    battle.next_turn()
    battle.next_turn()
    battle.next_turn()
    paladin.reset_turn(battle)
    assert battle.current_turn() is paladin
    assert AuraOfVitalityHealAction.can(paladin, battle)


def test_heal_action_listed_in_available_actions(tmp_path):
    session, battle, battle_map, paladin, ally = _setup(tmp_path)
    _cast(session, battle, battle_map, paladin, [1, 1])
    actions = paladin.available_actions(session, battle)
    assert any(isinstance(a, AuraOfVitalityHealAction) for a in actions)


def test_2024_cast_heals_and_counts_as_this_turns_pulse(tmp_path):
    session, battle, battle_map, paladin, ally = _setup(tmp_path, '5e-2024')
    assert session.load_spell('aura_of_vitality')['casting_time'].startswith('1:bonus')
    _cast(session, battle, battle_map, paladin, ally)
    assert ally.hp() > 1
    assert not AuraOfVitalityHealAction.can(paladin, battle)


def test_pulse_is_maximized_under_beacon_of_hope(tmp_path):
    session, battle, battle_map, paladin, ally = _setup(tmp_path)
    ally.register_effect('max_healing', type('Max', (), {'max_healing': staticmethod(lambda e, o=None: True)}))
    _cast(session, battle, battle_map, paladin, [1, 1])
    action = _pulse(session, battle, battle_map, paladin, ally)
    heal = next(i for i in action.result if i['type'] == 'spell_heal')
    assert heal['heal_roll'].result() == 12


def test_save_load_keeps_aura(tmp_path):
    session, battle, battle_map, paladin, ally = _setup(tmp_path)
    _cast(session, battle, battle_map, paladin, [1, 1])
    _pulse(session, battle, battle_map, paladin, ally)
    dump = Serialization().serialize(session, battle, session.maps)
    session2, battle2, _maps2 = Serialization().deserialize(dump)
    paladin2 = session2.entity_by_uid(paladin.entity_uid)
    assert isinstance(paladin2.concentration, AuraOfVitalityEffect)
    assert not AuraOfVitalityHealAction.can(paladin2, battle2)
