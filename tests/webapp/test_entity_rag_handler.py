"""
Test file for EntityRAGHandler

This module provides tests to verify the EntityRAGHandler functionality.
"""

import unittest
from unittest.mock import Mock, MagicMock
from webapp.entity_rag_handler import EntityRAGHandler


class TestEntityRAGHandler(unittest.TestCase):
    """Test cases for EntityRAGHandler."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_game_session = Mock()
        self.mock_current_game = Mock()
        self.mock_current_game.output_logger = Mock()
        self.rag_handler = EntityRAGHandler(self.mock_game_session, self.mock_current_game)
    
    def test_parse_language_from_response_no_language(self):
        """Test parsing response with no language specification."""
        response = "Hello, how are you?"
        language, text = self.rag_handler.parse_language_from_response(response)
        
        self.assertEqual(language, "common")
        self.assertEqual(text, response)
    
    def test_parse_language_from_response_with_language(self):
        """Test parsing response with language specification."""
        response = "Hello [in elvish] how are you?"
        language, text = self.rag_handler.parse_language_from_response(response)
        
        self.assertEqual(language, "elvish")
        self.assertEqual(text, "how are you?")
    
    def test_parse_language_from_response_malformed(self):
        """Test parsing response with malformed language specification."""
        response = "Hello [in elvish how are you?"
        language, text = self.rag_handler.parse_language_from_response(response)
        
        self.assertEqual(language, "common")
        self.assertEqual(text, response)
    
    def test_validate_language_for_entity_valid(self):
        """Test language validation with valid language."""
        mock_entity = Mock()
        mock_entity.languages.return_value = ["common", "elvish", "dwarvish"]
        
        result = self.rag_handler.validate_language_for_entity("elvish", mock_entity)
        self.assertEqual(result, "elvish")
    
    def test_validate_language_for_entity_invalid(self):
        """Test language validation with invalid language."""
        mock_entity = Mock()
        mock_entity.languages.return_value = ["common", "elvish", "dwarvish"]
        
        result = self.rag_handler.validate_language_for_entity("orcish", mock_entity)
        self.assertEqual(result, "common")  # Should fall back to first language
    
    def test_validate_language_for_entity_no_languages(self):
        """Test language validation with entity that has no languages."""
        mock_entity = Mock()
        mock_entity.languages.return_value = []
        
        result = self.rag_handler.validate_language_for_entity("elvish", mock_entity)
        self.assertEqual(result, "common")  # Should fall back to common
    
    def test_get_entity_context_basic(self):
        """Test getting basic entity context."""
        mock_entity = Mock()
        mock_entity.label.return_value = "Test Entity"
        mock_entity.entity_uid = "test-uid"
        mock_entity.description.return_value = "A test entity"
        mock_entity.languages.return_value = ["common"]
        
        # Mock various entity attributes
        mock_entity.hp.return_value = 20
        mock_entity.max_hp.return_value = 25
        mock_entity.armor_class.return_value = 15
        mock_entity.level.return_value = 5
        mock_entity.race.return_value = "Human"
        mock_entity.class_and_level.return_value = [("Fighter", 5)]
        mock_entity.inventory_items.return_value = [{"label": "Sword"}, {"label": "Shield"}]
        
        # Mock class_descriptor to return None so it falls back to class_and_level
        mock_entity.class_descriptor.return_value = None
        
        # Mock battle map
        mock_battle_map = Mock()
        mock_battle_map.entity_or_object_pos.return_value = (10, 15)
        self.mock_current_game.get_map_for_entity.return_value = mock_battle_map
        
        context = self.rag_handler.get_entity_context(mock_entity)
        
        self.assertEqual(context['name'], "Test Entity")
        self.assertEqual(context['entity_uid'], "test-uid")
        self.assertEqual(context['description'], "A test entity")
        self.assertEqual(context['hp'], 20)
        self.assertEqual(context['max_hp'], 25)
        self.assertEqual(context['ac'], 15)
        self.assertEqual(context['level'], 5)
        self.assertEqual(context['race'], "Human")
        self.assertEqual(context['class'], "Fighter 5")
        self.assertEqual(context['inventory'], ["Sword", "Shield"])
        self.assertEqual(context['position'], (10, 15))
    
    def test_get_nearby_entities_success(self):
        """Test getting nearby entities successfully."""
        mock_entity = Mock()
        mock_entity.entity_uid = "test-entity"
        
        # Mock nearby entities
        mock_nearby_entity1 = Mock()
        mock_nearby_entity1.entity_uid = "nearby-1"
        mock_nearby_entity1.label.return_value = "Nearby Entity 1"
        mock_nearby_entity1.conversable.return_value = True
        
        mock_nearby_entity2 = Mock()
        mock_nearby_entity2.entity_uid = "nearby-2"
        mock_nearby_entity2.label.return_value = "Nearby Entity 2"
        mock_nearby_entity2.conversable.return_value = False
        
        # Mock entity observe method
        mock_entity.observe.return_value = [
            (mock_nearby_entity1, 15),
            (mock_nearby_entity2, 25)
        ]
        
        # Mock battle map
        mock_battle_map = Mock()
        self.mock_current_game.get_map_for_entity.return_value = mock_battle_map
        
        result = self.rag_handler.get_nearby_entities(mock_entity, 30)
        
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['id'], "nearby-1")
        self.assertEqual(result[0]['name'], "Nearby Entity 1")
        self.assertEqual(result[0]['distance'], 15)
        self.assertTrue(result[0]['conversable'])
        self.assertEqual(result[1]['id'], "nearby-2")
        self.assertEqual(result[1]['name'], "Nearby Entity 2")
        self.assertEqual(result[1]['distance'], 25)
        self.assertFalse(result[1]['conversable'])
    
    def test_get_nearby_entities_error(self):
        """Test getting nearby entities with error."""
        mock_entity = Mock()
        mock_entity.observe.side_effect = Exception("Test error")
        
        result = self.rag_handler.get_nearby_entities(mock_entity, 30)
        
        self.assertEqual(result, [])
    
    def test_process_entity_response_empty(self):
        """Test processing empty entity response."""
        mock_receiver = Mock()
        mock_llm_handler = Mock()
        
        language, response = self.rag_handler.process_entity_response("", mock_receiver, mock_llm_handler)
        
        self.assertEqual(language, "common")
        self.assertEqual(response, "")
    
    def test_process_entity_response_with_rag_commands(self):
        """Test processing entity response with RAG commands."""
        mock_receiver = Mock()
        mock_receiver.languages.return_value = ["common", "elvish"]
        mock_receiver.inventory_items.return_value = [{"label": "Sword"}, {"label": "Shield"}]
        
        mock_llm_handler = Mock()
        mock_llm_handler.add_message = Mock()
        mock_llm_handler.generate_response.return_value = "I have a sword and shield"
        
        # Mock battle map for observation
        mock_battle_map = Mock()
        self.mock_current_game.get_map_for_entity.return_value = mock_battle_map
        
        # Test with inventory command
        response = "What do I have? [INVENTORY]"
        language, processed_response = self.rag_handler.process_entity_response(
            response, mock_receiver, mock_llm_handler
        )
        
        # Verify that the LLM handler was called
        mock_llm_handler.add_message.assert_called()
        mock_llm_handler.generate_response.assert_called()

    def test_build_conversation_response_plan_supports_no_response(self):
        mock_receiver = Mock()
        mock_receiver.languages.return_value = ["common"]

        plan = self.rag_handler.build_conversation_response_plan(
            "[NO_RESPONSE]",
            mock_receiver,
            speaker=Mock(),
            llm_conversation_handler=Mock(),
        )

        self.assertTrue(plan['skip'])
        self.assertEqual(plan['message'], "")

    def test_build_conversation_response_plan_parses_targets_and_volume(self):
        speaker = Mock()
        speaker.entity_uid = "speaker"
        speaker.label.return_value = "Speaker"

        target = Mock()
        target.entity_uid = "rose"
        target.label.return_value = "Rose"

        receiver = Mock()
        receiver.entity_uid = "thorn"
        receiver.languages.return_value = ["common", "elvish"]

        self.rag_handler.get_conversation_targets = Mock(return_value=[speaker, target])
        self.rag_handler.plan_response_volume = Mock(return_value=('shout', [target]))

        plan = self.rag_handler.build_conversation_response_plan(
            "[TO: @rose] [VOLUME: shout] [in elvish] Stay back.",
            receiver,
            speaker=speaker,
            llm_conversation_handler=Mock(),
        )

        self.assertFalse(plan['skip'])
        self.assertEqual(plan['language'], 'elvish')
        self.assertEqual(plan['message'], 'Stay back.')
        self.assertEqual(plan['targets'], [target])
        self.assertEqual(plan['volume'], 'shout')

    def test_build_conversation_response_plan_parses_approach_and_goal_directives(self):
        speaker = Mock()
        speaker.entity_uid = "speaker"

        receiver = Mock()
        receiver.entity_uid = "thorn"
        receiver.languages.return_value = ["common"]

        approach_target = Mock()
        approach_target.entity_uid = "door-1"

        self.rag_handler.resolve_named_target = Mock(return_value=approach_target)
        self.rag_handler.plan_response_volume = Mock(return_value=('normal', [speaker]))

        plan = self.rag_handler.build_conversation_response_plan(
            "[APPROACH: target=Front Door, distance=10] [SET_GOAL: Open the door and check inside] On my way.",
            receiver,
            speaker=speaker,
            llm_conversation_handler=Mock(),
        )

        self.assertEqual(plan['approach']['target'], approach_target)
        self.assertEqual(plan['approach']['distance_ft'], 10)
        self.assertEqual(plan['set_goal'], 'Open the door and check inside')
        self.assertEqual(plan['message'], 'On my way.')

    def test_build_conversation_response_plan_parses_request_check_directive(self):
        speaker = Mock()
        speaker.entity_uid = "speaker"

        receiver = Mock()
        receiver.entity_uid = "thorn"
        receiver.languages.return_value = ["common"]

        request_target = Mock()
        request_target.entity_uid = "pc-1"

        self.rag_handler.resolve_named_target = Mock(return_value=request_target)
        self.rag_handler.plan_response_volume = Mock(return_value=('normal', [speaker]))

        plan = self.rag_handler.build_conversation_response_plan(
            "[REQUEST_CHECK: skill=persuasion, target=speaker, dc=14] Convince me.",
            receiver,
            speaker=speaker,
            llm_conversation_handler=Mock(),
        )

        self.assertEqual(plan['request_check']['skill'], 'persuasion')
        self.assertEqual(plan['request_check']['target'], request_target)
        self.assertEqual(plan['request_check']['dc'], 14)
        self.assertEqual(plan['message'], 'Convince me.')

    def test_handle_insight_request_logs_and_regenerates_response(self):
        speaker = Mock()
        speaker.entity_uid = "pc-1"
        speaker.label.return_value = "Rumblebelly"

        receiver = Mock()
        receiver.entity_uid = "npc-1"
        receiver.label.return_value = "Thorn"
        receiver.memory_buffer = [{'source': speaker, 'message': 'I am telling the truth.'}]

        roll = Mock()
        roll.result.return_value = 17
        roll.__str__ = Mock(return_value='1d20+5')
        receiver.insight_check.return_value = roll

        conversation_handler = Mock()
        conversation_handler.generate_response.return_value = 'I believe you.'

        self.rag_handler.resolve_named_target = Mock(return_value=speaker)
        self.rag_handler._evaluate_insight_assessment = Mock(return_value={
            'assessment': 'truthful',
            'reason': 'Their story matches the party history.',
        })

        response = self.rag_handler._handle_insight_request(
            '[INSIGHT: target=speaker]',
            receiver,
            speaker,
            conversation_handler,
        )

        self.assertEqual(response, 'I believe you.')
        conversation_handler.add_message.assert_called_once()
        self.mock_current_game.output_logger.log.assert_called_once()
        logged_message = self.mock_current_game.output_logger.log.call_args.args[0]
        self.assertIn('insight check', logged_message)
        self.assertIn('truthful', logged_message)

    def test_apply_response_plan_directives_logs_requested_checks_to_players(self):
        actor = Mock()
        actor.entity_uid = "npc-1"
        actor.label.return_value = "Thorn"

        target = Mock()
        target.entity_uid = "pc-1"
        target.label.return_value = "Rumblebelly"

        self.mock_current_game.get_current_battle.return_value = None
        self.mock_current_game.entity_owners.return_value = []

        plan = {
            'set_goal': None,
            'goal_complete': False,
            'goal_give_up': False,
            'approach': None,
            'interact': None,
            'request_check': {'skill': 'intimidation', 'target': target, 'dc': 13},
        }

        result = self.rag_handler.apply_response_plan_directives(plan, actor, speaker=None, advance_time=False)

        self.assertEqual(result['executed_actions'], ['request_check'])
        self.mock_current_game.output_logger.log.assert_called_once()
        logged_message = self.mock_current_game.output_logger.log.call_args.args[0]
        logged_visibility = self.mock_current_game.output_logger.log.call_args.kwargs['visibility']
        self.assertIn('intimidation', logged_message)
        self.assertEqual(logged_visibility['kind'], 'entities')
        self.assertEqual(set(logged_visibility['entity_uids']), {'npc-1', 'pc-1'})

    def test_apply_response_plan_directives_schedules_goal_and_executes_actions(self):
        actor = Mock()
        actor.entity_uid = "npc-1"

        self.mock_current_game.get_current_battle.return_value = None
        self.mock_current_game.entity_owners.return_value = []
        self.mock_current_game.schedule_short_term_goal.return_value = {'goal': 'Inspect the chest'}

        move_action = Mock()
        interact_action = Mock()
        self.rag_handler.build_approach_action = Mock(return_value=move_action)
        self.rag_handler.build_interact_action = Mock(return_value=interact_action)

        plan = {
            'set_goal': 'Inspect the chest',
            'goal_complete': False,
            'goal_give_up': False,
            'approach': {'target': Mock(), 'distance_ft': 5},
            'interact': {'target': Mock(), 'action': 'open'},
        }

        result = self.rag_handler.apply_response_plan_directives(plan, actor, speaker=None, advance_time=True)

        self.mock_current_game.schedule_short_term_goal.assert_called_once_with(actor, 'Inspect the chest', speaker=None)
        self.assertEqual(self.mock_current_game.commit_and_update.call_count, 2)
        self.mock_current_game.advance_world_time.assert_called_once_with(seconds=6, trigger_environment=False)
        self.assertEqual(result['executed_actions'], ['approach', 'interact'])


if __name__ == '__main__':
    unittest.main() 