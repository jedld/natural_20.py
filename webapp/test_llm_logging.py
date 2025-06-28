#!/usr/bin/env python3
"""
Test script for LLM logging functionality.

This script demonstrates how the session-based logging works for LLM interactions.
"""

import os
import sys
from llm_handler import LLMHandler

def test_llm_logging():
    """Test the LLM logging functionality."""
    
    print("=== LLM Logging Test ===\n")
    
    # Initialize the LLM handler
    handler = LLMHandler()
    
    # Get session info
    session_info = handler.get_session_info()
    print(f"Session ID: {session_info['session_id']}")
    print(f"Log File: {session_info['log_file']}")
    print(f"Start Time: {session_info['start_time']}")
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
    
    # Test some interactions
    test_messages = [
        "Who are the characters?",
        "What is the current map?",
        "Tell me about the battle status"
    ]
    
    for i, message in enumerate(test_messages, 1):
        print(f"Test {i}: {message}")
        print("-" * 40)
        
        # Send message
        response = handler.send_message(message)
        print(f"Response: {response}")
        print()
    
    # Show final session info
    final_session_info = handler.get_session_info()
    print(f"Session Duration: {final_session_info['duration']}")
    print(f"Log file created: {os.path.exists(final_session_info['log_file'])}")
    
    if os.path.exists(final_session_info['log_file']):
        print(f"\nLog file contents preview:")
        print("-" * 50)
        with open(final_session_info['log_file'], 'r') as f:
            lines = f.readlines()
            for line in lines[:20]:  # Show first 20 lines
                print(line.rstrip())
        if len(lines) > 20:
            print("... (truncated)")
    
    print("\n=== Test Complete ===")

def test_session_management():
    """Test session management functionality."""
    
    print("\n=== Session Management Test ===\n")
    
    handler = LLMHandler()
    
    # Get initial session info
    session1_info = handler.get_session_info()
    print(f"Session 1 ID: {session1_info['session_id']}")
    
    # Send a message
    handler.initialize_provider('mock', {})
    handler.send_message("Hello")
    
    # Clear session and start new one
    handler.clear_session()
    session2_info = handler.get_session_info()
    print(f"Session 2 ID: {session2_info['session_id']}")
    
    # Verify different session IDs
    if session1_info['session_id'] != session2_info['session_id']:
        print("✓ Session management working correctly")
    else:
        print("✗ Session management failed - same session ID")

if __name__ == "__main__":
    test_llm_logging()
    test_session_management() 