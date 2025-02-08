Contains scripts for maintaining the webapp


Useful scripts:

mass rename optimized images:

```
#!/bin/bash
# This script renames files by removing the "-optimized" suffix from their names

find . -type f -name "*-optimized.*" | while read -r file; do
    newfile="${file/-optimized/}"
    echo "Renaming: $file -> $newfile"
    mv "$file" "$newfile"
done
```