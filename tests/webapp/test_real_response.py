#!/usr/bin/env python3
"""
Test script to simulate the real Ollama response format.
"""

import sys
import os
import logging
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set up logging to see debug messages
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')

from llm_handler import llm_handler
from game_context import GameContextProvider

def test_real_ollama_response():
    """Test with the exact response format from Ollama."""
    print("=== Testing Real Ollama Response Format ===")
    
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
    
    # Override the mock provider to return the exact format from your Ollama response
    original_send_message = llm_handler.current_provider.send_message
    
    def real_ollama_response(messages):
        # Return the exact format from your Ollama response
        return " [FUNCTION_CALL: get_map_info()]\n[FUNCTION_CALL: get_entities()]"
    
    llm_handler.current_provider.send_message = real_ollama_response
    
    print("Testing with real Ollama response format...")
    response = llm_handler.send_message("Give me basic information about the current game")
    print(f"Final response: {response}")
    
    # Restore original method
    llm_handler.current_provider.send_message = original_send_message
    
    return True

if __name__ == "__main__":
    test_real_ollama_response() 