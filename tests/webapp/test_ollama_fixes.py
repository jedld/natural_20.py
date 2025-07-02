#!/usr/bin/env python3
"""
Test script for Ollama fixes.
"""

import sys
import os
import logging
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set up logging to see info messages
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

from llm_handler import llm_handler
from game_context import GameContextProvider

def test_ollama_fixes():
    """Test the Ollama fixes."""
    print("=== Testing Ollama Fixes ===")
    
    # Initialize mock provider (we'll override it to simulate Ollama behavior)
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
        "get_entity_details",
        context_provider.get_entity_details,
        "Get detailed information about a specific entity by name"
    )
    
    # Test 1: Empty response handling
    print("\n=== Test 1: Empty Response Handling ===")
    
    # Override the mock provider to simulate empty response
    original_send_message = llm_handler.current_provider.send_message
    
    def mock_empty_response(messages):
        return ""
    
    llm_handler.current_provider.send_message = mock_empty_response
    
    response = llm_handler.send_message("Give me basic information about the current game")
    print(f"Response: {response}")
    
    # Test 2: Function call parsing with arguments
    print("\n=== Test 2: Function Call with Arguments ===")
    
    def mock_function_call_with_args(messages):
        return "[FUNCTION_CALL: get_entity_details(\"Test Entity\")]"
    
    llm_handler.current_provider.send_message = mock_function_call_with_args
    
    response = llm_handler.send_message("Tell me about the entity named 'Test Entity'")
    print(f"Response: {response}")
    
    # Test 3: Multiple function calls
    print("\n=== Test 3: Multiple Function Calls ===")
    
    def mock_multiple_functions(messages):
        return "[FUNCTION_CALL: get_map_info()]\n[FUNCTION_CALL: get_entities()]"
    
    llm_handler.current_provider.send_message = mock_multiple_functions
    
    response = llm_handler.send_message("Give me basic information about the current game")
    print(f"Response: {response}")
    
    # Restore original method
    llm_handler.current_provider.send_message = original_send_message
    
    return True

if __name__ == "__main__":
    test_ollama_fixes() 