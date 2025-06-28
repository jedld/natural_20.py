#!/usr/bin/env python3
"""
Test script for the thinking tag fix.

This script tests that responses with thinking tags but useful content after them
are properly handled and returned to the user.
"""

import os
import sys
from llm_handler import LLMHandler

def test_thinking_with_content():
    """Test handling of responses with thinking tags and useful content."""
    
    print("=== Testing Thinking Tag Fix ===\n")
    
    # Initialize the LLM handler
    handler = LLMHandler()
    
    # Get session info
    session_info = handler.get_session_info()
    print(f"Session ID: {session_info['session_id']}")
    print(f"Log File: {session_info['log_file']}")
    print()
    
    # Initialize mock provider for testing
    print("Initializing mock provider...")
    success = handler.initialize_provider('mock', {})
    if success:
        print("✓ Mock provider initialized successfully")
    else:
        print("✗ Failed to initialize mock provider")
        return
    
    print()
    
    # Test the _clean_response method directly with a sample response
    print("Testing _clean_response method with thinking tags and content...")
    
    # Sample response similar to what was in the log
    sample_response = '''<think>
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
    
    print("Original response length:", len(sample_response))
    print("Contains thinking tags:", "<think>" in sample_response)
    print("Contains useful content after thinking:", "Here's a complete" in sample_response)
    print()
    
    # Test the cleaning
    cleaned = handler._clean_response(sample_response)
    print("Cleaned response:")
    print("-" * 50)
    print(cleaned)
    print("-" * 50)
    print("Cleaned response length:", len(cleaned))
    print("Still contains useful content:", "Here's a complete" in cleaned)
    print("No thinking tags:", "<think>" not in cleaned)
    
    if "Here's a complete" in cleaned and "<think>" not in cleaned:
        print("✓ SUCCESS: Useful content preserved, thinking tags removed")
    else:
        print("✗ FAILURE: Content not properly cleaned")
    
    print()
    
    # Test with a response that has function calls
    print("Testing with response containing function calls...")
    function_response = '''<think>
I need to get information about the game state. Let me call the appropriate functions.
</think>

[FUNCTION_CALL: get_map_info()]
[FUNCTION_CALL: get_entities()]'''
    
    cleaned_function = handler._clean_response(function_response)
    print("Function response cleaned:")
    print("-" * 50)
    print(cleaned_function)
    print("-" * 50)
    
    if "[FUNCTION_CALL:" in cleaned_function and "<think>" not in cleaned_function:
        print("✓ SUCCESS: Function calls preserved, thinking tags removed")
    else:
        print("✗ FAILURE: Function calls not properly handled")
    
    print()
    
    # Test with empty response after thinking
    print("Testing with response that has only thinking...")
    thinking_only = '''<think>
I'm not sure what to do here. Let me think about this...
</think>'''
    
    cleaned_thinking_only = handler._clean_response(thinking_only)
    print("Thinking-only response cleaned:")
    print("-" * 50)
    print(cleaned_thinking_only)
    print("-" * 50)
    
    if len(cleaned_thinking_only.strip()) == 0:
        print("✓ SUCCESS: Empty response after thinking only")
    else:
        print("✗ FAILURE: Should be empty after thinking only")
    
    print("\n=== Test Complete ===")

if __name__ == "__main__":
    test_thinking_with_content() 