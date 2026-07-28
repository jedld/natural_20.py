"""Tests for discoverable object notes (Notable mixin)."""

import unittest
from unittest import mock
from natural20.item_library.object import Object
from natural20.event_manager import EventManager
from natural20.session import Session


def _session():
    return Session(root_path='tests/fixtures', event_manager=EventManager())


class TestNotableNotes(unittest.TestCase):
    def test_investigation_gated_note_requires_check_result(self):
        session = _session()
        obj = Object(session, None, {
            'name': 'clue',
            'notes': [
                {'note': 'Obvious scratch marks.'},
                {'note': 'Hidden ledger reference.', 'investigation_dc': 10},
            ],
        })
        pc = mock.MagicMock()
        pc.passive_perception.return_value = 12

        visible, _ = obj.list_notes(entity_pov=[pc])
        self.assertEqual(len(visible), 1)

        obj.check_results[pc] = {'investigation_check': 12}
        visible, _ = obj.list_notes(entity_pov=[pc])
        self.assertEqual(len(visible), 2)

    def test_religion_gated_note_uses_religion_check(self):
        session = _session()
        obj = Object(session, None, {
            'name': 'altar',
            'notes': [
                {'note': 'Rose ash on the stone.', 'religion_dc': 12},
            ],
        })
        pc = mock.MagicMock()
        obj.check_results[pc] = {'religion_check': 14}
        visible, _ = obj.list_notes(entity_pov=[pc])
        self.assertEqual(len(visible), 1)
        self.assertTrue(visible[0]['note'])

    def test_outward_appearance_surfaces_as_zero_dc_perception_note(self):
        session = _session()
        obj = Object(session, None, {
            'name': 'guard',
            'outward_appearance': 'A scarred dwarf in soot-stained plate.',
        })
        pc = mock.MagicMock()
        pc.passive_perception.return_value = 10
        self.assertTrue(obj.has_notes())
        visible, new_notes = obj.list_notes(entity=pc, perception=12)
        self.assertEqual(len(visible), 1)
        self.assertIn('scarred dwarf', visible[0]['note'])
        self.assertIn(pc, new_notes)


if __name__ == '__main__':
    unittest.main()
