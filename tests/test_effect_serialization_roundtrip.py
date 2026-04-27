"""Phase 4 tests for the effect serialization registry."""

import unittest

from natural20.session import Session
from natural20.event_manager import EventManager
from natural20.utils.effect_registry import (
    register_effect, lookup_effect, registered_effects,
    serialize_effect, deserialize_effect, effect_id_for,
)
from natural20.utils.spell_loader import register_serializable_effects


class _DummyEffect:
    @staticmethod
    def from_dict(data):
        d = _DummyEffect()
        d.payload = data.get('payload')
        return d

    def to_dict(self):
        return {'payload': getattr(self, 'payload', None)}


class TestEffectRegistry(unittest.TestCase):
    def setUp(self):
        register_serializable_effects()

    def test_curated_classes_are_registered(self):
        ids = registered_effects()
        for expected in ('bless', 'bane', 'mage_armor', 'resistance', 'guidance'):
            self.assertIn(expected, ids)

    def test_register_and_lookup_custom(self):
        register_effect('_dummy', _DummyEffect)
        self.assertIs(lookup_effect('_dummy'), _DummyEffect)

    def test_round_trip_custom(self):
        register_effect('_dummy', _DummyEffect)
        eff = _DummyEffect()
        eff.payload = {'note': 'hi'}
        payload = serialize_effect(eff)
        self.assertIsNotNone(payload)
        self.assertEqual(payload['effect_id'], '_dummy')
        rehydrated = deserialize_effect(payload)
        self.assertIsInstance(rehydrated, _DummyEffect)
        self.assertEqual(rehydrated.payload, {'note': 'hi'})

    def test_unknown_effect_round_trip_is_safe(self):
        class _Untracked:
            def to_dict(self):
                return {}
        self.assertIsNone(serialize_effect(_Untracked()))
        self.assertIsNone(deserialize_effect({'effect_id': 'nope', 'data': {}}))

    def test_effect_id_for_dummy(self):
        register_effect('_dummy', _DummyEffect)
        self.assertEqual(effect_id_for(_DummyEffect()), '_dummy')


if __name__ == '__main__':
    unittest.main()
