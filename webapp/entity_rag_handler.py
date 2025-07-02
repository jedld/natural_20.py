"""
Entity RAG Handler

This module handles the Retrieval-Augmented Generation (RAG) aspects of entity conversations,
including inventory queries, observation requests, and language parsing.
"""

import re
import logging
from typing import List, Tuple, Dict, Any, Optional
from natural20.entity import Entity
from natural20.session import Session

logger = logging.getLogger('werkzeug')


class EntityRAGHandler:
    """
    Handles RAG (Retrieval-Augmented Generation) operations for entity conversations.
    
    This class extracts and processes special commands in entity responses that require
    real-time game state information, such as inventory queries and observation requests.
    """
    
    def __init__(self, game_session: Session, current_game):
        """
        Initialize the Entity RAG Handler.
        
        Args:
            game_session: The current game session
            current_game: The current game instance
        """
        self.game_session = game_session
        self.current_game = current_game
    
    def process_entity_response(self, response: str, receiver: Entity, llm_conversation_handler) -> Tuple[str, str]:
        """
        Process an entity response for RAG commands and return the cleaned response and language.
        
        Args:
            response: The raw response from the LLM
            receiver: The entity receiving the response
            llm_conversation_handler: The LLM conversation handler instance
            
        Returns:
            Tuple of (language, cleaned_response)
        """
        if not response:
            return "common", ""
        
        # Parse language from response
        language, response = self.parse_language_from_response(response)
        
        # Validate language against entity's known languages
        if language not in receiver.languages():
            language = receiver.languages()[0]
        
        # Process RAG commands
        response = self._process_rag_commands(response, receiver, llm_conversation_handler)
        
        # Clean up any remaining bracketed content
        response = re.sub(r'\[.*?\]', '', response)
        
        return language, response
    
    def parse_language_from_response(self, response: str) -> Tuple[str, str]:
        """
        Parse language specification from AI response.
        
        Args:
            response: The raw response from the AI
            
        Returns:
            Tuple of (language, response_text)
        """
        if not response or "[in" not in response:
            return "common", response
        
        try:
            # Find the start of [in
            start_idx = response.find("[in")
            if start_idx != -1:
                # Find the closing bracket after [in
                end_bracket_idx = response.find("]", start_idx)
                if end_bracket_idx != -1:
                    # Extract language (everything between [in and ])
                    language = response[start_idx + 3:end_bracket_idx].strip()
                    # Extract the rest of the response after the closing bracket
                    response_text = response[end_bracket_idx + 1:].strip()
                    return language, response_text
                else:
                    # No closing bracket found, treat as common
                    return "common", response
            else:
                return "common", response
        except (IndexError, ValueError):
            # Fallback to common if parsing fails
            return "common", response

    def _process_rag_commands(self, response: str, receiver: Entity, llm_conversation_handler) -> str:
        """
        Process RAG commands in the response and generate appropriate responses.

        Args:
            response: The response containing RAG commands
            receiver: The entity processing the response
            llm_conversation_handler: The LLM conversation handler

        Returns:
            The processed response
        """
        # Handle hostile state change
        if "[GO_HOSTILE]" in response:
            return self._handle_hostile_state_change(receiver)

        if "[GO_FRIENDLY]" in response:
            return self._handle_friendly_state_change(receiver)

        # Handle inventory queries
        if "[INVENTORY" in response or "[LIST_INVENTORY" in response:
            return self._handle_inventory_query(receiver, llm_conversation_handler)

        # Handle observation requests
        if "[OBSERVE" in response:
            return self._handle_observation_request(receiver, llm_conversation_handler)

        return response

    def _handle_friendly_state_change(self, receiver: Entity) -> str:
        """
        Handle friendly state change command.

        Args:
            receiver: The entity changing to friendly state

        Returns:
            Empty string (response will be handled by caller)
        """
        try:
            receiver.update_state('active')
            self.current_game.update_group(receiver, 'a')
            logger.info(f"Entity {receiver.label()} is now in the friendly group")
            return ""
        except Exception as e:
            logger.error(f"Error changing entity to friendly state: {e}")
            return ""

    def _handle_hostile_state_change(self, receiver: Entity) -> str:
        """
        Handle hostile state change command.
        
        Args:
            receiver: The entity changing to hostile state
            
        Returns:
            Empty string (response will be handled by caller)
        """
        try:
            receiver.update_state('active')
            self.current_game.update_group(receiver, 'b')
            logger.info(f"Entity {receiver.label()} is now in the hostile group")
            return ""
        except Exception as e:
            logger.error(f"Error changing entity to hostile state: {e}")
            return ""
    
    def _handle_inventory_query(self, receiver: Entity, llm_conversation_handler) -> str:
        """
        Handle inventory query command.
        
        Args:
            receiver: The entity whose inventory is being queried
            llm_conversation_handler: The LLM conversation handler
            
        Returns:
            The response after inventory processing
        """
        try:
            # Get inventory items
            inventory_items = [item['label'] for item in receiver.inventory_items(self.game_session)]
            system_response = f'[INVENTORY] {", ".join(inventory_items)}'
            
            # Add system message and regenerate response
            llm_conversation_handler.add_message(receiver.entity_uid, 'system', system_response)
            response = llm_conversation_handler.generate_response(receiver.entity_uid)
            
            # Re-parse language for the new response
            if response:
                language, response = self.parse_language_from_response(response)
                return response
            
            return ""
        except Exception as e:
            logger.error(f"Error handling inventory query: {e}")
            return ""
    
    def _handle_observation_request(self, receiver: Entity, llm_conversation_handler) -> str:
        """
        Handle observation request command.
        
        Args:
            receiver: The entity making the observation
            llm_conversation_handler: The LLM conversation handler
            
        Returns:
            The response after observation processing
        """
        try:
            # Get nearby entities
            battle_map = self.current_game.get_map_for_entity(receiver)
            nearby = receiver.observe(battle_map)
            
            # Build observation response
            observation_text = ""
            for entity, distance in nearby:
                observation_text += f"{entity.label()} is {distance}ft away\n"
            
            system_response = f'[OBSERVE] {observation_text}'
            
            # Add system message and regenerate response
            llm_conversation_handler.add_message(receiver.entity_uid, 'system', system_response)
            response = llm_conversation_handler.generate_response(receiver.entity_uid)
            
            # Re-parse language for the new response
            if response:
                language, response = self.parse_language_from_response(response)
                return response
            
            return ""
        except Exception as e:
            logger.error(f"Error handling observation request: {e}")
            return ""
    
    def get_entity_context(self, entity: Entity) -> Dict[str, Any]:
        """
        Get comprehensive context information for an entity.
        
        Args:
            entity: The entity to get context for
            
        Returns:
            Dictionary containing entity context information
        """
        context = {
            'name': entity.label() if hasattr(entity, 'label') else str(entity),
            'entity_uid': getattr(entity, 'entity_uid', None),
            'description': entity.description() if hasattr(entity, 'description') else 'No description available.'
        }
        
        # Add combat stats
        if hasattr(entity, 'hp') and callable(getattr(entity, 'hp')):
            context['hp'] = entity.hp()
        elif hasattr(entity, 'hp'):
            context['hp'] = entity.hp
        
        if hasattr(entity, 'max_hp') and callable(getattr(entity, 'max_hp')):
            context['max_hp'] = entity.max_hp()
        elif hasattr(entity, 'max_hp'):
            context['max_hp'] = entity.max_hp
        
        if hasattr(entity, 'armor_class') and callable(getattr(entity, 'armor_class')):
            context['ac'] = entity.armor_class()
        elif hasattr(entity, 'ac'):
            context['ac'] = entity.ac
        
        # Add level information
        if hasattr(entity, 'level') and callable(getattr(entity, 'level')):
            context['level'] = entity.level()
        elif hasattr(entity, 'level'):
            context['level'] = entity.level
        
        # Add race information
        if hasattr(entity, 'race') and callable(getattr(entity, 'race')):
            context['race'] = entity.race()
        elif hasattr(entity, 'race'):
            context['race'] = entity.race
        
        # Add class information
        class_value = None
        if hasattr(entity, 'class_descriptor') and callable(getattr(entity, 'class_descriptor')):
            class_value = entity.class_descriptor()
        if class_value:
            context['class'] = class_value
        elif hasattr(entity, 'class_and_level') and callable(getattr(entity, 'class_and_level')):
            class_info = entity.class_and_level()
            if class_info:
                context['class'] = ', '.join([f"{cls} {lvl}" for cls, lvl in class_info])
        
        # Add inventory information
        try:
            inventory_items = entity.inventory_items(self.game_session)
            context['inventory'] = [item['label'] for item in inventory_items] if inventory_items else []
        except:
            context['inventory'] = []
        
        # Add position information
        try:
            battle_map = self.current_game.get_map_for_entity(entity)
            if battle_map and hasattr(battle_map, 'entity_or_object_pos'):
                context['position'] = battle_map.entity_or_object_pos(entity)
        except:
            context['position'] = None
        
        return context
    
    def get_nearby_entities(self, entity: Entity, range_ft: int = 30) -> List[Dict[str, Any]]:
        """
        Get nearby entities for an entity.
        
        Args:
            entity: The entity to get nearby entities for
            range_ft: The range in feet to search
            
        Returns:
            List of nearby entity information
        """
        try:
            battle_map = self.current_game.get_map_for_entity(entity)
            nearby = entity.observe(battle_map, range_ft)
            
            response = []
            for nearby_entity, distance in nearby:
                response.append({
                    'id': nearby_entity.entity_uid,
                    'name': nearby_entity.label(),
                    'distance': distance,
                    'conversable': nearby_entity.conversable()
                })
            
            return response
        except Exception as e:
            logger.error(f"Error getting nearby entities: {e}")
            return []
    
    def validate_language_for_entity(self, language: str, entity: Entity) -> str:
        """
        Validate that an entity can speak the specified language.
        
        Args:
            language: The language to validate
            entity: The entity to check
            
        Returns:
            The validated language (falls back to first available if invalid)
        """
        if language not in entity.languages():
            return entity.languages()[0] if entity.languages() else "common"
        return language 