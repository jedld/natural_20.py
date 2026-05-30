Contains scripts for maintaining the webapp

## Web asset optimization

**JS/CSS minify** (esbuild, writes `*.min.js` / `*.min.css` + `manifest.assets.json`):

```bash
npm run build:assets
```

**Raster images** (Pillow / optional `optipng`, `jpegoptim`, `cwebp`):

```bash
npm run optimize:images
# or: python webapp/scripts/optimize_web_assets.py --dry-run
```

**Both:**

```bash
npm run optimize:assets
```

Templates use `{{ asset_url('engine.js') }}`. Minified files are served when
`N20_USE_MINIFIED_ASSETS=1`, or by default when `FLASK_ENV=production` /
`FLASK_DEBUG=0`. Force dev sources with `N20_USE_MINIFIED_ASSETS=0`.

After changing static JS/CSS, run `npm run build:assets` before deploying.

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