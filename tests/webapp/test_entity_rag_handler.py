"""
Test file for EntityRAGHandler

This module provides tests to verify the EntityRAGHandler functionality.
"""

import unittest
from unittest.mock import Mock, MagicMock
from webapp.entity_rag_handler import EntityRAGHandler
from unittest.mock import patch


class TestEntityRAGHandler(unittest.TestCase):
    """Test cases for EntityRAGHandler."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_game_session = Mock()
        self.mock_game_session.game_time = 0
        self.mock_game_session.load_state.return_value = {}
        self.mock_game_session.game_properties = {
            'conversation_item_offers': {
                'scroll_speak_animals_modified': {
                    'aliases': ['scroll_speak_animals'],
                    'block_when': [
                        'offer_completed',
                        'target_has_item',
                        'target_effect_animal_communication',
                    ],
                },
            },
        }
        self.mock_current_game = Mock()
        self.mock_current_game.output_logger = Mock()
        self.mock_current_game.output_logger.get_visible_entries_for_entity.return_value = []
        self.mock_current_game.get_map_for_entity.return_value = None
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

    def test_get_nearby_entities_without_map_returns_empty(self):
        """Missing map should not call observe() with an invalid signature."""
        mock_entity = Mock()
        self.mock_current_game.get_map_for_entity.return_value = None

        result = self.rag_handler.get_nearby_entities(mock_entity, 30)

        self.assertEqual(result, [])
        mock_entity.observe.assert_not_called()
    
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

    def test_process_entity_response_passes_speaker_to_plan_builder(self):
        receiver = Mock()
        receiver.languages.return_value = ["common"]
        speaker = Mock()

        with patch.object(self.rag_handler, 'build_conversation_response_plan', return_value={
            'language': 'common',
            'message': 'ok',
        }) as mock_builder:
            self.rag_handler.process_entity_response("hello", receiver, speaker=speaker, llm_conversation_handler=Mock())

        self.assertTrue(mock_builder.called)
        self.assertIs(mock_builder.call_args.kwargs.get('speaker'), speaker)

    def test_keyword_hook_matches_phrase_with_connector_words(self):
        receiver = Mock()
        receiver.conversation_keywords.return_value = [
            {
                'keyword': 'hunters closing in',
                'update_state': [{'target': 'session', 'state': {'wild_sheep_scene2_started': True}}],
            }
        ]

        response = "The hunters are closing in."

        with patch('webapp.entity_rag_handler.GenericEventHandler') as handler_cls:
            handler_instance = Mock()
            handler_cls.return_value = handler_instance
            updated = self.rag_handler._process_rag_commands(response, speaker=Mock(), receiver=receiver, llm_conversation_handler=None)

        self.assertTrue(handler_instance.handle.called)
        self.assertEqual(updated, response)

    def test_keyword_hook_llm_semantic_fallback(self):
        receiver = Mock()
        receiver.conversation_keywords.return_value = [
            {'keyword': 'hunters closing in', 'update_state': [{'target': 'session', 'state': {'wild_sheep_scene2_started': True}}]}
        ]

        llm_conversation_handler = Mock()
        llm_conversation_handler.llm_hander = Mock()
        llm_conversation_handler.llm_hander.send_message.return_value = '{"matched_keywords": ["hunters closing in"]}'

        response = "Those trackers are almost here."

        with patch('webapp.entity_rag_handler.GenericEventHandler') as handler_cls:
            handler_instance = Mock()
            handler_cls.return_value = handler_instance
            self.rag_handler._process_rag_commands(response, speaker=Mock(), receiver=receiver, llm_conversation_handler=llm_conversation_handler)

        self.assertTrue(handler_instance.handle.called)

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

    def test_no_response_skips_keyword_llm_lookup(self):
        mock_receiver = Mock()
        mock_receiver.languages.return_value = ["common"]
        mock_receiver.conversation_keywords.return_value = [{'keyword': 'monster'}]

        llm_conversation_handler = Mock()
        llm_conversation_handler.llm_hander = Mock()

        plan = self.rag_handler.build_conversation_response_plan(
            "[NO_RESPONSE]",
            mock_receiver,
            speaker=Mock(),
            llm_conversation_handler=llm_conversation_handler,
        )

        self.assertTrue(plan['skip'])
        llm_conversation_handler.llm_hander.send_message.assert_not_called()

    def test_build_conversation_response_plan_falls_back_to_speaker_when_volume_plan_fails(self):
        speaker = Mock()
        speaker.entity_uid = "gomerin"
        speaker.label.return_value = "Gomerin"

        receiver = Mock()
        receiver.entity_uid = "rose_durst2"
        receiver.languages.return_value = ["common"]

        self.rag_handler.plan_response_volume = Mock(return_value=(None, []))

        plan = self.rag_handler.build_conversation_response_plan(
            "[in common] Yes... it's terrible. We're scared.",
            receiver,
            speaker=speaker,
            llm_conversation_handler=Mock(),
        )

        self.assertFalse(plan['skip'])
        self.assertEqual(plan['message'], "Yes... it's terrible. We're scared.")
        self.assertEqual(plan['targets'], [speaker])
        self.assertEqual(plan['volume'], 'shout')

    def test_build_conversation_response_plan_skips_semantic_keyword_llm(self):
        speaker = Mock()
        speaker.entity_uid = "gomerin"

        receiver = Mock()
        receiver.entity_uid = "rose_durst2"
        receiver.languages.return_value = ["common"]
        receiver.conversation_keywords.return_value = [{'keyword': 'basement'}]

        llm_conversation_handler = Mock()
        llm_conversation_handler.llm_hander = Mock()

        self.rag_handler.plan_response_volume = Mock(return_value=('normal', [speaker]))

        plan = self.rag_handler.build_conversation_response_plan(
            "[in common] In the basement! My parents keep it trapped down there.",
            receiver,
            speaker=speaker,
            llm_conversation_handler=llm_conversation_handler,
        )

        self.assertFalse(plan['skip'])
        llm_conversation_handler.llm_hander.send_message.assert_not_called()

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

    def test_resolve_named_target_matches_speaker_handle_without_map(self):
        speaker = Mock()
        speaker.entity_uid = 'aldric'
        speaker.label.return_value = 'Aldric'

        actor = Mock()
        actor.entity_uid = 'finethir'
        self.mock_game_session.entity_by_uid.return_value = None
        self.mock_current_game.get_map_for_entity.return_value = None

        target = self.rag_handler.resolve_named_target(actor, '@aldric', speaker=speaker)
        self.assertIs(target, speaker)

    def test_build_conversation_response_plan_parses_offer_item_directive(self):
        speaker = Mock()
        speaker.entity_uid = "speaker"

        receiver = Mock()
        receiver.entity_uid = "thorn"
        receiver.languages.return_value = ["common"]

        offer_target = Mock()
        offer_target.entity_uid = "pc-1"

        self.rag_handler.resolve_named_target = Mock(return_value=offer_target)
        self.rag_handler.plan_response_volume = Mock(return_value=('normal', [speaker]))

        plan = self.rag_handler.build_conversation_response_plan(
            "[OFFER_ITEM: item=scroll_speak_animals, target=speaker] Please take this.",
            receiver,
            speaker=speaker,
            llm_conversation_handler=Mock(),
        )

        self.assertIsNotNone(plan['offer_item'])
        self.assertEqual(plan['offer_item']['item'], 'scroll_speak_animals_modified')
        self.assertEqual(plan['offer_item']['target'], offer_target)
        self.assertEqual(plan['message'], 'Please take this.')

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

    def test_build_conversation_response_plan_extracts_aside_tag(self):
        speaker = Mock()
        speaker.entity_uid = "speaker"

        receiver = Mock()
        receiver.entity_uid = "thorn"
        receiver.languages.return_value = ["common"]

        self.rag_handler.plan_response_volume = Mock(return_value=('normal', [speaker]))

        plan = self.rag_handler.build_conversation_response_plan(
            "Please keep your voice down. [ASIDE: Rose grips Thorn's hand and glances at the dark doorway.]",
            receiver,
            speaker=speaker,
            llm_conversation_handler=Mock(),
        )

        self.assertFalse(plan['skip'])
        self.assertEqual(plan['message'], 'Please keep your voice down.')
        self.assertEqual(plan['narrative'], ["Rose grips Thorn's hand and glances at the dark doorway."])

    def test_build_conversation_response_plan_rewrites_first_person_aside_to_third_person(self):
        speaker = Mock()
        speaker.entity_uid = "speaker"

        receiver = Mock()
        receiver.entity_uid = "thorn"
        receiver.languages.return_value = ["common"]

        self.rag_handler.plan_response_volume = Mock(return_value=('normal', [speaker]))

        plan = self.rag_handler.build_conversation_response_plan(
            "Keep quiet. [ASIDE: I clutch my doll tighter, my eyes wide with terror.]",
            receiver,
            speaker=speaker,
            llm_conversation_handler=Mock(),
        )

        self.assertFalse(plan['skip'])
        self.assertEqual(plan['message'], 'Keep quiet.')
        self.assertEqual(plan['narrative'], ['They clutch their doll tighter, their eyes wide with terror.'])

    def test_build_conversation_response_plan_normalizes_llm_split_narrative_to_third_person(self):
        receiver = Mock()
        receiver.entity_uid = "thorn"
        receiver.languages.return_value = ["common"]

        speaker = Mock()
        speaker.entity_uid = "speaker"

        llm_conversation_handler = Mock()
        llm_conversation_handler.llm_hander = Mock()
        llm_conversation_handler.llm_hander.send_message.return_value = (
            '{"spoken":"Shh!","narrative":["I clutch my doll tighter while we watch the house."]}'
        )

        self.rag_handler.plan_response_volume = Mock(return_value=('normal', [speaker]))

        plan = self.rag_handler.build_conversation_response_plan(
            "Shh!\n\nI clutch my doll tighter while we watch the house.",
            receiver,
            speaker=speaker,
            llm_conversation_handler=llm_conversation_handler,
        )

        self.assertFalse(plan['skip'])
        self.assertEqual(plan['message'], 'Shh!')
        self.assertEqual(plan['narrative'], ['They clutch their doll tighter while they watch the house.'])

    def test_build_conversation_response_plan_filters_private_trust_judgment_and_requests_check(self):
        receiver = Mock()
        receiver.entity_uid = "rose"
        receiver.languages.return_value = ["common"]

        speaker = Mock()
        speaker.entity_uid = "pc-1"
        speaker.label.return_value = "RumbleBelly"

        self.rag_handler.plan_response_volume = Mock(return_value=('whisper', [speaker]))

        plan = self.rag_handler.build_conversation_response_plan(
            "Please help us. [ASIDE: They do not trust him.]",
            receiver,
            speaker=speaker,
            llm_conversation_handler=Mock(),
        )

        self.assertFalse(plan['skip'])
        self.assertEqual(plan['message'], 'Please help us.')
        self.assertEqual(plan['narrative'], [])
        self.assertIsNotNone(plan['request_check'])
        self.assertEqual(plan['request_check']['skill'], 'persuasion')
        self.assertEqual(plan['request_check']['target'], speaker)

    def test_build_conversation_response_plan_infers_intimidation_for_hostile_attitude(self):
        receiver = Mock()
        receiver.entity_uid = "rose"
        receiver.languages.return_value = ["common"]

        speaker = Mock()
        speaker.entity_uid = "pc-1"

        mock_battle = Mock()
        mock_battle.opposing.return_value = True
        mock_battle.allies.return_value = False
        self.mock_current_game.get_current_battle.return_value = mock_battle

        self.rag_handler.plan_response_volume = Mock(return_value=('whisper', [speaker]))

        plan = self.rag_handler.build_conversation_response_plan(
            "Stay back. [ASIDE: They do not trust him.]",
            receiver,
            speaker=speaker,
            llm_conversation_handler=Mock(),
        )

        self.assertFalse(plan['skip'])
        self.assertEqual(plan['narrative'], [])
        self.assertIsNotNone(plan['request_check'])
        self.assertEqual(plan['request_check']['skill'], 'intimidation')
        self.assertEqual(plan['request_check']['target'], speaker)

    def test_multiline_dialogue_joins_without_llm_split(self):
        spoken, narrative = self.rag_handler.extract_narrative_asides(
            "Shh... shh, Thorn. Don't cry. It's okay.\nThere's a monster in our house!",
            llm_conversation_handler=Mock(),
        )
        self.assertEqual(
            spoken,
            "Shh... shh, Thorn. Don't cry. It's okay. There's a monster in our house!",
        )
        self.assertEqual(narrative, [])

    def test_extract_narrative_asides_via_llm_fallback(self):
        receiver = Mock()
        receiver.entity_uid = "thorn"
        receiver.languages.return_value = ["common"]

        speaker = Mock()
        speaker.entity_uid = "speaker"

        llm_conversation_handler = Mock()
        llm_conversation_handler.llm_hander = Mock()
        llm_conversation_handler.llm_hander.send_message.return_value = (
            '{"spoken":"Shh! Please be quiet.","narrative":["Rose clutches Thorn and scans the house."]}'
        )

        self.rag_handler.plan_response_volume = Mock(return_value=('normal', [speaker]))

        plan = self.rag_handler.build_conversation_response_plan(
            "Shh! Please be quiet.\n\nRose clutches Thorn and scans the house.",
            receiver,
            speaker=speaker,
            llm_conversation_handler=llm_conversation_handler,
        )

        self.assertFalse(plan['skip'])
        self.assertEqual(plan['message'], 'Shh! Please be quiet.')
        self.assertEqual(plan['narrative'], ['Rose clutches Thorn and scans the house.'])

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

    def test_apply_response_plan_offers_item_even_during_battle(self):
        actor = Mock()
        actor.entity_uid = "npc-1"
        actor.inventory = {'scroll_speak_animals_modified': {'qty': 1}}

        target = Mock()
        target.entity_uid = "pc-1"

        self.mock_current_game.get_current_battle.return_value = Mock()
        self.mock_current_game.entity_owners.return_value = ['player1']
        self.mock_current_game.prompt = Mock()

        plan = {
            'set_goal': None,
            'goal_complete': False,
            'goal_give_up': False,
            'approach': None,
            'interact': None,
            'request_check': None,
            'offer_item': {'item': 'scroll_speak_animals_modified', 'target': target, 'auto_use': False},
        }

        result = self.rag_handler.apply_response_plan_directives(plan, actor, speaker=target, advance_time=False)
        self.assertEqual(result['executed_actions'], ['offer_item'])
        self.mock_current_game.prompt.assert_called_once()

    def test_apply_response_plan_directives_offers_item_via_prompt(self):
        actor = Mock()
        actor.entity_uid = "npc-1"
        actor.inventory = {'scroll_speak_animals_modified': {'qty': 1}}

        target = Mock()
        target.entity_uid = "pc-1"

        self.mock_current_game.get_current_battle.return_value = None
        self.mock_current_game.entity_owners.return_value = ['player1']
        self.mock_current_game.prompt = Mock()

        plan = {
            'set_goal': None,
            'goal_complete': False,
            'goal_give_up': False,
            'approach': None,
            'interact': None,
            'request_check': None,
            'offer_item': {'item': 'scroll_speak_animals_modified', 'target': target, 'auto_use': False},
        }

        result = self.rag_handler.apply_response_plan_directives(plan, actor, speaker=None, advance_time=False)

        self.assertEqual(result['executed_actions'], ['offer_item'])
        self.mock_current_game.prompt.assert_called_once()

    def test_offer_item_prompt_callback_accept_transfers_item(self):
        actor = Mock()
        actor.entity_uid = "npc-1"
        actor.inventory = {'scroll_speak_animals_modified': {'qty': 1}}

        target = Mock()
        target.entity_uid = "pc-1"

        self.mock_current_game.get_current_battle.return_value = None
        self.mock_current_game.entity_owners.return_value = ['player1']
        self.mock_current_game.prompt = Mock()
        self.mock_current_game.socketio = Mock()

        plan = {
            'set_goal': None,
            'goal_complete': False,
            'goal_give_up': False,
            'approach': None,
            'interact': None,
            'request_check': None,
            'offer_item': {'item': 'scroll_speak_animals_modified', 'target': target, 'auto_use': False},
        }

        self.rag_handler.apply_response_plan_directives(plan, actor, speaker=None, advance_time=False)
        callback = self.mock_current_game.prompt.call_args.kwargs['callback']
        callback({'response': 'Yes'})

        actor.deduct_item.assert_called_once_with('scroll_speak_animals_modified', 1)
        target.add_item.assert_called_once_with('scroll_speak_animals_modified', 1)
        self.mock_game_session.save_state.assert_called()
        self.mock_current_game.socketio.emit.assert_called()

    def test_offer_item_prompt_callback_ok_payload_transfers_item(self):
        actor = Mock()
        actor.entity_uid = "npc-1"
        actor.inventory = {'scroll_speak_animals_modified': {'qty': 1}}

        target = Mock()
        target.entity_uid = "pc-1"

        self.mock_current_game.get_current_battle.return_value = None
        self.mock_current_game.entity_owners.return_value = ['player1']
        self.mock_current_game.prompt = Mock()
        self.mock_current_game.socketio = Mock()

        plan = {
            'set_goal': None,
            'goal_complete': False,
            'goal_give_up': False,
            'approach': None,
            'interact': None,
            'request_check': None,
            'offer_item': {'item': 'scroll_speak_animals_modified', 'target': target, 'auto_use': False},
        }

        self.rag_handler.apply_response_plan_directives(plan, actor, speaker=None, advance_time=False)
        callback = self.mock_current_game.prompt.call_args.kwargs['callback']
        callback({'response': 'OK.'})

        actor.deduct_item.assert_called_once_with('scroll_speak_animals_modified', 1)
        target.add_item.assert_called_once_with('scroll_speak_animals_modified', 1)

    def test_offer_item_prompt_callback_boolean_true_payload_transfers_item(self):
        actor = Mock()
        actor.entity_uid = "npc-1"
        actor.inventory = {'scroll_speak_animals_modified': {'qty': 1}}

        target = Mock()
        target.entity_uid = "pc-1"

        self.mock_current_game.get_current_battle.return_value = None
        self.mock_current_game.entity_owners.return_value = ['player1']
        self.mock_current_game.prompt = Mock()
        self.mock_current_game.socketio = Mock()

        plan = {
            'set_goal': None,
            'goal_complete': False,
            'goal_give_up': False,
            'approach': None,
            'interact': None,
            'request_check': None,
            'offer_item': {'item': 'scroll_speak_animals_modified', 'target': target, 'auto_use': False},
        }

        self.rag_handler.apply_response_plan_directives(plan, actor, speaker=None, advance_time=False)
        callback = self.mock_current_game.prompt.call_args.kwargs['callback']
        callback({'response': True})

        actor.deduct_item.assert_called_once_with('scroll_speak_animals_modified', 1)
        target.add_item.assert_called_once_with('scroll_speak_animals_modified', 1)

    def test_can_offer_item_blocks_when_target_has_animal_communication(self):
        actor = Mock()
        actor.entity_uid = 'finethir'
        actor.inventory = {'scroll_speak_animals_modified': {'qty': 1}}

        target = Mock()
        target.entity_uid = 'aldric'
        target.inventory = {}

        self.mock_game_session.load_state.return_value = {}
        with patch('natural20.utils.conversation_offers.has_animal_communication', return_value=True):
            allowed, reason = self.rag_handler._can_offer_item(
                actor,
                target,
                'scroll_speak_animals_modified',
            )

        self.assertFalse(allowed)
        self.assertEqual(reason, 'target_effect_animal_communication')

    def test_can_offer_item_blocks_after_completed_offer(self):
        actor = Mock()
        actor.entity_uid = 'finethir'
        actor.inventory = {'scroll_speak_animals_modified': {'qty': 1}}

        target = Mock()
        target.entity_uid = 'aldric'
        target.inventory = {}

        self.mock_game_session.load_state.return_value = {
            'completed': {'finethir:aldric:scroll_speak_animals_modified': 12},
        }
        allowed, reason = self.rag_handler._can_offer_item(
            actor,
            target,
            'scroll_speak_animals_modified',
        )
        self.assertFalse(allowed)
        self.assertEqual(reason, 'offer_completed')

    def test_apply_response_plan_skips_repeat_scroll_offer_when_target_has_effect(self):
        actor = Mock()
        actor.entity_uid = 'finethir'
        actor.inventory = {'scroll_speak_animals_modified': {'qty': 1}}

        target = Mock()
        target.entity_uid = 'aldric'
        target.inventory = {}

        self.mock_current_game.get_current_battle.return_value = None
        self.mock_current_game.entity_owners.return_value = ['player1']
        self.mock_current_game.prompt = Mock()
        self.mock_game_session.load_state.return_value = {}

        plan = {
            'set_goal': None,
            'goal_complete': False,
            'goal_give_up': False,
            'approach': None,
            'interact': None,
            'request_check': None,
            'offer_item': {
                'item': 'scroll_speak_animals_modified',
                'target': target,
                'auto_use': False,
            },
        }

        with patch('natural20.utils.conversation_offers.has_animal_communication', return_value=True):
            result = self.rag_handler.apply_response_plan_directives(
                plan,
                actor,
                speaker=target,
                advance_time=False,
            )

        self.assertEqual(result['executed_actions'], [])
        self.mock_current_game.prompt.assert_not_called()

    def test_offer_item_prompt_callback_decline_does_not_transfer_item(self):
        actor = Mock()
        actor.entity_uid = "npc-1"
        actor.inventory = {'scroll_speak_animals_modified': {'qty': 1}}

        target = Mock()
        target.entity_uid = "pc-1"

        self.mock_current_game.get_current_battle.return_value = None
        self.mock_current_game.entity_owners.return_value = ['player1']
        self.mock_current_game.prompt = Mock()
        self.mock_current_game.socketio = Mock()

        plan = {
            'set_goal': None,
            'goal_complete': False,
            'goal_give_up': False,
            'approach': None,
            'interact': None,
            'request_check': None,
            'offer_item': {'item': 'scroll_speak_animals_modified', 'target': target, 'auto_use': False},
        }

        self.rag_handler.apply_response_plan_directives(plan, actor, speaker=None, advance_time=False)
        callback = self.mock_current_game.prompt.call_args.kwargs['callback']
        callback({'response': 'No'})

        actor.deduct_item.assert_not_called()
        target.add_item.assert_not_called()

    def test_sanitize_insight_reason_strips_dm_only_disclosures(self):
        fallback = 'fallback reason'
        cleaned = self.rag_handler._sanitize_insight_reason(
            "Their gaze flickers when they answer. The target is an illusionary "
            "construct created by the house, so there is no biological tell. "
            "Still, the wording feels rehearsed.",
            fallback,
        )
        # Sentences mentioning illusion/construct/created-by-the-house must be
        # dropped, but the in-character cues should survive.
        self.assertNotIn('illusion', cleaned.lower())
        self.assertNotIn('construct', cleaned.lower())
        self.assertNotIn('created by the house', cleaned.lower())
        self.assertIn('gaze flickers', cleaned)
        self.assertIn('rehearsed', cleaned)

    def test_sanitize_insight_reason_falls_back_when_everything_redacted(self):
        fallback = 'You cannot tell for sure.'
        cleaned = self.rag_handler._sanitize_insight_reason(
            "The target is an illusion. Behind the scenes the DM has marked them as undead.",
            fallback,
        )
        self.assertEqual(cleaned, fallback)


if __name__ == '__main__':
    unittest.main() 