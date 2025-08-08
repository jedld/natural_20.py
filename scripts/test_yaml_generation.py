#!/usr/bin/env python3
"""
Test script to demonstrate generating wall/door tiles from objects.yml files.
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from generate_wall_door_tile import generate_from_objects_yaml

def test_yaml_generation():
    """Test generating tiles from the test fixtures objects.yml file."""
    
    # Path to the test fixtures objects.yml file
    test_yaml_path = "../tests/fixtures/items/objects.yml"
    
    if not os.path.exists(test_yaml_path):
        print(f"Test YAML file not found: {test_yaml_path}")
        print("Please run this script from the scripts directory")
        return
    
    print("Testing YAML tile generation with test fixtures...")
    print("=" * 60)
    
    # Generate tiles from the YAML file
    generate_from_objects_yaml(
        yaml_file_path=test_yaml_path,
        output_dir="test_yaml_tiles",
        size=64,
        wall_thickness=10
    )
    
    print("\nTest completed! Check the 'test_yaml_tiles' directory for generated images.")

if __name__ == '__main__':
    test_yaml_generation()
