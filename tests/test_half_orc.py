import random
import unittest
import numpy as np

from natural20.session import Session
from natural20.event_manager import EventManager
from natural20.player_character import PlayerCharacter
from natural20.battle import Battle
from natural20.map import Map


class TestHalfOrc(unittest.TestCase):
    def setUp(self):
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.map)
        np.random.seed(7000)
        random.seed(7000)
        self.pc = PlayerCharacter.load(self.session, 'half_orc_barbarian.yml')
        self.battle.add(self.pc, 'a', position=[0, 5])
        self.battle.start()
        self.pc.reset_turn(self.battle)

    # --- race definition ---

    def test_race_features_present(self):
        self.assertTrue(self.pc.class_feature('relentless_endurance'))
        self.assertTrue(self.pc.class_feature('savage_attacks'))
        self.assertTrue(self.pc.class_feature('menacing'))

    def test_race_attribute_bonus_present_in_yaml(self):
        # The race YAML advertises +2 STR / +1 CON for the character builder;
        # verify the structured data is exposed via race_properties.
        bonus = self.pc.race_properties.get('attribute_bonus', {})
        self.assertEqual(bonus.get('str'), 2)
        self.assertEqual(bonus.get('con'), 1)

    def test_race_speed_and_darkvision(self):
        self.assertEqual(self.pc.speed(), 30)
        self.assertEqual(self.pc.race_properties.get('darkvision'), 60)

    def test_orc_language(self):
        self.assertIn('orc', self.pc.languages())
        self.assertIn('common', self.pc.languages())

    def test_intimidation_skill_proficient(self):
        # Intimidation comes from race.
        self.assertTrue(self.pc.proficient('intimidation'))

    # --- relentless endurance ---

    def test_relentless_endurance_drops_to_one_hp(self):
        # Reduce to 0 HP from a hit larger than current HP but not lethal.
        self.pc.attributes['hp'] = 5
        self.pc.take_damage(10, battle=self.battle, damage_type='slashing')
        self.assertEqual(self.pc.hp(), 1)
        self.assertFalse(self.pc.unconscious())
        self.assertTrue(self.pc.relentless_endurance_used)

    def test_relentless_endurance_consumed_only_once(self):
        self.pc.attributes['hp'] = 5
        self.pc.take_damage(10, battle=self.battle, damage_type='slashing')
        self.assertEqual(self.pc.hp(), 1)
        # Second time it shouldn't trigger.
        self.pc.take_damage(5, battle=self.battle, damage_type='slashing')
        self.assertTrue(self.pc.unconscious())

    def test_relentless_endurance_recharges_on_long_rest(self):
        self.pc.attributes['hp'] = 5
        self.pc.take_damage(10, battle=self.battle, damage_type='slashing')
        self.assertTrue(self.pc.relentless_endurance_used)
        self.pc.long_rest()
        self.assertFalse(self.pc.relentless_endurance_used)

    def test_relentless_endurance_not_for_instant_death(self):
        # Massive damage that exceeds max_hp by max_hp -> instant death.
        self.pc.attributes['hp'] = 5
        # max_hp = 22 -> need hp <= -22 after damage. damage = 5+22 = 27
        self.pc.take_damage(50, battle=self.battle, damage_type='slashing')
        self.assertTrue(self.pc.dead())

    # --- savage attacks ---

    def _run_attack_with_roll(self, attack_rolls):
        from natural20.actions.attack_action import AttackAction
        from natural20.die_roll import DieRoll
        from natural20 import die_roll as die_roll_module
        from unittest.mock import patch

        target = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle.add(target, 'b', position=[1, 5])

        descriptions = []
        original = die_roll_module.DieRoll.roll

        def spy(roll_str, *args, **kwargs):
            descriptions.append(kwargs.get('description', ''))
            return original(roll_str, *args, **kwargs)

        action = AttackAction(self.session, self.pc, 'attack',
                              {'target': target, 'using': 'battleaxe'})
        action.using = 'battleaxe'
        action.target = target
        action.attack_roll = DieRoll(list(attack_rolls), 0, 20)

        with patch.object(die_roll_module.DieRoll, 'roll', side_effect=spy):
            action.resolve(self.session, self.map, {'battle': self.battle})

        return descriptions

    def test_savage_attacks_extra_die_on_crit(self):
        descriptions = self._run_attack_with_roll([20])
        self.assertIn('dice_roll.savage_attacks', descriptions)

    def test_savage_attacks_no_extra_die_on_normal_hit(self):
        descriptions = self._run_attack_with_roll([10])
        self.assertNotIn('dice_roll.savage_attacks', descriptions)


if __name__ == '__main__':
    unittest.main()
