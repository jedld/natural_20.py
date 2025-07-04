#!/usr/bin/env python3
"""
Test script to verify CORS configuration from environment variables.
"""

import os
import sys

# Add the parent directory to the path so we can import the app
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

def test_cors_configuration():
    """Test CORS configuration from environment variables."""
    print("=== CORS Configuration Test ===\n")
    
    # Test different scenarios
    test_cases = [
        {
            'name': 'No CORS_ORIGINS set (development)',
            'env_vars': {},
            'expected_behavior': 'Use default development origins'
        },
        {
            'name': 'No CORS_ORIGINS set (production)',
            'env_vars': {'FLASK_ENV': 'production', 'AWS_ENVIRONMENT': 'true'},
            'expected_behavior': 'Use default production origins'
        },
        {
            'name': 'CORS_ORIGINS set with custom domains',
            'env_vars': {'CORS_ORIGINS': 'https://myapp.com,https://www.myapp.com'},
            'expected_behavior': 'Use custom origins from environment'
        },
        {
            'name': 'CORS_ORIGINS set to wildcard',
            'env_vars': {'CORS_ORIGINS': '*'},
            'expected_behavior': 'Allow all origins'
        },
        {
            'name': 'CORS_ORIGINS with mixed protocols',
            'env_vars': {'CORS_ORIGINS': 'http://localhost:5000,https://myapp.com'},
            'expected_behavior': 'Use mixed protocol origins'
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"Test {i}: {test_case['name']}")
        print(f"Expected: {test_case['expected_behavior']}")
        
        # Set environment variables for this test
        original_env = {}
        for key, value in test_case['env_vars'].items():
            original_env[key] = os.environ.get(key)
            os.environ[key] = value
        
        try:
            # Import the app module to test the CORS configuration
            # We need to do this carefully to avoid running the full app
            import importlib.util
            spec = importlib.util.spec_from_file_location("app", "app.py")
            app_module = importlib.util.module_from_spec(spec)
            
            # Execute the module to get the CORS configuration
            with open("app.py", "r") as f:
                app_code = f.read()
            
            # Create a minimal execution environment
            exec_globals = {
                '__name__': '__main__',
                '__file__': 'app.py',
                'os': os,
                'logging': __import__('logging'),
                'Flask': __import__('flask').Flask,
                'SocketIO': __import__('flask_socketio').SocketIO,
                'Session': __import__('flask_session').Session,
                'CORS': __import__('flask_cors').CORS,
                'json': __import__('json'),
                'click': __import__('click'),
                'Image': __import__('PIL').Image,
                'importlib': __import__('importlib'),
                'requests': __import__('requests'),
                're': __import__('re'),
                'random': __import__('random'),
                'optparse': __import__('optparse'),
                'pdb': __import__('pdb'),
                'i18n': __import__('i18n'),
                'yaml': __import__('yaml'),
                'time': __import__('time'),
                'uuid': __import__('uuid'),
                'threading': __import__('threading'),
                'traceback': __import__('traceback'),
                'datetime': __import__('datetime'),
                'logging': __import__('logging'),
                'logger': __import__('logging').getLogger('werkzeug')
            }
            
            # Execute the app code up to the CORS configuration
            lines = app_code.split('\n')
            cors_config_lines = []
            for line in lines:
                cors_config_lines.append(line)
                if 'allowed_origins = get_allowed_origins()' in line:
                    break
            
            cors_config_code = '\n'.join(cors_config_lines)
            
            # Execute the CORS configuration code
            exec(cors_config_code, exec_globals)
            
            # Get the allowed origins
            allowed_origins = exec_globals.get('allowed_origins', [])
            
            print(f"Result: {allowed_origins}")
            
            # Validate the result
            if test_case['env_vars'].get('CORS_ORIGINS'):
                expected_origins = [origin.strip() for origin in test_case['env_vars']['CORS_ORIGINS'].split(',')]
                if allowed_origins == expected_origins:
                    print("✅ PASSED - Custom origins used correctly")
                else:
                    print(f"❌ FAILED - Expected {expected_origins}, got {allowed_origins}")
            else:
                # Check if defaults are used
                if allowed_origins:
                    print("✅ PASSED - Default origins used correctly")
                else:
                    print("❌ FAILED - No origins configured")
            
        except Exception as e:
            print(f"❌ ERROR - {e}")
        
        finally:
            # Restore original environment variables
            for key, value in original_env.items():
                if value is not None:
                    os.environ[key] = value
                else:
                    os.environ.pop(key, None)
        
        print()

def main():
    """Run the CORS configuration tests."""
    print("Testing CORS configuration from environment variables...\n")
    
    # Show current environment
    print("Current environment variables:")
    cors_origins = os.environ.get('CORS_ORIGINS')
    flask_env = os.environ.get('FLASK_ENV', 'development')
    aws_env = os.environ.get('AWS_ENVIRONMENT', 'false')
    
    print(f"  CORS_ORIGINS: {cors_origins or 'Not set'}")
    print(f"  FLASK_ENV: {flask_env}")
    print(f"  AWS_ENVIRONMENT: {aws_env}")
    print()
    
    # Run tests
    test_cors_configuration()
    
    print("=== Test Complete ===")
    print("\nTo test with different configurations:")
    print("  export CORS_ORIGINS='https://myapp.com,https://www.myapp.com'")
    print("  export FLASK_ENV=production")
    print("  export AWS_ENVIRONMENT=true")
    print("  python test_cors_config.py")

if __name__ == "__main__":
    main() 