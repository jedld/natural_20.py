"""Tests for Entity modifier registry (Phase 3)."""

import random
import unittest

from natural20.session import Session
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.battle import Battle
from natural20.player_character import PlayerCharacter


class TestModifierStacking(unittest.TestCase):
    def make_session(self):
        em = EventManager()
        em.standard_cli()
        return Session(root_path='tests/fixtures', event_manager=em)

    def setUp(self):
        random.seed(7000)
        self.session = self.make_session()
        self.entity = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.battle_map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.battle_map)
        self.battle.add(self.entity, 'a', position=[0, 5])

    def test_add_and_collect_int_modifier(self):
        self.entity.add_modifier('attack_roll', 'inspiration', 2)
        mods = self.entity.collect_modifiers('attack_roll')
        self.assertEqual(len(mods), 1)
        self.assertEqual(mods[0]['value'], 2)
        self.assertEqual(mods[0]['source'], 'inspiration')

    def test_add_and_collect_dice_modifier(self):
        self.entity.add_modifier('save_roll', 'bardic', '1d6')
        mods = self.entity.collect_modifiers('save_roll', {'ability': 'wisdom'})
        self.assertEqual(mods[0]['value'], '1d6')

    def test_kind_filter(self):
        self.entity.add_modifier('attack_roll', 'a', 1)
        self.entity.add_modifier('save_roll', 'b', 2)
        self.assertEqual(len(self.entity.collect_modifiers('attack_roll')), 1)
        self.assertEqual(len(self.entity.collect_modifiers('save_roll')), 1)
        self.assertEqual(self.entity.collect_modifiers('damage_roll'), [])

    def test_remove_modifier_by_source(self):
        self.entity.add_modifier('attack_roll', 'a', 1)
        self.entity.add_modifier('attack_roll', 'b', 2)
        self.entity.remove_modifier('a')
        remaining = self.entity.collect_modifiers('attack_roll')
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]['source'], 'b')

    def test_callable_value(self):
        def computed(ent, ctx):
            return 1 if ctx.get('ability') == 'wisdom' else 0
        self.entity.add_modifier('save_roll', 'computed', computed)
        wis = self.entity.collect_modifiers('save_roll', {'ability': 'wisdom'})
        cha = self.entity.collect_modifiers('save_roll', {'ability': 'charisma'})
        self.assertEqual(wis[0]['value'], 1)
        # Callable returned 0; still included (None would be filtered).
        self.assertEqual(cha[0]['value'], 0)

    def test_callable_returning_none_is_filtered(self):
        self.entity.add_modifier('save_roll', 'maybe', lambda e, c: None)
        self.assertEqual(self.entity.collect_modifiers('save_roll'), [])

    def test_condition_gates_modifier(self):
        self.entity.add_modifier(
            'attack_roll', 'situational', 3,
            condition=lambda e, c: c.get('battle') is not None,
        )
        self.assertEqual(len(self.entity.collect_modifiers('attack_roll', {'battle': self.battle})), 1)
        self.assertEqual(self.entity.collect_modifiers('attack_roll', {}), [])

    def test_save_throw_includes_registry_modifier(self):
        # Add a +5 save_roll modifier and verify the resulting roll is at
        # least 5 higher than the base. Use a fixed seed and run twice.
        random.seed(7000)
        baseline = self.entity.save_throw('wisdom', battle=self.battle)
        random.seed(7000)
        self.entity.add_modifier('save_roll', 'aura', 5)
        boosted = self.entity.save_throw('wisdom', battle=self.battle)
        self.assertGreaterEqual(boosted.result(), baseline.result() + 5)


if __name__ == '__main__':
    unittest.main()
