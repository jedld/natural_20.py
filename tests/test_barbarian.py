import random
import unittest
import numpy as np

from natural20.session import Session
from natural20.event_manager import EventManager
from natural20.player_character import PlayerCharacter
from natural20.battle import Battle
from natural20.map import Map
from natural20.actions.rage_action import RageAction, RecklessAttackAction, EndRageAction
from natural20.weapons import damage_modifier, compute_advantages_and_disadvantages


class TestBarbarian(unittest.TestCase):
    def setUp(self):
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.map)
        np.random.seed(7000)
        random.seed(7000)
        self.barbarian = PlayerCharacter.load(self.session, 'goliath_barbarian.yml')
        self.battle.add(self.barbarian, 'a', position=[0, 5])
        # An NPC opponent for advantage / damage tests.
        self.fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle.add(self.fighter, 'b', position=[1, 5])
        self.battle.start()
        self.barbarian.reset_turn(self.battle)

    # --- features ---

    def test_class_features_present(self):
        self.assertTrue(self.barbarian.class_feature('rage'))
        self.assertTrue(self.barbarian.class_feature('unarmored_defense_barbarian'))
        # Level 2 features:
        self.assertTrue(self.barbarian.class_feature('reckless_attack'))
        self.assertTrue(self.barbarian.class_feature('danger_sense'))

    # --- rage pool ---

    def test_rage_pool_initialized(self):
        self.assertEqual(self.barbarian.rage_max, 2)
        self.assertEqual(self.barbarian.rage_count, 2)
        self.assertTrue(self.barbarian.has_rage(1))
        self.assertEqual(self.barbarian.rage_damage_bonus(), 2)

    def test_consume_rage(self):
        self.barbarian.consume_rage(1)
        self.assertEqual(self.barbarian.rage_count, 1)
        self.barbarian.consume_rage(5)
        self.assertEqual(self.barbarian.rage_count, 0)
        self.assertFalse(self.barbarian.has_rage(1))

    def test_long_rest_refills_rage(self):
        self.barbarian.consume_rage(2)
        self.barbarian.begin_rage()  # already 0 uses, but force state
        # Reset state before long rest
        self.barbarian.raging = True
        self.barbarian.long_rest()
        self.assertEqual(self.barbarian.rage_count, 2)
        self.assertFalse(self.barbarian.is_raging())

    # --- rage mechanics ---

    def test_rage_action_can_and_apply(self):
        self.assertTrue(RageAction.can(self.barbarian, self.battle))
        action = RageAction(self.session, self.barbarian, 'rage').build_map()
        action.resolve(self.session, self.map, {'battle': self.battle})
        for item in action.result:
            RageAction.apply(self.battle, item, self.session)
        self.assertTrue(self.barbarian.is_raging())
        self.assertEqual(self.barbarian.rage_count, 1)
        # Bonus action consumed
        self.assertEqual(self.barbarian.total_bonus_actions(self.battle), 0)
        # Cannot rage again while already raging
        self.assertFalse(RageAction.can(self.barbarian, self.battle))

    def test_rage_resistance_to_bps(self):
        self.assertFalse(self.barbarian.resistant_to('bludgeoning'))
        self.barbarian.begin_rage()
        self.assertTrue(self.barbarian.resistant_to('bludgeoning'))
        self.assertTrue(self.barbarian.resistant_to('piercing'))
        self.assertTrue(self.barbarian.resistant_to('slashing'))
        self.assertFalse(self.barbarian.resistant_to('fire'))
        self.barbarian.end_rage()
        self.assertFalse(self.barbarian.resistant_to('bludgeoning'))

    def test_rage_damage_bonus_on_str_melee(self):
        battleaxe = self.session.load_weapon('battleaxe')
        # Without rage: STR mod (+3), no rage bonus
        normal = damage_modifier(self.barbarian, battleaxe)
        self.assertNotIn('+5', normal)
        self.barbarian.begin_rage()
        with_rage = damage_modifier(self.barbarian, battleaxe)
        # +3 STR mod + 2 rage = +5
        self.assertTrue(with_rage.endswith('+5'))

    def test_rage_no_bonus_on_dex_attack(self):
        # use dagger as a finesse weapon - but barbarian's STR (3) >= DEX (2)
        # so STR is selected anyway. Force DEX check via a weapon that
        # cannot use STR: ranged. Use sling (ranged_attack).
        sling = self.session.load_weapon('sling')
        self.barbarian.begin_rage()
        result = damage_modifier(self.barbarian, sling)
        # DEX +2, no rage bonus on ranged
        self.assertTrue(result.endswith('+2'))

    def test_rage_duration_decrements_each_turn(self):
        self.barbarian.begin_rage()
        self.assertEqual(self.barbarian.rage_rounds_remaining, 10)
        self.barbarian.resolve_trigger('start_of_turn')
        self.assertEqual(self.barbarian.rage_rounds_remaining, 9)

    # --- reckless attack ---

    def test_reckless_attack_grants_advantage(self):
        battleaxe = self.session.load_weapon('battleaxe')
        adv_before, _ = compute_advantages_and_disadvantages(
            self.session, self.barbarian, self.fighter, battleaxe, battle=self.battle
        )
        self.assertNotIn('reckless_attack', adv_before)
        self.barbarian.use_reckless_attack()
        adv_after, _ = compute_advantages_and_disadvantages(
            self.session, self.barbarian, self.fighter, battleaxe, battle=self.battle
        )
        self.assertIn('reckless_attack', adv_after)

    def test_reckless_attack_grants_attackers_advantage(self):
        battleaxe = self.session.load_weapon('battleaxe')
        self.barbarian.use_reckless_attack()
        adv, _ = compute_advantages_and_disadvantages(
            self.session, self.fighter, self.barbarian, battleaxe, battle=self.battle
        )
        self.assertIn('target_is_reckless', adv)

    def test_reckless_action_apply(self):
        self.assertTrue(RecklessAttackAction.can(self.barbarian, self.battle))
        action = RecklessAttackAction(self.session, self.barbarian, 'reckless_attack').build_map()
        action.resolve(self.session, self.map, {'battle': self.battle})
        for item in action.result:
            RecklessAttackAction.apply(self.battle, item, self.session)
        self.assertTrue(self.barbarian.is_reckless())
        # Not selectable again until next turn
        self.assertFalse(RecklessAttackAction.can(self.barbarian, self.battle))

    def test_reckless_clears_at_start_of_turn(self):
        self.barbarian.use_reckless_attack()
        self.assertTrue(self.barbarian.is_reckless())
        # Simulate next turn
        self.barbarian.resolve_trigger('start_of_turn')
        self.assertFalse(self.barbarian.is_reckless())

    # --- unarmored defense ---

    def test_unarmored_defense_barbarian(self):
        # Strip armor (the goliath_barbarian.yml fixture has none).
        # AC = 10 + DEX (+2) + CON (+3) = 15
        self.assertEqual(self.barbarian.armor_class(), 15)

    def test_end_rage_action(self):
        self.barbarian.begin_rage()
        self.assertTrue(self.barbarian.is_raging())
        action = EndRageAction(self.session, self.barbarian, 'end_rage').build_map()
        action.resolve(self.session, self.map, {'battle': self.battle})
        for item in action.result:
            EndRageAction.apply(self.battle, item, self.session)
        self.assertFalse(self.barbarian.is_raging())


if __name__ == '__main__':
    unittest.main()
