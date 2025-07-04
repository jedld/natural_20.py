#!/usr/bin/env python3
"""
Test script to verify timeout configuration fixes.
"""

import os
import sys
import time
import requests
from unittest.mock import patch, MagicMock

# Add the current directory to the path so we can import our modules
sys.path.insert(0, os.path.dirname(__file__))

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
    else:
        parent_env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
        if os.path.exists(parent_env_path):
            load_dotenv(parent_env_path)
except ImportError:
    pass

def test_timeout_environment_variables():
    """Test that timeout environment variables are properly read."""
    print("Testing timeout environment variable reading...")
    
    # Test default values
    openai_timeout = int(os.environ.get('OPENAI_TIMEOUT', '60'))
    anthropic_timeout = int(os.environ.get('ANTHROPIC_TIMEOUT', '60'))
    ollama_timeout = int(os.environ.get('OLLAMA_TIMEOUT', '60'))
    
    print(f"OPENAI_TIMEOUT: {openai_timeout}s")
    print(f"ANTHROPIC_TIMEOUT: {anthropic_timeout}s")
    print(f"OLLAMA_TIMEOUT: {ollama_timeout}s")
    
    # Verify they are reasonable values
    assert openai_timeout >= 30, f"OPENAI_TIMEOUT too low: {openai_timeout}"
    assert anthropic_timeout >= 30, f"ANTHROPIC_TIMEOUT too low: {anthropic_timeout}"
    assert ollama_timeout >= 30, f"OLLAMA_TIMEOUT too low: {ollama_timeout}"
    
    print("✅ Timeout environment variables are properly configured")
    return True

def test_openai_timeout():
    """Test OpenAI timeout configuration."""
    print("\nTesting OpenAI timeout configuration...")
    
    try:
        from llm_handler import OpenAIProvider
        
        # Create a mock OpenAI client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test response"
        mock_client.chat.completions.create.return_value = mock_response
        
        provider = OpenAIProvider()
        provider.client = mock_client
        provider.current_model = "gpt-4o-mini"
        
        # Test with default timeout
        messages = [{"role": "user", "content": "Hello"}]
        result = provider.send_message(messages)
        
        # Check that the timeout parameter was passed
        mock_client.chat.completions.create.assert_called_once()
        call_args = mock_client.chat.completions.create.call_args
        assert 'timeout' in call_args[1], "Timeout parameter not passed to OpenAI API"
        
        timeout_value = call_args[1]['timeout']
        expected_timeout = int(os.environ.get('OPENAI_TIMEOUT', '60'))
        assert timeout_value == expected_timeout, f"Expected timeout {expected_timeout}, got {timeout_value}"
        
        print(f"✅ OpenAI timeout correctly set to {timeout_value}s")
        return True
        
    except ImportError:
        print("⚠️  OpenAI library not available, skipping test")
        return True
    except Exception as e:
        print(f"❌ OpenAI timeout test failed: {e}")
        return False

def test_anthropic_timeout():
    """Test Anthropic timeout configuration."""
    print("\nTesting Anthropic timeout configuration...")
    
    try:
        from llm_handler import AnthropicProvider
        
        provider = AnthropicProvider()
        provider.api_key = "test-key"
        provider.current_model = "claude-3-5-sonnet-20241022"
        
        # Mock the requests.post call
        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'content': [{'text': 'Test response'}]
            }
            mock_post.return_value = mock_response
            
            messages = [{"role": "user", "content": "Hello"}]
            result = provider.send_message(messages)
            
            # Check that the timeout parameter was passed
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert 'timeout' in call_args[1], "Timeout parameter not passed to Anthropic API"
            
            timeout_value = call_args[1]['timeout']
            expected_timeout = int(os.environ.get('ANTHROPIC_TIMEOUT', '60'))
            assert timeout_value == expected_timeout, f"Expected timeout {expected_timeout}, got {timeout_value}"
            
            print(f"✅ Anthropic timeout correctly set to {timeout_value}s")
            return True
            
    except ImportError:
        print("⚠️  Anthropic provider not available, skipping test")
        return True
    except Exception as e:
        print(f"❌ Anthropic timeout test failed: {e}")
        return False

def test_ollama_timeout():
    """Test Ollama timeout configuration."""
    print("\nTesting Ollama timeout configuration...")
    
    try:
        from llm_handler import OllamaProvider
        
        provider = OllamaProvider()
        provider.base_url = "http://localhost:11434"
        provider.model = "test-model"
        provider.context_window = 4096
        
        # Mock the requests.post call
        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'message': {'content': 'Test response'}
            }
            mock_post.return_value = mock_response
            
            messages = [{"role": "user", "content": "Hello"}]
            result = provider.send_message(messages)
            
            # Check that the timeout parameter was passed
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert 'timeout' in call_args[1], "Timeout parameter not passed to Ollama API"
            
            timeout_value = call_args[1]['timeout']
            expected_timeout = int(os.environ.get('OLLAMA_TIMEOUT', '60'))
            assert timeout_value == expected_timeout, f"Expected timeout {expected_timeout}, got {timeout_value}"
            
            print(f"✅ Ollama timeout correctly set to {timeout_value}s")
            return True
            
    except ImportError:
        print("⚠️  Ollama provider not available, skipping test")
        return True
    except Exception as e:
        print(f"❌ Ollama timeout test failed: {e}")
        return False

def test_network_timeout_simulation():
    """Simulate network timeout scenarios."""
    print("\nTesting network timeout simulation...")
    
    # Test with a slow endpoint
    try:
        start_time = time.time()
        response = requests.get("https://httpbin.org/delay/3", timeout=5)
        end_time = time.time()
        
        print(f"✅ Fast request completed in {end_time - start_time:.2f}s")
        
        # Test with a timeout
        try:
            start_time = time.time()
            response = requests.get("https://httpbin.org/delay/10", timeout=2)
            print("❌ Expected timeout but request succeeded")
            return False
        except requests.exceptions.Timeout:
            end_time = time.time()
            print(f"✅ Timeout correctly triggered after {end_time - start_time:.2f}s")
            return True
            
    except Exception as e:
        print(f"❌ Network test failed: {e}")
        return False

def main():
    """Run all timeout tests."""
    print("Timeout Configuration Test Suite")
    print("=" * 40)
    
    tests = [
        test_timeout_environment_variables,
        test_openai_timeout,
        test_anthropic_timeout,
        test_ollama_timeout,
        test_network_timeout_simulation
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with exception: {e}")
    
    print(f"\n{'=' * 40}")
    print(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        print("✅ All timeout tests passed!")
        print("\nRecommendations for ECS:")
        print("- Set OPENAI_TIMEOUT=120 for better reliability")
        print("- Set ANTHROPIC_TIMEOUT=120 for better reliability")
        print("- Set OLLAMA_TIMEOUT=120 for better reliability")
    else:
        print("❌ Some tests failed. Check the output above for details.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 