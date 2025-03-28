#!/usr/bin/env python3
import argparse
from PIL import Image, ImageDraw

def create_dismiss_version(image_path, thickness_percent=3):
    # Open the image
    img = Image.open(image_path)
    
    # Create a copy of the image to draw on
    draw = ImageDraw.Draw(img)
    
    # Get image dimensions
    width, height = img.size
    
    # Calculate line thickness based on image size and percentage
    thickness = max(1, int(min(width, height) * (thickness_percent / 100)))
    
    # Draw X
    # First diagonal line
    draw.line([(0, 0), (width, height)], fill='red', width=thickness)
    # Second diagonal line
    draw.line([(width, 0), (0, height)], fill='red', width=thickness)
    
    # Create output filename by adding '_dismiss' before the extension
    output_path = image_path.rsplit('.', 1)[0] + '_dismiss.' + image_path.rsplit('.', 1)[1]
    
    # Save the modified image
    img.save(output_path)
    print(f"Created dismiss version: {output_path}")

def main():
    parser = argparse.ArgumentParser(description='Create a dismiss version of an image by drawing an X over it')
    parser.add_argument('image_path', help='Path to the input image')
    parser.add_argument('--thickness', type=float, default=3,
                      help='Thickness of the X as a percentage of image size (default: 3)')
    
    args = parser.parse_args()
    create_dismiss_version(args.image_path, args.thickness)

if __name__ == "__main__":
    main() 