#!/bin/bash
# This script resizes all PNG images in the specified assets folders
# to 75x75 pixels and optimizes them for the web.
# It uses ImageMagick's convert tool and optipng for optimization.
#
# Usage:
#   ./optimize_images.sh [folders_file]
#
# The folders file should contain one path per line.
# If no file is specified, it defaults to "../static/items".

# If a folders file is provided, read folder paths from it.
if [ "$#" -ne 1 ]; then
    echo "Usage: $0 [folders_file]"
    exit 1
fi

FOLDER_FILE="$1"
if [ ! -f "$FOLDER_FILE" ]; then
    echo "Error: File not found at $FOLDER_FILE"
    exit 1
fi

# Read folders from the file (ignoring empty lines)
FOLDERS=()
while IFS= read -r line || [ -n "$line" ]; do
    [ -n "$line" ] && FOLDERS+=("$line")
done < "$FOLDER_FILE"

# Loop through each specified folder
for ASSETS_DIR in "${FOLDERS[@]}"; do
    echo "Processing folder: $ASSETS_DIR"

    # Check if the assets folder exists
    if [ ! -d "$ASSETS_DIR" ]; then
        echo "Error: Assets folder not found at $ASSETS_DIR"
        continue
    fi

    # Loop through all PNG images in the assets folder
    for img in "$ASSETS_DIR"/*.png; do
        # Skip if no PNG files are found
        [ -e "$img" ] || continue
        
        echo "Optimizing image: $img"
        
        # Define output file (adds a "-optimized" suffix before the extension)
        base=$(basename "$img" .png)
        out="$ASSETS_DIR/${base}-optimized.png"
        
        # Resize and crop image to exactly 75x75 px:
        # -resize 75x75^ scales the image while preserving aspect ratio until the smaller side fits 75px
        # -gravity center -extent 75x75 crops the centered area to 75x75
        convert "$img" -resize 75x75^ -gravity center -extent 75x75 "$out"
        
        # Further optimize the image with optipng (level 7 optimization)
        optipng -o7 "$out"
    done

    echo "Completed optimization for folder: $ASSETS_DIR"
done

echo "Image optimization completed."