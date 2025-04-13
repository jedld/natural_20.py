#!/bin/bash

# Script to check image sizes in user_levels directories and webapp/static
# Output format: size_bytes,filename
# Sorted by size (largest to smallest)

# Find all image files and get their sizes
find user_levels webapp/static -type f \( -iname "*.png" -o -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.gif" -o -iname "*.webp" \) \
    \( -path "*/static/*" -o -path "*/assets/*" \) -printf "%s,%P\n" | sort -nr 