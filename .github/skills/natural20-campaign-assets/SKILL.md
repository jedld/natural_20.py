---
name: natural20-campaign-assets
description: "Generate Natural20 campaign NPC circular tokens, login/title backgrounds, and missing item/spell inventory icons via the local Image Gen MCP server (port 8020). Use when asked to create token art, portraits, title screens, item icons, spell icons, or fill missing campaign image assets."
argument-hint: "--campaign user_levels/<slug> [--force] [--portraits]"
user-invocable: true
---

# Natural20 Campaign Asset Generator (Image Gen MCP)

## Load context

1. Read [docs/CAMPAIGN_ASSET_GENERATOR.md](../../../docs/CAMPAIGN_ASSET_GENERATOR.md)
2. Confirm Image Gen MCP is reachable: `python scripts/generate_campaign_assets.py --campaign <path> --status`
3. If status reports CUDA OOM / not ready, stop and tell the user to free GPU VRAM — do not fake binary assets.

## Commands

```bash
python scripts/generate_campaign_assets.py --campaign user_levels/<slug> --dry-run
python scripts/generate_campaign_assets.py --campaign user_levels/<slug>
python scripts/generate_campaign_assets.py --campaign user_levels/<slug> --force --portraits

# Item / spell inventory icons (see docs/CAMPAIGN_ASSET_GENERATOR.md)
python scripts/generate_game_icons.py --root templates --scan-only
python scripts/generate_game_icons.py --root templates --icon-style "flat style icons" --limit 5
python scripts/generate_game_icons.py --root templates --no-items --no-spells --icon-style "flat style icons"
```

Env: `N20_IMAGE_GEN_MCP_URL` (default `http://127.0.0.1:8020/mcp`).

## Rules

- NPC tokens **must** go through `make_circular_token` (256px + brown ring) — never leave square raw diffusion output as the VTT token.
- Write files under `campaign/assets/`; set `token_image` on NPC YAML when updating.
- NPCs with `portrait_scene` also get `profile_image` under `assets/portraits/` — see `natural20-npc-generator` skill.
- Login background path comes from `index.json` → `login_background`.
- Prefer `--dry-run` before long GPU jobs.
