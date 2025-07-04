#!/usr/bin/env python3
"""
Simple test script to verify CORS configuration from environment variables.
"""

import os
import sys
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('werkzeug')

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

def get_allowed_origins():
    """Get allowed origins from environment variables or use defaults."""
    
    # Check for explicit CORS origins configuration
    cors_origins = os.environ.get('CORS_ORIGINS')
    if cors_origins:
        # Parse comma-separated list of origins
        origins = [origin.strip() for origin in cors_origins.split(',') if origin.strip()]
        logger.info(f"Using CORS origins from environment: {origins}")
        return origins
    
    # Determine environment
    is_aws = os.environ.get('AWS_ENVIRONMENT', 'false').lower() == 'true'
    is_production = os.environ.get('FLASK_ENV', 'development') == 'production'
    
    # Fallback to environment-based defaults
    if is_aws or is_production:
        # In AWS/production, allow the ALB domain and any subdomains
        default_origins = [
            "http://natural20-alb-1402295348.us-east-1.elb.amazonaws.com",
            "https://natural20-alb-1402295348.us-east-1.elb.amazonaws.com",
            "*"  # Fallback to allow all origins in production
        ]
    else:
        # In local development, allow localhost origins
        default_origins = [
            "http://localhost:5000", 
            "http://127.0.0.1:5000", 
            "http://localhost:5001", 
            "http://127.0.0.1:5001"
        ]
    
    logger.info(f"Using default CORS origins for {'production' if (is_aws or is_production) else 'development'}: {default_origins}")
    return default_origins

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
            # Get the allowed origins
            allowed_origins = get_allowed_origins()
            
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
    print("  python test_cors_simple.py")

if __name__ == "__main__":
    main() 