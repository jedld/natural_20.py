"""Tests for Bardic Inspiration grant and consumption."""

import random
import unittest

from natural20.actions.bardic_inspiration_action import BardicInspirationAction
from natural20.battle import Battle
from natural20.die_roll import DieRoll
from natural20.effects.bardic_inspiration_effect import (
    BardicInspirationEffect,
    apply_bardic_inspiration_to_roll,
    has_bardic_inspiration_die,
)
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session


class TestBardicInspiration(unittest.TestCase):
    def setUp(self):
        random.seed(7000)
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.map)
        self.bard = PlayerCharacter.load(self.session, 'human_bard.yml')
        self.ally = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle.add(self.bard, 'a', position=[0, 5])
        self.battle.add(self.ally, 'a', position=[1, 5])
        self.battle.start()
        self.bard.reset_turn(self.battle)

    def _grant_inspiration(self):
        action = BardicInspirationAction(self.session, self.bard, 'bardic_inspiration')
        action.target = self.ally
        action.resolve(self.session, None, {'battle': self.battle})
        self.battle.commit(action)
        return action

    def test_grant_uses_bonus_action_and_stamps_effect_object(self):
        self._grant_inspiration()
        self.assertEqual(self.bard.bardic_inspiration_count, 2)
        self.assertEqual(self.battle.entity_state_for(self.bard)['bonus_action'], 0)
        effects = [
            e for e in self.ally.casted_effects
            if isinstance(e.get('effect'), BardicInspirationEffect)
        ]
        self.assertEqual(len(effects), 1)
        self.assertEqual(effects[0]['effect'].die, '1d6')
        self.assertTrue(has_bardic_inspiration_die(self.ally))

    def test_cannot_target_self(self):
        action = BardicInspirationAction(self.session, self.bard, 'bardic_inspiration')
        action.target = self.bard
        action.resolve(self.session, None, {'battle': self.battle})
        self.assertEqual(action.result, [])

    def test_replacing_inspiration_removes_prior_die(self):
        self._grant_inspiration()
        action = BardicInspirationAction(self.session, self.bard, 'bardic_inspiration')
        action.target = self.ally
        action.resolve(self.session, None, {'battle': self.battle})
        self.battle.commit(action)
        bi_effects = [
            e for e in self.ally.casted_effects
            if isinstance(e.get('effect'), BardicInspirationEffect)
        ]
        self.assertEqual(len(bi_effects), 1)

    def test_consumes_on_failed_ability_check(self):
        self._grant_inspiration()
        DieRoll.fudge(3, die_sides=20)
        DieRoll.fudge(6, die_sides=6)
        roll = self.ally.athletics_check(self.battle)
        success = roll.result() >= 12
        self.assertTrue(success)
        self.assertFalse(has_bardic_inspiration_die(self.ally))

    def test_holds_die_on_success_without_using(self):
        self._grant_inspiration()
        DieRoll.fudge(18, die_sides=20)
        roll = self.ally.athletics_check(self.battle)
        success = roll.result() >= 5
        self.assertTrue(success)
        self.assertTrue(has_bardic_inspiration_die(self.ally))

    def test_apply_helper_consumes_die(self):
        self._grant_inspiration()
        DieRoll.fudge(2, die_sides=20)
        DieRoll.fudge(6, die_sides=6)
        roll = DieRoll.roll('1d20+2', entity=self.ally, battle=self.battle)
        roll.metadata['roll_kind'] = 'ability_check'
        roll = apply_bardic_inspiration_to_roll(roll, self.ally, 10, 'ge', battle=self.battle)
        self.assertGreaterEqual(roll.result(), 10)
        self.assertFalse(has_bardic_inspiration_die(self.ally))

    def test_bardic_inspiration_die_scales_at_level_5(self):
        self.bard.properties['classes'] = {'bard': 5}
        self.bard.bard_level = 5
        self.assertEqual(self.bard.bardic_inspiration_die(), '1d8')


if __name__ == '__main__':
    unittest.main()
