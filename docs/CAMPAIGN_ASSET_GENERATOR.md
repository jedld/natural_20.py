# Campaign Asset Generator (Image Gen MCP)

Generate **circular NPC tokens** and **login / title backgrounds** for a Natural20
campaign using the local **Image Gen MCP** server
(`Image Gen MCP (local)`, typically `http://127.0.0.1:8020/mcp`).

Tokens are post-processed with the same circular stamp used by the webapp
character builder (`natural20.image_gen.tokens.make_circular_token` —
256×256, brown ring border, transparent corners).

## Prerequisites

1. Start the Image Gen MCP server (streamable HTTP), e.g. on port 8020.
2. Ensure the GPU has free VRAM (the server returns CUDA OOM if another model
   already filled the card). First `generate_image` call lazy-loads the pipeline.
3. Optional env overrides:
   - `N20_IMAGE_GEN_MCP_URL` / `IMAGE_GEN_MCP_URL` — MCP endpoint
     (default `http://127.0.0.1:8020/mcp`)

**Model notes:** Default active model is often `flux-dev`. Do **not** pass
`aspect_ratio` for FLUX presets (Qwen-only). This tool uses explicit `WxH`
sizes (`1024x1024` tokens, `1280x720` login backgrounds).

## Quick start

```bash
# Probe readiness
python scripts/generate_campaign_assets.py \
  --campaign user_levels/outcasts_path \
  --status

# Preview what would be generated
python scripts/generate_campaign_assets.py \
  --campaign user_levels/outcasts_path \
  --dry-run

# Generate missing NPC tokens + login background
python scripts/generate_campaign_assets.py \
  --campaign user_levels/outcasts_path

# Force regenerate everything (tokens + title art + character portraits)
python scripts/generate_campaign_assets.py \
  --campaign user_levels/outcasts_path \
  --force \
  --portraits \
  --mcp-url http://127.0.0.1:8020/mcp
```

## What gets written

| Asset | Path | Notes |
|-------|------|--------|
| NPC tokens | `assets/token_<kind>.png` | Circular, 256px, ring border |
| NPC scene portraits | `assets/portraits/portrait_<kind>.jpg` | When NPC YAML has `portrait_scene` |
| Login / title | `assets/<login_background>` from `index.json` | e.g. `thyros_cityscape.jpg` |
| PC portraits (optional) | `assets/characters/<name>.png` | `--portraits` |

When `--update-yaml` is on (default), each NPC YAML also gets:

```yaml
token_image: token_whisper.png
```

For NPCs with `portrait_scene` (`tavern`, `market`, `street`, `town`), the tool also writes:

```yaml
profile_image: portraits/portrait_whisper.jpg
```

`Entity.profile_image()` prefers `profile_image` for dialog/info UI; `token_image` is the circular map token.

Optional per-NPC fields:

| Field | Purpose |
|-------|---------|
| `portrait_scene` | Scene-backed portrait prompt (`tavern`, `market`, `street`, `town`) |
| `outward_appearance` | Physical look used for token/portrait prompts (preferred over `description`) |
| `image_prompt` | Override auto-generated diffusion prompt (keep under ~65 words for CLIP) |
| `asset_theme` (in `game.yml`) | Campaign-wide mood string appended to prompts |

`Entity.token_image()` resolves generated tokens under `/assets/`.

## CLI flags

| Flag | Effect |
|------|--------|
| `--tokens` / `--no-tokens` | NPC circular tokens (default on) |
| `--background` / `--no-background` | Login/title image (default on) |
| `--portraits` | Selectable character portraits |
| `--force` | Overwrite existing files |
| `--dry-run` | Print plan; no MCP calls |
| `--only KIND` | Limit to NPC kind / portrait name (repeatable) |
| `--token-size N` | Output token size (default 256) |
| `--quality low\|medium\|high\|auto` | MCP quality preset |
| `--status` | MCP readiness probe |

## Programmatic use

```python
from natural20.image_gen.campaign_assets import generate_campaign_assets

report = generate_campaign_assets(
    "user_levels/outcasts_path",
    mcp_url="http://127.0.0.1:8020/mcp",
    tokens=True,
    background=True,
    force=False,
)
```

Inject a fake generator in tests via `generator=callable`.

## Item and spell icons

Use `scripts/generate_game_icons.py` to find missing inventory / spell bar / **action bar**
icons and generate them via the same Image Gen MCP server. Generated PNGs are
**optimized in place** by default (PNG compression + optional `.webp` companions).

```bash
# List gaps (no GPU)
python scripts/generate_game_icons.py --root templates --scan-only | head

# Preview prompts
python scripts/generate_game_icons.py --root templates --dry-run --limit 3 \
  --icon-style "flat style icons, bold silhouette, dark vignette"

# Generate missing bundled icons
python scripts/generate_game_icons.py --root templates --icon-style "flat style icons"

# Action icons only (webapp/static/actions)
python scripts/generate_game_icons.py --root templates --no-items --no-spells \
  --icon-style "flat style icons"

# Campaign session root (uses game.yml asset_theme in prompts); write items to campaign/assets/items
python scripts/generate_game_icons.py --campaign user_levels/wild_sheep_chase \
  --write-to campaign --only healing_potion
```

| Flag | Effect |
|------|--------|
| `--icon-style` | Style phrase for every prompt (default: flat style fantasy game icon…) |
| `--items` / `--spells` / `--actions` | Toggle which catalogs to scan (all on by default) |
| `--scan-only` | JSON list of missing icons, no MCP |
| `--write-to bundled\|campaign` | Item output directory (spells → `webapp/static/spells`, actions → `webapp/static/actions`) |
| `--optimize` / `--no-optimize` | PNG compress after save (default: on) |
| `--webp` | Also emit `.webp` siblings (UI still uses `.png` unless templates are updated) |
| `--only ID` | Limit to one item/spell/action slug (repeatable) |
| `--item-size` / `--spell-size` / `--action-size` | Resize output (default 128px) |

Per-entry YAML overrides: `image_prompt` or `icon_prompt` on the item/spell entry.

Action icons are discovered from `natural20/actions` build literals, attack flavor
suffixes (`attack_melee`, …), class-feature buttons (`divine_smite`, `wild_shape`, …),
and `items/objects.yml` interact `buttons` (`interact_open`, `open_chest`, …).

## Related

- NPC townsfolk workflow: `.github/skills/natural20-npc-generator/SKILL.md`
- Map tile backgrounds (procedural): [MAP_IMAGE_GENERATOR.md](MAP_IMAGE_GENERATOR.md)
- Story bible for Outcasts theme prompts: [OUTCASTS_PATH_STORY.md](OUTCASTS_PATH_STORY.md)
- Character builder token stamp: `webapp/blueprints/helpers/character_builder_utils.py`
