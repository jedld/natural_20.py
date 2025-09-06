#!/bin/bash
# Resize and optimize PNG images in one or more asset folders.
# - Supports per-folder target size via folders.txt (e.g., "../static/spells 75x75").
# - Default size is 75x75; you can override with a 2nd CLI arg (e.g., "./optimize_images.sh folders.txt 128x128").
# - Uses ImageMagick (convert) and optipng.
#
# Usage:
#   ./optimize_images.sh [folders_file] [default_size]
#
# Examples:
#   ./optimize_images.sh                       # uses ./folders.txt and 75x75
#   ./optimize_images.sh folders.txt 128x128   # uses 128x128 when a line doesn't specify a size
#
# folders.txt format:
#   One entry per line. Optional size after the path, separated by whitespace.
#     ../static/spells 75x75
#     ../static/actions 128x128
#   Lines beginning with '#' are comments.

# Set default folder file if none is provided
FOLDER_FILE="folders.txt"
DEFAULT_SIZE="75x75"

# Args: [folders_file] [default_size]
if [ "$#" -ge 1 ] && [ -n "$1" ]; then
    FOLDER_FILE="$1"
fi
if [ "$#" -ge 2 ] && [ -n "$2" ]; then
    DEFAULT_SIZE="$2"
fi

# Check if the folder file exists
if [ ! -f "$FOLDER_FILE" ]; then
    echo "Error: File not found at $FOLDER_FILE"
    exit 1
fi

# Process each line: "<folder> [<size>]"
while IFS= read -r line || [ -n "$line" ]; do
    # Skip empty and comment lines
    if [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]]; then
        continue
    fi

    # Read folder and optional size (whitespace separated)
    folder_path=""
    folder_size=""
    # shellcheck disable=SC2086
    read -r folder_path folder_size <<< "$line"

    # Validate/assign size
    if [[ -z "$folder_size" || ! "$folder_size" =~ ^[0-9]+x[0-9]+$ ]]; then
        folder_size="$DEFAULT_SIZE"
    fi

    echo "Processing folder: $folder_path (size: $folder_size)"

    # Check if the assets folder exists
    if [ ! -d "$folder_path" ]; then
        echo "Error: Assets folder not found at $folder_path"
        continue
    fi

    # Loop through all PNG images in the assets folder
    shopt -s nullglob
    for img in "$folder_path"/*.png; do
        echo "Optimizing image: $img"

        # Define output file (adds a "-optimized" suffix before the extension)
        base=$(basename "$img" .png)
        out="$folder_path/${base}-optimized.png"

        # Resize and crop image to the requested size (e.g., 75x75 or 128x128):
        # -resize <WxH>^ preserves aspect ratio until the smaller side fits
        # -gravity center + -background none + -extent <WxH> crops to exact size with transparency preserved
        convert "$img" -resize "${folder_size}^" -gravity center -background none -extent "$folder_size" "$out"

        # Further optimize the image with optipng (level 7 optimization)
        optipng -o7 "$out" >/dev/null 2>&1 || optipng -o7 "$out"
    done
    shopt -u nullglob

    echo "Completed optimization for folder: $folder_path"
done < "$FOLDER_FILE"

echo "Image optimization completed."