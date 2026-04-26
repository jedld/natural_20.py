import random
import unittest
import numpy as np

from natural20.session import Session
from natural20.event_manager import EventManager
from natural20.player_character import PlayerCharacter
from natural20.battle import Battle
from natural20.map import Map


class TestDruid(unittest.TestCase):
    def setUp(self):
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.map)
        np.random.seed(7000)
        random.seed(7000)
        self.druid = PlayerCharacter.load(self.session, 'human_druid.yml')
        self.battle.add(self.druid, 'a', position=[0, 5])
        self.battle.start()
        self.druid.reset_turn(self.battle)

    # --- features ---

    def test_class_features_present(self):
        self.assertTrue(self.druid.class_feature('druidic'))
        self.assertTrue(self.druid.class_feature('spellcasting'))
        self.assertTrue(self.druid.class_feature('wild_shape'))
        self.assertTrue(self.druid.class_feature('druid_circle'))

    # --- spellcasting ---

    def test_spell_attack_modifier_uses_wisdom(self):
        # WIS 16 -> +3, prof L2 -> +2 = +5
        self.assertEqual(self.druid.spell_attack_modifier(class_type='druid'), 5)

    def test_spell_save_dc(self):
        # 8 + prof + wis mod = 8 + 2 + 3 = 13
        self.assertEqual(self.druid.spell_save_dc(ability_type='wisdom'), 13)

    def test_spell_slots_initialized(self):
        # Druid L2 -> 3 first-level slots, 2 cantrips
        self.assertEqual(self.druid.max_spell_slots(1, 'druid'), 3)
        self.assertEqual(self.druid.spell_slots_count(1, 'druid'), 3)

    def test_spell_lists_include_druid_spells(self):
        prepared = self.druid.prepared_spells()
        self.assertIn('guidance', prepared)
        self.assertIn('cure_wounds', prepared)
        self.assertIn('thunderwave', prepared)

    # --- wild shape ---

    def test_wild_shape_pool_initialized(self):
        self.assertEqual(self.druid.wild_shape_max, 2)
        self.assertEqual(self.druid.wild_shape_count, 2)
        self.assertTrue(self.druid.has_wild_shape(1))

    def test_consume_wild_shape(self):
        self.druid.consume_wild_shape(1)
        self.assertEqual(self.druid.wild_shape_count, 1)
        self.druid.consume_wild_shape(2)  # clamps at 0
        self.assertEqual(self.druid.wild_shape_count, 0)
        self.assertFalse(self.druid.has_wild_shape(1))

    def test_short_rest_refills_wild_shape(self):
        self.druid.consume_wild_shape(2)
        self.assertEqual(self.druid.wild_shape_count, 0)
        # short_rest_for_druid is invoked via the per-class iteration
        self.druid.short_rest_for_druid(None)
        self.assertEqual(self.druid.wild_shape_count, 2)

    def test_long_rest_refills_slots_and_wild_shape(self):
        self.druid.consume_wild_shape(2)
        self.druid.consume_spell_slot(1, 'druid')
        self.assertEqual(self.druid.wild_shape_count, 0)
        self.assertEqual(self.druid.spell_slots_count(1, 'druid'), 2)

        self.druid.long_rest()
        self.assertEqual(self.druid.wild_shape_count, 2)
        self.assertEqual(self.druid.spell_slots_count(1, 'druid'), 3)


if __name__ == '__main__':
    unittest.main()
