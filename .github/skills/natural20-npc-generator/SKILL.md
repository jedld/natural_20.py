---
name: natural20-npc-generator
description: >-
  Add ambient townsfolk, shopkeepers, guards, and other conversational NPCs to a
  Natural20 campaign: author YAML stat blocks, place tokens on maps, write LLM
  backstories, and generate circular tokens plus scene portraits via Image Gen MCP.
  Use when asked to populate a town, tavern, market, hub, or social scene with NPCs,
  make a location feel lived-in, or batch-create NPC cast members with art.
argument-hint: "--campaign user_levels/<slug> [location: tavern|market|hub]"
user-invocable: true
---

# Natural20 NPC Generator

Add **playable, conversational NPCs** to an existing campaign — not full campaign scaffolding (see `natural20-campaign-builder`) and not map tiles (see `natural20-dungeon-generator`).

Canonical reference: [user_levels/wild_sheep_chase/npcs/](../../../user_levels/wild_sheep_chase/npcs/) + [town_market.yml](../../../user_levels/wild_sheep_chase/maps/town_market.yml) (Mara, Pip, Henrik, Sella, Wren, Garret).

## Load context

1. Read [docs/CAMPAIGN_BUILDING.md](../../../docs/CAMPAIGN_BUILDING.md) → NPCs, NPC Overrides, Dialog.
2. Read [docs/CAMPAIGN_ASSET_GENERATOR.md](../../../docs/CAMPAIGN_ASSET_GENERATOR.md) for token/portrait generation.
3. Inspect the target map: spawn points, walkable tiles, existing legend tokens, `game.yml` groups.
4. For image generation, follow `.github/skills/natural20-campaign-assets/SKILL.md`.

## Workflow checklist

```
- [ ] 1. Plan cast (roles, count, location, combat relevance)
- [ ] 2. Create one YAML per NPC (filename = sub_type)
- [ ] 3. Place on map (entities + legend overrides)
- [ ] 4. Update area narrations if needed
- [ ] 5. Generate tokens/portraits (Image Gen MCP)
- [ ] 6. Validate campaign loads
```

## 1. Plan the cast

For each location, aim for **3–6 NPCs** with distinct roles:

| Role | Examples | Typical flags |
|------|----------|---------------|
| Staff / authority | bartender, innkeeper, guard captain | `dialog: true`, local gossip |
| Patrons / crowd | drunk, gossip, traveler | `dialog: true` or ambient only |
| Merchants | fishmonger, spice seller | `dialog: true`, mundane inventory talk |
| Combatants | bandits, guards who fight | omit `passive`, full actions |

Decide **group** from `game.yml` (`c` = neutral townsfolk is common). Ambient NPCs should use `passive: true` so they do not act in combat.

**Do not** make progression depend solely on LLM phrasing — backstories may hint at quests but must not gate required beats.

## 2. Author NPC YAML

**One file per NPC.** `sub_type` on the map must match the filename stem:

```
npcs/mara_bartender.yml  →  sub_type: mara_bartender
```

### Minimal commoner / townsfolk template

```yaml
---
kind: Mara
description: >
  Stout human woman in her forties with rolled sleeves. Proprietor of the
  Prancing Flagon — knows every regular and every scandal.
portrait_scene: tavern          # optional — triggers scene portrait + token
size: medium
race:
  - human
alignment: neutral_good
default_ac: 10
max_hp: 11
hp_die: 2d8+2
speed: 30
passive_perception: 11
token:
  - MB                        # map token (2 chars → use map.entities, not legend string)
color: brown
ability:
  str: 12
  dex: 10
  con: 12
  int: 11
  wis: 13
  cha: 14
languages:
  - common
cr: 0
xp: 0
proficiency_bonus: 2
actions: []
```

### Image-generation fields (optional)

| Field | Values | Effect |
|-------|--------|--------|
| `portrait_scene` | key from `asset_prompts.yml` → `scenes` | Scene-backed portrait in `assets/portraits/` + circular token |
| `image_prompt` | free text | Override auto prompt entirely |
| `asset_theme` | in `game.yml` | Short campaign mood string for prompts |
| `asset_prompts.yml` | campaign root | Token/portrait styles, login scenes, `scenes:` map (see `docs/CAMPAIGN_ASSET_GENERATOR.md`) |

After generation, YAML gets:

```yaml
token_image: token_mara.png
profile_image: portraits/portrait_mara.jpg
```

`Entity.profile_image()` prefers `profile_image` (dialog/info UI); `token_image` is the map token.

### Voice (optional TTS)

```yaml
gender: female
voice:
  gender: female
  age: young              # young | elderly (adult is default)
  prompt: Cheerful halfling barmaid, bubbly and warm
  style: happy            # calm | angry | happy | lazy | whisper
  accent: british         # american, british, irish, romanian, ...
  language: en
```

Place `gender` and `voice` on the NPC YAML file (not map overrides). CosyVoice uses `prompt`, `style`, and `accent` when TTS is enabled.

## 3. Place on the map

### Entities block

Multi-character tokens **must** use `map.entities` (not inline legend strings):

```yaml
map:
  entities:
    - token: MB
      pos: [8, 17]
    - token: PB
      pos: [13, 19]
```

### Legend overrides

```yaml
legend:
  MB:
    name: Mara
    type: npc
    sub_type: mara_bartender
    group: c
    overrides:
      entity_uid: mara_bartender      # stable UID — required for dialog/save
      label: Mara (Bartender)
      passive: true
      dialog: true
      conversation_handler: llm
      backstory: |
        You are Mara, proprietor of the Prancing Flagon...
        KNOWLEDGE: local gossip about [villain], [hook NPC], north woods danger.
        COMBAT: stay behind the bar; urge patrons to flee.
        Use [TO: speaker] when addressing one adventurer.
```

**Placement rules:**

- Put NPCs on **walkable** tiles (`.` in base layer), not inside walls.
- Avoid stacking on `player_spawn_points` unless intentional.
- Keep combat enemies on separate groups from townsfolk.
- Use unique `entity_uid` values across the campaign.

### Area narrations

Update `area_narrations` bounds to name key NPCs when the party enters a zone — reinforces that the place is lived-in.

## 4. LLM backstory pattern

Keep backstories **short and structured** (map `overrides.backstory`, not NPC YAML):

```
ROLE: one sentence identity.
PERSONALITY: 2–3 traits.
KNOWLEDGE: 3–5 facts the NPC can share (gossip, warnings, rumors).
BOUNDARIES: what they won't do / don't know.
COMBAT: flee, hide, or call guards — unless they are fighters.
TAGS: [TO: speaker], [TO: all], [ASIDE: ...] as needed.
```

For quest-critical NPCs, also add `conversation_buffer` seed lines and `converstation_keywords` handlers (see Finethir in `town_market.yml`).

## 5. Generate art

Probe MCP first:

```bash
python scripts/generate_campaign_assets.py --campaign user_levels/<slug> --status
```

Generate only new NPCs (skips existing tokens):

```bash
python scripts/generate_campaign_assets.py \
  --campaign user_levels/<slug> \
  --no-background \
  --only Mara --only Pip --only Henrik
```

`portrait_scene` NPCs produce **both** `assets/portraits/portrait_<kind>.jpg` and `assets/token_<kind>.png`.

Use `--dry-run` before long GPU jobs. Do not fabricate binary assets if MCP is down.

Set `asset_theme` in `game.yml` (short mood line) and campaign styles in `asset_prompts.yml`:

```yaml
# game.yml
asset_theme: whimsical D&D one-shot, Amphail market town, warm afternoon light

# asset_prompts.yml (campaign root — not in natural20/)
token_style: fantasy VTT token bust, painterly, warm afternoon light, ...
portrait_style: painterly fantasy portrait, warm natural light, ...
scenes:
  tavern: medieval tavern, hearth glow, blurred patrons
```

## 6. Validate

```bash
python scripts/validate_campaign.py user_levels/<slug>
```

Smoke-load NPCs:

```python
from natural20.session import Session
s = Session("user_levels/<slug>")
# Session init rolls HP for map NPCs — confirm no load errors
```

Start webapp and verify tokens + dialog:

```bash
cd webapp && TEMPLATE_DIR=../user_levels/<slug> python -m flask run
```

## Anti-patterns

- **Multi-entry `npcs/townsfolk.yml`** — engine loads by **filename stem**; use `mara_bartender.yml`, not a shared file.
- **Single-char legend keys in string layers** — use `map.entities` for 2+ char tokens.
- **Combat stats on ambient NPCs** — `cr: 0`, `actions: []`, `passive: true` unless they join fights.
- **Square diffusion output as VTT token** — always run through `make_circular_token` via the asset script.
- **Quest gates in LLM-only knowledge** — duplicate critical facts in signs, journals, or keyword handlers.

## Related skills

- `natural20-campaign-builder` — full campaign scaffold
- `natural20-campaign-assets` — Image Gen MCP tokens and backgrounds
- `natural20-dungeon-generator` — procedural dungeon maps (different use case)
