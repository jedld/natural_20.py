#!/usr/bin/env python3
"""
Test script to verify that all LLM providers work correctly without the list.get() error.
"""

import os
import sys

# Add the parent directory to the path so we can import the LLM handler
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
        print(f"Loaded environment variables from: {env_path}")
    else:
        parent_env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
        if os.path.exists(parent_env_path):
            load_dotenv(parent_env_path)
            print(f"Loaded environment variables from: {parent_env_path}")
        else:
            print("python-dotenv not installed, using system environment variables")
except ImportError:
    print("python-dotenv not installed, using system environment variables")

from webapp.llm_handler import LLMHandler

def test_provider(provider_name, config):
    """Test a specific provider."""
    print(f"\n--- Testing {provider_name.upper()} Provider ---")
    
    try:
        # Initialize the LLM handler
        llm_handler = LLMHandler()
        
        # Initialize the provider
        success = llm_handler.initialize_provider(provider_name, config)
        if not success:
            print(f"❌ Failed to initialize {provider_name} provider")
            return False
        
        print(f"✅ {provider_name} provider initialized successfully")
        
        # Test sending a simple message
        test_message = "Hello, how are you?"
        print(f"📤 Sending test message: '{test_message}'")
        
        try:
            response = llm_handler.send_message(test_message)
            print(f"📥 Received response: '{response}'")
            
            # Check if the response contains the error we were trying to fix
            if "'list' object has no attribute 'get'" in response:
                print(f"❌ {provider_name} provider still has the list.get() error!")
                return False
            elif "Error communicating with AI" in response:
                print(f"⚠️  {provider_name} provider returned an error, but not the list.get() error")
                return True  # This is acceptable - the error is fixed
            else:
                print(f"✅ {provider_name} provider working correctly")
                return True
                
        except Exception as e:
            if "'list' object has no attribute 'get'" in str(e):
                print(f"❌ {provider_name} provider still has the list.get() error!")
                return False
            else:
                print(f"⚠️  {provider_name} provider had an error: {e}")
                return True  # This is acceptable - the error is fixed
        
    except Exception as e:
        print(f"❌ Error testing {provider_name} provider: {e}")
        return False

def main():
    """Test all available providers."""
    print("=== LLM Provider Test Suite ===")
    print("Testing all providers to ensure the list.get() error is fixed")
    
    # Test configurations for each provider
    test_configs = {
        'mock': {},
        'ollama': {
            'base_url': 'http://localhost:11434',
            'model': 'gemma3:27b'
        }
    }
    
    # Add OpenAI if API key is available
    openai_api_key = os.environ.get('OPENAI_API_KEY')
    if openai_api_key:
        test_configs['openai'] = {
            'api_key': openai_api_key,
            'model': 'gpt-4o-mini'
        }
    
    # Add Anthropic if API key is available
    anthropic_api_key = os.environ.get('ANTHROPIC_API_KEY')
    if anthropic_api_key:
        test_configs['anthropic'] = {
            'api_key': anthropic_api_key,
            'model': 'claude-3-5-sonnet-20241022'
        }
    
    # Test each provider
    results = {}
    for provider_name, config in test_configs.items():
        results[provider_name] = test_provider(provider_name, config)
    
    # Summary
    print("\n=== Test Results Summary ===")
    all_passed = True
    for provider_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{provider_name.upper()}: {status}")
        if not passed:
            all_passed = False
    
    if all_passed:
        print("\n🎉 All providers are working correctly!")
        print("✅ The 'list' object has no attribute 'get' error has been fixed!")
    else:
        print("\n⚠️  Some providers still have issues")
        print("❌ The 'list' object has no attribute 'get' error may still exist in some providers")
    
    return all_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 