import os
import random
import unittest
import numpy as np

from natural20.session import Session
from natural20.event_manager import EventManager
from natural20.player_character import PlayerCharacter
from natural20.battle import Battle
from natural20.map import Map
from natural20.actions.attack_action import AttackAction
from natural20.actions.flurry_of_blows_action import FlurryOfBlowsAction
from natural20.actions.patient_defense_action import PatientDefenseAction
from natural20.actions.step_of_the_wind_action import StepOfTheWindAction
from natural20.actions.martial_arts_bonus_attack_action import MartialArtsBonusAttackAction


class TestMonk(unittest.TestCase):
    def setUp(self):
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.map)
        np.random.seed(7000)
        random.seed(7000)
        self.monk = PlayerCharacter.load(self.session, 'human_monk.yml')
        self.battle.add(self.monk, 'a', position=[0, 5])
        self.battle.start()
        self.monk.reset_turn(self.battle)

    # ------------------------- core stats -------------------------

    def test_class_features_present(self):
        self.assertTrue(self.monk.class_feature('martial_arts'))
        self.assertTrue(self.monk.class_feature('unarmored_defense_monk'))
        self.assertTrue(self.monk.class_feature('ki'))
        self.assertTrue(self.monk.class_feature('flurry_of_blows'))
        self.assertTrue(self.monk.class_feature('patient_defense'))
        self.assertTrue(self.monk.class_feature('step_of_the_wind'))
        self.assertTrue(self.monk.class_feature('unarmored_movement'))

    def test_unarmored_defense_ac(self):
        # No armor, no shield. AC = 10 + DEX(3) + WIS(3) = 16
        self.assertEqual(self.monk.armor_class(), 16)

    def test_unarmored_movement_bonus_at_level_2(self):
        # Human base 30 + 10 ft Unarmored Movement at L2.
        self.assertEqual(self.monk.speed(), 40)

    def test_ki_pool_initialized(self):
        self.assertEqual(self.monk.max_ki, 2)
        self.assertEqual(self.monk.ki_count, 2)
        self.assertTrue(self.monk.has_ki(1))

    def test_short_rest_refills_ki(self):
        self.monk.consume_ki(2)
        self.assertEqual(self.monk.ki_count, 0)
        self.monk.short_rest(self.battle, prompt=False, force=True)
        self.assertEqual(self.monk.ki_count, 2)

    # ------------------------- martial arts -------------------------

    def test_martial_arts_die(self):
        self.assertEqual(self.monk.martial_arts_die(), '1d4')

    def test_is_monk_weapon_unarmed_and_shortsword(self):
        unarmed = self.session.load_weapon('unarmed_attack')
        shortsword = self.session.load_weapon('shortsword')
        longsword = self.session.load_weapon('longsword')
        self.assertTrue(self.monk.is_monk_weapon(unarmed))
        self.assertTrue(self.monk.is_monk_weapon(shortsword))
        self.assertFalse(self.monk.is_monk_weapon(longsword))

    def test_attack_ability_uses_dex_for_unarmed(self):
        unarmed = self.session.load_weapon('unarmed_attack')
        # Monk's STR=13 (+1) and DEX=16 (+3); martial arts -> use DEX.
        self.assertEqual(self.monk.attack_ability_mod(unarmed), 3)

    def test_damage_die_substituted_for_unarmed(self):
        from natural20.weapons import damage_modifier
        unarmed = self.session.load_weapon('unarmed_attack')
        # Should roll the martial arts die (1d4) instead of a flat 1
        self.assertEqual(damage_modifier(self.monk, unarmed), '1d4+3')

    # ------------------------- bonus action -------------------------

    def _spawn_dummy_target(self):
        # Use an existing NPC on the battle map.
        target = self.map.entity_at(5, 5)
        self.battle.add(target, 'b')
        target.reset_turn(self.battle)
        return target

    def test_flurry_of_blows_consumes_ki_and_bonus_action(self):
        target = self._spawn_dummy_target()
        # Simulate that the monk has already taken Attack with a monk weapon
        state = self.battle.entity_state_for(self.monk)
        state['martial_arts_pending'] = True

        self.assertTrue(FlurryOfBlowsAction.can(self.monk, self.battle))

        action = FlurryOfBlowsAction(self.session, self.monk, 'flurry_of_blows')
        action.target = target
        action.second_target = target
        action.resolve(self.session, None, {'battle': self.battle})
        self.battle.commit(action)

        # bonus action consumed
        self.assertEqual(self.battle.entity_state_for(self.monk)['bonus_action'], 0)
        # ki spent
        self.assertEqual(self.monk.ki_count, 1)
        # martial arts pending cleared
        self.assertFalse(self.battle.entity_state_for(self.monk)['martial_arts_pending'])

    def test_patient_defense_dodges_and_spends_ki(self):
        self.assertTrue(PatientDefenseAction.can(self.monk, self.battle))
        action = PatientDefenseAction(self.session, self.monk, 'patient_defense')
        action.resolve(self.session, None, {'battle': self.battle})
        self.battle.commit(action)
        self.assertEqual(self.monk.ki_count, 1)
        self.assertEqual(self.battle.entity_state_for(self.monk)['bonus_action'], 0)
        self.assertTrue(self.monk.dodge(self.battle))

    def test_step_of_the_wind_dash_increases_movement(self):
        starting_movement = self.battle.entity_state_for(self.monk)['movement']
        action = StepOfTheWindAction(
            self.session, self.monk, 'step_of_the_wind', {'mode': 'dash'}
        )
        action.resolve(self.session, None, {'battle': self.battle})
        self.battle.commit(action)
        self.assertEqual(self.monk.ki_count, 1)
        self.assertEqual(
            self.battle.entity_state_for(self.monk)['movement'],
            starting_movement + self.monk.speed(),
        )

    def test_step_of_the_wind_disengage_sets_disengage_flag(self):
        action = StepOfTheWindAction(
            self.session, self.monk, 'step_of_the_wind', {'mode': 'disengage'}
        )
        action.resolve(self.session, None, {'battle': self.battle})
        self.battle.commit(action)
        self.assertEqual(self.monk.ki_count, 1)
        self.assertIn('disengage', self.battle.entity_state_for(self.monk)['statuses'])

    def test_martial_arts_bonus_attack_only_after_attack(self):
        # Without martial_arts_pending, the bonus attack must not be available.
        self.assertFalse(MartialArtsBonusAttackAction.can(self.monk, self.battle))
        state = self.battle.entity_state_for(self.monk)
        state['martial_arts_pending'] = True
        self.assertTrue(MartialArtsBonusAttackAction.can(self.monk, self.battle))


if __name__ == '__main__':
    unittest.main()
