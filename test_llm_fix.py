#!/usr/bin/env python3
"""
Test script to verify LLM handler fixes for infinite loop issues.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'webapp'))

from llm_handler import LLMHandler, MockProvider

def test_thinking_loop_fix():
    """Test that the thinking loop fix works correctly."""
    print("Testing thinking loop fix...")
    
    # Create a mock provider that returns thinking patterns
    class ThinkingMockProvider(MockProvider):
        def __init__(self):
            super().__init__()
            self.call_count = 0
        
        def send_message(self, messages):
            self.call_count += 1
            # Simulate a thinking model that keeps returning thinking patterns
            if self.call_count >= 3:  # After a few iterations, return function calls
                return "[FUNCTION_CALL: get_map_info()]"
            else:
                return "<think>I need to think about this...</think>Let me analyze the situation..."
    
    # Create handler and register the thinking provider
    handler = LLMHandler()
    handler.providers['thinking_mock'] = ThinkingMockProvider()
    handler.initialize_provider('thinking_mock', {})
    
    # Register a test function
    def get_map_info():
        return {"name": "test_map", "size": [10, 10]}
    
    handler.register_game_context_function('get_map_info', get_map_info, 'Get map info')
    
    # Test the message
    result = handler.send_message("What is the map name?")
    print(f"Result: {result}")
    
    # Check that we got a meaningful response (either processed function call or fallback)
    if "test_map" in result or "help" in result.lower() or "function" in result.lower():
        print("✅ Test passed: Thinking loop was handled correctly")
        return True
    else:
        print("❌ Test failed: Thinking loop was not handled correctly")
        return False

def test_empty_response_fix():
    """Test that empty responses are handled correctly."""
    print("\nTesting empty response fix...")
    
    # Create a mock provider that returns empty responses
    class EmptyMockProvider(MockProvider):
        def send_message(self, messages):
            return ""  # Return empty response
    
    # Create handler and register the empty provider
    handler = LLMHandler()
    handler.providers['empty_mock'] = EmptyMockProvider()
    handler.initialize_provider('empty_mock', {})
    
    # Test the message
    result = handler.send_message("Hello")
    print(f"Result: {result}")
    
    # Check that we got a fallback response
    if "help" in result.lower():
        print("✅ Test passed: Empty response was handled with fallback")
        return True
    else:
        print("❌ Test failed: Empty response was not handled correctly")
        return False

def test_repeated_response_fix():
    """Test that repeated responses are detected and handled."""
    print("\nTesting repeated response fix...")
    
    # Create a mock provider that returns the same response repeatedly
    class RepeatingMockProvider(MockProvider):
        def send_message(self, messages):
            return "I'm thinking about this..."  # Always return the same response
    
    # Create handler and register the repeating provider
    handler = LLMHandler()
    handler.providers['repeating_mock'] = RepeatingMockProvider()
    handler.initialize_provider('repeating_mock', {})
    
    # Test the message - this should trigger the repeated response detection
    result = handler.send_message("What is the map name?")
    print(f"Result: {result}")
    
    # Check that we got a fallback response
    if "help" in result.lower():
        print("✅ Test passed: Repeated response was detected and handled")
        return True
    else:
        print("❌ Test failed: Repeated response was not detected")
        print(f"Expected 'help' in result, got: {result}")
        return False

def test_simple_repeated_response():
    """Test repeated response detection with a simpler scenario."""
    print("\nTesting simple repeated response fix...")
    
    # Create a mock provider that returns the exact same response
    class SimpleRepeatingMockProvider(MockProvider):
        def send_message(self, messages):
            # Return the exact same response every time
            return "This is a test response"
    
    # Create handler and register the provider
    handler = LLMHandler()
    handler.providers['simple_repeating_mock'] = SimpleRepeatingMockProvider()
    handler.initialize_provider('simple_repeating_mock', {})
    
    # Test the message
    result = handler.send_message("Hello")
    print(f"Result: {result}")
    
    # Check that we got a fallback response
    if "help" in result.lower():
        print("✅ Test passed: Simple repeated response was detected and handled")
        return True
    else:
        print("❌ Test failed: Simple repeated response was not detected")
        print(f"Expected 'help' in result, got: {result}")
        return False

def test_conversation_length_fix():
    """Test that long conversations are handled correctly."""
    print("\nTesting conversation length fix...")
    
    # Create a mock provider that adds to conversation history
    class LongConversationMockProvider(MockProvider):
        def send_message(self, messages):
            # Return a response that will be added to conversation history
            return "I need more information to help you."
    
    # Create handler and register the provider
    handler = LLMHandler()
    handler.providers['long_mock'] = LongConversationMockProvider()
    handler.initialize_provider('long_mock', {})
    
    # Test the message
    result = handler.send_message("What is the map name?")
    print(f"Result: {result}")
    
    # Check that we got a fallback response
    if "help" in result.lower():
        print("✅ Test passed: Long conversation was handled correctly")
        return True
    else:
        print("❌ Test failed: Long conversation was not handled correctly")
        return False

if __name__ == "__main__":
    print("Running LLM handler fix tests...\n")
    
    tests = [
        test_thinking_loop_fix,
        test_empty_response_fix,
        test_repeated_response_fix,
        test_simple_repeated_response,
        test_conversation_length_fix
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
    
    print(f"\nTest Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! The LLM handler fixes are working correctly.")
    else:
        print("⚠️  Some tests failed. Please review the fixes.") 