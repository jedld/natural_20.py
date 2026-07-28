# Map Image Generator

Render Natural20 map YAML files to tile-based PNG or JPEG images for documentation,
VTT backgrounds, or LLM context.

## Batch mode: missing map backgrounds

Generate `assets/maps/<map_id>.png` for every campaign map that has no
`background_image`, or references a file that does not exist:

```bash
# Preview what would be rendered
python scripts/render_map_image.py \
  --campaign user_levels/outcasts_path \
  --batch-missing \
  --dry-run

# Render missing assets and wire YAML references
python scripts/render_map_image.py \
  --campaign user_levels/outcasts_path \
  --batch-missing \
  --update-yaml

# Only fix maps that already declare background_image but are missing the file
python scripts/render_map_image.py \
  --campaign user_levels/outcasts_path \
  --batch-missing \
  --skip-unassigned
```

Batch mode defaults to `base,objects,entities` layers, reads `tile_size` from
`index.json`, picks a palette from map name/description / `render.palette`, and
skips compositing any existing `background_image` so regeneration stays clean.

Flags:

| Flag | Effect |
|------|--------|
| `--update-yaml` | Set `background_image: <map_id>.png` after rendering |
| `--dry-run` | List pending maps without writing files |
| `--force` | Re-render even when the PNG already exists |
| `--skip-unassigned` | Ignore maps with no `background_image` field |

## Quick start

```bash
# Standalone map YAML
python scripts/render_map_image.py \
  --input templates/maps/goblin_cave.yml \
  --output /tmp/goblin_cave.png \
  --tile-size 48 \
  --palette dirt

# Campaign map
python scripts/render_map_image.py \
  --campaign user_levels/outcasts_path \
  --map cathedral \
  --output /tmp/cathedral.png \
  --tile-size 40 \
  --palette cathedral \
  --grid
```

## Rendering modes

### Procedural (default)

Draws theme-aware floor, wall, water, and door textures, plus procedural object
icons (teleporters, altars, candles, notes, chests, barrels, campfires, pits).
Uses bundled sprites from `webapp/static/assets/objects/` when available.
NPCs render as colored markers.

Palette is inferred from the map name/description (`sewer`, `cathedral`,
`prison`, `manor`, `street`, `cobble`, `dirt`, `grass`, `stone`) unless
`--palette` or `render.palette` is set. Map `illumination` and fog
`default_effect` are applied as atmospheric overlays.

### Campaign background image

If the map YAML sets `background_image`, the renderer pastes that asset under
the tile layers (honoring `image_offset_px`).

### Diffusion background (optional)

Generate an AI background underlay from the map name, description, and theme:

```bash
# Local Image Gen MCP (recommended)
python scripts/render_map_image.py \
  --campaign user_levels/outcasts_path \
  --map cathedral \
  --output /tmp/cathedral_ai.png \
  --diffusion mcp \
  --background-opacity 0.4

# OpenAI
export OPENAI_API_KEY=...
python scripts/render_map_image.py \
  --campaign user_levels/outcasts_path \
  --map cathedral \
  --output /tmp/cathedral_ai.png \
  --diffusion openai \
  --background-opacity 0.4
```

### MCP theme texture packs

Procedural tiles alone can look too similar across locations. Bake per-theme
floor/wall/water atlases with the Image Gen MCP, then re-render:

```bash
python scripts/render_map_image.py \
  --campaign user_levels/outcasts_path \
  --batch-missing \
  --force \
  --prepare-textures \
  --diffusion mcp \
  --diffusion-quality low \
  --background-opacity 0.4
```

Texture packs cache under `~/.cache/natural20/map_textures/<theme>/`
(`N20_MAP_TEXTURE_ROOT` overrides). Themes: `cathedral`, `sewer`, `prison`,
`manor`, `street`, `tavern`, `docks`, etc.

After writing campaign assets, compress for the web:

```bash
python webapp/scripts/optimize_web_assets.py user_levels/<campaign>/assets --force
npm run optimize:images
```

## Layers

`--layers` accepts a comma-separated list:

| Layer | Content |
|-------|---------|
| `base` | Terrain (`#`, `.`, water, walls from legend) |
| `objects` | `base_1` and `base_2` legend tokens |
| `entities` | `map.entities` placements |
| `meta` | NPC positions from `meta` layer |

Example: blueprint-style floor plan only:

```bash
python scripts/render_map_image.py --input map.yml -o plan.png --layers base,objects
```

## Map YAML hints

Optional `render` block in map YAML (or under `map.render`):

```yaml
render:
  tile_size: 48
  palette: sewer
```

## Python API

```python
from natural20.map_image import render_map_image

render_map_image(
    campaign="user_levels/outcasts_path",
    map_name="cathedral",
    output="cathedral.png",
    tile_size=48,
    palette="cathedral",
)
```

## Tests

```bash
pytest tests/test_map_image.py
```
