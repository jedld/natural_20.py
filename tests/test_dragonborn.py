"""Tests for Dragonborn racial traits (5e 2014 rules).

Covers:
- Draconic ancestry loading (get_draconic_ancestry / get_draconic_ancestry_info)
- Damage resistance wiring from draconic ancestry
- BreathWeaponAction registration in class_feature_registry
- Breath weapon usage tracking (once per short/long rest)
- Breath weapon reset on short_rest and long_rest
"""

import copy
import random
import unittest

from natural20.battle import Battle
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.utils.class_feature_registry import (
    collect_class_feature_actions,
)
from natural20.actions.breath_weapon_action import BreathWeaponAction


class _MakeSession:
    """Shared session factory."""

    @staticmethod
    def make_session():
        return Session(root_path='tests/fixtures')


class TestDraconicAncestryLoading(unittest.TestCase, _MakeSession):
    """Draconic ancestry should be loaded from subrace or ancestry property."""

    def setUp(self):
        self.session = self.make_session()

    def test_ancestry_loaded_from_subrace(self):
        pc = PlayerCharacter.load(self.session, 'characters/dragonborn_fighter.yml')
        self.assertEqual(pc.get_draconic_ancestry(), 'red')

    def test_ancestry_info_returns_correct_data(self):
        pc = PlayerCharacter.load(self.session, 'characters/dragonborn_fighter.yml')
        info = pc.get_draconic_ancestry_info()
        self.assertIsNotNone(info)
        self.assertEqual(info['damage_type'], 'fire')
        self.assertEqual(info['save'], 'dex')
        self.assertEqual(info['shape'], 'cone')

    def test_ancestry_info_with_explicit_key(self):
        pc = PlayerCharacter.load(self.session, 'characters/dragonborn_fighter.yml')
        info = pc.get_draconic_ancestry_info('black')
        self.assertIsNotNone(info)
        self.assertEqual(info['damage_type'], 'acid')
        self.assertEqual(info['save'], 'dex')
        self.assertEqual(info['shape'], 'line')

    def test_ancestry_info_returns_none_for_bad_key(self):
        pc = PlayerCharacter.load(self.session, 'characters/dragonborn_fighter.yml')
        info = pc.get_draconic_ancestry_info('nonexistent')
        self.assertIsNone(info)

    def test_non_dragonborn_returns_none_ancestry(self):
        pc = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.assertIsNone(pc.get_draconic_ancestry())


class TestDamageResistanceWiring(unittest.TestCase, _MakeSession):
    """Damage resistance from draconic ancestry should be wired on load."""

    def setUp(self):
        self.session = self.make_session()

    def test_red_dragonborn_resists_fire(self):
        pc = PlayerCharacter.load(self.session, 'characters/dragonborn_fighter.yml')
        self.assertIn('fire', pc.resistances)

    def test_black_dragonborn_resists_acid(self):
        pc = PlayerCharacter.load(
            self.session,
            'characters/dragonborn_fighter.yml',
            override={'subrace': 'black'},
        )
        self.assertIn('acid', pc.resistances)

    def test_white_dragonborn_resists_cold(self):
        pc = PlayerCharacter.load(
            self.session,
            'characters/dragonborn_fighter.yml',
            override={'subrace': 'white'},
        )
        self.assertIn('cold', pc.resistances)

    def test_non_dragonborn_has_no_extra_resistance(self):
        pc = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.assertNotIn('fire', pc.resistances)


class TestBreathWeaponActionRegistration(unittest.TestCase, _MakeSession):
    """BreathWeaponAction should be registered in class_feature_registry."""

    def setUp(self):
        self.session = self.make_session()

    def test_breath_weapon_action_available_for_dragonborn(self):
        pc = PlayerCharacter.load(self.session, 'characters/dragonborn_fighter.yml')
        actions = collect_class_feature_actions(self.session, pc)
        action_types = [type(a).__name__ for a in actions]
        self.assertIn('BreathWeaponAction', action_types)

    def test_breath_weapon_action_not_available_for_non_dragonborn(self):
        pc = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        actions = collect_class_feature_actions(self.session, pc)
        action_types = [type(a).__name__ for a in actions]
        self.assertNotIn('BreathWeaponAction', action_types)

    def test_breath_weapon_action_has_correct_damage_type(self):
        pc = PlayerCharacter.load(self.session, 'characters/dragonborn_fighter.yml')
        actions = collect_class_feature_actions(self.session, pc)
        bw_actions = [a for a in actions if isinstance(a, BreathWeaponAction)]
        self.assertEqual(len(bw_actions), 1)
        self.assertEqual(bw_actions[0].damage_type, 'fire')

    def test_breath_weapon_action_has_correct_shape(self):
        pc = PlayerCharacter.load(self.session, 'characters/dragonborn_fighter.yml')
        actions = collect_class_feature_actions(self.session, pc)
        bw_actions = [a for a in actions if isinstance(a, BreathWeaponAction)]
        self.assertEqual(bw_actions[0].shape, 'cone')

    def test_breath_weapon_action_has_correct_save_ability(self):
        pc = PlayerCharacter.load(self.session, 'characters/dragonborn_fighter.yml')
        actions = collect_class_feature_actions(self.session, pc)
        bw_actions = [a for a in actions if isinstance(a, BreathWeaponAction)]
        self.assertEqual(bw_actions[0].save_ability, 'dex')

    def test_breath_weapon_can_checks_ancestry(self):
        pc = PlayerCharacter.load(self.session, 'characters/dragonborn_fighter.yml')
        self.assertTrue(BreathWeaponAction.can(pc, None))

    def test_breath_weapon_can_returns_false_for_non_dragonborn(self):
        pc = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.assertFalse(BreathWeaponAction.can(pc, None))


class TestBreathWeaponUsageTracking(unittest.TestCase, _MakeSession):
    """Breath weapon should track usage and reset on rest."""

    def setUp(self):
        self.session = self.make_session()
        self.map = Map(self.session, 'battle_sim_objects')

    def test_initial_usage_flag_is_false(self):
        pc = PlayerCharacter.load(self.session, 'characters/dragonborn_fighter.yml')
        self.assertFalse(pc.breath_weapon_used)

    def test_breath_weapon_can_returns_false_after_use(self):
        pc = PlayerCharacter.load(self.session, 'characters/dragonborn_fighter.yml')
        # Without battle, can() only checks ancestry and feature presence
        self.assertTrue(BreathWeaponAction.can(pc, None))
        # Simulate usage
        pc.breath_weapon_used = True
        # With battle=None, usage is still checked
        self.assertFalse(BreathWeaponAction.can(pc, None))

    def test_short_rest_resets_breath_weapon(self):
        pc = PlayerCharacter.load(self.session, 'characters/dragonborn_fighter.yml')
        pc.breath_weapon_used = True
        self.assertFalse(BreathWeaponAction.can(pc, None))
        # Short rest resets (force=True to skip precondition checks)
        pc.short_rest(None, force=True)
        self.assertFalse(pc.breath_weapon_used)
        self.assertTrue(BreathWeaponAction.can(pc, None))

    def test_long_rest_resets_breath_weapon(self):
        pc = PlayerCharacter.load(self.session, 'characters/dragonborn_fighter.yml')
        pc.breath_weapon_used = True
        self.assertFalse(BreathWeaponAction.can(pc, None))
        # Long rest resets
        pc.long_rest(force=True)
        self.assertFalse(pc.breath_weapon_used)

    def test_breath_weapon_serialization_round_trip(self):
        pc = PlayerCharacter.load(self.session, 'characters/dragonborn_fighter.yml')
        pc.breath_weapon_used = True
        data = pc.to_dict()
        self.assertEqual(data.get('class_resources', {}).get('breath_weapon_used'), True)
        # Restore via from_dict (static method pattern)
        restored = PlayerCharacter.from_dict(data)
        self.assertTrue(restored.breath_weapon_used)


class TestBreathWeaponActionSerialization(unittest.TestCase, _MakeSession):
    """BreathWeaponAction should serialize and deserialize correctly."""

    def setUp(self):
        self.session = self.make_session()

    def test_to_dict_contains_required_fields(self):
        pc = PlayerCharacter.load(self.session, 'characters/dragonborn_fighter.yml')
        action = BreathWeaponAction(
            session=self.session,
            source=pc,
            target=None,
            ancestry='red',
            damage_type='fire',
            save_ability='dex',
            shape='cone',
            level=1,
        )
        data = action.to_dict()
        self.assertEqual(data['ancestry'], 'red')
        self.assertEqual(data['damage_type'], 'fire')
        self.assertEqual(data['save_ability'], 'dex')
        self.assertEqual(data['shape'], 'cone')
        self.assertEqual(data['level'], 1)

    def test_from_dict_round_trip(self):
        pc = PlayerCharacter.load(self.session, 'characters/dragonborn_fighter.yml')
        action = BreathWeaponAction(
            session=self.session,
            source=pc,
            target=None,
            ancestry='black',
            damage_type='acid',
            save_ability='dex',
            shape='line',
            level=5,
            range_feet=20,
        )
        data = action.to_dict()
        restored = BreathWeaponAction.from_dict(data, self.session)
        self.assertEqual(restored.ancestry, 'black')
        self.assertEqual(restored.damage_type, 'acid')
        self.assertEqual(restored.save_ability, 'dex')
        self.assertEqual(restored.shape, 'line')
        self.assertEqual(restored.level, 5)
        self.assertEqual(restored.range_feet, 20)


class TestBreathWeaponBuildMap(unittest.TestCase, _MakeSession):
    """BreathWeaponAction.build_map should return correct selector."""

    def setUp(self):
        self.session = self.make_session()

    def test_cone_shape_returns_select_cone(self):
        pc = PlayerCharacter.load(self.session, 'characters/dragonborn_fighter.yml')
        action = BreathWeaponAction(
            session=self.session,
            source=pc,
            target=None,
            ancestry='red',
            damage_type='fire',
            save_ability='dex',
            shape='cone',
            level=1,
        )
        map_data = action.build_map()
        self.assertEqual(map_data['type'], 'select_cone')

    def test_line_shape_returns_select_line(self):
        pc = PlayerCharacter.load(
            self.session,
            'characters/dragonborn_fighter.yml',
            override={'subrace': 'black'},
        )
        action = BreathWeaponAction(
            session=self.session,
            source=pc,
            target=None,
            ancestry='black',
            damage_type='acid',
            save_ability='dex',
            shape='line',
            level=1,
        )
        map_data = action.build_map()
        self.assertEqual(map_data['type'], 'select_line')


class TestBreathWeaponDCCalculation(unittest.TestCase, _MakeSession):
    """BreathWeaponAction DC should use 8 + proficiency + ability modifier."""

    def setUp(self):
        self.session = self.make_session()

    def test_dc_calculation_level_1(self):
        """Level 1 Dragonborn: proficiency=2, DEX mod=+1 → DC = 8+2+1 = 11."""
        pc = PlayerCharacter.load(self.session, 'characters/dragonborn_fighter.yml')
        action = BreathWeaponAction(
            session=self.session,
            source=pc,
            target=None,
            ancestry='red',
            damage_type='fire',
            save_ability='dex',
            shape='cone',
            level=1,
        )
        dc = action._get_save_dc()
        self.assertEqual(dc, 11)


if __name__ == '__main__':
    unittest.main()
