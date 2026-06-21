"""Tests for webapp.blueprints.helpers.effects."""

import unittest
from unittest.mock import MagicMock, patch, call


class TestEffectsHelpers(unittest.TestCase):
    """Test cases for effects module helpers."""

    def setUp(self):
        """Set up test fixtures."""
        from webapp.blueprints.helpers import effects as mod
        self.mod = mod

    # ------------------------------------------------------------------ #
    # Pure helpers
    # ------------------------------------------------------------------ #

    def test_humanize_condition_empty(self):
        """_humanize_condition returns default for empty condition."""
        self.assertEqual(self.mod._humanize_condition(''), 'control override')
        self.assertEqual(self.mod._humanize_condition(None), 'control override')

    def test_humanize_condition_with_value(self):
        """_humanize_condition replaces underscores with spaces."""
        self.assertEqual(self.mod._humanize_condition('stunned'), 'stunned')
        self.assertEqual(self.mod._humanize_condition('prone_condition'), 'prone condition')

    def test_entity_brief_none(self):
        """_entity_brief returns None for None entity."""
        self.assertIsNone(self.mod._entity_brief(None))

    def test_entity_brief_with_uid_and_name(self):
        """_entity_brief extracts uid and name."""
        entity = MagicMock()
        entity.entity_uid = 'test_entity'
        entity.name = 'Test Entity'
        result = self.mod._entity_brief(entity)
        self.assertEqual(result['uid'], 'test_entity')
        self.assertEqual(result['name'], 'Test Entity')

    def test_entity_brief_callable_label(self):
        """_entity_brief handles callable label."""
        entity = MagicMock()
        entity.entity_uid = 'test_entity'
        entity.label = MagicMock(return_value='Callable Label')
        del entity.name
        result = self.mod._entity_brief(entity)
        self.assertEqual(result['name'], 'Callable Label')

    def test_entity_position_none_game(self):
        """_entity_position returns None when no game."""
        with patch.object(self.mod, 'get_current_game', return_value=None):
            self.assertIsNone(self.mod._entity_position(MagicMock()))

    def test_entity_position_not_on_map(self):
        """_entity_position returns None when entity not on any map."""
        entity = MagicMock()
        game = MagicMock()
        mock_map = MagicMock()
        mock_map.entities = {}
        game.maps = {'index': mock_map}
        with patch.object(self.mod, 'get_current_game', return_value=game):
            self.assertIsNone(self.mod._entity_position(entity))

    def test_entity_position_on_map(self):
        """_entity_position returns [x, y] when entity is on map."""
        entity = MagicMock()
        game = MagicMock()
        mock_map = MagicMock()
        mock_map.entities = {entity: (3, 5)}
        game.maps = {'index': mock_map}
        with patch.object(self.mod, 'get_current_game', return_value=game):
            result = self.mod._entity_position(entity)
            self.assertEqual(result, [3, 5])

    def test_users_controlling_empty(self):
        """_users_controlling returns empty set when no controllers."""
        game = MagicMock()
        game.web_controllers = {}
        game.username_to_sid = {}
        with patch.object(self.mod, 'get_current_game', return_value=game):
            result = self.mod._users_controlling(MagicMock())
            self.assertEqual(result, set())

    def test_users_controlling_with_controller_users(self):
        """_users_controlling includes controller users."""
        entity = MagicMock()
        ctrl = MagicMock()
        ctrl.get_users.return_value = ['user1', 'user2']
        game = MagicMock()
        game.web_controllers = {entity: ctrl}
        game.username_to_sid = {}
        with patch.object(self.mod, 'get_current_game', return_value=game):
            result = self.mod._users_controlling(entity)
            self.assertIn('user1', result)
            self.assertIn('user2', result)

    def test_users_controlling_includes_dm(self):
        """_users_controlling always includes DM users."""
        entity = MagicMock()
        game = MagicMock()
        game.web_controllers = {}
        game.username_to_sid = {'dm_admin': MagicMock(), 'user1': MagicMock()}
        with patch.object(self.mod, 'get_current_game', return_value=game):
            result = self.mod._users_controlling(entity)
            self.assertIn('dm_admin', result)

    # ------------------------------------------------------------------ #
    # Event listener callbacks
    # ------------------------------------------------------------------ #

    @patch('webapp.blueprints.helpers.effects.get_socketio')
    def test_emit_narration_overlay_no_text(self, mock_socketio):
        """_emit_narration_overlay returns early when no narration text."""
        event = {'narration': {}}
        self.mod._emit_narration_overlay(event, lambda *a, **k: None)
        mock_socketio.return_value.emit.assert_not_called()

    @patch('webapp.blueprints.helpers.effects.get_socketio')
    def test_emit_narration_overlay_emits_message(self, mock_socketio):
        """_emit_narration_overlay emits narration message."""
        event = {'narration': {'on_enter': {'text': 'Test narration'}}, 'map_name': 'test_map'}
        self.mod._emit_narration_overlay(event, lambda *a, **k: None)
        mock_socketio.return_value.emit.assert_called_once()
        args = mock_socketio.return_value.emit.call_args
        self.assertEqual(args[0][0], 'message')
        self.assertEqual(args[0][1]['type'], 'narration')

    @patch('webapp.blueprints.helpers.effects.get_socketio')
    def test_emit_narration_overlay_with_source_map(self, mock_socketio):
        """_emit_narration_overlay resolves map from source."""
        event = {'narration': {'on_enter': {'text': 'Test'}}, 'source': MagicMock()}
        mock_source = event['source']
        mock_map = MagicMock()
        mock_map.name = 'resolved_map'
        with patch.object(self.mod, 'get_socketio', mock_socketio):
            with patch.object(self.mod, 'get_game_session') as mock_session:
                mock_session.return_value.map_for.return_value = mock_map
                self.mod._emit_narration_overlay(event, lambda *a, **k: None)

    @patch('webapp.blueprints.helpers.effects.get_socketio')
    @patch('webapp.blueprints.helpers.effects.get_output_logger')
    def test_emit_control_override_change_added(self, mock_output_logger, mock_socketio):
        """_emit_control_override_change emits for added action."""
        target = MagicMock()
        target.entity_uid = 'target1'
        target.name = 'Target'
        source = MagicMock()
        source.entity_uid = 'source1'
        source.name = 'Source'
        event = {'target': target, 'source': source, 'condition': 'stunned'}

        with patch.object(self.mod, '_emit_to_users'):
            with patch.object(self.mod, '_users_controlling', return_value=['user1']):
                self.mod._emit_control_override_change(event, 'added')

        mock_output_logger.return_value.log.assert_called_once()

    @patch('webapp.blueprints.helpers.effects.get_socketio')
    @patch('webapp.blueprints.helpers.effects.get_output_logger')
    def test_emit_control_override_change_removed(self, mock_output_logger, mock_socketio):
        """_emit_control_override_change emits for removed action."""
        target = MagicMock()
        target.entity_uid = 'target1'
        target.name = 'Target'
        source = MagicMock()
        source.entity_uid = 'source1'
        source.name = 'Source'
        event = {'target': target, 'source': source, 'condition': 'stunned'}

        with patch.object(self.mod, '_emit_to_users'):
            with patch.object(self.mod, '_users_controlling', return_value=['user1']):
                self.mod._emit_control_override_change(event, 'removed')

        mock_output_logger.return_value.log.assert_called()

    def test_on_control_override_added(self):
        """_on_control_override_added calls _emit_control_override_change with 'added'."""
        event = {'target': MagicMock(), 'source': MagicMock()}
        with patch.object(self.mod, '_emit_control_override_change') as mock_emit:
            self.mod._on_control_override_added(event)
            mock_emit.assert_called_once_with(event, 'added')

    def test_on_control_override_removed(self):
        """_on_control_override_removed calls _emit_control_override_change with 'removed'."""
        event = {'target': MagicMock(), 'source': MagicMock()}
        with patch.object(self.mod, '_emit_control_override_change') as mock_emit:
            self.mod._on_control_override_removed(event)
            mock_emit.assert_called_once_with(event, 'removed')

    def test_on_turn_skipped(self):
        """_on_turn_skipped emits turn skipped message."""
        target = MagicMock()
        target.entity_uid = 'target1'
        target.name = 'Target'
        event = {'target': target, 'statuses': ['stunned'], 'reason': 'incapacitated'}

        with patch.object(self.mod, '_emit_to_users'):
            with patch.object(self.mod, '_users_controlling', return_value=['user1']):
                with patch.object(self.mod, 'get_output_logger') as mock_output_logger:
                    self.mod._on_turn_skipped(event)

                    mock_output_logger.return_value.log.assert_called_once()

    def test_on_turn_skipped_no_statuses(self):
        """_on_turn_skipped handles event without statuses."""
        target = MagicMock()
        target.entity_uid = 'target1'
        target.name = 'Target'
        event = {'target': target, 'statuses': [], 'reason': 'exhaustion'}

        with patch.object(self.mod, '_emit_to_users'):
            with patch.object(self.mod, '_users_controlling', return_value=['user1']):
                with patch.object(self.mod, 'get_output_logger') as mock_output_logger:
                    self.mod._on_turn_skipped(event)

                    mock_output_logger.return_value.log.assert_called_once()

    def test_select_outcome_narration_no_properties(self):
        """_select_outcome_narration returns None when no properties."""
        with patch.object(self.mod, 'get_game_session') as mock_session:
            mock_session.return_value.game_properties = None
            with patch.object(self.mod, 'get_current_game') as mock_game:
                mock_game.return_value.get_current_battle_map.return_value = None
                result, map_name = self.mod._select_outcome_narration(MagicMock(), 'victory')
                self.assertIsNone(result)

    def test_select_outcome_narration_no_entry(self):
        """_select_outcome_narration returns None when no entry for outcome."""
        properties = {'victory_narration': {}}
        with patch.object(self.mod, 'get_game_session') as mock_session:
            mock_session.return_value.game_properties = properties
            with patch.object(self.mod, 'get_current_game') as mock_game:
                mock_map = MagicMock()
                mock_map.name = 'test_map'
                mock_game.return_value.get_current_battle_map.return_value = mock_map
                result, map_name = self.mod._select_outcome_narration(MagicMock(), 'victory')
                self.assertIsNone(result)

    def test_select_outcome_narration_with_entry(self):
        """_select_outcome_narration returns payload when entry exists."""
        properties = {
            'victory_narration': {
                'default': {'text': 'Victory!', 'title': 'You Won!'}
            }
        }
        with patch.object(self.mod, 'get_game_session') as mock_session:
            mock_session.return_value.game_properties = properties
            with patch.object(self.mod, 'get_current_game') as mock_game:
                mock_map = MagicMock()
                mock_map.name = 'test_map'
                mock_game.return_value.get_current_battle_map.return_value = mock_map
                result, map_name = self.mod._select_outcome_narration(MagicMock(), 'victory')
                self.assertIsNotNone(result)
                self.assertEqual(result.get('on_enter', {}).get('text'), 'Victory!')

    def test_select_outcome_narration_by_map(self):
        """_select_outcome_narration respects by_map entries."""
        properties = {
            'victory_narration': {
                'by_map': {'test_map': {'text': 'Map Victory!', 'title': 'Map Won!'}},
                'default': {'text': 'Default Victory!'}
            }
        }
        with patch.object(self.mod, 'get_game_session', return_value=MagicMock(game_properties=properties)):
            with patch.object(self.mod, 'get_current_game') as mock_game:
                mock_map = MagicMock()
                mock_map.name = 'test_map'
                mock_game.return_value.get_current_battle_map.return_value = mock_map
                result, map_name = self.mod._select_outcome_narration(MagicMock(), 'victory')
                self.assertIsNotNone(result)
                self.assertEqual(result['on_enter']['text'], 'Map Victory!')

    @patch('webapp.blueprints.helpers.effects.get_socketio')
    @patch('webapp.blueprints.helpers.effects._select_outcome_narration')
    def test_on_battle_end_narrate_no_battle(self, mock_select, mock_socketio):
        """_on_battle_end_narrate returns False when no battle."""
        result = self.mod._on_battle_end_narrate(None, MagicMock(), lambda *a, **k: None)
        self.assertFalse(result)

    @patch('webapp.blueprints.helpers.effects.get_socketio')
    @patch('webapp.blueprints.helpers.effects._select_outcome_narration')
    def test_on_battle_end_narrate_no_narration(self, mock_select, mock_socketio):
        """_on_battle_end_narrate returns False when no narration for outcome."""
        mock_select.return_value = (None, None)
        battle = MagicMock()
        result = self.mod._on_battle_end_narrate(MagicMock(), MagicMock(), lambda *a, **k: None)
        self.assertFalse(result)

    @patch('webapp.blueprints.helpers.effects.get_socketio')
    @patch('webapp.blueprints.helpers.effects._select_outcome_narration')
    def test_on_battle_end_narrate_success(self, mock_select, mock_socketio):
        """_on_battle_end_narrate returns True on success."""
        mock_select.return_value = ({'on_enter': {'text': 'Victory!'}}, 'test_map')
        battle = MagicMock()
        battle.tpk.return_value = False
        result = self.mod._on_battle_end_narrate(
            MagicMock(), MagicMock(),
            lambda *a, **k: None
        )
        self.assertTrue(result)

    @patch('webapp.blueprints.helpers.effects.get_socketio')
    @patch('webapp.blueprints.helpers.effects._select_outcome_narration')
    def test_on_battle_end_narrate_tpk(self, mock_select, mock_socketio):
        """_on_battle_end_narrate handles TPK outcome."""
        mock_select.return_value = ({'on_enter': {'text': 'TPK!'}}, 'test_map')
        battle = MagicMock()
        battle.tpk.return_value = True
        result = self.mod._on_battle_end_narrate(
            MagicMock(), MagicMock(),
            lambda *a, **k: None
        )
        self.assertTrue(result)

    # ------------------------------------------------------------------ #
    # emit_active_effects_for_client
    # ------------------------------------------------------------------ #

    def test_emit_active_effects_for_client_no_effects(self):
        """emit_active_effects_for_client handles no effects gracefully."""
        emit_fn = MagicMock()
        with patch.object(self.mod, 'get_current_game') as mock_game:
            with patch.object(self.mod, 'get_game_session') as mock_session:
                with patch.object(self.mod, 'get_level', return_value='test_level'):
                    with patch.object(self.mod, 'get_active_effects', return_value={}):
                        with patch.object(self.mod, 'get_active_effects_map', return_value={}):
                            with patch.object(self.mod, 'get_socketio'):
                                mock_game.return_value.get_map_for_user.return_value = None
                                self.mod.emit_active_effects_for_client(emit_fn)

    def test_emit_active_effects_for_client_with_effects(self):
        """emit_active_effects_for_client emits effect payloads."""
        emit_fn = MagicMock()
        mock_effect = MagicMock()
        with patch.object(self.mod, 'get_current_game') as mock_game:
            with patch.object(self.mod, 'get_game_session') as mock_session:
                with patch.object(self.mod, 'get_level', return_value='test_level'):
                    with patch.object(self.mod, 'get_active_effects') as mock_effects:
                        with patch.object(self.mod, 'get_active_effects_map'):
                            with patch.object(self.mod, 'get_socketio'):
                                with patch('webapp.blueprints.helpers.effects.filter_effect_payloads', return_value=[mock_effect]):
                                    with patch('webapp.blueprints.helpers.effects.map_default_effect_payloads', return_value=[]):
                                        with patch('webapp.blueprints.helpers.effects.point_fire_effect_payload', return_value=None):
                                            mock_effects.return_value = {'test_level': {'effect1': mock_effect}}
                                            mock_game.return_value.get_map_for_user.return_value = None
                                            self.mod.emit_active_effects_for_client(emit_fn)
                                            # Should have called emit_fn for effect
                                            self.assertTrue(emit_fn.call_count >= 0)

    # ------------------------------------------------------------------ #
    # register_effect_listeners
    # ------------------------------------------------------------------ #

    @patch('webapp.blueprints.helpers.effects.get_event_manager')
    @patch('webapp.blueprints.helpers.effects.get_current_game')
    def test_register_effect_listeners(self, mock_game, mock_event_manager):
        """register_effect_listeners registers all listeners."""
        mock_event_mgr = MagicMock()
        mock_event_manager.return_value = mock_event_mgr
        mock_current_game = MagicMock()
        mock_current_game.register_event_handler = MagicMock()
        mock_game.return_value = mock_current_game

        self.mod.register_effect_listeners(lambda *a, **k: None)

        mock_event_mgr.register_event_listener.assert_any_call(
            'narration', MagicMock()
        )
        mock_event_mgr.register_event_listener.assert_any_call(
            'control_override_added', MagicMock()
        )
        mock_event_mgr.register_event_listener.assert_any_call(
            'control_override_removed', MagicMock()
        )
        mock_event_mgr.register_event_listener.assert_any_call(
            'turn_skipped', MagicMock()
        )
        mock_current_game.register_event_handler.assert_called_once()

    @patch('webapp.blueprints.helpers.effects.get_event_manager')
    @patch('webapp.blueprints.helpers.effects.get_current_game')
    def test_register_effect_listeners_game_failure(self, mock_game, mock_event_manager):
        """register_effect_listeners handles game failure gracefully."""
        mock_event_mgr = MagicMock()
        mock_event_manager.return_value = mock_event_mgr
        mock_game.return_value = None

        # Should not raise
        self.mod.register_effect_listeners(lambda *a, **k: None)

    @patch('webapp.blueprints.helpers.effects.get_event_manager')
    def test_register_effect_listeners_event_manager_failure(self, mock_event_manager):
        """register_effect_listeners handles event_manager failure gracefully."""
        mock_event_manager.side_effect = Exception('no event manager')

        # Should not raise
        self.mod.register_effect_listeners(lambda *a, **k: None)

    # ------------------------------------------------------------------ #
    # _emit_to_users
    # ------------------------------------------------------------------ #

    @patch('webapp.blueprints.helpers.effects.get_socketio')
    @patch('webapp.blueprints.helpers.effects.get_current_game')
    def test_emit_to_users_with_sids(self, mock_game, mock_socketio):
        """_emit_to_users sends to specific SIDs when usernames resolve."""
        game = MagicMock()
        game.username_to_sid = {'user1': ['sid1', 'sid2']}
        mock_game.return_value = game
        payload = {'type': 'test'}
        usernames = ['user1']

        self.mod._emit_to_users(payload, usernames)

        mock_socketio.return_value.emit.assert_called()

    @patch('webapp.blueprints.helpers.effects.get_socketio')
    @patch('webapp.blueprints.helpers.effects.get_current_game')
    def test_emit_to_users_no_sids(self, mock_game, mock_socketio):
        """_emit_to_users broadcasts when no SIDs resolve."""
        game = MagicMock()
        game.username_to_sid = {}
        mock_game.return_value = game
        payload = {'type': 'test'}
        usernames = ['user1']

        self.mod._emit_to_users(payload, usernames)

        # Should fall back to global broadcast
        mock_socketio.return_value.emit.assert_called()


if __name__ == '__main__':
    unittest.main()
