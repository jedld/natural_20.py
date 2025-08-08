#!/usr/bin/env python3
"""
Example script demonstrating the wall/door tile generator.
Generates several example tiles with different configurations.
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from generate_wall_door_tile import create_wall_door_tile

def generate_examples():
    """Generate example tiles to demonstrate the utility."""
    
    # Create output directory
    output_dir = "example_tiles"
    os.makedirs(output_dir, exist_ok=True)
    
    examples = [
        {
            "name": "corner_room_top_left",
            "walls": ["top", "left"],
            "door": None,
            "description": "Corner room with walls on top and left"
        },
        {
            "name": "corridor_horizontal",
            "walls": ["top", "bottom"],
            "door": None,
            "description": "Horizontal corridor with walls on top and bottom"
        },
        {
            "name": "room_with_door_top",
            "walls": ["top", "left", "right"],
            "door": "top",
            "description": "Room with walls on three sides and door on top"
        },
        {
            "name": "room_with_door_left",
            "walls": ["top", "left", "bottom"],
            "door": "left",
            "description": "Room with walls on three sides and door on left"
        },
        {
            "name": "full_room_with_door",
            "walls": ["top", "bottom", "left", "right"],
            "door": "bottom",
            "description": "Enclosed room with door on bottom"
        },
        {
            "name": "single_wall_top",
            "walls": ["top"],
            "door": None,
            "description": "Single wall on top"
        },
        {
            "name": "t_junction",
            "walls": ["left", "right", "bottom"],
            "door": None,
            "description": "T-junction with walls on left, right, and bottom"
        },
        {
            "name": "large_room_with_door",
            "walls": ["top", "bottom", "left", "right"],
            "door": "right",
            "size": 128,
            "door_width": 40,
            "description": "Large room (128x128) with wide door"
        }
    ]
    
    print("Generating example tiles...")
    print("=" * 50)
    
    for example in examples:
        output_path = os.path.join(output_dir, f"{example['name']}.png")
        
        create_wall_door_tile(
            size=example.get('size', 64),
            walls=example['walls'],
            door_location=example['door'],
            door_width=example.get('door_width', 20),
            wall_thickness=10,
            output_path=output_path
        )
        
        print(f"✓ {example['name']}.png - {example['description']}")
    
    print("=" * 50)
    print(f"All example tiles generated in '{output_dir}' directory!")
    print("\nYou can view the generated tiles to see different configurations.")


if __name__ == '__main__':
    generate_examples()
