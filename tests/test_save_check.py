"""Tests for Phase 1 spell-extension primitives."""

import random
import unittest

from natural20.die_roll import DieRoll
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.spell.extensions.damage_scaling import DamageScalingMixin
from natural20.spell.extensions.save_check import SaveCheck, SaveResult


class TestDamageScaling(unittest.TestCase):
    def test_scaled_damage_dice_at_base_level(self):
        self.assertEqual(
            DamageScalingMixin._scaled_damage_dice("3d6", "1d6", at_level=1),
            "3d6",
        )

    def test_scaled_damage_dice_upcast(self):
        self.assertEqual(
            DamageScalingMixin._scaled_damage_dice("3d6", "1d6", at_level=4),
            "6d6",
        )

    def test_scaled_damage_dice_thunderwave_pattern(self):
        self.assertEqual(
            DamageScalingMixin._scaled_damage_dice("2d8", "1d8", at_level=3),
            "4d8",
        )

    def test_die_size_mismatch_raises(self):
        with self.assertRaises(ValueError):
            DamageScalingMixin._scaled_damage_dice("3d6", "1d4", at_level=2)

    def test_per_slot_multi_die(self):
        # Some spells add 2d6 per slot.
        self.assertEqual(
            DamageScalingMixin._scaled_damage_dice("8d6", "2d6", at_level=4),
            "14d6",
        )


class TestSaveCheckUnit(unittest.TestCase):
    """SaveCheck against a real PlayerCharacter so we exercise save_throw."""

    @classmethod
    def setUpClass(cls):
        em = EventManager()
        em.standard_cli()
        cls.session = Session(root_path='tests/fixtures', event_manager=em)

    def setUp(self):
        random.seed(4242)
        self.caster = PlayerCharacter.load(self.session, 'high_elf_mage.yml')

    def test_save_check_returns_save_result(self):
        result = SaveCheck.make(self.caster, 'dexterity', dc=5, battle=None)
        self.assertIsInstance(result, SaveResult)
        self.assertEqual(result.ability, 'dexterity')
        self.assertEqual(result.dc, 5)
        self.assertIsNotNone(result.roll)
        # DC of 5 against d20+dex_mod is almost certainly a pass on this seed.
        self.assertTrue(result.passed)
        self.assertTrue(bool(result))

    def test_save_check_impossible_dc_fails(self):
        result = SaveCheck.make(self.caster, 'dexterity', dc=99, battle=None)
        self.assertFalse(result.passed)

    def test_unconscious_autofails_dex(self):
        # Mark the caster unconscious; SaveCheck must short-circuit.
        self.caster.statuses.append('unconscious')
        try:
            result = SaveCheck.make(self.caster, 'dexterity', dc=1, battle=None)
            self.assertTrue(result.auto_failed)
            self.assertFalse(result.passed)
            self.assertIsNone(result.roll)
        finally:
            self.caster.statuses.remove('unconscious')


class TestSaveModifierHook(unittest.TestCase):
    """The new ``save_modifier`` eval_effect hook must be additive."""

    @classmethod
    def setUpClass(cls):
        em = EventManager()
        em.standard_cli()
        cls.session = Session(root_path='tests/fixtures', event_manager=em)

    def setUp(self):
        random.seed(99)
        self.entity = PlayerCharacter.load(self.session, 'high_elf_mage.yml')

    def test_no_modifier_registered_no_change(self):
        # Baseline: roll with the same seed and confirm save_throw still works.
        random.seed(123)
        a = self.entity.save_throw('wisdom', battle=None).result()
        random.seed(123)
        b = self.entity.save_throw('wisdom', battle=None).result()
        self.assertEqual(a, b)

    def test_register_save_modifier_int_bonus(self):
        class _Plus3:
            def save_modifier(self, _entity, opts):
                base = opts.get('value') or 0
                return base + 3

        random.seed(55)
        baseline = self.entity.save_throw('wisdom', battle=None).result()

        self.entity.register_effect(
            'save_modifier', _Plus3(), 'save_modifier',
            effect=None, source=None, duration=None,
        )
        try:
            random.seed(55)
            modified = self.entity.save_throw('wisdom', battle=None).result()
        finally:
            # cleanup so other tests aren't polluted
            self.entity.effects.pop('save_modifier', None)

        self.assertEqual(modified - baseline, 3)


class TestBurningHandsRefactor(unittest.TestCase):
    """Smoke test: the refactored BurningHands still produces save-for-half events."""

    def setUp(self):
        em = EventManager()
        em.standard_cli()
        self.session = Session(root_path='tests/fixtures', event_manager=em)
        random.seed(2024)
        self.caster = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.map = Map(self.session, 'battle_sim_objects')
        from natural20.battle import Battle
        self.battle = Battle(self.session, self.map)
        self.battle.add(self.caster, 'a', position=[4, 5])
        self.battle.start()
        self.caster.reset_turn(self.battle)

    def test_resolve_emits_spell_damage_with_save_failed_field(self):
        from natural20.actions.spell_action import SpellAction
        builder = SpellAction.build(self.session, self.caster)['next'](
            ['burning_hands', 1])['next']
        action = builder([5, 5])  # cone toward (5,5)
        action.resolve(self.session, self.map, {'battle': self.battle})
        spell_events = [r for r in action.result if r.get('type') == 'spell_damage']
        # If anybody is in the cone we should see save_failed populated.
        for evt in spell_events:
            self.assertIn('save_failed', evt)
            self.assertIn('spell_save', evt)
            self.assertIn('damage', evt)
            self.assertEqual(evt['attack_name'], 'burning_hands')


if __name__ == '__main__':
    unittest.main()
