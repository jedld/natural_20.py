#!/usr/bin/env python3
"""
Test script for the real scenario from the log.

This script simulates the exact scenario where the LLM generates thinking tags
followed by useful content, and verifies that the content is properly returned.
"""

import os
import sys
from llm_handler import LLMHandler

class TestOllamaProvider:
    """Mock provider that simulates the real Ollama response from the log."""
    
    def __init__(self):
        self.initialized = True
        self.current_model = "test-model"
        self.conversation_history = []
    
    def initialize(self, config):
        return True
    
    def send_message(self, messages):
        # Simulate the exact response from the log
        return '''<think>
Okay, so I'm trying to figure out how to help the user with their D&D game data. They've provided some JSON-like data that includes details about characters and non-playable opponents (NPCs). The first thing I notice is that they want a complete, user-friendly response based on this information.

Looking at the data, there are two main sections: Characters and NPCs. Each has several entries with fields like name, type, entity_uid, position, hp, max_hp, level, dead status, and whether they're unconscious, prone, or hidden.

I think the best approach is to present this information in a clear and organized way. Maybe I can start by explaining what each section represents. For Characters, it's straightforward—each has a name, type (player or NPC), position on the grid, health stats, level, and status. The same goes for NPCs.

I should probably format this as two separate lists to make it easy to read. Under Characters, I'll list each one with their details. Then do the same for NPCs. This way, the user can quickly compare the different classes or encounter enemies without getting overwhelmed.

Also, since they mentioned wanting a complete response, I should include all 12 characters and 30+ NPCs in the data provided. That means no omissions—everything is included as per their JSON input.

I need to make sure that each entry is clear and concise. Maybe using bullet points or numbered lists could help, but since it's a text response, I'll just list them out with line breaks for readability.

Another thing to consider is the user's possible needs. They might be looking to analyze their party composition or prepare for an encounter. By providing all the necessary details in one place, they can easily compare stats and make informed decisions.

I should also mention that if there are any specific questions or need further analysis, I'm here to help. This opens up a conversation for them to ask more detailed questions if needed.

Finally, I'll wrap it up by offering assistance with anything else they might need beyond just presenting the data.
</think>

Here's a complete and organized presentation of your game data:

### Characters
- **Player Characters**
  - **Name:** Darrak  
    **Type:** Player  
    **Position:** [9, 3]  
    **HP:** 11/11  
    **Level:** 0.25  
    **Status:** Alive

- **NPCs**
  - **Name:** Goblin Warrior
    **Type:** NPC
    **Position:** [5, 7]
    **HP:** 7/7
    **Level:** 1
    **Status:** Alive

This gives you a complete overview of all characters in your current game session. Would you like me to provide more specific details about any particular character or help you analyze the party composition?'''
    
    def get_available_models(self):
        return ["test-model"]
    
    def set_model(self, model_name):
        self.current_model = model_name
        return True

def test_real_scenario():
    """Test the real scenario from the log."""
    
    print("=== Testing Real Scenario from Log ===\n")
    
    # Initialize the LLM handler
    handler = LLMHandler()
    
    # Get session info
    session_info = handler.get_session_info()
    print(f"Session ID: {session_info['session_id']}")
    print(f"Log File: {session_info['log_file']}")
    print()
    
    # Replace the mock provider with our test provider
    handler.providers['mock'] = TestOllamaProvider()
    
    # Initialize the test provider
    print("Initializing test provider...")
    success = handler.initialize_provider('mock', {})
    if success:
        print("✓ Test provider initialized successfully")
    else:
        print("✗ Failed to initialize test provider")
        return
    
    print()
    
    # Test the complete flow
    print("Testing complete message flow with thinking tags and content...")
    
    # Send a message that will trigger the response with thinking tags
    response = handler.send_message("Show me the characters in the game")
    
    print("Final response received:")
    print("-" * 50)
    print(response)
    print("-" * 50)
    
    # Check if the response contains the useful content
    contains_useful_content = "Here's a complete" in response
    contains_character_info = "Darrak" in response
    contains_npc_info = "Goblin Warrior" in response
    no_thinking_tags = "<think>" not in response
    
    print(f"Contains useful content: {contains_useful_content}")
    print(f"Contains character info: {contains_character_info}")
    print(f"Contains NPC info: {contains_npc_info}")
    print(f"No thinking tags: {no_thinking_tags}")
    
    if contains_useful_content and contains_character_info and contains_npc_info and no_thinking_tags:
        print("✓ SUCCESS: Real scenario handled correctly!")
        print("   - Thinking tags removed")
        print("   - Useful content preserved")
        print("   - Character information included")
        print("   - Response returned to user")
    else:
        print("✗ FAILURE: Real scenario not handled correctly")
    
    print()
    
    # Check the log file to see what was logged
    if os.path.exists(session_info['log_file']):
        print("Log file created successfully")
        with open(session_info['log_file'], 'r') as f:
            content = f.read()
            if "THINKING_DETECTED" in content:
                print("✓ Thinking detection logged")
            if "RAW RESPONSE FROM LLM" in content:
                print("✓ Raw response logged")
            if "Found useful content after thinking tags" in content:
                print("✓ Useful content detection logged")
    else:
        print("✗ Log file not created")
    
    print("\n=== Test Complete ===")

if __name__ == "__main__":
    test_real_scenario() 