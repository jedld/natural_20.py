"""Tests for NPC-only object annotations."""

import unittest
from unittest import mock

from natural20.item_library.object import Object
from natural20.event_manager import EventManager
from natural20.session import Session
from natural20.utils.object_annotations import format_annotations_for_subject


def _session():
    return Session(root_path='tests/fixtures', event_manager=EventManager())


class TestAnnotatable(unittest.TestCase):
    def test_player_characters_never_see_annotations(self):
        session = _session()
        obj = Object(session, None, {
            'name': 'safe',
            'annotations': [
                {'text': 'Staff ledger code'},
            ],
        })
        pc = mock.MagicMock()
        pc.is_npc.return_value = False

        visible, _ = obj.list_annotations(pc)
        self.assertEqual(visible, [])

    def test_npc_viewer_allowlist(self):
        session = _session()
        obj = Object(session, None, {
            'name': 'safe',
            'annotations': [
                {
                    'text': 'Mara only scratch',
                    'viewers': ['mara_bartender'],
                },
            ],
        })
        mara = mock.MagicMock()
        mara.is_npc.return_value = True
        mara.entity_uid = 'mara_bartender'
        mara.properties = {}

        pip = mock.MagicMock()
        pip.is_npc.return_value = True
        pip.entity_uid = 'pip_barmaid'
        pip.properties = {}

        mara_visible, _ = obj.list_annotations(mara)
        pip_visible, _ = obj.list_annotations(pip)

        self.assertEqual(len(mara_visible), 1)
        self.assertEqual(mara_visible[0]['text'], 'Mara only scratch')
        self.assertEqual(pip_visible, [])

    def test_any_npc_sees_annotation_without_viewers_list(self):
        session = _session()
        obj = Object(session, None, {
            'name': 'safe',
            'annotations': [
                {'text': 'Staff memo'},
            ],
        })
        npc = mock.MagicMock()
        npc.is_npc.return_value = True
        npc.properties = {}

        visible, _ = obj.list_annotations(npc)
        self.assertEqual(len(visible), 1)
        self.assertEqual(visible[0]['text'], 'Staff memo')

    def test_perception_dc_is_ignored(self):
        session = _session()
        obj = Object(session, None, {
            'name': 'safe',
            'annotations': [
                {'text': 'Still visible', 'perception_dc': 99},
            ],
        })
        npc = mock.MagicMock()
        npc.is_npc.return_value = True
        npc.passive_perception.return_value = 1
        npc.properties = {}

        visible, _ = obj.list_annotations(npc)
        self.assertEqual(len(visible), 1)

    def test_format_annotations_for_subject(self):
        session = _session()
        obj = Object(session, None, {
            'name': 'safe',
            'annotations': [
                {'text': 'Key on third hook'},
            ],
        })
        npc = mock.MagicMock()
        npc.is_npc.return_value = True
        npc.properties = {}

        text = format_annotations_for_subject(npc, obj)
        self.assertIn('Key on third hook', text)


if __name__ == '__main__':
    unittest.main()
