#!/usr/bin/env python3
"""
Spell Scroll Maker - A tool to overlay spell images on a scroll background.

This script takes a spell image and overlays it on a background image (default: spell_scroll.png).
It supports scaling the target image before overlaying it on the background.
"""

import os
import argparse
from PIL import Image


def overlay_images(background_path, target_path, output_path, scale_factor=1.0, position=None):
    """
    Overlay a target image on a background image with optional scaling.
    
    Args:
        background_path (str): Path to the background image
        target_path (str): Path to the target image to overlay
        output_path (str): Path where the merged image will be saved
        scale_factor (float): Factor to scale the target image (1.0 = original size)
        position (tuple): Optional (x, y) position to place the target image. 
                         If None, centers the image.
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Open the background image
        background = Image.open(background_path)
        
        # Open the target image
        target = Image.open(target_path)
        
        # Ensure the target image has an alpha channel
        if target.mode != 'RGBA':
            target = target.convert('RGBA')
        
        # Scale the target image if needed
        if scale_factor != 1.0:
            new_width = int(target.width * scale_factor)
            new_height = int(target.height * scale_factor)
            target = target.resize((new_width, new_height), Image.LANCZOS)
        
        # Create a copy of the background to work with
        result = background.copy()
        
        # Ensure the result image has an alpha channel
        if result.mode != 'RGBA':
            result = result.convert('RGBA')
        
        # Calculate position to center the target if position is not specified
        if position is None:
            x = (background.width - target.width) // 2
            y = (background.height - target.height) // 2
        else:
            x, y = position
        
        # Create a new image with alpha channel for compositing
        composite = Image.new('RGBA', result.size, (0, 0, 0, 0))
        composite.paste(target, (x, y))
        
        # Composite the images
        result = Image.alpha_composite(result, composite)
        
        # Convert back to RGB if needed for saving as PNG
        if result.mode == 'RGBA':
            result = result.convert('RGB')
        
        # Save the result
        result.save(output_path, "PNG")
        print(f"Successfully created {output_path}")
        return True
    
    except Exception as e:
        print(f"Error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Overlay a spell image on a scroll background")
    parser.add_argument("target_image", help="Path to the spell image to overlay")
    parser.add_argument("--background", "-b", default="spell_scroll.png", 
                        help="Path to the background image (default: spell_scroll.png)")
    parser.add_argument("--output", "-o", default="output.png", 
                        help="Path for the output image (default: output.png)")
    parser.add_argument("--scale", "-s", type=float, default=1.0, 
                        help="Scale factor for the target image (default: 1.0)")
    parser.add_argument("--position", "-p", type=int, nargs=2, metavar=("X", "Y"),
                        help="Optional X Y position to place the target image")
    
    args = parser.parse_args()
    
    # Check if files exist
    if not os.path.exists(args.target_image):
        print(f"Error: Target image '{args.target_image}' not found")
        return
    
    if not os.path.exists(args.background):
        print(f"Error: Background image '{args.background}' not found")
        return
    
    # Process the images
    overlay_images(args.background, args.target_image, args.output, args.scale, args.position)


if __name__ == "__main__":
    main()
