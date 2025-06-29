#!/usr/bin/env python3
"""
Example script demonstrating how to set and use context window size with Ollama provider.

This script shows how to:
1. Initialize the Ollama provider with a custom context window size
2. Set the context window size after initialization
3. Get the current context window size
4. Use the LLM handler with the configured context window
"""

import sys
import os

# Add the parent directory to the path so we can import the llm_handler
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from llm_handler import llm_handler

def main():
    print("=== Ollama Context Window Example ===\n")
    
    # Example 1: Initialize with custom context window size
    print("1. Initializing Ollama provider with 8192 context window...")
    config = {
        'base_url': 'http://localhost:11434',
        'model': 'llama3.2:3b',  # Change this to your available model
        'context_window': 8192   # Set custom context window size
    }
    
    success = llm_handler.initialize_provider('ollama', config)
    if not success:
        print("❌ Failed to initialize Ollama provider")
        print("Make sure Ollama is running and the model is available")
        return
    
    print("✅ Ollama provider initialized successfully")
    
    # Example 2: Get current context window size
    current_context_window = llm_handler.get_context_window()
    print(f"📏 Current context window size: {current_context_window}")
    
    # Example 3: Change context window size after initialization
    print("\n2. Changing context window size to 4096...")
    success = llm_handler.set_context_window(4096)
    if success:
        print("✅ Context window size changed successfully")
        new_context_window = llm_handler.get_context_window()
        print(f"📏 New context window size: {new_context_window}")
    else:
        print("❌ Failed to change context window size")
    
    # Example 4: Get provider info (includes context window)
    print("\n3. Provider information:")
    provider_info = llm_handler.get_provider_info()
    for key, value in provider_info.items():
        print(f"   {key}: {value}")
    
    # Example 5: Test with a simple message
    print("\n4. Testing with a simple message...")
    try:
        response = llm_handler.send_message("Hello! Can you tell me about the current game state?")
        print(f"🤖 AI Response: {response}")
    except Exception as e:
        print(f"❌ Error sending message: {e}")
    
    # Example 6: Show different context window sizes
    print("\n5. Testing different context window sizes...")
    context_sizes = [2048, 4096, 8192, 16384]
    
    for size in context_sizes:
        print(f"\n   Setting context window to {size}...")
        if llm_handler.set_context_window(size):
            current_size = llm_handler.get_context_window()
            print(f"   ✅ Context window set to {current_size}")
        else:
            print(f"   ❌ Failed to set context window to {size}")

if __name__ == "__main__":
    main() 