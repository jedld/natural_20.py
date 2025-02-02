from PIL import Image, ImageDraw
import numpy as np
import random

def generate_texture(material, width, height):
    """Generates a simple texture based on the material type."""
    if material == 'wood':
        base_color = (139, 69, 19, 255)  # Brown
        grain_color = (160, 82, 45, 255)  # Slightly lighter brown
        texture = np.full((height, width, 4), base_color, dtype=np.uint8)
        for x in range(width):
            if random.random() > 0.8:
                for y in range(height):
                    if random.random() > 0.5:
                        texture[y, x] = grain_color
    
    elif material == 'metal':
        base_color = (169, 169, 169, 255)  # Dark Gray
        highlight_color = (192, 192, 192, 255)  # Lighter gray
        texture = np.full((height, width, 4), base_color, dtype=np.uint8)
        for x in range(width):
            if random.random() > 0.9:
                for y in range(height):
                    if random.random() > 0.7:
                        texture[y, x] = highlight_color
    
    elif material == 'stone':
        base_color = (112, 128, 144, 255)  # Slate Gray
        highlight_color = (169, 169, 169, 255)  # Lighter gray
        texture = np.full((height, width, 4), base_color, dtype=np.uint8)
        for y in range(height):
            for x in range(width):
                if random.random() > 0.95:
                    texture[y, x] = highlight_color
    else:
        raise ValueError("Unsupported material. Choose from 'wood', 'metal', or 'stone'.")
    
    return Image.fromarray(texture)

def generate_door(material='wood', width=64, height=16):
    """Generates a procedural door PNG image based on the given material."""
    door_texture = generate_texture(material, width, height)
    
    # Create an image with transparency
    door_image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    door_image.paste(door_texture, (0, 0))
    
    draw = ImageDraw.Draw(door_image)
    
    # Draw simple door details (frame)
    draw.rectangle([(1, 1), (width-2, height-2)], outline=(50, 30, 10, 255), width=2)
    
    # Draw a small handle (golden)
    draw.ellipse([(width - 10, height // 2 - 2), (width - 8, height // 2 + 2)], fill=(218, 165, 32, 255))
    
    return door_image

def save_door_image(material, filename="door.png"):
    """Saves the generated door image as a PNG file."""
    door = generate_door(material)
    door.save(filename, "PNG")
    print(f"Saved {filename} with {material} texture.")

# Example usage:
if __name__ == "__main__":
    save_door_image("wood", "wood_door.png")
    save_door_image("metal", "metal_door.png")
    save_door_image("stone", "stone_door.png")
