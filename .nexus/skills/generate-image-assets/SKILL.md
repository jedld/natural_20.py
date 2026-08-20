# Image Asset Generation Skill

Guide for generating image assets (action icons, effect icons, spell icons, tokens, portraits) via the Image Gen MCP server for any campaign.

## Prerequisites

- Image Gen MCP server running (default: `http://127.0.0.1:8020/mcp`)
- PIL/Pillow installed
- Campaign directory exists under `user_levels/<campaign>/`

## Asset Types and Output Locations

| Asset Type | Output Path | Size | Example |
|---|---|---|---|
| Action button | `n20-webapp/webapp/static/actions/<slug>.png` | 256x256 | `shell_defense.png` |
| Effect icon | `n20-webapp/webapp/static/assets/effect/<slug>.png` | 64x64 | `shell_defense.png` |
| NPC token | `user_levels/<campaign>/assets/token_<name>.png` | 256x256 (circular) | `token_tortle.png` |
| Character token | `user_levels/<campaign>/assets/token_<name>.png` | 256x256 (circular) | `token_oogway.png` |
| Character portrait | `user_levels/<campaign>/assets/characters/<name>.png` | 256x256 | `portrait_tortle.png` |
| Item icon | `n20-webapp/webapp/static/assets/items/<slug>.png` | 256x256 | `tortle_shell.png` |
| Spell icon | `n20-webapp/webapp/static/spells/spell_<slug>.png` | 256x256 | `spell_shell_defense.png` |

## Quick Generation Commands

### Pre-built generation scripts

```bash
# Generate tortle-specific assets (shell_defense icon + tokens)
python scripts/generate_tortle_assets.py \
  --campaign user_levels/death_house \
  --mcp-url http://127.0.0.1:8020/mcp

# Dry run (preview what would be generated)
python scripts/generate_tortle_assets.py --dry-run

# Generate only specific asset types
python scripts/generate_tortle_assets.py --action-only
python scripts/generate_tortle_assets.py --effect-only
python scripts/generate_tortle_assets.py --token-only

# Overwrite existing assets
python scripts/generate_tortle_assets.py --force
```

### Campaign-wide assets

```bash
# Generate NPC tokens, portraits, backgrounds for a campaign
python scripts/generate_campaign_assets.py \
  --campaign user_levels/death_house \
  --mcp-url http://127.0.0.1:8020/mcp \
  --tokens --portraits --full-body

# Preview planned generations
python scripts/generate_campaign_assets.py \
  --campaign user_levels/death_house \
  --dry-run
```

### Custom generation via Python

```python
from natural20.image_gen.mcp_client import ImageGenMcpClient, save_pil
from natural20.image_gen.tokens import make_circular_token

with ImageGenMcpClient("http://127.0.0.1:8020/mcp") as mcp:
    # Generate action icon
    result = mcp.generate_image(
        prompt="Your prompt here",
        negative_prompt="unwanted elements",
        size="256x256",
        quality="medium",
    )
    save_pil(result.image, "output_path.png")
    
    # Generate circular token
    token = make_circular_token(result.image, 256)
    save_pil(token, "token_output.png")
```

## Prompt Construction

Use helpers from `natural20.image_gen.prompts`:

```python
from natural20.image_gen.prompts import (
    action_icon_prompt,     # For action buttons
    effect_icon_prompt,     # For status effects
    npc_token_prompt,       # For NPC tokens
    character_portrait_prompt,  # For character portraits
    item_icon_prompt,       # For item icons
    spell_icon_prompt,      # For spell icons
    npc_scene_portrait_prompt,  # For full-body NPC portraits
    action_icon_negative,   # Negative prompts for actions
    TOKEN_NEGATIVE,         # Negative prompts for tokens
    ICON_NEGATIVE,          # General icon negative prompt
)
```

### Prompt patterns by asset type

**Action icons:** "Combat action icon: <subject>, D&D RPG icon style, hand-drawn fantasy art, ability button icon, square composition, no text"

**Effect icons:** "Status effect buff icon: <name/label>, <school> school, D&D RPG icon style, square composition, no text, no border frame"

**NPC tokens:** "fantasy VTT token bust, close-up head and shoulders, face centered, fills frame, <description>, painterly gothic horror, <theme>, cold desaturated light, high-detail face"

**Character portraits:** "painterly gothic horror portrait, head and shoulders, face centered, <description>, cold misty light, no text"

**Item icons:** "<item description>, D&D 5e RPG item icon, square composition, no text"

**Spell icons:** "D&D 5e spell icon: <spell name>, <visual description>, fantasy magic icon, square composition, no text"

## Adding Shell Defense Visual Effects to Frontend

For race-specific states like tortle shell_defense:

1. Generate effect icon: `n20-webapp/webapp/static/assets/effect/shell_defense.png`
2. Add CSS overlay class to `n20-webapp/webapp/static/status_effects.js`:
   ```javascript
   // In EFFECT_CLASS map:
   shell_defense: 'pe-shell-defend',
   ```
3. Add CSS keyframes and class to `injectStylesOnce()`:
   ```css
   @keyframes pe-shell-pulse {
     0% { transform: scale(0.95); opacity: 0.35; }
     100% { transform: scale(1.05); opacity: 0.15; }
   }
   .pe-shell-defend {
     border-radius: 50%;
     background: radial-gradient(circle, rgba(139, 90, 43, 0.55) 0%, rgba(101, 67, 33, 0.30) 55%, rgba(101, 67, 33, 0.0) 78%);
     border: 3px solid rgba(160, 120, 60, 0.5);
     box-shadow: 0 0 16px rgba(139, 90, 43, 0.5), inset 0 0 10px rgba(139, 90, 43, 0.35);
     animation: pe-shell-pulse 1.8s ease-in-out infinite alternate;
   }
   ```
4. Wire event handlers in `engine.js` or `spell_effects.js`:
   ```javascript
   // In event handler:
   if (event.event === 'shell_defense_enter') {
     if (window.PersistentEffects) {
       window.PersistentEffects.applyForEntity(event.source);
     }
   }
   if (event.event === 'shell_defense_exit') {
     if (window.PersistentEffects) {
       window.PersistentEffects.removeForEntity(event.source);
     }
   }
   ```

## Troubleshooting

- **MCP server not responding**: Check if the server is running: `curl http://127.0.0.1:8020/mcp`
- **Timeout errors**: Increase timeout via `N20_IMAGE_GEN_MCP_TIMEOUT` env var
- **Low quality images**: Use `--quality high` flag or specify `model: flux-dev`
- **Missing negative prompts**: Use the predefined negative prompt helpers
