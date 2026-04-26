import random
import unittest
import numpy as np

from natural20.session import Session
from natural20.event_manager import EventManager
from natural20.player_character import PlayerCharacter
from natural20.battle import Battle
from natural20.map import Map


class TestTiefling(unittest.TestCase):
    def setUp(self):
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.map)
        np.random.seed(7000)
        random.seed(7000)
        self.pc = PlayerCharacter.load(self.session, 'tiefling_fighter.yml')
        self.battle.add(self.pc, 'a', position=[0, 5])
        self.battle.start()
        self.pc.reset_turn(self.battle)

    # --- race definition ---

    def test_race_features_present(self):
        self.assertTrue(self.pc.class_feature('hellish_resistance'))
        self.assertTrue(self.pc.class_feature('infernal_legacy'))

    def test_race_attribute_bonus_in_yaml(self):
        bonus = self.pc.race_properties.get('attribute_bonus', {})
        self.assertEqual(bonus.get('cha'), 2)
        self.assertEqual(bonus.get('int'), 1)

    def test_race_speed_and_darkvision(self):
        self.assertEqual(self.pc.speed(), 30)
        self.assertEqual(self.pc.race_properties.get('darkvision'), 60)

    def test_infernal_language(self):
        langs = self.pc.languages()
        self.assertIn('infernal', langs)
        self.assertIn('common', langs)

    # --- hellish resistance ---

    def test_fire_resistance_listed(self):
        self.assertTrue(self.pc.resistant_to('fire'))

    def test_fire_damage_halved(self):
        start = self.pc.hp()
        self.pc.take_damage(10, battle=self.battle, damage_type='fire',
                            session=self.session)
        # 10 fire halved to 5
        self.assertEqual(self.pc.hp(), start - 5)

    def test_non_fire_damage_unaffected(self):
        start = self.pc.hp()
        self.pc.take_damage(10, battle=self.battle, damage_type='slashing',
                            session=self.session)
        self.assertEqual(self.pc.hp(), start - 10)


if __name__ == '__main__':
    unittest.main()
