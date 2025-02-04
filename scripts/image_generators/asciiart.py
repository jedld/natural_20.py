#!/usr/bin/env python3
import pyfiglet

def generate_ascii_art(text, font="standard"):
    """
    Generate ASCII art from the given text using the specified font.
    
    :param text: The text to convert.
    :param font: The font to use (default is "standard").
    :return: A string containing the ASCII art.
    """
    return pyfiglet.figlet_format(text, font=font)

def main():
    # Prompt the user to input the text
    text = input("Enter text to convert to ASCII art: ")
    
    # Ask the user if they want to specify a font
    font = input("Enter a font (or press Enter to use 'standard'): ").strip() or "standard"
    
    try:
        ascii_art = generate_ascii_art(text, font)
        print("\nGenerated ASCII Art:\n")
        print(ascii_art)
    except Exception as e:
        print("An error occurred while generating ASCII art:", e)

if __name__ == '__main__':
    main()
