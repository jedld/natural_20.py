#!/usr/bin/env python3
"""
Test script to verify LLM configuration from environment variables.
Run this script to check if your LLM provider is configured correctly.
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

def test_llm_configuration():
    """Test the LLM configuration from environment variables."""
    
    print("=== LLM Configuration Test ===\n")
    
    # Check LLM provider
    llm_provider = os.environ.get('LLM_PROVIDER', 'ollama').lower()
    print(f"LLM Provider: {llm_provider}")
    
    if llm_provider == 'openai':
        print("\n--- OpenAI Configuration ---")
        api_key = os.environ.get('OPENAI_API_KEY')
        model = os.environ.get('OPENAI_MODEL', 'gpt-4o-mini')
        base_url = os.environ.get('OPENAI_BASE_URL', 'https://api.openai.com/v1')
        
        print(f"API Key: {'✓ Set' if api_key else '✗ Not set'}")
        print(f"Model: {model}")
        print(f"Base URL: {base_url}")
        
        if not api_key:
            print("⚠️  Warning: OPENAI_API_KEY is required for OpenAI provider")
            
    elif llm_provider == 'anthropic':
        print("\n--- Anthropic Configuration ---")
        api_key = os.environ.get('ANTHROPIC_API_KEY')
        model = os.environ.get('ANTHROPIC_MODEL', 'claude-3-5-sonnet-20241022')
        
        print(f"API Key: {'✓ Set' if api_key else '✗ Not set'}")
        print(f"Model: {model}")
        
        if not api_key:
            print("⚠️  Warning: ANTHROPIC_API_KEY is required for Anthropic provider")
            
    elif llm_provider == 'ollama':
        print("\n--- Ollama Configuration ---")
        base_url = os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434')
        model = os.environ.get('OLLAMA_MODEL', 'gemma3:27b')
        
        print(f"Base URL: {base_url}")
        print(f"Model: {model}")
        
        # Test Ollama connection
        try:
            import requests
            response = requests.get(f"{base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                print("✓ Ollama server is reachable")
                models = response.json().get('models', [])
                model_names = [m['name'] for m in models]
                if model in model_names:
                    print(f"✓ Model '{model}' is available")
                else:
                    print(f"⚠️  Model '{model}' not found in available models: {model_names[:5]}...")
            else:
                print(f"✗ Ollama server returned status code: {response.status_code}")
        except Exception as e:
            print(f"✗ Cannot connect to Ollama server: {e}")
            
    elif llm_provider == 'mock':
        print("\n--- Mock Configuration ---")
        print("✓ Mock provider configured (for testing)")
        
    else:
        print(f"\n⚠️  Unknown provider: {llm_provider}")
        print("Available providers: openai, anthropic, ollama, mock")
    
    print("\n=== Test Complete ===")
    
    # Try to initialize the LLM handler
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
                    print("⚠️  OPENAI_API_KEY not set, LLM features will be disabled")
                    return llm_handler
                
                config = {
                    'api_key': api_key,
                    'model': model
                }
                if base_url:
                    config['base_url'] = base_url
                    
                success = llm_handler.initialize_provider('openai', config)
                if success:
                    print("✓ OpenAI provider initialized successfully")
                else:
                    print("✗ Failed to initialize OpenAI provider")
                    
            elif llm_provider == 'anthropic':
                api_key = os.environ.get('ANTHROPIC_API_KEY')
                model = os.environ.get('ANTHROPIC_MODEL', 'claude-3-5-sonnet-20241022')
                
                if not api_key:
                    print("⚠️  ANTHROPIC_API_KEY not set, LLM features will be disabled")
                    return llm_handler
                
                config = {
                    'api_key': api_key,
                    'model': model
                }
                
                success = llm_handler.initialize_provider('anthropic', config)
                if success:
                    print("✓ Anthropic provider initialized successfully")
                else:
                    print("✗ Failed to initialize Anthropic provider")
                    
            elif llm_provider == 'ollama':
                base_url = os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434')
                model = os.environ.get('OLLAMA_MODEL', 'gemma3:27b')
                
                config = {
                    'base_url': base_url,
                    'model': model
                }
                
                success = llm_handler.initialize_provider('ollama', config)
                if success:
                    print("✓ Ollama provider initialized successfully")
                else:
                    print("✗ Failed to initialize Ollama provider")
                    
            else:
                print(f"⚠️  Unknown LLM provider: {llm_provider}, using mock provider")
                llm_handler.initialize_provider('mock', {})
            
            return llm_handler
        
        print("\n--- Testing LLM Handler Initialization ---")
        llm_handler = initialize_llm_from_env()
        
        # Test sending a simple message
        if llm_handler.current_provider:
            print("✓ LLM handler initialized with provider")
            provider_info = llm_handler.get_provider_info()
            print(f"  Provider: {provider_info.get('provider_type', 'unknown')}")
            print(f"  Model: {provider_info.get('current_model', 'unknown')}")
        else:
            print("✗ LLM handler initialization failed")
            
    except ImportError as e:
        print(f"✗ Could not import LLM handler: {e}")
    except Exception as e:
        print(f"✗ Error during LLM handler test: {e}")

if __name__ == "__main__":
    test_llm_configuration() 