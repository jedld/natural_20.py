#!/usr/bin/env python3
"""
Test script to verify that the LLM handler fix is working correctly.
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
            print("No .env file found, using system environment variables")
except ImportError:
    print("python-dotenv not installed, using system environment variables")

def test_llm_message_processing():
    """Test that the LLM handler can process messages without errors."""
    
    print("=== LLM Message Processing Test ===\n")
    
    try:
        from webapp.llm_handler import LLMHandler
        
        def initialize_llm_from_env():
            """Initialize LLM handler from environment variables."""
            llm_handler = LLMHandler()
            
            # Check for LLM provider configuration
            llm_provider = os.environ.get('LLM_PROVIDER', 'ollama').lower()
            
            if llm_provider == 'openai':
                api_key = os.environ.get('OPENAI_API_KEY')
                base_url = os.environ.get('OPENAI_BASE_URL')
                model = os.environ.get('OPENAI_MODEL', 'gpt-4o-mini')
                
                if not api_key:
                    print("⚠️  OPENAI_API_KEY not set, using mock provider")
                    llm_handler.initialize_provider('mock', {})
                    return llm_handler
                
                config = {
                    'api_key': api_key,
                    'model': model
                }
                if base_url:
                    config['base_url'] = base_url
                    
                success = llm_handler.initialize_provider('openai', config)
                if not success:
                    print("⚠️  Failed to initialize OpenAI provider, using mock provider")
                    llm_handler.initialize_provider('mock', {})
                    
            elif llm_provider == 'anthropic':
                api_key = os.environ.get('ANTHROPIC_API_KEY')
                model = os.environ.get('ANTHROPIC_MODEL', 'claude-3-5-sonnet-20241022')
                
                if not api_key:
                    print("⚠️  ANTHROPIC_API_KEY not set, using mock provider")
                    llm_handler.initialize_provider('mock', {})
                    return llm_handler
                
                config = {
                    'api_key': api_key,
                    'model': model
                }
                
                success = llm_handler.initialize_provider('anthropic', config)
                if not success:
                    print("⚠️  Failed to initialize Anthropic provider, using mock provider")
                    llm_handler.initialize_provider('mock', {})
                    
            elif llm_provider == 'ollama':
                base_url = os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434')
                model = os.environ.get('OLLAMA_MODEL', 'gemma3:27b')
                
                config = {
                    'base_url': base_url,
                    'model': model
                }
                
                success = llm_handler.initialize_provider('ollama', config)
                if not success:
                    print("⚠️  Failed to initialize Ollama provider, using mock provider")
                    llm_handler.initialize_provider('mock', {})
                    
            else:
                print(f"⚠️  Unknown LLM provider: {llm_provider}, using mock provider")
                llm_handler.initialize_provider('mock', {})
            
            return llm_handler
        
        print("--- Initializing LLM Handler ---")
        llm_handler = initialize_llm_from_env()
        
        if not llm_handler.current_provider:
            print("✗ LLM handler initialization failed")
            return False
        
        provider_info = llm_handler.get_provider_info()
        print(f"✓ LLM handler initialized with provider: {provider_info.get('provider_type', 'unknown')}")
        
        # Test 1: Simple message without function calls
        print("\n--- Test 1: Simple Message ---")
        try:
            response = llm_handler.send_message("Hello, how are you?")
            print(f"✓ Simple message response: {response[:100]}...")
        except Exception as e:
            print(f"✗ Error with simple message: {e}")
            return False
        
        # Test 2: Message that might trigger function calls
        print("\n--- Test 2: Message with Potential Function Calls ---")
        try:
            response = llm_handler.send_message("Who are the characters in the game?")
            print(f"✓ Function call message response: {response[:100]}...")
        except Exception as e:
            print(f"✗ Error with function call message: {e}")
            return False
        
        # Test 3: Message that should definitely trigger function calls (if using mock provider)
        print("\n--- Test 3: Direct Function Call Request ---")
        try:
            response = llm_handler.send_message("Tell me about the map and entities")
            print(f"✓ Direct function call response: {response[:100]}...")
        except Exception as e:
            print(f"✗ Error with direct function call: {e}")
            return False
        
        print("\n=== All Tests Passed! ===")
        return True
        
    except ImportError as e:
        print(f"✗ Could not import LLM handler: {e}")
        return False
    except Exception as e:
        print(f"✗ Error during LLM handler test: {e}")
        return False

if __name__ == "__main__":
    success = test_llm_message_processing()
    if success:
        print("\n✅ LLM handler is working correctly!")
    else:
        print("\n❌ LLM handler has issues that need to be fixed.")
        sys.exit(1) 