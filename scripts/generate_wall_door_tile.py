#!/usr/bin/env python3
"""
Utility script to generate PNG images for walls and doors in D&D style.
Creates square tiles with walls on specified sides and doors at specified locations.
"""

import argparse
from PIL import Image, ImageDraw
import os
import yaml
import sys


def create_wall_door_tile(
    size=64,
    walls=None,
    door_location=None,
    door_width=20,
    wall_thickness=10,
    output_path="tile.png"
):
    """
    Generate a square PNG tile with walls and doors.
    
    Args:
        size (int): Dimension of the square image in pixels
        walls (list): List of wall positions ('top', 'bottom', 'left', 'right')
        door_location (str): Location of door ('top', 'bottom', 'left', 'right')
        door_width (int): Width of the door opening in pixels
        wall_thickness (int): Thickness of walls in pixels
        output_path (str): Path to save the generated PNG
    """
    if walls is None:
        walls = []
    
    # Create image with stone floor background
    img = Image.new('RGB', (size, size), color='#8B7355')  # Stone floor color
    draw = ImageDraw.Draw(img)
    
    # Add floor texture (simple pattern)
    for i in range(0, size, 8):
        for j in range(0, size, 8):
            # Add subtle stone tile lines
            if i > 0:
                draw.line([(i, 0), (i, size)], fill='#7A6B4F', width=1)
            if j > 0:
                draw.line([(0, j), (size, j)], fill='#7A6B4F', width=1)
    
    # Wall colors
    wall_color = '#4A4A4A'  # Dark stone gray
    wall_highlight = '#6A6A6A'  # Lighter gray for 3D effect
    wall_shadow = '#2A2A2A'  # Darker gray for shadows
    
    # Door colors
    door_color = '#8B4513'  # Saddle brown for wood
    door_highlight = '#A0522D'  # Lighter brown
    door_shadow = '#654321'  # Darker brown
    door_frame = '#2F2F2F'  # Dark frame
    
    # Draw walls
    wall_coords = {
        'top': [(0, 0), (size, wall_thickness)],
        'bottom': [(0, size - wall_thickness), (size, size)],
        'left': [(0, 0), (wall_thickness, size)],
        'right': [(size - wall_thickness, 0), (size, size)]
    }
    
    for wall in walls:
        if wall in wall_coords:
            x1, y1 = wall_coords[wall][0]
            x2, y2 = wall_coords[wall][1]
            
            # Draw main wall
            draw.rectangle([x1, y1, x2, y2], fill=wall_color)
            
            # Add 3D effect to walls
            if wall == 'top':
                # Highlight on top edge
                draw.line([(x1, y1), (x2, y1)], fill=wall_highlight, width=2)
                # Shadow on bottom edge
                draw.line([(x1, y2-1), (x2, y2-1)], fill=wall_shadow, width=1)
            elif wall == 'bottom':
                # Highlight on top edge
                draw.line([(x1, y1), (x2, y1)], fill=wall_highlight, width=1)
                # Shadow on bottom edge
                draw.line([(x1, y2-1), (x2, y2-1)], fill=wall_shadow, width=2)
            elif wall == 'left':
                # Highlight on left edge
                draw.line([(x1, y1), (x1, y2)], fill=wall_highlight, width=2)
                # Shadow on right edge
                draw.line([(x2-1, y1), (x2-1, y2)], fill=wall_shadow, width=1)
            elif wall == 'right':
                # Highlight on left edge
                draw.line([(x1, y1), (x1, y2)], fill=wall_highlight, width=1)
                # Shadow on right edge
                draw.line([(x2-1, y1), (x2-1, y2)], fill=wall_shadow, width=2)
    
    # Draw door if specified
    if door_location and door_location in walls:
        door_start = (size - door_width) // 2
        door_end = door_start + door_width
        
        if door_location == 'top':
            # Clear wall area for door
            draw.rectangle([door_start, 0, door_end, wall_thickness], fill=door_frame)
            # Draw door
            draw.rectangle([door_start + 2, 2, door_end - 2, wall_thickness - 2], fill=door_color)
            # Door panels (bigger)
            panel_width = (door_width - 10) // 2  # Increased spacing
            if panel_width > 2:  # Only draw panels if there's enough space
                draw.rectangle([door_start + 4, 3, door_start + 4 + panel_width, wall_thickness - 3], 
                             fill=door_highlight, outline=door_shadow)
                draw.rectangle([door_end - 4 - panel_width, 3, door_end - 4, wall_thickness - 3], 
                             fill=door_highlight, outline=door_shadow)
            # Door handle (bigger)
            handle_size = max(2, wall_thickness // 4)
            handle_x = door_start + door_width - 8
            draw.ellipse([handle_x, wall_thickness//2 - handle_size, handle_x + handle_size*2, wall_thickness//2 + handle_size], 
                        fill='#FFD700')
            
        elif door_location == 'bottom':
            # Clear wall area for door
            draw.rectangle([door_start, size - wall_thickness, door_end, size], fill=door_frame)
            # Draw door
            draw.rectangle([door_start + 2, size - wall_thickness + 2, door_end - 2, size - 2], fill=door_color)
            # Door panels (bigger)
            panel_width = (door_width - 10) // 2  # Increased spacing
            if panel_width > 2:  # Only draw panels if there's enough space
                draw.rectangle([door_start + 4, size - wall_thickness + 3, door_start + 4 + panel_width, size - 3], 
                             fill=door_highlight, outline=door_shadow)
                draw.rectangle([door_end - 4 - panel_width, size - wall_thickness + 3, door_end - 4, size - 3], 
                             fill=door_highlight, outline=door_shadow)
            # Door handle (bigger)
            handle_size = max(2, wall_thickness // 4)
            handle_x = door_start + door_width - 8
            draw.ellipse([handle_x, size - wall_thickness//2 - handle_size, handle_x + handle_size*2, size - wall_thickness//2 + handle_size], 
                        fill='#FFD700')
            
        elif door_location == 'left':
            # Clear wall area for door
            draw.rectangle([0, door_start, wall_thickness, door_end], fill=door_frame)
            # Draw door
            draw.rectangle([2, door_start + 2, wall_thickness - 2, door_end - 2], fill=door_color)
            # Door panels (bigger)
            panel_height = (door_width - 10) // 2  # Increased spacing
            if panel_height > 2:  # Only draw panels if there's enough space
                draw.rectangle([3, door_start + 4, wall_thickness - 3, door_start + 4 + panel_height], 
                             fill=door_highlight, outline=door_shadow)
                draw.rectangle([3, door_end - 4 - panel_height, wall_thickness - 3, door_end - 4], 
                             fill=door_highlight, outline=door_shadow)
            # Door handle (bigger)
            handle_size = max(2, wall_thickness // 4)
            handle_y = door_start + door_width - 8
            draw.ellipse([wall_thickness//2 - handle_size, handle_y, wall_thickness//2 + handle_size, handle_y + handle_size*2], 
                        fill='#FFD700')
            
        elif door_location == 'right':
            # Clear wall area for door
            draw.rectangle([size - wall_thickness, door_start, size, door_end], fill=door_frame)
            # Draw door
            draw.rectangle([size - wall_thickness + 2, door_start + 2, size - 2, door_end - 2], fill=door_color)
            # Door panels (bigger)
            panel_height = (door_width - 10) // 2  # Increased spacing
            if panel_height > 2:  # Only draw panels if there's enough space
                draw.rectangle([size - wall_thickness + 3, door_start + 4, size - 3, door_start + 4 + panel_height], 
                             fill=door_highlight, outline=door_shadow)
                draw.rectangle([size - wall_thickness + 3, door_end - 4 - panel_height, size - 3, door_end - 4], 
                             fill=door_highlight, outline=door_shadow)
            # Door handle (bigger)
            handle_size = max(2, wall_thickness // 4)
            handle_y = door_start + door_width - 8
            draw.ellipse([size - wall_thickness//2 - handle_size, handle_y, size - wall_thickness//2 + handle_size, handle_y + handle_size*2], 
                        fill='#FFD700')
    
    # Save the image
    img.save(output_path)
    print(f"Generated tile saved as: {output_path}")


def generate_from_objects_yaml(yaml_file_path, output_dir="generated_tiles", size=64, wall_thickness=10):
    """
    Generate wall/door tiles from an objects.yml file.
    
    Args:
        yaml_file_path (str): Path to the objects.yml file
        output_dir (str): Directory to save generated images
        size (int): Dimension of the square image in pixels
        wall_thickness (int): Thickness of walls in pixels
    """
    if not os.path.exists(yaml_file_path):
        print(f"Error: YAML file not found: {yaml_file_path}")
        return
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Load YAML file
    try:
        with open(yaml_file_path, 'r') as f:
            objects_data = yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading YAML file: {e}")
        return
    
    if not objects_data:
        print("Error: YAML file is empty or invalid")
        return
    
    generated_count = 0
    
    print(f"Processing objects from {yaml_file_path}...")
    print("=" * 60)
    
    for object_key, object_data in objects_data.items():
        if not isinstance(object_data, dict):
            continue
            
        item_class = object_data.get('item_class', '')
        
        # Check if this is a wall or door object we should process
        if item_class in ['DoorObjectWall', 'DoorObject', 'StoneWallDirectional']:
            border = object_data.get('border', [0, 0, 0, 0])
            door_pos = object_data.get('door_pos', None)
            
            # Convert border array to wall sides
            # border format: [top, right, bottom, left]
            walls = []
            if len(border) >= 4:
                if border[0]:  # top
                    walls.append('top')
                if border[1]:  # right
                    walls.append('right')
                if border[2]:  # bottom
                    walls.append('bottom')
                if border[3]:  # left
                    walls.append('left')
            
            # Convert door_pos to door location
            door_location = None
            if door_pos is not None:
                if door_pos == 0:
                    door_location = 'top'
                elif door_pos == 1:
                    door_location = 'right'
                elif door_pos == 2:
                    door_location = 'bottom'
                elif door_pos == 3:
                    door_location = 'left'
            
            # For DoorObjectWall, ensure the door location has a wall
            # (doors need walls to be placed on)
            if item_class == 'DoorObjectWall' and door_location:
                if door_location not in walls:
                    walls.append(door_location)
            

            
            output_filename = f"{object_key}.png"
            output_path = os.path.join(output_dir, output_filename)
            
            # Determine door width based on size (make doors bigger)
            door_width = max(24, size // 3)  # Increased from size//4 to size//3, minimum 24px
            
            try:
                create_wall_door_tile(
                    size=size,
                    walls=walls,
                    door_location=door_location if item_class == 'DoorObjectWall' else None,
                    door_width=door_width,
                    wall_thickness=wall_thickness,
                    output_path=output_path
                )
                
                object_name = object_data.get('name', object_key)
                print(f"✓ {output_filename} - {object_name}")
                generated_count += 1
                
            except Exception as e:
                print(f"✗ Failed to generate {output_filename}: {e}")
    
    print("=" * 60)
    print(f"Generated {generated_count} tiles in '{output_dir}' directory!")


def main():
    parser = argparse.ArgumentParser(description='Generate D&D style wall and door tiles')
    parser.add_argument('--size', type=int, default=64, 
                       help='Size of the square image in pixels (default: 64)')
    parser.add_argument('--walls', nargs='*', 
                       choices=['top', 'bottom', 'left', 'right'],
                       help='Locations of walls (e.g., --walls top left)')
    parser.add_argument('--door', choices=['top', 'bottom', 'left', 'right'],
                       help='Location of door (must be on a wall)')
    parser.add_argument('--door-width', type=int, default=32,
                       help='Width of the door opening in pixels (default: 32)')
    parser.add_argument('--wall-thickness', type=int, default=10,
                       help='Thickness of walls in pixels (default: 10)')
    parser.add_argument('--output', type=str, default='tile.png',
                       help='Output filename (default: tile.png)')
    parser.add_argument('--yaml', type=str,
                       help='Path to objects.yml file to auto-generate tiles from')
    parser.add_argument('--output-dir', type=str, default='generated_tiles',
                       help='Output directory for auto-generated tiles (default: generated_tiles)')
    
    args = parser.parse_args()
    
    # If YAML file is provided, generate from YAML
    if args.yaml:
        generate_from_objects_yaml(
            yaml_file_path=args.yaml,
            output_dir=args.output_dir,
            size=args.size,
            wall_thickness=args.wall_thickness
        )
        return
    
    # Validate that door is on a wall
    if args.door and (not args.walls or args.door not in args.walls):
        print("Error: Door must be placed on an existing wall")
        return
    
    # Validate door width
    if args.door_width >= args.size - args.wall_thickness:
        print("Error: Door width too large for the tile size")
        return
    
    create_wall_door_tile(
        size=args.size,
        walls=args.walls or [],
        door_location=args.door,
        door_width=args.door_width,
        wall_thickness=args.wall_thickness,
        output_path=args.output
    )


if __name__ == '__main__':
    main()
