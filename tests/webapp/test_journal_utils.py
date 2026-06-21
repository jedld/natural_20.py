"""Tests for webapp.blueprints.helpers.journal_utils."""

import unittest
from unittest.mock import MagicMock, patch, call


class TestJournalUtils(unittest.TestCase):
    """Test cases for journal_utils module."""

    def setUp(self):
        """Set up test fixtures."""
        from webapp.blueprints.helpers import journal_utils as mod
        self.mod = mod

    # ------------------------------------------------------------------ #
    # _journal_owner_check
    # ------------------------------------------------------------------ #

    def test_journal_owner_check_dm(self):
        """_journal_owner_check allows DM users."""
        with patch.object(self.mod, 'user_role', return_value=['dm']):
            character = MagicMock()
            allowed, error = self.mod._journal_owner_check(character)
            self.assertTrue(allowed)
            self.assertIsNone(error)

    def test_journal_owner_check_not_authenticated(self):
        """_journal_owner_check returns 401 for unauthenticated users."""
        with patch.object(self.mod, 'user_role', return_value=['player1']):
            with patch('webapp.blueprints.helpers.journal_utils.session', {'username': None}):
                character = MagicMock()
                allowed, error = self.mod._journal_owner_check(character)
                self.assertFalse(allowed)
                self.assertIsNotNone(error)
                response, status = error
                self.assertEqual(status, 401)

    def test_journal_owner_check_owned_character(self):
        """_journal_owner_check allows players to edit their own characters."""
        with patch.object(self.mod, 'user_role', return_value=['player1']):
            with patch('webapp.blueprints.helpers.journal_utils.session', {'username': 'player1'}):
                with patch.object(self.mod, 'entities_controlled_by', return_value=['pc1']):
                    character = 'pc1'
                    allowed, error = self.mod._journal_owner_check(character)
                    self.assertTrue(allowed)
                    self.assertIsNone(error)

    def test_journal_owner_check_forbidden(self):
        """_journal_owner_check returns 403 for characters not owned by player."""
        with patch.object(self.mod, 'user_role', return_value=['player1']):
            with patch('webapp.blueprints.helpers.journal_utils.session', {'username': 'player1'}):
                with patch.object(self.mod, 'entities_controlled_by', return_value=['pc2']):
                    character = 'pc2'
                    allowed, error = self.mod._journal_owner_check(character)
                    self.assertFalse(allowed)
                    self.assertIsNotNone(error)
                    response, status = error
                    self.assertEqual(status, 403)

    # ------------------------------------------------------------------ #
    # _serialize_journal
    # ------------------------------------------------------------------ #

    def test_serialize_journal_with_search_journal(self):
        """_serialize_journal uses search_journal when available."""
        character = MagicMock()
        character.search_journal.return_value = [{'id': 1, 'text': 'test'}]
        result = self.mod._serialize_journal(character, query='test', kind='narration', limit=10)
        character.search_journal.assert_called_once_with(query='test', kind='narration', limit=10)
        self.assertEqual(result, [{'id': 1, 'text': 'test'}])

    def test_serialize_journal_fallback_to_journal_attr(self):
        """_serialize_journal falls back to journal attribute."""
        character = MagicMock(spec=[])
        character.journal = [{'id': 1, 'text': 'test'}]
        result = self.mod._serialize_journal(character)
        self.assertEqual(result, [{'id': 1, 'text': 'test'}])

    def test_serialize_journal_empty_journal(self):
        """_serialize_journal returns empty list when no journal."""
        character = MagicMock(spec=[])
        character.journal = None
        result = self.mod._serialize_journal(character)
        self.assertEqual(result, [])

    def test_serialize_journal_no_journal_attr(self):
        """_serialize_journal returns empty list when no journal attr."""
        character = MagicMock(spec=[])
        delattr(character, 'journal')
        result = self.mod._serialize_journal(character)
        self.assertEqual(result, [])

    # ------------------------------------------------------------------ #
    # _persist_journal_change
    # ------------------------------------------------------------------ #

    def test_persist_journal_change_success(self):
        """_persist_journal_change calls save_game_async."""
        mock_save = MagicMock()
        with patch.object(self.mod, 'get_current_game') as mock_game:
            with patch.object(self.mod, 'get_logger'):
                mock_game.return_value.save_game_async = mock_save
                character = MagicMock()

                self.mod._persist_journal_change(character)

                mock_save.assert_called_once()

    def test_persist_journal_change_no_save_method(self):
        """_persist_journal_change handles missing save method."""
        with patch.object(self.mod, 'get_current_game') as mock_game:
            with patch.object(self.mod, 'get_logger'):
                mock_game.return_value.save_game_async = None
                character = MagicMock()

                self.mod._persist_journal_change(character)
                # Should not raise

    def test_persist_journal_change_exception_logged(self):
        """_persist_journal_change logs exception on save failure."""
        mock_save = MagicMock(side_effect=RuntimeError('save failed'))
        with patch.object(self.mod, 'get_current_game') as mock_game:
            with patch.object(self.mod, 'get_logger') as mock_logger:
                mock_game.return_value.save_game_async = mock_save
                mock_log = MagicMock()
                mock_logger.return_value = mock_log
                character = MagicMock()

                self.mod._persist_journal_change(character)

                mock_log.debug.assert_called()

    # ------------------------------------------------------------------ #
    # _log_journal_entry_to_campaign_db
    # ------------------------------------------------------------------ #

    def test_log_journal_entry_success(self):
        """_log_journal_entry_to_campaign_db logs entry to campaign DB."""
        mock_db = MagicMock()
        with patch.object(self.mod, 'get_current_game') as mock_game:
            with patch.object(self.mod, 'get_logger'):
                mock_game.return_value.campaign_log_db = mock_db
                character = MagicMock()
                character.entity_uid = 'test_pc'
                entry = {'text': 'test entry'}

                self.mod._log_journal_entry_to_campaign_db(character, entry)

                mock_db.append_journal_entry.assert_called_once_with('test_pc', entry)

    def test_log_journal_entry_no_db(self):
        """_log_journal_entry_to_campaign_db does nothing without campaign_log_db."""
        with patch.object(self.mod, 'get_current_game') as mock_game:
            with patch.object(self.mod, 'get_logger'):
                mock_game.return_value.campaign_log_db = None
                character = MagicMock()
                entry = {'text': 'test entry'}

                self.mod._log_journal_entry_to_campaign_db(character, entry)
                # Should not raise

    def test_log_journal_entry_no_entry(self):
        """_log_journal_entry_to_campaign_db does nothing with no entry."""
        with patch.object(self.mod, 'get_current_game') as mock_game:
            with patch.object(self.mod, 'get_logger'):
                mock_game.return_value.campaign_log_db = MagicMock()
                character = MagicMock()

                self.mod._log_journal_entry_to_campaign_db(character, None)
                # Should not raise

    def test_log_journal_entry_exception_logged(self):
        """_log_journal_entry_to_campaign_db logs exception on failure."""
        mock_db = MagicMock()
        mock_db.append_journal_entry.side_effect = RuntimeError('db error')
        with patch.object(self.mod, 'get_current_game') as mock_game:
            with patch.object(self.mod, 'get_logger'):
                mock_game.return_value.campaign_log_db = mock_db
                character = MagicMock()
                entry = {'text': 'test entry'}

                self.mod._log_journal_entry_to_campaign_db(character, entry)

    # ------------------------------------------------------------------ #
    # _record_narration_for_pcs
    # ------------------------------------------------------------------ #

    def test_record_narration_for_pcs_no_text(self):
        """_record_narration_for_pcs returns early when no text."""
        narration = {'on_enter': {}}
        self.mod._record_narration_for_pcs(narration)
        # Should not raise

    def test_record_narration_for_pcs_with_target_uids(self):
        """_record_narration_for_pcs records for targeted PCs."""
        mock_pc = MagicMock()
        mock_pc.entity_uid = 'pc1'
        mock_pc.add_journal_entry.return_value = {'text': 'narration text'}

        mock_map = MagicMock()
        mock_map.entities = {}

        with patch.object(self.mod, 'get_current_game') as mock_game:
            with patch.object(self.mod, 'get_socketio') as mock_socketio:
                with patch.object(self.mod, 'get_logger'):
                    mock_game.return_value.maps = {'index': mock_map}
                    mock_game.return_value.get_entity_by_uid.return_value = mock_pc
                    mock_socketio.return_value.emit = MagicMock()

                    narration = {'on_enter': {'text': 'narration text', 'title': 'Test'}}
                    self.mod._record_narration_for_pcs(narration, target_uids=['pc1'], source='npc1')

                    mock_pc.add_journal_entry.assert_called_once()
                    mock_socketio.return_value.emit.assert_called_once()

    def test_record_narration_for_pcs_all_on_map(self):
        """_record_narration_for_pcs records for all PCs on map when no targets."""
        mock_pc = MagicMock()
        mock_pc.entity_uid = 'pc1'
        mock_pc.add_journal_entry.return_value = {'text': 'narration text'}

        mock_map = MagicMock()
        mock_map.name = 'test_map'
        mock_map.entities = {mock_pc: (0, 0)}

        with patch.object(self.mod, 'get_current_game') as mock_game:
            with patch.object(self.mod, 'get_socketio') as mock_socketio:
                with patch.object(self.mod, 'get_logger'):
                    mock_game.return_value.maps = {'index': mock_map}
                    mock_socketio.return_value.emit = MagicMock()

                    narration = {'on_enter': {'text': 'narration text', 'title': 'Test'}}
                    self.mod._record_narration_for_pcs(narration, map_name='test_map')

                    mock_pc.add_journal_entry.assert_called_once()
                    mock_socketio.return_value.emit.assert_called_once()

    def test_record_narration_for_pcs_non_pc_skipped(self):
        """_record_narration_for_pcs skips non-PlayerCharacter entities."""
        mock_npc = MagicMock()
        mock_npc.entity_uid = 'npc1'

        mock_map = MagicMock()
        mock_map.entities = {mock_npc: (0, 0)}

        with patch.object(self.mod, 'get_current_game') as mock_game:
            with patch.object(self.mod, 'get_socketio') as mock_socketio:
                with patch.object(self.mod, 'get_logger'):
                    mock_game.return_value.maps = {'index': mock_map}
                    mock_socketio.return_value.emit = MagicMock()

                    narration = {'on_enter': {'text': 'narration text'}}
                    self.mod._record_narration_for_pcs(narration)

                    mock_socketio.return_value.emit.assert_not_called()

    def test_record_narration_for_pcs_tags(self):
        """_record_narration_for_pcs includes outcome and tpk in tags."""
        mock_pc = MagicMock()
        mock_pc.entity_uid = 'pc1'
        mock_pc.add_journal_entry.return_value = {'text': 'narration text'}

        mock_map = MagicMock()
        mock_map.entities = {mock_pc: (0, 0)}

        with patch.object(self.mod, 'get_current_game') as mock_game:
            with patch.object(self.mod, 'get_socketio') as mock_socketio:
                with patch.object(self.mod, 'get_logger'):
                    mock_game.return_value.maps = {'index': mock_map}
                    mock_socketio.return_value.emit = MagicMock()

                    narration = {
                        'on_enter': {
                            'text': 'narration text',
                            'outcome': 'victory',
                            'tpk': True,
                            'title': 'Test',
                        }
                    }
                    self.mod._record_narration_for_pcs(narration)

                    # Check that tags include outcome and tpk
                    call_kwargs = mock_pc.add_journal_entry.call_args[1]
                    self.assertIn('victory', call_kwargs.get('tags', []))
                    self.assertIn('tpk', call_kwargs.get('tags', []))

    def test_record_narration_for_pcs_no_add_journal_entry(self):
        """_record_narration_for_pcs skips PCs without add_journal_entry."""
        mock_pc = MagicMock(spec=[])
        mock_pc.entity_uid = 'pc1'
        delattr(mock_pc, 'add_journal_entry')

        mock_map = MagicMock()
        mock_map.entities = {mock_pc: (0, 0)}

        with patch.object(self.mod, 'get_current_game') as mock_game:
            with patch.object(self.mod, 'get_socketio') as mock_socketio:
                with patch.object(self.mod, 'get_logger'):
                    mock_game.return_value.maps = {'index': mock_map}
                    mock_socketio.return_value.emit = MagicMock()

                    narration = {'on_enter': {'text': 'narration text'}}
                    self.mod._record_narration_for_pcs(narration)

                    mock_socketio.return_value.emit.assert_not_called()

    def test_record_narration_for_pcs_not_dict(self):
        """_record_narration_for_pcs returns early when narration is not a dict."""
        self.mod._record_narration_for_pcs('not a dict')
        # Should not raise

    def test_record_narration_for_pcs_no_affected_uids_no_emit(self):
        """_record_narration_for_pcs does not emit when no UIDs affected."""
        mock_pc = MagicMock()
        mock_pc.entity_uid = 'pc1'
        mock_pc.add_journal_entry.return_value = None  # No stored entry

        mock_map = MagicMock()
        mock_map.entities = {mock_pc: (0, 0)}

        with patch.object(self.mod, 'get_current_game') as mock_game:
            with patch.object(self.mod, 'get_socketio') as mock_socketio:
                with patch.object(self.mod, 'get_logger'):
                    mock_game.return_value.maps = {'index': mock_map}
                    mock_socketio.return_value.emit = MagicMock()

                    narration = {'on_enter': {'text': 'narration text'}}
                    self.mod._record_narration_for_pcs(narration)

                    mock_socketio.return_value.emit.assert_not_called()

    def test_record_narration_for_pcs_socket_emit_fails(self):
        """_record_narration_for_pcs handles socket emit failure gracefully."""
        mock_pc = MagicMock()
        mock_pc.entity_uid = 'pc1'
        mock_pc.add_journal_entry.return_value = {'text': 'narration text'}

        mock_map = MagicMock()
        mock_map.entities = {mock_pc: (0, 0)}

        with patch.object(self.mod, 'get_current_game') as mock_game:
            with patch.object(self.mod, 'get_socketio') as mock_socketio:
                with patch.object(self.mod, 'get_logger'):
                    mock_game.return_value.maps = {'index': mock_map}
                    mock_socketio.return_value.emit.side_effect = Exception('socket error')

                    narration = {'on_enter': {'text': 'narration text'}}
                    self.mod._record_narration_for_pcs(narration)
                    # Should not raise


if __name__ == '__main__':
    unittest.main()
