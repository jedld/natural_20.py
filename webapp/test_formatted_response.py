#!/usr/bin/env python3
"""
Test script to verify that function call results are formatted by the LLM.
"""

import sys
import os
import logging
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set up logging to see info messages
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

from llm_handler import llm_handler
from game_context import GameContextProvider

def test_formatted_response():
    """Test that function call results are formatted by the LLM."""
    print("=== Testing Formatted Response ===")
    
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
    
    # Override the mock provider to return function calls and then format them
    original_send_message = llm_handler.current_provider.send_message
    call_count = 0
    
    def mock_response_with_formatting(messages):
        nonlocal call_count
        call_count += 1
        
        # First call: return function calls
        if call_count == 1:
            return " [FUNCTION_CALL: get_map_info()]\n[FUNCTION_CALL: get_entities()]"
        # Second call: format the results
        else:
            # Extract the game data from the formatting request
            for msg in messages:
                if "Game data:" in msg.get('content', ''):
                    game_data = msg['content'].split('Game data:')[1].split('\n\nPlease provide')[0]
                    return f"""Based on the current game state, here's what I found:

**Map Information:**
{game_data}

The map appears to be a 10x10 grid with 5 feet per grid square. There are currently no entities on the map.

Would you like more specific information about any particular aspect of the game?"""
            
            return "I've gathered the game information for you. How can I help further?"
    
    llm_handler.current_provider.send_message = mock_response_with_formatting
    
    print("Testing with function calls that should be formatted...")
    response = llm_handler.send_message("Give me basic information about the current game")
    print(f"Final formatted response: {response}")
    
    # Restore original method
    llm_handler.current_provider.send_message = original_send_message
    
    return True

if __name__ == "__main__":
    test_formatted_response() 