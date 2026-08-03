"""Regression tests for spell apply dispatch."""

import unittest
from unittest.mock import MagicMock

from natural20.actions.spell_action import SpellAction
from natural20.event_manager import EventManager
from natural20.session import Session
from natural20.spell.wizard_spells import FlySpell, UtilityWizardSpell


class TestSpellApplyDispatch(unittest.TestCase):
    def setUp(self):
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.battle = MagicMock()
        self.battle.session = self.session
        self.caster = MagicMock()
        self.caster.name = 'Crysania'
        self.caster.statuses = []
        self.caster.register_effect = MagicMock()
        self.logged = []
        self.session.event_manager.register_event_listener(
            'spell_buf',
            lambda event: self.logged.append(event),
        )

    def test_fly_apply_logs_once(self):
        spell_props = self.session.load_spell('fly')
        fly = FlySpell(self.session, self.caster, 'FlySpell', spell_props)
        item = {
            'type': 'wizard_spell_effect',
            'source': self.caster,
            'target': self.caster,
            'effect': fly,
            'spell': spell_props,
        }
        SpellAction.apply(self.battle, item, self.session)
        self.assertEqual(len(self.logged), 1)
        self.assertIs(self.logged[0]['spell'], fly)

    def test_utility_wizard_spell_apply_ignores_wrong_type(self):
        spell_props = self.session.load_spell('fly')
        fly = FlySpell(self.session, self.caster, 'FlySpell', spell_props)
        item = {
            'type': 'spell_damage',
            'source': self.caster,
            'target': self.caster,
            'effect': fly,
            'spell': spell_props,
        }
        UtilityWizardSpell.apply(self.battle, item, self.session)
        self.assertEqual(self.logged, [])
