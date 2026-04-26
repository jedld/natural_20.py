import random
import unittest
import numpy as np

from natural20.session import Session
from natural20.event_manager import EventManager
from natural20.player_character import PlayerCharacter
from natural20.battle import Battle
from natural20.map import Map
from natural20.actions.feline_agility_action import FelineAgilityAction
from natural20.weapons import damage_modifier


class TestTabaxi(unittest.TestCase):
    def setUp(self):
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.map)
        np.random.seed(7000)
        random.seed(7000)
        self.pc = PlayerCharacter.load(self.session, 'tabaxi_rogue.yml')
        self.battle.add(self.pc, 'a', position=[0, 5])
        self.battle.start()
        self.pc.reset_turn(self.battle)

    # --- race definition ---

    def test_race_features_present(self):
        self.assertTrue(self.pc.class_feature('feline_agility'))
        self.assertTrue(self.pc.class_feature('cats_claws'))
        self.assertTrue(self.pc.class_feature('cats_talent'))

    def test_race_attribute_bonus_in_yaml(self):
        bonus = self.pc.race_properties.get('attribute_bonus', {})
        self.assertEqual(bonus.get('dex'), 2)
        self.assertEqual(bonus.get('cha'), 1)

    def test_race_speed_and_darkvision(self):
        self.assertEqual(self.pc.speed(), 30)
        self.assertEqual(self.pc.race_properties.get('darkvision'), 60)

    def test_climb_speed(self):
        self.assertEqual(self.pc.climb_speed(), 20)

    def test_languages(self):
        langs = self.pc.languages()
        self.assertIn('common', langs)

    def test_perception_and_stealth_proficiency(self):
        # Cat's Talent: proficiency in Perception and Stealth via race YAML.
        self.assertTrue(self.pc.proficient('perception'))
        self.assertTrue(self.pc.proficient('stealth'))

    # --- Cat's Claws ---

    def test_unarmed_strike_is_1d4(self):
        weapon = self.session.load_weapon('unarmed_attack')
        roll = damage_modifier(self.pc, weapon)
        self.assertIn('1d4', roll)

    def test_unarmed_strike_summary_is_slashing(self):
        info = self.pc.unarmed_strike_info()
        self.assertEqual(info['damage_type'], 'slashing')
        self.assertIn('1d4', info['damage'])
        self.assertIn("Cat's Claws", info['properties'])

    def test_attack_action_damage_type_is_slashing(self):
        from natural20.actions.attack_action import AttackAction
        attack = AttackAction(self.session, self.pc, 'attack', { 'using': 'unarmed_attack' })
        weapon, _, _, _, _ = attack.get_weapon_info({ 'using': 'unarmed_attack' })
        self.assertEqual(weapon['damage_type'], 'slashing')

    def test_attack_action_label_says_cats_claws(self):
        from natural20.actions.attack_action import AttackAction
        attack = AttackAction(self.session, self.pc, 'attack', { 'using': 'unarmed_attack' })
        attack.using = 'unarmed_attack'
        self.assertIn("Cat's Claws", attack.label())

    def test_attack_action_weapon_icon_is_cats_claws(self):
        from natural20.actions.attack_action import AttackAction
        attack = AttackAction(self.session, self.pc, 'attack', { 'using': 'unarmed_attack' })
        attack.using = 'unarmed_attack'
        self.assertEqual(attack.weapon_icon(), 'cats_claws')

    def test_unarmed_strike_summary_name_is_cats_claws(self):
        info = self.pc.unarmed_strike_info()
        self.assertEqual(info['name'], "Cat's Claws")

    # --- Feline Agility ---

    def test_feline_agility_action_available(self):
        actions = self.pc.available_actions(self.session, self.battle)
        self.assertTrue(any(isinstance(a, FelineAgilityAction) for a in actions))

    def test_feline_agility_doubles_movement(self):
        state = self.battle.entity_state_for(self.pc)
        starting = state['movement']
        action = FelineAgilityAction(self.session, self.pc, 'feline_agility')
        action.resolve(self.session, self.map, { 'battle': self.battle })
        for r in action.result:
            FelineAgilityAction.apply(self.battle, r, self.session)
        self.assertEqual(state['movement'], starting + self.pc.speed())
        self.assertTrue(self.pc.feline_agility_used)

    def test_feline_agility_not_available_after_use(self):
        self.pc.feline_agility_used = True
        actions = self.pc.available_actions(self.session, self.battle)
        self.assertFalse(any(isinstance(a, FelineAgilityAction) for a in actions))

    def test_feline_agility_resets_after_no_move_turn(self):
        # Use feline agility, then end the turn without consuming any movement.
        self.pc.feline_agility_used = True
        state = self.battle.entity_state_for(self.pc)
        # Simulate the end of a turn where the PC did not move.
        # reset_turn at the start of next turn should detect movement
        # remained equal to starting (no movement consumed) and recharge.
        self.pc._feline_movement_start = state['movement']  # snapshot
        # Trigger a new turn reset; movement remaining still equals start.
        self.pc.reset_turn(self.battle)
        self.assertFalse(self.pc.feline_agility_used)

    def test_feline_agility_persists_when_movement_consumed(self):
        self.pc.feline_agility_used = True
        state = self.battle.entity_state_for(self.pc)
        self.pc._feline_movement_start = state['movement']
        # Simulate the PC having moved (consumed movement) by reducing it.
        state['movement'] = max(0, state['movement'] - 5)
        self.pc.reset_turn(self.battle)
        # Movement was consumed last turn -> Feline Agility stays used.
        self.assertTrue(self.pc.feline_agility_used)

    def test_long_rest_resets_feline_agility(self):
        self.pc.feline_agility_used = True
        self.pc.long_rest()
        self.assertFalse(self.pc.feline_agility_used)


if __name__ == '__main__':
    unittest.main()
