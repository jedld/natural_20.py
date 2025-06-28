#!/usr/bin/env python3
"""
Debug script to test function call processing.
"""

import sys
import os
import logging
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set up logging to see debug messages
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')

from llm_handler import llm_handler
from game_context import GameContextProvider

def test_function_call_processing():
    """Test function call processing with actual game context."""
    print("=== Testing Function Call Processing ===")
    
    # Initialize mock provider
    success = llm_handler.initialize_provider('mock', {})
    print(f"LLM handler initialization: {'SUCCESS' if success else 'FAILED'}")
    
    # Create a mock game context provider
    class MockGameSession:
        def __init__(self):
            self.root_path = '/tmp'

    class MockCurrentGame:
        def get_current_battle_map(self):
            return None
        def get_current_battle(self):
            return None

    mock_session = MockGameSession()
    mock_game = MockCurrentGame()
    context_provider = GameContextProvider(mock_session, mock_game)

    # Register the actual game context functions
    llm_handler.register_game_context_function(
        "get_map_info",
        context_provider.get_map_info,
        "Get current map information including terrain, layout, and basic details"
    )
    
    llm_handler.register_game_context_function(
        "get_entities",
        context_provider.get_entities,
        "Get all entities on the current map with their positions and basic information"
    )
    
    llm_handler.register_game_context_function(
        "get_player_characters",
        context_provider.get_player_characters,
        "Get information about player characters on the current map"
    )
    
    llm_handler.register_game_context_function(
        "get_npcs",
        context_provider.get_npcs,
        "Get information about NPCs on the current map"
    )
    
    llm_handler.register_game_context_function(
        "get_entity_details",
        context_provider.get_entity_details,
        "Get detailed information about a specific entity by name"
    )
    
    llm_handler.register_game_context_function(
        "get_battle_status",
        context_provider.get_battle_status,
        "Get current battle information if combat is active"
    )
    
    print(f"Registered functions: {list(llm_handler.game_context_functions.keys())}")
    
    # Test the exact response format you're getting from Ollama
    test_response = " [FUNCTION_CALL: get_map_info()]\n[FUNCTION_CALL: get_entities()]"
    print(f"\nTesting with response: {repr(test_response)}")
    
    # Test function call processing directly
    result = llm_handler._process_function_calls(test_response)
    print(f"\nProcessed result: {result}")
    
    # Test with the full send_message flow
    print("\nTesting full send_message flow:")
    response = llm_handler.send_message("Give me basic information about the current game")
    print(f"Final response: {response}")
    
    return True

if __name__ == "__main__":
    test_function_call_processing() 