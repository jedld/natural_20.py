"""Tests for campaign-persisted NPC memory store and conversation tags."""

import os
import shutil
import tempfile
import unittest
from unittest.mock import Mock

from natural20.npc_memory_store import NpcMemoryStore
from webapp.entity_rag_handler import EntityRAGHandler


class TestNpcMemoryStore(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store = NpcMemoryStore(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_create_list_get_update_delete(self):
        created = self.store.create(
            'rose_durst',
            title='Basement warning',
            summary='Player warned about the basement',
            body='Gomerin said the basement stairs are unsafe.',
            tags=['player', 'warning'],
            game_time=42,
            source='test',
            created_by='tester',
        )
        self.assertTrue(created['id'])

        summaries = self.store.list_summaries('rose_durst')
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]['title'], 'Basement warning')

        fetched = self.store.get('rose_durst', created['id'])
        self.assertEqual(fetched['body'], 'Gomerin said the basement stairs are unsafe.')

        updated = self.store.update(
            'rose_durst',
            created['id'],
            summary='Updated summary',
        )
        self.assertEqual(updated['summary'], 'Updated summary')

        deleted = self.store.delete('rose_durst', created['id'])
        self.assertTrue(deleted)
        self.assertIsNone(self.store.get('rose_durst', created['id']))

    def test_format_context_summary(self):
        self.store.create('npc1', title='A', summary='First', game_time=1)
        self.store.create('npc1', title='B', summary='Second', game_time=2, importance=5)
        text = self.store.format_context_summary('npc1', limit=2)
        self.assertIn('[RECALL:', text)
        self.assertIn('B', text)

    def test_persists_to_campaign_directory(self):
        self.store.create('npc1', title='Persisted', summary='On disk')
        path = os.path.join(self.tmpdir, 'npc_memories', 'npc1.json')
        self.assertTrue(os.path.isfile(path))


class TestNpcMemoryConversationTags(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.mock_game_session = Mock()
        self.mock_game_session.game_time = 10
        self.mock_game_session.game_properties = {}
        self.mock_game_session.root_path = self.tmpdir

        self.mock_current_game = Mock()
        self.mock_current_game.get_current_battle.return_value = None
        self.mock_current_game.entity_owners.return_value = []
        self.mock_current_game.output_logger = Mock()
        self.mock_current_game.output_logger.get_visible_entries_for_entity.return_value = []
        self.mock_current_game.npc_memory_store = NpcMemoryStore(self.tmpdir)

        self.rag_handler = EntityRAGHandler(self.mock_game_session, self.mock_current_game)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_parse_remember_directive(self):
        actor = Mock()
        actor.entity_uid = 'npc1'
        directives = self.rag_handler.parse_action_directives(
            '[REMEMBER: title=Met the party, summary=They asked about the well]',
            actor,
        )
        self.assertEqual(directives['remember']['title'], 'Met the party')

    def test_apply_remember_creates_memory(self):
        actor = Mock()
        actor.entity_uid = 'npc1'
        plan = {
            'remember': {
                'title': 'Party visit',
                'summary': 'They visited the shop',
                'body': 'They visited the shop and asked about supplies.',
            },
        }
        result = self.rag_handler.apply_response_plan_directives(plan, actor)
        self.assertIn('remember', result['executed_actions'])
        summaries = self.mock_current_game.npc_memory_store.list_summaries('npc1')
        self.assertEqual(len(summaries), 1)

    def test_npc_memory_context_summary(self):
        self.mock_current_game.npc_memory_store.create(
            'npc1',
            title='Old debt',
            summary='Owes the merchant gold',
        )
        actor = Mock()
        actor.entity_uid = 'npc1'
        text = self.rag_handler.npc_memory_context_summary(actor)
        self.assertIn('Old debt', text)
        self.assertIn('[RECALL:', text)


if __name__ == '__main__':
    unittest.main()
