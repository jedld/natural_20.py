"""Tests for the Light cantrip."""

import random
import unittest

import numpy as np

from natural20.session import Session
from natural20.event_manager import EventManager
from natural20.player_character import PlayerCharacter
from natural20.battle import Battle
from natural20.map import Map
from natural20.spell.light_spell import LightSpell, LightEffect


class TestLightSpell(unittest.TestCase):
    def setUp(self):
        random.seed(4242)
        np.random.seed(4242)
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.battle_map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.battle_map)
        self.wizard = PlayerCharacter.load(self.session, 'silvery_barbs_wizard.yml')
        self.battle.add(self.wizard, 'a', position=[0, 5])
        self.wizard.reset_turn(self.battle)

    # -- YAML / loader -------------------------------------------------
    def test_spell_loads(self):
        spell = self.session.load_spell('light')
        self.assertEqual(spell['level'], 0)
        self.assertEqual(spell['casting_time'], '1:action')
        self.assertEqual(spell['range'], 5)
        self.assertEqual(spell['bright'], 20)
        self.assertEqual(spell['dim'], 20)
        self.assertEqual(spell['school'], 'evocation')
        self.assertEqual(spell['duration'], '1h')
        self.assertIn('Wizard', spell['spell_list_classes'])
        self.assertEqual(spell['spell_class'], 'Natural20::Light')

    def test_loader_resolves_class(self):
        from natural20.utils.spell_loader import load_spell_class
        cls = load_spell_class('LightSpell')
        self.assertIs(cls, LightSpell)

    # -- light_override math ------------------------------------------
    def test_light_override_returns_20_20(self):
        out = LightSpell.light_override(self.wizard, {'bright': 0, 'dim': 0})
        self.assertEqual(out, {'bright': 20, 'dim': 20})

    def test_light_override_does_not_shrink_existing_light(self):
        out = LightSpell.light_override(self.wizard, {'bright': 30, 'dim': 30})
        self.assertEqual(out, {'bright': 30, 'dim': 30})

    # -- apply on willing ally (no save) ------------------------------
    def _make_spell(self):
        spell_props = self.session.load_spell('light')
        return LightSpell(self.session, self.wizard, 'LightSpell', spell_props)

    def test_apply_on_self_attaches_light_override(self):
        spell = self._make_spell()
        effect = LightEffect(self.wizard, self.wizard)
        item = {
            'type': 'light',
            'source': self.wizard,
            'target': self.wizard,
            'color': 'white',
            'effect': effect,
            'spell': spell.properties,
            'saving_throw': None,
            'save_success': False,
        }
        LightSpell.apply(self.battle, item, session=self.session)

        self.assertTrue(self.wizard.has_effect('light_override'))
        light = self.wizard.light_properties()
        self.assertIsNotNone(light)
        self.assertGreaterEqual(light['bright'], 20)
        self.assertGreaterEqual(light['dim'], 20)
        # Caster tracks the casted effect
        self.assertTrue(self.wizard.has_casted_effect('light'))

    # -- recast ends prior instance -----------------------------------
    def test_recast_ends_prior_light(self):
        spell = self._make_spell()
        effect_a = LightEffect(self.wizard, self.wizard)
        LightSpell.apply(self.battle, {
            'type': 'light', 'source': self.wizard, 'target': self.wizard,
            'color': 'white', 'effect': effect_a, 'spell': spell.properties,
            'saving_throw': None, 'save_success': False,
        }, session=self.session)

        effect_b = LightEffect(self.wizard, self.wizard, color='blue')
        LightSpell.apply(self.battle, {
            'type': 'light', 'source': self.wizard, 'target': self.wizard,
            'color': 'blue', 'effect': effect_b, 'spell': spell.properties,
            'saving_throw': None, 'save_success': False,
        }, session=self.session)

        # Only the second effect should remain in casted_effects.
        active = [f for f in self.wizard.casted_effects if f['effect'].id == 'light']
        self.assertEqual(len(active), 1)
        self.assertIs(active[0]['effect'], effect_b)

    # -- dismiss removes light_override -------------------------------
    def test_dismiss_removes_light_override(self):
        spell = self._make_spell()
        effect = LightEffect(self.wizard, self.wizard)
        LightSpell.apply(self.battle, {
            'type': 'light', 'source': self.wizard, 'target': self.wizard,
            'color': 'white', 'effect': effect, 'spell': spell.properties,
            'saving_throw': None, 'save_success': False,
        }, session=self.session)
        self.assertTrue(self.wizard.has_effect('light_override'))

        self.wizard.remove_effect('light')
        self.assertFalse(self.wizard.has_effect('light_override'))
        self.assertFalse(self.wizard.has_casted_effect('light'))

    # -- hostile target requires DEX save -----------------------------
    def test_hostile_save_success_fizzles_spell(self):
        from unittest.mock import patch
        skeleton = self.session.npc('skeleton')
        self.battle.add(skeleton, 'b', position=[1, 5])
        self.battle.start()
        self.wizard.reset_turn(self.battle)
        skeleton.reset_turn(self.battle)

        spell = self._make_spell()
        # Force resolve to behave deterministically: patch save_throw to return
        # a roll that beats the DC.
        class _FakeRoll:
            def result(self_inner):
                return 99

        with patch.object(skeleton, 'save_throw', return_value=_FakeRoll()):
            result = spell.resolve(self.wizard, self.battle, _FakeAction(skeleton), self.battle_map)

        self.assertEqual(len(result), 1)
        item = result[0]
        self.assertIsNotNone(item['saving_throw'])
        self.assertTrue(item['save_success'])

        LightSpell.apply(self.battle, item, session=self.session)
        # Spell fizzled — no light_override on skeleton, no casted effect on wizard.
        self.assertFalse(skeleton.has_effect('light_override'))
        self.assertFalse(self.wizard.has_casted_effect('light'))

    def test_hostile_save_fail_lights_target(self):
        from unittest.mock import patch
        skeleton = self.session.npc('skeleton')
        self.battle.add(skeleton, 'b', position=[1, 5])
        self.battle.start()
        self.wizard.reset_turn(self.battle)
        skeleton.reset_turn(self.battle)

        spell = self._make_spell()

        class _FakeRoll:
            def result(self_inner):
                return 1

        with patch.object(skeleton, 'save_throw', return_value=_FakeRoll()):
            result = spell.resolve(self.wizard, self.battle, _FakeAction(skeleton), self.battle_map)

        item = result[0]
        self.assertFalse(item['save_success'])

        LightSpell.apply(self.battle, item, session=self.session)
        self.assertTrue(skeleton.has_effect('light_override'))
        self.assertTrue(self.wizard.has_casted_effect('light'))

    # -- ally target needs no save ------------------------------------
    def test_ally_target_no_save_required(self):
        spell = self._make_spell()
        # Targeting self → no save required even though battle is active.
        self.battle.start()
        self.wizard.reset_turn(self.battle)

        result = spell.resolve(self.wizard, self.battle, _FakeAction(self.wizard), self.battle_map)
        item = result[0]
        self.assertIsNone(item['saving_throw'])


class _FakeAction:
    """Stand-in for SpellAction with just the .target attribute."""
    def __init__(self, target):
        self.target = target
        self.at_level = 0


if __name__ == '__main__':
    unittest.main()
