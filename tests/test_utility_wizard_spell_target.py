from types import SimpleNamespace
from unittest.mock import MagicMock

from natural20.spell.wizard_spells import UtilityWizardSpell


class _Creature:
    def __init__(self):
        self.statuses = []
        self.effects = []

    def register_effect(self, name, handler, **kwargs):
        self.effects.append(name)


def _spell():
    spell = UtilityWizardSpell.__new__(UtilityWizardSpell)
    spell.properties = {'id': 'mage_armor'}
    return spell


def _apply(target):
    session = SimpleNamespace(event_manager=MagicMock())
    item = {'type': 'wizard_spell_effect', 'source': None, 'target': target,
            'effect': object(), 'spell': {'id': 'mage_armor'}}
    UtilityWizardSpell.apply(None, item, session)


def test_list_target_from_auto_targeting_applies_to_creature():
    creature = _Creature()
    _apply([creature])
    assert creature.effects == ['mage_armor']
    assert 'mage_armor' in creature.statuses


def test_point_target_does_not_crash():
    _apply([3, 4])


def test_resolve_unwraps_list_target_and_defaults_to_caster():
    caster, ally = _Creature(), _Creature()
    spell = _spell()
    [item] = spell.resolve(caster, None, SimpleNamespace(target=[ally]), None)
    assert item['target'] is ally
    [item] = spell.resolve(caster, None, SimpleNamespace(target=None), None)
    assert item['target'] is caster
