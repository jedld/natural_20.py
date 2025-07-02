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


if __name__ == '__main__':
    unittest.main() 