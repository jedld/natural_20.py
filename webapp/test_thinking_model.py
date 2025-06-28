#!/usr/bin/env python3
"""
Test script for thinking model handling in the LLM handler.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from llm_handler import llm_handler
from game_context import GameContextProvider

def test_thinking_model_handling():
    """Test the back-and-forth conversation handling for thinking models."""
    print("=== Testing Thinking Model Handling ===")
    
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

    # Register test functions
    def mock_get_map_info():
        return "Mock Map: Goblin Cave (20x15)"
    
    def mock_get_entities():
        return "Mock Entities: [Player1, Goblin1]"
    
    def mock_get_player_characters():
        return "Mock Player Characters: [Player1, Player2]"
    
    def mock_get_npcs():
        return "Mock NPCs: [Goblin1, Goblin2]"
    
    def mock_get_entity_details(entity_name):
        return f"Mock Entity Details for {entity_name}"
    
    def mock_get_battle_status():
        return "Mock Battle: Active, Turn 3"
    
    # Register the functions
    llm_handler.register_game_context_function("get_map_info", mock_get_map_info, "Get map info")
    llm_handler.register_game_context_function("get_entities", mock_get_entities, "Get entities")
    llm_handler.register_game_context_function("get_player_characters", mock_get_player_characters, "Get player characters")
    llm_handler.register_game_context_function("get_npcs", mock_get_npcs, "Get NPCs")
    llm_handler.register_game_context_function("get_entity_details", mock_get_entity_details, "Get entity details")
    llm_handler.register_game_context_function("get_battle_status", mock_get_battle_status, "Get battle status")
    
    # Test 1: Normal response (no thinking)
    print("\n1. Testing normal response (no thinking):")
    response = llm_handler.send_message("Who are the characters?")
    print(f"Response: {response}")
    
    # Clear history for next test
    llm_handler.clear_history()
    
    # Test 2: Simulate thinking model response
    print("\n2. Testing thinking model response:")
    
    # Override the mock provider's send_message to simulate thinking
    original_send_message = llm_handler.current_provider.send_message
    
    def thinking_send_message(messages):
        # Simulate a thinking model that first outputs thinking, then function calls
        if len(messages) == 2:  # First call
            return """<think>
Okay, so I need to figure out what information is required when giving a basic 
overview of the D&D Virtual Tabletop game. The user has asked for "basic information," 
which could encompass several things like the map details, entities present, player 
characters, NPCs, and maybe some initial battle status.

First, I should determine how to get each piece of information. From the rules 
provided, I know that functions like get_map_info(), get_entities(), 
get_player_characters(), get_npcs(), and get_battle_status() are available. Also, 
using get_entity_details() for specific entities is an option if needed.

For a basic game overview, it makes sense to include the map's information because 
that sets the stage. So I'll start with [FUNCTION_CALL: get_map_info()]. Next, listing 
all entities would give players an idea of what they're interacting with, so 
[FUNCTION_CALL: get_entities()] should be included.

Then, knowing who is currently a player character (PC) is essential for a new player's 
perspective, so [FUNCTION_CALL: get_player_characters()] is necessary. Including the 
NPCs will show any antagonists or helpful characters present, so [FUNCTION_CALL: 
get_npcs()] is another required call.

Lastly, checking the battle status tells if there are any active conflicts or 
objectives, so [FUNCTION_CALL: get_battle_status()] should be added to cover that 
aspect.

I don't think I need to go into specific details about entities unless the user asks 
for a particular one. Since it's "basic information," providing a general overview of 
all these aspects covers most needs without getting too detailed.
</think>

[FUNCTION_CALL: get_map_info()]
[FUNCTION_CALL: get_entities()]
[FUNCTION_CALL: get_player_characters()]
[FUNCTION_CALL: get_npcs()]
[FUNCTION_CALL: get_battle_status()]"""
        else:  # Follow-up call
            return "[FUNCTION_CALL: get_map_info()]\n[FUNCTION_CALL: get_entities()]"
    
    llm_handler.current_provider.send_message = thinking_send_message
    
    response = llm_handler.send_message("Give me basic information about the current game")
    print(f"Response: {response}")
    
    # Restore original method
    llm_handler.current_provider.send_message = original_send_message
    
    print("\n=== Test Complete ===")
    return True

if __name__ == "__main__":
    test_thinking_model_handling() 