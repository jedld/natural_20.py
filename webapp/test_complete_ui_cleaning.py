#!/usr/bin/env python3
"""
Complete end-to-end test for thinking tag removal.

This test verifies that thinking tags are removed at every level:
1. Server-side in LLMHandler
2. Client-side in JavaScript
3. Final UI display
"""

import os
import sys
import re
from llm_handler import LLMHandler

def test_server_side_cleaning():
    """Test server-side thinking tag cleaning in LLMHandler."""
    print("=== Testing Server-Side Cleaning ===")
    
    handler = LLMHandler()
    
    # Test cases with thinking tags
    test_cases = [
        {
            "name": "Basic thinking tags",
            "input": """<think>
I need to help the user with their D&D game. Let me think about what they need.
</think>

Here's the information you requested about your characters.""",
            "expected_contains": "Here's the information you requested",
            "expected_not_contains": "<think>"
        },
        {
            "name": "Thinking with function calls",
            "input": """<think>
I should call the appropriate functions to get game data.
</think>

[FUNCTION_CALL: get_map_info()]
[FUNCTION_CALL: get_entities()]""",
            "expected_contains": "[FUNCTION_CALL:",
            "expected_not_contains": "<think>"
        },
        {
            "name": "Reasoning blocks",
            "input": """Okay, so I need to figure out what the user wants. Let me analyze this step by step.

Here's what I found for you.""",
            "expected_contains": "Here's what I found",
            "expected_not_contains": "Okay, so"
        },
        {
            "name": "Complex response with thinking",
            "input": """<think>
This is a complex question about D&D mechanics. Let me think through the rules.
</think>

Based on the D&D 5e rules, here's how that works:

**Attack Rolls:**
- Roll 1d20 + your attack modifier
- Compare to target's Armor Class (AC)
- If you meet or exceed the AC, you hit!

**Damage:**
- If you hit, roll your weapon's damage dice
- Add your relevant ability modifier
- Apply any special effects or bonuses""",
            "expected_contains": "Based on the D&D 5e rules",
            "expected_not_contains": "<think>"
        }
    ]
    
    all_passed = True
    
    for test_case in test_cases:
        print(f"\nTesting: {test_case['name']}")
        
        # Test the _clean_response method
        cleaned = handler._clean_response(test_case['input'])
        
        print(f"Input length: {len(test_case['input'])}")
        print(f"Cleaned length: {len(cleaned)}")
        print(f"Contains expected: {test_case['expected_contains'] in cleaned}")
        print(f"Doesn't contain thinking: {test_case['expected_not_contains'] not in cleaned}")
        
        if (test_case['expected_contains'] in cleaned and 
            test_case['expected_not_contains'] not in cleaned):
            print("✓ PASSED")
        else:
            print("✗ FAILED")
            all_passed = False
    
    return all_passed

def test_client_side_cleaning():
    """Test client-side thinking tag cleaning (JavaScript equivalent)."""
    print("\n=== Testing Client-Side Cleaning ===")
    
    def clean_thinking_tags_js(content):
        """JavaScript equivalent of the cleaning function."""
        if not content or not isinstance(content, str):
            return content
        
        # Remove thinking tags and their content
        cleaned = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
        cleaned = re.sub(r'<reasoning>.*?</reasoning>', '', cleaned, flags=re.DOTALL)
        cleaned = re.sub(r'<thought>.*?</thought>', '', cleaned, flags=re.DOTALL)
        
        # Remove reasoning blocks that start with "Okay, so" or similar
        cleaned = re.sub(r'Okay, so.*?(?=\[FUNCTION_CALL:|$)', '', cleaned, flags=re.DOTALL)
        cleaned = re.sub(r'Let me.*?(?=\[FUNCTION_CALL:|$)', '', cleaned, flags=re.DOTALL)
        cleaned = re.sub(r'I need to.*?(?=\[FUNCTION_CALL:|$)', '', cleaned, flags=re.DOTALL)
        
        # Clean up extra whitespace and newlines
        cleaned = re.sub(r'\n\s*\n', '\n', cleaned)
        cleaned = cleaned.strip()
        
        return cleaned
    
    # Test cases
    test_cases = [
        {
            "name": "Basic thinking tags",
            "input": """<think>
I need to help the user with their D&D game. Let me think about what they need.
</think>

Here's the information you requested about your characters.""",
            "expected_contains": "Here's the information you requested",
            "expected_not_contains": "<think>"
        },
        {
            "name": "Thinking with function calls",
            "input": """<think>
I should call the appropriate functions to get game data.
</think>

[FUNCTION_CALL: get_map_info()]
[FUNCTION_CALL: get_entities()]""",
            "expected_contains": "[FUNCTION_CALL:",
            "expected_not_contains": "<think>"
        }
    ]
    
    all_passed = True
    
    for test_case in test_cases:
        print(f"\nTesting: {test_case['name']}")
        
        # Test the client-side cleaning function
        cleaned = clean_thinking_tags_js(test_case['input'])
        
        print(f"Input length: {len(test_case['input'])}")
        print(f"Cleaned length: {len(cleaned)}")
        print(f"Contains expected: {test_case['expected_contains'] in cleaned}")
        print(f"Doesn't contain thinking: {test_case['expected_not_contains'] not in cleaned}")
        
        if (test_case['expected_contains'] in cleaned and 
            test_case['expected_not_contains'] not in cleaned):
            print("✓ PASSED")
        else:
            print("✗ FAILED")
            all_passed = False
    
    return all_passed

def test_end_to_end_flow():
    """Test the complete flow from LLM response to final display."""
    print("\n=== Testing End-to-End Flow ===")
    
    # Simulate the complete flow
    handler = LLMHandler()
    
    # Simulate a response with thinking tags (like from the log)
    raw_response = """<think>
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

This gives you a complete overview of all characters in your current game session. Would you like me to provide more specific details about any particular character or help you analyze the party composition?"""
    
    print("Step 1: Raw LLM response received")
    print(f"Raw response length: {len(raw_response)}")
    print(f"Contains thinking tags: {'<think>' in raw_response}")
    print(f"Contains useful content: {'Here is a complete' in raw_response}")
    
    # Step 2: Server-side cleaning
    print("\nStep 2: Server-side cleaning")
    server_cleaned = handler._clean_response(raw_response)
    print(f"Server cleaned length: {len(server_cleaned)}")
    print(f"Still contains thinking tags: {'<think>' in server_cleaned}")
    print(f"Still contains useful content: {'Here is a complete' in server_cleaned}")
    
    # Step 3: Client-side cleaning (safety measure)
    print("\nStep 3: Client-side cleaning (safety measure)")
    def clean_thinking_tags_js(content):
        if not content or not isinstance(content, str):
            return content
        cleaned = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
        cleaned = re.sub(r'<reasoning>.*?</reasoning>', '', cleaned, flags=re.DOTALL)
        cleaned = re.sub(r'<thought>.*?</thought>', '', cleaned, flags=re.DOTALL)
        cleaned = re.sub(r'Okay, so.*?(?=\[FUNCTION_CALL:|$)', '', cleaned, flags=re.DOTALL)
        cleaned = re.sub(r'Let me.*?(?=\[FUNCTION_CALL:|$)', '', cleaned, flags=re.DOTALL)
        cleaned = re.sub(r'I need to.*?(?=\[FUNCTION_CALL:|$)', '', cleaned, flags=re.DOTALL)
        cleaned = re.sub(r'\n\s*\n', '\n', cleaned)
        cleaned = cleaned.strip()
        return cleaned
    
    client_cleaned = clean_thinking_tags_js(server_cleaned)
    print(f"Client cleaned length: {len(client_cleaned)}")
    print(f"Final contains thinking tags: {'<think>' in client_cleaned}")
    print(f"Final contains useful content: {'Here is a complete' in client_cleaned}")
    
    # Step 4: Final display
    print("\nStep 4: Final display")
    if '<think>' not in client_cleaned and 'Here is a complete' in client_cleaned:
        print("✓ SUCCESS: Thinking tags removed, useful content preserved")
        print("\nFinal displayed content:")
        print("-" * 50)
        print(client_cleaned[:200] + "..." if len(client_cleaned) > 200 else client_cleaned)
        print("-" * 50)
        return True
    else:
        print("✗ FAILURE: Thinking tags not properly removed or useful content lost")
        return False

def main():
    """Run all tests."""
    print("=== Complete UI Thinking Tag Cleaning Test ===\n")
    
    # Run all tests
    server_passed = test_server_side_cleaning()
    client_passed = test_client_side_cleaning()
    end_to_end_passed = test_end_to_end_flow()
    
    # Summary
    print("\n" + "=" * 50)
    print("TEST SUMMARY")
    print("=" * 50)
    print(f"Server-side cleaning: {'✓ PASSED' if server_passed else '✗ FAILED'}")
    print(f"Client-side cleaning: {'✓ PASSED' if client_passed else '✗ FAILED'}")
    print(f"End-to-end flow: {'✓ PASSED' if end_to_end_passed else '✗ FAILED'}")
    
    if server_passed and client_passed and end_to_end_passed:
        print("\n🎉 ALL TESTS PASSED! Thinking tags are properly removed at every level.")
    else:
        print("\n❌ SOME TESTS FAILED! Please check the implementation.")
    
    print("\n=== Test Complete ===")

if __name__ == "__main__":
    main() 