"""Tests for Battle's concentration tracker (Phase 3)."""

import random
import unittest

from natural20.session import Session
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.battle import Battle
from natural20.player_character import PlayerCharacter
from natural20.actions.spell_action import SpellAction


class _DummyEffect:
    def __init__(self, name='dummy'):
        self.name = name

    def __repr__(self):
        return self.name


class TestConcentrationTracker(unittest.TestCase):
    def make_session(self):
        em = EventManager()
        em.standard_cli()
        return Session(root_path='tests/fixtures', event_manager=em)

    def setUp(self):
        random.seed(7000)
        self.session = self.make_session()
        self.cleric = PlayerCharacter.load(self.session, 'dwarf_cleric.yml')
        self.battle_map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.battle_map)
        self.battle.add(self.cleric, 'a', position=[0, 5])

    def test_start_concentration_sets_effect_and_records_dc(self):
        eff = _DummyEffect('first')
        out = self.battle.start_concentration(self.cleric, eff, save_dc=12)
        self.assertIs(out, eff)
        self.assertIs(self.cleric.current_concentration(), eff)
        self.assertEqual(getattr(eff, 'concentration_save_dc'), 12)
        self.assertTrue(getattr(eff, 'concentration_auto_break'))

    def test_start_concentration_replaces_prior_effect(self):
        first = _DummyEffect('first')
        second = _DummyEffect('second')
        self.battle.start_concentration(self.cleric, first)
        self.battle.start_concentration(self.cleric, second)
        self.assertIs(self.cleric.current_concentration(), second)

    def test_concentration_owner_for_lookup(self):
        eff = _DummyEffect('lookup')
        self.battle.start_concentration(self.cleric, eff)
        self.assertIs(self.battle.concentration_owner_for(eff), self.cleric)
        self.assertIsNone(self.battle.concentration_owner_for(_DummyEffect('absent')))

    def test_end_concentration_clears_effect(self):
        eff = _DummyEffect('clear')
        self.battle.start_concentration(self.cleric, eff)
        self.battle.end_concentration(self.cleric)
        self.assertIsNone(self.cleric.current_concentration())

    def test_bless_uses_battle_start_concentration(self):
        # Real spell migration smoke-test: bless still works and sets
        # concentration via the new battle wrapper.
        target = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.battle.add(target, 'a', position=[1, 5])
        self.cleric.reset_turn(self.battle)
        action = SpellAction.build(self.session, self.cleric)['next'](
            ['bless', 0]
        )['next']([target])
        action.resolve(self.session, self.battle_map, {'battle': self.battle})
        self.battle.commit(action)
        self.assertIsNotNone(self.cleric.current_concentration())


if __name__ == '__main__':
    unittest.main()
