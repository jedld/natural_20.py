#!/usr/bin/env python3
"""
Test script for object spawner functionality
"""

import requests
import json

# Test the available_objects endpoint
def test_available_objects():
    """Test getting available objects"""
    try:
        # Note: You'll need to run this with proper authentication/session
        response = requests.get('http://localhost:5000/available_objects')
        
        if response.status_code == 200:
            data = response.json()
            print("✓ Available objects endpoint working")
            print(f"Found {len(data.get('objects', []))} objects")
            
            # Print first few objects
            for obj in data.get('objects', [])[:5]:
                print(f"  - {obj['name']} (ID: {obj['id']})")
        else:
            print(f"✗ Available objects endpoint failed: {response.status_code}")
            print(response.text)
            
    except Exception as e:
        print(f"✗ Error testing available objects: {e}")

def test_spawn_object():
    """Test spawning an object"""
    try:
        # Test data
        test_data = {
            'object_type': 'barrel',
            'x': 5,
            'y': 5
        }
        
        response = requests.post(
            'http://localhost:5000/spawn_object',
            json=test_data,
            headers={'Content-Type': 'application/json'}
        )
        
        if response.status_code == 200:
            data = response.json()
            print("✓ Spawn object endpoint working")
            print(f"Spawned object with entity_uid: {data.get('entity_uid')}")
        else:
            print(f"✗ Spawn object endpoint failed: {response.status_code}")
            print(response.text)
            
    except Exception as e:
        print(f"✗ Error testing spawn object: {e}")

if __name__ == "__main__":
    print("Testing Object Spawner Functionality")
    print("="*40)
    print("Note: Make sure the webapp is running and you're logged in as DM")
    print()
    
    test_available_objects()
    print()
    test_spawn_object()
