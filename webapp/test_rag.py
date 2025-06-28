#!/usr/bin/env python3
"""
Test script for RAG functionality in the D&D VTT AI system.

This script tests the game context functions and LLM handler integration.
"""

import sys
import os
import json
import logging

# Add the parent directory to the path so we can import the modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from webapp.llm_handler import llm_handler, MockProvider
from webapp.game_context import GameContextProvider

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_mock_provider():
    """Test the mock provider functionality."""
    print("=== Testing Mock Provider ===")
    
    # Initialize mock provider
    mock_provider = MockProvider()
    success = mock_provider.initialize({})
    print(f"Mock provider initialization: {'SUCCESS' if success else 'FAILED'}")
    
    # Test message sending
    response = mock_provider.send_message("Tell me about the map")
    print(f"Mock response: {response}")
    
    # Test with context
    context = {
        "current_map": "Test Map",
        "entities": [{"name": "Player 1", "type": "PlayerCharacter"}],
        "battle": False
    }
    response_with_context = mock_provider.send_message("What's happening?", context)
    print(f"Mock response with context: {response_with_context}")
    
    return success

def test_game_context_functions():
    """Test the game context functions (without actual game session)."""
    print("\n=== Testing Game Context Functions ===")
    
    # Create a mock game session and current game
    class MockGameSession:
        def __init__(self):
            self.root_path = "/tmp"
    
    class MockCurrentGame:
        def get_current_battle_map(self):
            return None
        
        def get_current_battle(self):
            return None
    
    mock_session = MockGameSession()
    mock_game = MockCurrentGame()
    
    # Initialize game context provider
    context_provider = GameContextProvider(mock_session, mock_game)
    
    # Test map info
    map_info = context_provider.get_map_info()
    print(f"Map info: {json.dumps(map_info, indent=2)}")
    
    # Test entities
    entities = context_provider.get_entities()
    print(f"Entities: {json.dumps(entities, indent=2)}")
    
    # Test player characters
    pcs = context_provider.get_player_characters()
    print(f"Player characters: {json.dumps(pcs, indent=2)}")
    
    # Test NPCs
    npcs = context_provider.get_npcs()
    print(f"NPCs: {json.dumps(npcs, indent=2)}")
    
    # Test battle status
    battle_status = context_provider.get_battle_status()
    print(f"Battle status: {json.dumps(battle_status, indent=2)}")
    
    return True

def test_llm_handler_integration():
    """Test the LLM handler integration with game context functions."""
    print("\n=== Testing LLM Handler Integration ===")
    
    # Initialize LLM handler with mock provider
    success = llm_handler.initialize_provider('mock', {})
    print(f"LLM handler initialization: {'SUCCESS' if success else 'FAILED'}")
    
    # Register a simple test function
    def test_function():
        return {"test": "data", "message": "Hello from test function"}
    
    llm_handler.register_game_context_function(
        "test_function",
        test_function,
        "A test function for RAG integration"
    )
    
    # Test getting game context
    context = llm_handler.get_game_context()
    print(f"Game context: {json.dumps(context, indent=2)}")
    
    # Test sending a message
    response = llm_handler.send_message("Hello, can you help me with the game?")
    print(f"LLM response: {response}")
    
    # Test conversation history
    history = llm_handler.get_conversation_history()
    print(f"Conversation history length: {len(history)}")
    
    # Test clearing history
    llm_handler.clear_history()
    history_after_clear = llm_handler.get_conversation_history()
    print(f"History after clear: {len(history_after_clear)}")
    
    return success

def test_function_registration():
    """Test that functions are properly registered."""
    print("\nTesting function registration...")
    
    # Initialize mock provider
    llm_handler.initialize_provider("mock", {})
    
    # Manually register test functions to verify the fix
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
    
    # Check if functions are registered
    expected_functions = [
        "get_map_info",
        "get_entities", 
        "get_player_characters",
        "get_npcs",
        "get_entity_details",
        "get_battle_status"
    ]
    
    for func_name in expected_functions:
        if func_name in llm_handler.game_context_functions:
            print(f"✓ Function '{func_name}' is registered")
        else:
            print(f"✗ Function '{func_name}' is NOT registered")
    
    # Test the parse_and_execute_function_calls method
    test_response = "[FUNCTION_CALL: get_player_characters()]"
    try:
        results = llm_handler.parse_and_execute_function_calls(test_response)
        print(f"✓ parse_and_execute_function_calls works: {results}")
        if "Mock Player Characters" in str(results):
            print("✓ Function execution confirmed")
        else:
            print("✗ Function execution failed")
    except Exception as e:
        print(f"✗ parse_and_execute_function_calls failed: {e}")

def test_function_calling():
    """Test that the LLM properly calls functions when needed."""
    print("Testing function calling...")
    
    # Initialize mock provider
    llm_handler.initialize_provider("mock", {})
    
    # Register test functions
    def mock_get_player_characters():
        return "Mock Player Characters: [Player1, Player2]"
    
    def mock_get_npcs():
        return "Mock NPCs: [Goblin1, Goblin2]"
    
    def mock_get_map_info():
        return "Mock Map: Goblin Cave (20x15)"
    
    def mock_get_entities():
        return "Mock Entities: [Player1 at (5,5), Goblin1 at (10,8)]"
    
    def mock_get_battle_status():
        return "Mock Battle: Active, Turn 3"
    
    # Register the functions
    llm_handler.register_game_context_function("get_player_characters", mock_get_player_characters, "Get player characters")
    llm_handler.register_game_context_function("get_npcs", mock_get_npcs, "Get NPCs")
    llm_handler.register_game_context_function("get_map_info", mock_get_map_info, "Get map info")
    llm_handler.register_game_context_function("get_entities", mock_get_entities, "Get entities")
    llm_handler.register_game_context_function("get_battle_status", mock_get_battle_status, "Get battle status")
    
    # Test character question
    print("\n1. Testing character question:")
    response = llm_handler.send_message("Who are the characters?")
    print(f"Response: {response}")
    
    # Check if function calls are present
    if "[FUNCTION_CALL:" in response:
        print("✓ Function calls detected in response")
    else:
        print("✗ No function calls detected")
    
    # Test map question
    print("\n2. Testing map question:")
    response = llm_handler.send_message("What's on the map?")
    print(f"Response: {response}")
    
    if "[FUNCTION_CALL:" in response:
        print("✓ Function calls detected in response")
    else:
        print("✗ No function calls detected")
    
    # Test battle question
    print("\n3. Testing battle question:")
    response = llm_handler.send_message("What's the battle status?")
    print(f"Response: {response}")
    
    if "[FUNCTION_CALL:" in response:
        print("✓ Function calls detected in response")
    else:
        print("✗ No function calls detected")

def test_function_execution():
    """Test that functions are actually executed."""
    print("\nTesting function execution...")
    
    # Initialize mock provider
    llm_handler.initialize_provider("mock", {})
    
    # Register test functions
    def mock_get_player_characters():
        return "Mock Player Characters: [Player1, Player2]"
    
    llm_handler.register_game_context_function("get_player_characters", mock_get_player_characters, "Get player characters")
    
    # Test a response that should trigger function calls
    response = llm_handler.send_message("Who are the characters?")
    
    # Check if function results are present
    if "Mock Player Characters:" in response:
        print("✓ Function execution detected")
    else:
        print("✗ Function execution not detected")
        print(f"Full response: {response}")

def test_system_prompt():
    """Test that the system prompt includes function calling instructions."""
    print("\nTesting system prompt...")
    
    prompt = llm_handler._build_system_prompt()
    
    required_elements = [
        "FUNCTION_CALL:",
        "get_map_info()",
        "get_entities()",
        "get_player_characters()",
        "get_npcs()",
        "ALWAYS use functions"
    ]
    
    for element in required_elements:
        if element in prompt:
            print(f"✓ Found '{element}' in system prompt")
        else:
            print(f"✗ Missing '{element}' in system prompt")

def main():
    """Run all tests."""
    print("RAG System Test Suite")
    print("=" * 50)
    
    tests = [
        ("Mock Provider", test_mock_provider),
        ("Game Context Functions", test_game_context_functions),
        ("LLM Handler Integration", test_llm_handler_integration),
        ("System Prompt Generation", test_system_prompt),
        ("Function Registration", test_function_registration),
        ("Function Calling", test_function_calling),
        ("Function Execution", test_function_execution)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
            print(f"✓ {test_name}: {'PASSED' if result else 'FAILED'}")
        except Exception as e:
            results.append((test_name, False))
            print(f"✗ {test_name}: FAILED - {e}")
            logger.error(f"Test {test_name} failed: {e}")
    
    # Summary
    print("\n" + "=" * 50)
    print("TEST SUMMARY")
    print("=" * 50)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "PASSED" if result else "FAILED"
        print(f"{test_name}: {status}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! RAG system is working correctly.")
        return 0
    else:
        print("❌ Some tests failed. Please check the implementation.")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 