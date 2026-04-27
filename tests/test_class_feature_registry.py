"""Phase 4 tests for class feature registry."""

import unittest

from natural20.session import Session
from natural20.event_manager import EventManager
from natural20.player_character import PlayerCharacter
from natural20.utils.class_feature_registry import (
    register_class_feature, unregister_class_feature, registered_features,
    collect_class_feature_actions,
)


class _StubAction:
    def __init__(self, session, source, action_type):
        self.session = session
        self.source = source
        self.action_type = action_type

    @staticmethod
    def can(entity, battle):
        return True


class TestClassFeatureRegistry(unittest.TestCase):
    def make_session(self):
        em = EventManager()
        em.standard_cli()
        return Session(root_path='tests/fixtures', event_manager=em)

    def setUp(self):
        self.session = self.make_session()
        self.entity = PlayerCharacter.load(self.session, 'high_elf_mage.yml')

    def tearDown(self):
        for fid in ['_test_feature', '_test_feature_off']:
            unregister_class_feature(fid)

    def test_register_and_lookup(self):
        register_class_feature(feature_id='_test_feature', action_class=_StubAction)
        self.assertIn('_test_feature', registered_features())
        actions = collect_class_feature_actions(self.session, self.entity)
        ids = [a.action_type for a in actions if isinstance(a, _StubAction)]
        self.assertIn('_test_feature', ids)

    def test_provides_predicate_gates(self):
        register_class_feature(
            feature_id='_test_feature_off',
            action_class=_StubAction,
            provides=lambda e: False,
        )
        actions = collect_class_feature_actions(self.session, self.entity)
        ids = [a.action_type for a in actions if isinstance(a, _StubAction)]
        self.assertNotIn('_test_feature_off', ids)

    def test_unregister(self):
        register_class_feature(feature_id='_test_feature', action_class=_StubAction)
        self.assertTrue(unregister_class_feature('_test_feature'))
        self.assertNotIn('_test_feature', registered_features())

    def test_available_actions_consults_registry(self):
        register_class_feature(feature_id='_test_feature', action_class=_StubAction)
        # Fighter has no spell autobuild; battle=None is fine.
        fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        actions = fighter.available_actions(self.session, None)
        ids = [getattr(a, 'action_type', None) for a in actions]
        self.assertIn('_test_feature', ids)


if __name__ == '__main__':
    unittest.main()
