# Campaign Building Guide

This guide explains how to create custom campaigns, maps, NPCs, and encounters
for the Natural20 D&D simulation engine.

---

## Table of Contents

1. [Campaign Directory Structure](#campaign-directory-structure)
2. [Game Configuration (game.yml)](#game-configuration)
3. [Level Configuration (index.json)](#level-configuration)
4. [Map Files](#map-files)
   - [Map Layers](#map-layers)
   - [Legend Entries](#legend-entries)
   - [Lighting](#lighting)
   - [Visual Effects](#visual-effects)
   - [Narration](#narration)
5. [NPCs](#npcs)
   - [NPC Templates](#npc-templates)
   - [NPC Overrides in Maps](#npc-overrides-in-maps)
   - [NPC Dialog & Conversation](#npc-dialog--conversation)
   - [Sidekick NPCs](#sidekick-npcs)
6. [Player Characters](#player-characters)
   - [Feats, auras and edition overrides](#feats-auras-and-edition-overrides)
7. [Objects](#objects)
   - [Built-in Object Types](#built-in-object-types)
   - [Doors](#doors)
   - [Chests](#chests)
   - [Traps](#traps)
   - [Teleporters](#teleporters)
   - [Switches](#switches)
   - [Proximity Triggers](#proximity-triggers)
8. [Terrain](#terrain)
9. [Items & Inventory](#items--inventory)
10. [Triggers & Events](#triggers--events)
11. [Groups & Factions](#groups--factions)
12. [Multi-Map Campaigns](#multi-map-campaigns)
13. [Complete Example](#complete-example)
14. [Procedural Dungeons](#procedural-dungeons)
15. [Battlemap import](#battlemap-import-image--yaml)

---

## Campaign Directory Structure

A campaign is a directory that mirrors the `templates/` layout. The engine
resolves resources by first checking the campaign directory, then any imported
campaigns declared in `game.yml`, and finally falling back to `templates/`.
Item catalogues (`weapons`, `equipment`, `magic_items`,
`objects`, `spells`, `equipment_packs`) are **automatically merged** with the
bundled templates when a campaign file exists without an explicit `inherit`
directive — campaign keys override template keys.

To start from scratch, run `./start_web.sh --new --edit my_campaign` (or
`python -m natural20.campaign_scaffold user_levels/my_campaign --title "My Campaign"`).
It creates `index.json`, `game.yml`, an empty starting map, and a DM login
(`dm` / `admin`), then boots the campaign in edit mode. See
`docs/WEBAPP_BLUEPRINTS.md` → "New campaign at startup".

See [YAML Template Inheritance](#yaml-template-inheritance) for explicit
inheritance and per-entry overrides.

```
my_campaign/
├── game.yml                  # Campaign configuration (required)
├── index.json                # Web UI / level configuration (required for webapp)
├── npc_system_prompt.txt     # LLM system prompt template for NPC dialog (optional)
├── entity_token_map.csv      # Entity → token-image mapping (optional)
├── spell_token_map.csv       # Spell → token-image mapping (optional)
├── weapon_token_map.csv      # Weapon → token-image mapping (optional)
├── assets/                   # Images, sounds, backgrounds
│   ├── items/                # Campaign-only item icons (not in templates/)
│   ├── sounds/
│   ├── characters/           # Character portrait PNGs
│   └── ...
├── characters/               # Player character YAML sheets
│   ├── high_elf_mage.yml
│   └── dwarf_cleric.yml
├── char_classes/             # Class definitions (override or extend)
│   ├── wizard.yml
│   └── fighter.yml
├── items/                    # Item definitions (override or extend)
│   ├── objects.yml           # Map objects (chests, traps, doors, etc.)
│   ├── weapons.yml
│   ├── equipment.yml
│   └── spells.yml
├── maps/                     # Map YAML files
│   ├── entrance.yml
│   └── dungeon.yml
├── map_graph.yml             # Optional Map Connections tile positions
├── npcs/                     # NPC template YAML files
│   ├── goblin.yml
│   └── custom_boss.yml
├── races/                    # Race definitions
│   └── elf.yml
└── locales/                  # i18n strings
    └── en.yml
```

## YAML Template Inheritance

Campaign YAML files can inherit from the bundled `templates/` folder or from
any other YAML file on disk. This avoids copying large SRD catalogues into
every campaign.

### File-level inheritance

Add an `inherit` key (aliases: `$inherit`, `extends`, `$extends`) at the top of
a YAML file. The value may be a single path or a list of paths processed in
order; the current file is merged on top (child wins on conflicts).

```yaml
# user_levels/my_campaign/items/equipment.yml
inherit: templates/items/equipment.yml

investigators_badge:
  name: Investigator's Badge
  type: gear
  weight: 0.1
```

Path resolution (first match wins):

| Form | Resolves to |
|------|-------------|
| `templates/items/equipment.yml` | Bundled templates folder |
| `@templates/items/equipment.yml` | Same as above |
| `./relative.yml` | Relative to the current file |
| `/absolute/path.yml` | Absolute path |
| `@campaign/death_house/items/equipment.yml` | Sibling campaign path under the same campaigns parent directory |
| `campaigns/death_house/items/equipment.yml` | Same as above |

When `inherit` is present, **automatic template merging is disabled** for that
file — the inherit chain is authoritative.

### Automatic template merge (item catalogues)

For `items/{weapons,equipment,magic_items,objects,spells,equipment_packs}.yml`,
if the campaign file exists **without** `inherit`, the engine deep-merges the
bundled template catalogue and then the campaign file. Campaign-only keys are
added; overlapping keys use the campaign value.

You can omit a catalogue file entirely and the bundled template version is used.

### Entry-level inheritance

Within a mapping resource, an entry may inherit another entry by key:

```yaml
holy_symbol:
  name: Holy Symbol
  type: trinket
  weight: 1

investigators_badge:
  inherit: holy_symbol
  name: Investigator's Badge
```

### NPCs, races, classes, backgrounds, maps

Individual resource files under `npcs/`, `races/`, `char_classes/`,
`backgrounds/`, and `maps/` also support `inherit` and fall back to the
bundled template file when the campaign copy is missing.

### Importing from another campaign

You can share content directly across campaigns by adding imports in `game.yml`:

```yaml
imports:
  - death_house               # sibling campaign folder name
  - ../shared_content_pack    # relative path
  - /absolute/path/to/campaign
```

Imported campaigns are searched after the current campaign and before bundled
templates. Earlier entries in `imports` have higher precedence than later
entries.

### Running a Campaign

```bash
# Development
cd webapp && python -m flask run

# With a custom campaign directory
cd webapp && TEMPLATE_DIR=../user_levels/my_campaign python -m flask run

# Or using the start script
cd webapp && ./start_web.sh ../user_levels/my_campaign/
```

### Agent-Assisted Campaign Building

The workspace skill at
`.github/skills/natural20-campaign-builder/SKILL.md` guides coding agents through
source intake, user tailoring, scene and dependency design, engine-capability
checks, campaign scaffolding, playability review, and validation. Invoke
`/natural20-campaign-builder` or ask the agent to build or adapt a Natural20
campaign from a description, outline, or user-provided source.

Validate a campaign from the repository root before launching it:

```bash
python scripts/validate_campaign.py user_levels/my_campaign
```

The validator checks YAML syntax and formatting, configuration and map
references, item/NPC/spell/object definitions (campaign plus bundled
`templates/`), resource and asset paths, coordinates, teleporters, and then
loads the campaign through `Session`. It reports optional missing assets as
warnings and exits nonzero for errors.

Options:

- `--static-only` — skip engine `Session` load while scaffolding
- `--verbose` — show engine-load traceback
- `--json` — machine-readable report
- `--repair` — propose automated fixes (dry-run by default)
- `--repair --apply` — write fixes with backups under `.campaign_validator_backups/`
- `--no-llm` — deterministic stub/typo repairs only

The legacy skill wrapper at
`.github/skills/natural20-campaign-builder/scripts/validate_campaign.py`
delegates to the same tool.

---

## Game Configuration

**File**: `game.yml` (root of campaign directory)

This is the top-level campaign definition.

```yaml
name: "My Campaign"

# Optional ASCII art title displayed at startup
title:
  - "  __  __          ____                            _             "
  - " |  \\/  |_   _  / ___|__ _ _ __ ___  _ __   __ _(_) __ _ _ __  "
  - " | |\\/| | | | || |   / _` | '_ ` _ \\| '_ \\ / _` | |/ _` | '_ \\ "
  - " | |  | | |_| || |__| (_| | | | | | | |_) | (_| | | (_| | | | |"
  - " |_|  |_|\\__, | \\____\\__,_|_| |_| |_| .__/ \\__,_|_|\\__, |_| |_|"
  - "         |___/                        |_|            |___/       "
title_color: red

description: A brief description of the campaign
author: Your Name
players: 4                       # Expected number of players

# Starting map (path relative to campaign root, without .yml extension)
starting_map: maps/entrance.yml

# Named maps for multi-map campaigns (used by teleporters)
# Use the file stem as the key (`entrance`, not a display title). Older
# campaigns used `index` for the starting map; if you keep that key, make
# sure it points at `starting_map`. Do not reuse `index` for a later map
# unless `starting_map` already names a different key (the engine will
# follow `starting_map`).
maps:
  entrance: maps/entrance
  dungeon_1: maps/dungeon_level_1
  dungeon_2: maps/dungeon_level_2

# Optional map sets (party POV worlds). Omit for a single implicit `root` set.
# See docs/MAP_SETS.md. Teleporters may only target maps in the same set.
# map_sets:
#   root:
#     label: Dungeon
#     maps: [entrance, dungeon_1, dungeon_2]
#   overland:
#     label: World Map
#     maps: [world_map]


# Directory containing player character sheets
player_profiles: characters

# Optional: conversation item offers for LLM NPCs ([OFFER_ITEM] guards + guidance)
conversation_offer_guidance:
  target_has_item: "- {target} already carries the {item_label}; do not offer it again."
conversation_item_offers:
  my_quest_item:
    item_label: brass key
    aliases: [quest_key]
    block_when: [offer_completed, target_has_item]

# Faction/group definitions
groups:
  a:                             # Players (default group)
    default: true
    enemies:
      - b
    neutral:
      - c
    allies:
      - d
  b:                             # Hostile NPCs
    enemies:
      - a
  c:                             # Neutral creatures
    neutral:
      - a
      - b

# Optional progression mode. Defaults to XP thresholds.
progression:
  mode: xp                       # xp | dm | event | milestone
  events:
    first_boss_defeated:
      label: First Boss Defeated
      levels: 1                  # or target_level: 3
      auto: true                 # grant when campaign_event first_boss_defeated fires

# Optional day/night cycle (derived from monotonic game_time in seconds)
time_of_day:
  enabled: true
  day_length_seconds: 86400      # one in-game day (use 1200 for fast testing)
  start_at_seconds: 28800          # campaign begins at 08:00 on day 1
  phases:
    - id: night
      label: Night
      from_hour: 0
      to_hour: 5
      illumination: 0.12
      background_key: night
      is_night: true
    - id: dawn
      label: Dawn
      from_hour: 5
      to_hour: 7
      illumination: 0.45
      background_key: dawn
    - id: morning
      label: Morning
      from_hour: 7
      to_hour: 12
      illumination: 0.95
      background_key: day
    - id: afternoon
      label: Afternoon
      from_hour: 12
      to_hour: 17
      illumination: 1.0
      background_key: day
    - id: dusk
      label: Dusk
      from_hour: 17
      to_hour: 20
      illumination: 0.5
      background_key: dusk
    - id: night
      label: Night
      from_hour: 20
      to_hour: 24
      illumination: 0.12
      background_key: night
      is_night: true

# Optional: one LLM autonomous tick per dialog NPC after each out-of-combat
# environment time advance (movement > goal > ambient routine).
npc_environment_ticks:
  enabled: true
```

### Group System

Groups define factional relationships for combat:

| Relationship | Meaning |
|---|---|
| `enemies` | Will attack on sight; can be targeted |
| `neutral` | Won't initiate combat; can still be targeted |
| `allies` | Friendly; won't be targeted by default |
| `default: true` | New entities without an explicit group join this one |

---

## Level Configuration

**File**: `index.json` (root of campaign directory)

Configures the web UI: login, character selection, soundtracks, and map
dimensions.

```json
{
  "tile_size": 75,
  "height": 17,
  "width": 22,
  "title": "My Campaign",
  "login_background": "my_login_bg.png",
  "character_selection_background": "char_select_bg.png",
  "map": "maps/entrance",
  "autosave": false,

  "other_maps": {
    "dungeon_1": "maps/dungeon_level_1",
    "dungeon_2": "maps/dungeon_level_2"
  },

  "selectable_characters": [
    {
      "name": "gomerin",
      "file": "characters/gomerin.png",
      "description": "A brave warrior with a heart of gold."
    },
    {
      "name": "crysania",
      "file": "characters/crysania.png",
      "description": "A skilled mage with a mysterious past."
    }
  ],

  "soundtracks": [
    {
      "name": "background",
      "file": "sounds/ambient.mp3",
      "volume": 20
    },
    {
      "name": "battle",
      "file": "sounds/combat.mp3",
      "volume": 30
    }
  ],

  "logins": [
    { "name": "gomerin",  "password": "gomerin",  "role": ["player"] },
    { "name": "crysania", "password": "crysania", "role": ["player"] },
    { "name": "dm",       "password": "admin",    "role": ["dm"] }
  ],

  "default_controllers": [
    { "entity_uid": "gomerin",  "controllers": ["gomerin"] },
    { "entity_uid": "crysania", "controllers": ["crysania"] }
  ]
}
```

### Key Fields

| Field | Type | Description |
|---|---|---|
| `tile_size` | int | Pixel size of each grid square |
| `height`, `width` | int | Default map dimensions in tiles |
| `title` | string | Page / window title |
| `map` | string | Starting map path (without `.yml`) |
| `other_maps` | object | Named map paths for DM map-switching UI |
| `login_background` | string | Image filename in `assets/` for the login screen |
| `login_ui` | object | Optional login screen layout/theme (panel position, fonts, colors). See [Login screen styling](#login-screen-styling). |
| `character_selection_background` | string | Image for character selection |
| `autosave` | bool | Enable automatic save |
| `selectable_characters` | array | Characters players can pick at login |
| `suppress_dialog_descriptions` | bool or `"player_characters"` | Hide entity descriptions in the JRPG talk panel and the NPC public card / PC character sheet for non-DM players (mystery / spoiler-safe) |
| `highlight_doors` | bool | Highlight visible door fixtures on the map with an amber overlay (player-facing UI) |
| `soundtracks` | array | Background music tracks |
| `logins` | array | User accounts (`role`: `"player"` or `"dm"`) |
| `default_controllers` | array | Which users control which entities |

### Login screen styling

Set `login_background` to an image under `assets/` (served at `/assets/<file>`). For
full layout control, add a `login_ui` object in `index.json`:

```json
{
  "login_background": "title.png",
  "login_ui": {
    "background": "title.png",
    "show_title_text": false,
    "background_fit": "cover",
    "background_position": "center top",
    "font_family": "'Cinzel', serif",
    "google_fonts": "https://fonts.googleapis.com/css2?family=Cinzel:wght@400;600&display=swap",
    "panel": {
      "layout": "bottom-right",
      "width": "300px",
      "offset_x": "4vw",
      "offset_y": "7vh",
      "background": "rgba(46, 26, 71, 0.94)",
      "padding": "22px",
      "border_radius": "14px",
      "border": "2px solid #d4af37",
      "box_shadow": "0 14px 36px rgba(0,0,0,0.55)"
    },
    "labels": { "color": "#f5deb3" },
    "inputs": { "background": "#fff8dc", "border": "1px solid #d4af37", "color": "#2e1a47" },
    "button": { "text": "Enter the Chase", "background": "#d4af37", "color": "#2e1a47" },
    "error": { "background": "rgba(120,12,12,0.92)", "color": "#fff" }
  }
}
```

`panel.layout` supports `center`, `bottom-right`, `bottom-left`, `top-right`, and
`top-left`. Optional `login_ui.custom_css` appends campaign-specific CSS rules.

See `user_levels/wild_sheep_chase/index.json` for a worked example using
`assets/title.png`.

---

## Map Files

Map YAML files define the physical layout, objects, NPCs, lighting, and effects
for a single area. They live in the `maps/` directory.

### Minimal Map

```yaml
name: Simple Room
description: A 10x10 room

map:
  illumination: 1.0              # 0.0 = pitch dark, 1.0 = fully lit
  base:
    - "##########"
    - "#........#"
    - "#........#"
    - "#........#"
    - "#........#"
    - "#........#"
    - "#........#"
    - "#........#"
    - "#........#"
    - "##########"
```

### Top-Level Map Properties

| Property | Type | Default | Description |
|---|---|---|---|
| `name` | string | — | Map display name |
| `description` | string | — | Map description |
| `grid_size` | int | `5` | Feet per grid square |
| `background_image` | string | — | Path to background image (in `assets/`) |
| `image_offset_px` | [x, y] | `[0, 0]` | Pixel offset for background image alignment |
| `default_effect` | object | — | Persistent visual effect (see [Visual Effects](#visual-effects)) |
| `point_fires` | array | — | Fire/candle particle emitters |
| `narration` | object | — | Cinematic text overlay (see [Narration](#narration)) |
| `default_soundtrack` | string | campaign `background` | Ambient track when no `music_zones` match |
| `music_zones` | array | — | Rectangular regions that switch ambient music (see below) |
| `map` | object | — | Map data (layers, entities, size, illumination) |
| `legend` | object | — | Character → object/NPC mapping |
| `lights` | object | — | Static light source definitions |
| `triggers` | object | — | Area-wide triggers |
| `extensions` | object | — | Web-specific extensions |

### Location-based ambient music (`music_zones`)

Register soundtrack tracks in `index.json` (`soundtracks` array), then define
zones on a map. When a player character moves (or loads the map), the webapp
switches to the matching track. Combat music still overrides zones while a
battle is active.

```yaml
default_soundtrack: background

music_zones:
  - id: prancing_flagon
    soundtrack: tavern_interior
    priority: 10
    bounds: {x1: 7, y1: 16, x2: 15, y2: 24}
```

| Field | Description |
|---|---|
| `id` | Optional slug for authoring reference |
| `soundtrack` | Track `name` from `index.json` → `soundtracks` |
| `bounds` | Inclusive tile rectangle (`x1`/`y1` top-left, `x2`/`y2` bottom-right) |
| `priority` | Higher wins when zones overlap (default `0`) |

Place MP3 files under `assets/sounds/` in the campaign folder. If a zone
references a missing file, the track is skipped at load time and a warning is
logged.

### Map Layers

The `map` object contains the grid layers and configuration:

```yaml
map:
  illumination: 0.5              # Base light level (0.0–1.0)
  size: [26, 14]                 # Explicit dimensions [width, height]
                                 # width = characters per ASCII row, height = number of rows.
                                 # Must match map.base. A mismatch fails map load with a
                                 # diagnostic (which layer/row, expected vs actual).
                                 # (auto-detected from base layer if omitted)

  # Ground layer — defines walls and floor. Required.
  # Characters: # = wall, . = floor/ground, _ = empty
  base:
    - "##########"
    - "#........#"
    - "#........#"
    - "##########"

  # Object layer — doors, chests, traps, etc. Optional.
  # Characters reference legend entries. '.' = empty.
  base_1:
    - ".........."
    - "....=....."
    - ".......c.."
    - ".........."

  # Decoration/overlay layer. Optional. '.' = empty.
  base_2:
    - ".........."
    - ".........."
    - ".........."
    - ".........."

  # NPC/entity placement layer. Optional. '.' = empty.
  meta:
    - ".........."
    - "...g......"
    - ".........B"
    - ".........."

  # Static light source placement layer. Optional. '.' = empty.
  light:
    - ".........."
    - "....A....."
    - ".........."
    - ".........."

  # Manual per-tile light intensity map. Optional.
  light_map:
    - ".........."

  # Direct entity placement (alternative to meta layer).
  entities:
    - token: R
      pos: [5, 3]
    - token: T1
      layer: object     # 'object' places on object layer
      pos: [0, 6]

  # List-based placement for base / base_1 / base_2 / meta layers (editor-friendly).
  # Works on top of the grid strings above: each entry is materialized onto its
  # layer grid at load time. Edit mode prefers adding objects here (stable ids).
  layer_placements:
    - id: lp_base_1_water_pool    # stable handle for the map editor
      layer: base_1               # base | base_1 | base_2 | meta
      token: ^
      pos: [2, 2]
    - id: lp_meta_torch
      layer: meta
      token: T
      pos: [4, 1]
```

#### Hard-Coded Tokens (base layer)

| Token | Object | Properties |
|---|---|---|
| `#` | Stone Wall | Opaque, impassable, blocks pathfinding |
| `.` | Ground | Passable, placeable |
| `_` | Empty | No terrain |
| `-` | Door (horizontal) | Auto-detects orientation |
| `\|` | Door (vertical) | Auto-detects orientation |

All other characters in `base`, `base_1`, or `base_2` are looked up in
the `legend`.

### Legend Entries

The `legend` maps single characters (or multi-character keys for `entities`)
to objects and NPCs.

#### NPC Legend Entry

```yaml
legend:
  g:
    name: _auto_               # Auto-generate name, or specify one
    type: npc
    sub_type: goblin            # Must match a file in npcs/ (goblin.yml)
    group: b                    # Faction group (see Groups)
    overrides: {}               # Optional NPC stat/behavior overrides
```

#### Object Legend Entry

```yaml
legend:
  c:
    name: chest
    type: chest                 # Must match a key in items/objects.yml
    key: iron_key               # Object-specific properties
    inventory:
      - type: healing_potion
        qty: 2
```

#### Teleporter Legend Entry

```yaml
legend:
  T1:
    name: stairs_down
    type: teleporter
    target_map: dungeon_1       # Must match a key in game.yml maps
    target_position: [3, 7]     # Destination [x, y]
```

#### Spawn Point Legend Entry

```yaml
legend:
  A:
    name: spawn_point_north
    type: spawn_point
```

#### Mask Legend Entry

```yaml
legend:
  M:
    type: mask                  # Placeholder token, no object created
```

### Lighting

Set `map.illumination` to control the base light level. Add light sources via
the `light` layer and `lights` legend:

```yaml
map:
  illumination: 0.0            # Dark — requires light sources
  light:
    - ".........."
    - "....A....."               # 'A' is a light source
    - ".........."

lights:
  A:
    bright: 20                  # Bright light radius (feet)
    dim: 10                     # Dim light radius (feet)
```

Objects can also emit light:

```yaml
legend:
  f:
    name: campfire
    type: campfire
    light:
      bright: 20
      dim: 10
```

#### Illumination Levels

| Level | Name | Effect |
|---|---|---|
| 1.0 | Bright light | Normal vision |
| 0.5 | Dim light | Disadvantage on Perception; darkvision helps |
| < 0.5 | Heavily obscured | Hidden creatures can't be seen without darkvision |
| 0.0 | Darkness | Total darkness; darkvision treats as dim light |

#### Day/Night and Outdoor Tiles

Campaign `time_of_day` in `game.yml` drives ambient light on **outdoor** tiles.
Indoor tiles keep `map.illumination` as their base.

Mark outdoor squares with an `outside` layer (`o` = outside, `.` = indoor/not
affected). For fully outdoor maps use `outdoor: true` instead of a grid.

```yaml
map:
  illumination: 0.85             # indoor base (taverns, covered stalls)
  outdoor: false
  outside:
    - "oooooooooo"
    - "oooooooooo"
    - "..oooooo.."
```

Swap backgrounds by phase using `background_images` (keys match
`time_of_day.phases[].background_key`, usually `day`, `night`, `dawn`, `dusk`):

```yaml
background_image: town_market_day.jpg
background_images:
  day: town_market_day.jpg
  night: town_market_night.jpg
  dawn: town_market_dawn.jpg
  dusk: town_market_dusk.jpg
```

Legacy aliases `background_image_day` / `background_image_night` also work.

DM controls: `POST /admin/time_of_day` with `{ "override_phase_id": "night" }`
or `{ "clear_override": true }`. MCP: `dm.advance_time` plus the override
endpoint above. NPC and DM LLM prompts receive the current clock and phase.

### Visual Effects

#### Fog Effect

```yaml
default_effect:
  effect: fog
  action: start
  config:
    color: "#aab4c8"           # Fog color
    density: 0.9               # Density 0.0–1.0
    speed: 0.2                 # Animation speed
    height: 0.0                # Height offset
    opacity: 0.8               # Visual opacity
    noise_scale: 0.1           # Perlin noise scale

    # Optional token interaction (fog clears around tokens)
    token_interaction:
      enable: true
      radius_px: 70
      count_per_token: 3
      speed: 0.6
      opacity: 0.2

    # Optional masking (confine fog to an area)
    mask: true
    mask_feather: 18
    mask_layers:
      - type: polygon
        points:
          - [0, 6]
          - [5, 3]
          - [10, 6]
          - [5, 10]
```

#### Point Fires (Particle Effects)

```yaml
point_fires:
  - pos: [5, 8]               # Grid position [x, y]
    shape: campfire            # "campfire" or "candle"
    plasma: true               # Plasma visual (optional)
    intensity: 0.95            # 0.0–1.0
    color: "#ff7a2b"           # Flame color
    speed: 0.1                 # Animation speed
  - pos: [3, 2]
    shape: candle
    intensity: 0.35
    speed: 0.1
    offset_px: [30, 30]        # Pixel offset from grid center
```

#### Background Image

```yaml
background_image: dungeon_bg.png   # In assets/
image_offset_px: [0, 0]           # Pixel alignment offset
```

#### Web Extensions

```yaml
extensions:
  web:
    background_color: '#000000'    # Page background color
```

### Narration

Show a cinematic DM narration overlay when players enter a map.

```yaml
narration:
  on_enter:
    title: "Old Svalich Road"          # Optional heading (gold, centered)
    text: >
      The gravel road leads to a village, its tall houses dark
      as tombstones. A soft whimpering draws your eye toward a
      pair of children standing in the middle of an otherwise
      lifeless street.
    once: true                         # Only show the first time
                                       # (tracked in browser localStorage)
```

The narration displays:
- On initial page load when the map has a `narration` property
- When a player switches to a map that has a `narration` property

Players dismiss it by clicking anywhere.

---

## NPCs

### NPC Templates

NPC template files live in `npcs/` (e.g., `npcs/goblin.yml`). The `sub_type`
in a legend entry must match the filename (without `.yml`).

```yaml
---
kind: Goblin
description: >
  Goblins are small, black-hearted humanoids that lair in
  despoiled dungeons and other dismal settings.
size: small                          # tiny/small/medium/large/huge/gargantuan
race:
  - humanoid
  - goblinoid
alignment: neutral_evil

# Combat stats
default_ac: 15
max_hp: 7
hp_die: 2d6                         # Random HP (overrides max_hp if rolled)
speed: 30                           # Movement speed in feet
passive_perception: 9
darkvision: 60                       # Darkvision range (feet); omit if none
proficiency_bonus: 2
cr: 0.25                            # Challenge rating
xp: 50                              # Experience points

# Unique named NPCs (optional)
# entity_uid: npc_ireena            # Stable id — not a spawn-time UUID
# unique: true                      # Optional explicit flag; Unique badge in the NPC Spawner
# Dropping a unique NPC that already exists on the same map set moves that token.

# Ability scores
ability:
  str: 8
  dex: 14
  con: 10
  int: 10
  wis: 8
  cha: 8

# Skill bonuses
skills:
  stealth: 6

# Known languages
languages:
  - common
  - goblin

# Special attributes / class features
attributes:
  - nimble_escape

# Display
token:
  - g                               # Single character for map display
color: green                         # Terminal / ASCII color

# Combat actions
actions:
  - name: Scimitar
    type: melee_attack
    if: equipped:scimitar            # Only available if equipped
    range: 5
    targets: 1
    attack: 4                        # Attack bonus
    damage: 5                        # Average damage
    damage_die: 1d6+2               # Damage roll
    damage_type: slashing
  - name: Shortbow
    type: ranged_attack
    if: equipped:shortbow
    range: 80                        # Normal range (feet)
    range_max: 320                   # Long range (feet)
    targets: 1
    attack: 4
    damage: 5
    damage_die: 1d6
    damage_mod: 2                    # Added to damage
    damage_type: piercing
    ammo: arrows                     # Requires ammunition

# Starting equipment
equipped:
  - scimitar
  - shortbow
  - leather_armor
  - shield

# Starting inventory
default_inventory:
  - type: arrows
    qty: 20
```

Spellcasters add `spell_ability` (or `spellcasting_ability`), `spell_slots`,
and `prepared_spells`. The NPC stat block then shows the Monster Manual line
`Its spellcasting ability is Wisdom (spell save DC 13, +5 to hit with spell attacks)`
using 8 + proficiency bonus + ability modifier. Optional `spell_save_dc` and
`spell_attack_bonus` override the computed values. Set `spellcaster_level`
(alias `caster_level`) to the stat block's "Nth-level spellcaster": cantrip
damage scales from it (5th/11th/17th), not from CR. Without it, cantrips scale
from `cr`, so a CR 15 vampire wizard would roll 3d8 Ray of Frost instead of 2d8.

```yaml
spell_ability: wisdom
spellcaster_level: 3
spell_slots:
  '1': 2
prepared_spells:
  - sacred_flame
  - cure_wounds
  - healing_word
```

`xp` is used by encounter reward tools and defaults to the D&D 5e 2014
CR-to-XP table when omitted and `cr` is present. Keep explicit `xp` when a
custom creature should award a nonstandard amount.

#### Large/Multi-Square Creatures

For creatures larger than 1×1, use a multi-line token:

```yaml
token:
  - OO
  - OO
```

#### Damage Vulnerabilities, Resistances, and Immunities

```yaml
damage_vulnerabilities:
  - radiant
damage_resistances:
  - fire
  - bludgeoning
damage_immunities:
  - poison
  - necrotic
condition_immunities:
  - charmed
  - frightened
  - poisoned
```

Notes:

- The engine accepts both `damage_resistances` and `resistances` for resistance lists.
- The engine accepts both `damage_immunities` and `immunities` for immunities.
- The engine accepts both `damage_vulnerabilities` and `vulnerabilities` for vulnerabilities.
- Per 5e rules, immunity overrides all, and resistance/vulnerability to the same damage type cancel out.

#### On-Hit Effects

Actions can trigger effects on a successful hit:

```yaml
actions:
  - name: Claws
    type: melee_attack
    range: 5
    attack: 5
    damage_die: 2d6+3
    damage_type: slashing
    on_hit:
      - description: "DC 10 CON save or paralyzed"
        save_dc: constitution:10
        if: "target:!undead"           # Only affects non-undead
        flavor_fail: ghoul.paralysis
        fail: status:paralyzed
```

#### Legendary Actions

Legendary creatures list their options under `legendary_actions`. The pool
(`legendary_action_count`, default 3) is full when the creature joins a battle
and refills at the start of its turn. At the end of every *other* creature's
turn the battle offers it one option (`Battle.eval_legendary_action`).

```yaml
legendary_action_count: 3          # optional, defaults to 3
legendary_actions:
  - name: move
    type: move                     # moves up to its speed
    description: Moves up to its speed without provoking opportunity attacks.
    # provokes_opportunity_attacks: true   # opt in for creatures whose move does provoke
  - name: claw                     # attack options use the same shape as `actions`
    type: melee_attack
    range: 5
    attack: 9
    damage_die: 1d8+4
    damage_type: slashing
  - name: bite
    type: melee_attack
    cost: 2                        # "Costs 2 Actions"; default 1
    if: state:grappling
    range: 5
    attack: 9
    damage_die: 1d6+4
    damage_type: piercing
```

How the AI uses them (`GenericController.legendary_action_listener`, shared by
the heuristic, LLM and JEV controllers so there's no extra model call per turn):

- It attacks the best enemy in reach (not only the creature whose turn just
  ended), scoring expected damage per legendary action spent. Options that
  cost more than the remaining pool are not offered.
- If no attack is possible and the creature has a melee legendary attack, a
  `type: move` option walks it (full speed, paid from the pool, movement left
  untouched) to the closest square within reach of a visible enemy. It won't
  approach when below 25% HP.
- The LLM turn prompt's `Resources` line shows `legendary=N/M [...]` so the
  turn planner knows the pool exists.

The VTT stat block shows `(Costs N Actions)` after options with `cost > 1`, and
the combat log prefixes these actions with `[legendary action]`.

**Manually controlled legendary creatures (VTT "manual" controller).** A
`WebController` does not auto-pick; its `legendary_action_listener` queues the
creature on `Battle.pending_legendary_phases`, and the webapp opens a
*legendary action phase* (`Battle.legendary_phase` = the creature's UID) right
after the turn ends instead of advancing initiative:

- The turn panel shows a gold "Legendary Action" banner with the remaining pool
  and an **End Legendary Action** button (other users see "X is taking a
  legendary action…"); the initiative row is outlined in gold.
- The creature's action bar only lists its legendary attacks (with an `L<cost>`
  badge) and, if it has a `type: move` option, a Move that may use its full
  speed (paid from the pool, no opportunity attacks unless
  `provokes_opportunity_attacks: true`). Spells and items are hidden.
- Performing one legendary action ends the window automatically (one option per
  window, per the SRD); the next queued legendary creature gets its window, or
  the battle moves to the next turn. **End Legendary Action** skips it.
- The phase is saved with the battle, so a save made mid-phase resumes there.

#### Monster traits and advanced NPC attacks (vampires, dragons, …)

SRD stat-block traits are plain YAML keys on the NPC; the engine implements them
generically in `natural20/utils/monster_traits.py` (no creature names in code).
All state lives in `entity.attributes`, so it is saved/loaded with the game.

```yaml
legendary_resistance: 3            # N/day; listing `legendary_resistance` under
                                   # `attributes` also works (= 3). Resets on long rest.
legendary_resistance_policy:       # optional; defaults shown
  concentration: auto              # auto | always | never (concentration checks only)
  concentration_min_level: 3       # auto: protect only spells of this level or higher
  concentration_reserve: 1         # auto: uses always kept back for saves against effects
  concentration_per_round: 1       # auto: at most this many concentration rescues per round
regeneration:
  hp: 20                           # regained at the start of its turn (needs >= 1 HP)
  suppressed_by: [radiant, holy_water]   # damage types/attack names that stop it next turn
  blocked_by: [sunlight, running_water]
misty_escape:                      # 0 HP -> mist form instead of dying/unconscious
  blocked_by: [sunlight, running_water]  # destroyed instead
  coffin: {map: crypt, position: [4, 7]} # optional resting place (omit = reaches it off-map)
  recovery_seconds: 3600           # paralyzed in the coffin, then regains 1 HP
undead_fortitude:                  # or list `undead_fortitude` under attributes
  bypass: [bludgeoning]            # damage types that skip the save (default: radiant);
                                   # critical hits always skip it. DC = 5 + damage taken
cannot_speak: true                 # understands its languages but makes no callouts
multiattack:                       # 2+ comma lists = allowed combinations
  - claws,claws2                   # "two attacks, only one of which can be a bite"
  - claws,bite
  # - blade,blade,axe              # a name may repeat within one combination
  # - any_of: [blade, axe]         # "three attacks in any combination"
  #   count: 3
actions:
  - name: claws
    type: melee_attack
    attack: 9
    damage_die: 1d8+4
    damage_type: slashing
    multiattack_group: 1
    additional_damage:             # rider damage on hit (crit doubles its dice)
      - damage_die: 4d6
        damage_type: necrotic
    grapple_instead:               # offers a "(grapple)" variant: no primary damage,
      escape_dc: 18                # target grappled with a fixed escape DC
  - name: bite
    type: melee_attack
    multiattack_group: 1
    damage_die: 1d6+4
    damage_type: piercing
    target_if: [willing, grappled_by_source, incapacitated, restrained]   # any-of
    additional_damage:
      - damage_die: 3d6
        damage_type: necrotic
        life_drain: true           # target HP max -= damage taken, attacker heals it;
                                   # max 0 kills. Cleared on the target's long rest.
  - name: charm
    type: ranged_attack
    range: 30
    force_hit: true
    no_damage: true                # skip the 0-damage attack log line
    target_creature_types: [humanoid]   # PCs count as humanoid
    on_hit:
      - save_dc: wisdom:17
        fail: status:charmed       # source-linked charm (see below)
        duration: 86400
        repeat_save_when_harmed: true
  - name: draining_blade
    type: melee_attack
    damage_die: 3d6+5
    damage_type: necrotic
    on_hit:
      - if: "target:!object"       # no save_dc = always applies on a hit
        fail: effect:no_healing    # target can't regain HP until the attacker's next turn
```

Behaviour notes:

- **Finishing downed foes**: by default AI combatants leave creatures at 0 HP alone while a
  standing foe can be attacked, because hitting a dying creature only adds death save failures.
  Set `finish_downed: true` on a ruthless NPC (or PC) to keep attacking the fallen.
- **Legendary Resistance** applies to any save rolled with a DC (`save_throw(..., opts={'dc': n})`,
  `SaveCheck`, spell and attack riders). Pure probability estimates that call `save_throw`
  without a DC never spend a use. The log reads "… uses Legendary Resistance to succeed instead".
  Concentration checks (damage-triggered CON saves) follow `legendary_resistance_policy`. Under
  `auto` a use is spent only when the spell is level 3 or higher, it is affecting at least one
  living enemy, and more than `concentration_reserve` uses remain. A minor buff is never worth a
  daily use, and the last one stays for a Hold Person or Banishment save. At most
  `concentration_per_round` uses (default 1) go to concentration each round, so a Magic Missile
  or Scorching Ray volley that forces one check per hit cannot drain the pool in a single turn. `always` restores the old
  "spend on every failed save" behaviour; `never` keeps uses for effects only.
- **Sunlight / running water**: a creature is in sunlight with the `in_sunlight` status, a map
  `sunlight: true`, or `sunlight: day` while the campaign clock is not night. Running water is the
  `in_running_water` status or a square in the map's `running_water_squares`.
- **Misty Escape** removes the creature from the battle and map, adds `mist_form`, and stores
  `attributes.misty_escape.recover_at`; `Session.increment_game_time` revives it at 1 HP.
- **Charmed** (`attributes.charmed_by[<charmer uid>]`, `charmed` status): the charmed creature
  can't attack its charmer, counts as `willing` for that charmer's `target_if`, and repeats the
  save whenever the charmer or a non-hostile ally of the charmer damages it.
- **AI**: `AttackAction.ai_value` (used by `GenericController` for normal and legendary picks)
  adds rider damage, life-drain healing when hurt, the follow-up a grapple unlocks (e.g. the
  bite), and `P(fail save) x ai_value` (default 8) for `status:` riders. Speak is never chosen
  as a combat action by the heuristic.
- The VTT action bar shows the grapple variant with a **Grapple** badge; `/action` and MCP
  `actions.execute` honour `grapple_instead: true` in the posted opts.
- Active grapples are visible on the map: a chain links grappler and grappled tokens, and the
  token badges and tile hover hint say who is grappling whom (with the escape DC when fixed).
  See `docs/WEBAPP_BLUEPRINTS.md` → "Grapple indicators".
- A `grapple_instead` hit deals no damage. The grapple ends automatically when the grappled
  creature dies, the grappler is incapacitated, or the target leaves its reach. AI grapplers
  drop dead, unconscious, or non-hostile creatures for free instead of dragging them at half
  speed. See `docs/RULESETS.md` → "Grappler-side rules".

#### Breath weapons and other area abilities (`type: area_save`, recharge)

An NPC `actions` entry with `type: area_save` is a breath weapon or similar
area ability. It is not an attack (it never appears in `attack_options` or a
multiattack). `NpcAreaAction` (`natural20/actions/npc_area_action.py`, action
type `npc_area_ability`) offers it on the creature's turn:

```yaml
actions:
  - name: noxious_breath
    label: Noxious Breath
    type: area_save
    shape: cone              # cone | line | radius (around the creature)
    range: 15                # cone/line length or radius in feet
    width: 5                 # line width
    save: constitution
    dc: 14
    damage_die: 6d6
    damage_type: poison
    half_on_success: true    # default
    recharge: 5-6            # once used, a d6 at the start of each turn readies it on 5+
    cost: action             # or bonus_action
    on_fail: [exhaustion:1]  # also condition:<name> (until the end of the target's next turn)
    success_immunity: {key: draconian_noxious_breath, hours: 24}
    description: Shown on the NPC stat block.
```

- Used recharge abilities are listed in `attributes['recharge_spent']`. `Battle.start_turn`
  rolls for them (`roll_recharges`) and logs the roll.
- `success_immunity` stores `attributes['ability_immunities'][key]` (game-time expiry).
  Creatures sharing the key are immune to *every* ability with that key until it expires.
  It is not saved for player characters (their `attributes` aren't serialized).
- The VTT shows the ability on the action bar (cone/line targeting reuse the spell
  `select_cone` / `select_line` UI). `GenericController` scores it with `ai_value`
  (expected damage to foes minus allies caught in the area); JEV and LLM controllers
  see it as a normal option.

#### Innate spellcasting (`innate_spellcasting`)

Stat-block spellcasting with daily uses instead of spell slots
(`natural20/utils/innate_spellcasting.py`):

```yaml
innate_spellcasting:
  ability: charisma
  dc: 14                     # optional; default 8 + PB + ability mod
  attack: 6                  # optional; default PB + ability mod
  no_material: true          # skips material components for these spells
  at_will: [mage_hand, invisibility]
  per_day:
    2: [disguise_self, dimension_door, sending]
    1: [dominate_person]
```

The spells are added to `prepared_spells()`. Each per-day spell gets a
long-rest resource pool `innate:<spell>` that is spent when it is cast
(it goes through the same `free_casts` path as warlock invocations), and
at-will spells cost nothing. The NPC's `spell_save_dc` and spell attack bonus
use `dc` / `attack`. The webapp stat block lists the spells as "At will" /
"N/day each" with the uses left.

#### Glide

`glide: {fall_reduction_ft: 100}` (or `glide: true`) on an NPC or race
subtracts that many feet from a fall before falling damage is rolled
(`map_stack_descent.glide_reduction_ft`), unless the creature is
incapacitated. The horizontal glide distance is not modelled.

#### Summoning allies (`summons`, e.g. Children of the Night)

Abilities that call creatures (the SRD Vampire's *Children of the Night*, and similar)
are a top-level `summons` list on the NPC — not an entry under `actions`. Engine code:
`natural20/utils/summons.py` and `natural20/actions/summon_creatures_action.py`.

```yaml
summons:
- name: children_of_the_night
  label: Children of the Night
  uses_per_day: 1            # omit = unlimited; recharges on a long rest
  cost: action               # or bonus_action
  blocked_by: [sunlight]     # same blockers as regeneration / misty_escape
  requires: []               # optional: night (campaign clock), outdoors, indoors
  arrival: 1d4               # rounds until they arrive (0 / omitted = immediately)
  duration: 3600             # game seconds before they leave
  dismiss: bonus_action      # cost to dismiss them (false = can't)
  placement_radius: 6        # squares around the summoner to place them
  options:                   # each option is a separate choice
  - {npc: swarm_of_bats, count: 2d4}
  - {npc: swarm_of_rats, count: 2d4}
  - {npc: wolf, count: 3d6, requires: [outdoors]}
```

- **Outdoors** is the map property `outdoors: true`. A map with any `sunlight` setting
  counts as outdoors unless it sets `outdoors: false`.
- **Calling** spends the action and a use, and logs "X uses Children of the Night, calling N …
  (arriving in R rounds)". The creatures are placed near the summoner at the start of its turn
  once the arrival round comes (immediately outside combat). They join its group and roll
  their own initiative. An AI summoner gives each one a fresh `GenericController`; a manually
  controlled summoner shares its `WebController`, so the DM drives them too.
- **Leaving**: they disappear when `duration` elapses, when the summoner dies (creatures still on
  their way are cancelled), when the summoner takes a long rest, or through the
  **Dismiss** action (`DismissSummonsAction`).
- **AI**: `GenericController` scores each option by the expected damage the creatures add,
  discounted by arrival time (zero when no enemy is visible). LLM/JEV prompts list the options
  with the remaining uses and arrival delay.
- **VTT**: the action bar shows one button per option ("Children of the Night: 2d4 Swarm of Bats").
  `/action` with `SummonCreaturesAction` and no `choice` returns a `select_choice` prompt.
- State lives in `attributes.summon_uses`, `attributes.pending_summons` and
  `attributes.active_summons`. Summoned creatures carry `properties.summoner_uid`.
  All of it is saved with the game.

#### Polymorph and beast forms

The *Polymorph* spell (`natural20/spell/polymorph_spell.py`) turns a PC or NPC into a beast
statblock from `npcs/<beast>.yml`. The shared helpers are in `natural20/utils/polymorph.py`,
so other effects that work the same way can reuse them.

```yaml
polymorph:          # templates/items/spells.yml (override per campaign)
  beast_form: wolf          # used for willing / allied targets
  hostile_beast_form: cat   # used for unwilling targets that fail the Wisdom save
```

- **Saves**: an unwilling (opposing) target makes a Wisdom save, and the result is logged in
  both cases: `save_fail` on a failure, a spell miss on a success. Allies are willing and don't
  save. Shapechangers (race `shapechanger`) and creatures at 0 HP are unaffected and get a
  "Polymorph has no effect" log line. The beast's CR is capped at the target's CR (for NPCs) or
  level (for PCs); if the configured form is too strong, the hostile form is used instead.
- **The form**: all statistics, including INT/WIS/CHA, come from the beast. The target gets
  the beast's HP, the `polymorphed` status, and only basic actions: attacks, movement, Dodge,
  Hide, grapple and so on. It can't cast spells, use items, or use class/monster features.
  For a PC, `class_feature()` only answers from the beast's `attributes`, so reactions such
  as Uncanny Dodge and race traits such as Lucky are unavailable in the form. Wild Shape
  keeps them. AI creatures avoid attacking a foe their own side polymorphed while another
  foe can be targeted (`polymorph.polymorphed_by_side_of`). PCs reuse the Wild Shape overlay (`_wild_shape_state` with `source: polymorph`, so the
  druid's "Revert Wild Shape" action is not offered). NPCs snapshot their statblock into
  `properties.polymorph_state`. Both are saved with the game.
- **Ending**: the form ends when the caster's concentration ends (damage, a new
  concentration spell, or dismissal). It also ends when the beast drops to 0 HP: the creature
  reverts, excess damage carries over to its normal HP, and the spell ends. A big hit on a
  tiny beast form is not treated as massive damage against the real creature. Wild Shape
  forms use the same 0 HP carry-over path (`Entity.take_damage` → `end_assumed_form`).

#### Spell areas, material costs and casting requirements

Level 3 SRD spells that cover an ongoing area or have special costs use generic YAML keys
(`templates/items/spells.yml`), so campaign spells can reuse them:

```yaml
revivify:
  consumed_materials:          # spent on cast; the spell is greyed out without them
    - { item: diamond, qty: 1 }
  max_dead_seconds: 60         # corpse age limit (death_info.game_time)
call_lightning:
  requires: [open_sky]         # also: outdoors, indoors
  min_ceiling_ft: 100          # open_sky = map outdoors, or ceiling_height >= this
spirit_guardians:
  ai_no_recast: true           # AI won't recast while already concentrating on it
```

- **Map keys**: `outdoors: true`, `ceiling_height: <ft>` (open sky checks), and `stormy: true`
  or a `weather` string containing storm words (Call Lightning's extra damage die).
- **Persistent zones** (`natural20/spell/extensions/persistent_zone.py`): Spirit Guardians (a
  15-ft emanation that moves with the caster and only hurts creatures opposing the caster), Sleet
  Storm, Stinking Cloud and Grease. A zone can define `slows(entity, pos)`, and
  `Map.difficult_terrain` honours it. Their tile objects subclass
  `natural20/spell/objects/zone_tile.py` (`ZoneTile`), and both zones and tiles survive save/load
  through the `!persistent_zone` and `!zone_tile` serialization tags.
- **Call Lightning** leaves a storm on the caster. While they concentrate, a
  `CallLightningBoltAction` (one action per turn) calls a new bolt anywhere under the 60-ft cloud.
- **Revivify** targets a corpse square (`select_square` with `require_corpse`,
  `corpse_max_age_seconds`, `corpse_allies_only`). It brings the creature back with
  `Entity.revive(hp=1)`.
- **Mass Healing Word** auto-targets the six most wounded allies (`select_target` with
  `auto_pick: most_wounded`).
- **Domain spells** (for example Tempest's Call Lightning and Sleet Storm) count as cleric spells
  for slots, even when they come from another class's list.
- **Post-hit smites** (Searing Smite, Shining Smite) share
  `natural20/spell/extensions/post_hit_smite.py`: a `PostHitSmiteOffer` `on_attack_hit` hook
  (registered in `Paladin.initialize_paladin`) offers one bonus-action option per slot at or above
  the spell's level. Shining Smite registers `targeted_advantage_override`, a 5-ft dim
  `light_override` and an `invisibility_suppressed` marker on the target while the paladin
  concentrates.
- **Beacon of Hope** registers `save_advantage_modifier` (Wisdom), `death_save_advantage_modifier`
  (read by `Entity.death_saving_throw`) and `max_healing` on every target. Dice healing goes
  through `natural20/utils/healing.py` `effective_heal_roll(target, roll)`, which returns
  `DieRoll.maximized()` under `max_healing` (spell heals, healing potions, potion-effect items,
  Aura of Vitality).
- **Daylight** offers a choice: a point (places a `DaylightSource` map object, bright 60 / dim 60)
  or a held object (a `light_override` on the caster). Overlapping `Darkness` objects from a spell
  of level 3 or lower are dispelled, ending the caster's Darkness concentration. Both map objects
  subclass `natural20/spell/objects/spell_area_source.py` and save/load via the `!magical_darkness`
  and `!daylight_source` tags. Effects that hold a map handle can define `relink_maps(maps)`,
  which `relink_spell_entities` calls on load.
- **Curses**: spell YAML `curse: true` (Hex) marks an effect as a curse, as does the `cursed`
  status. Item YAML `cursed: true` marks a cursed item. **Remove Curse**
  (`natural20/utils/curses.py`) ends curse effects (the caster loses concentration), clears
  `cursed`, and lists equipped cursed items in `properties['curse_broken_items']`.
- **Aura of Vitality** leaves an `AuraOfVitalityEffect` concentration marker. While it lasts,
  `AuraOfVitalityHealAction` (bonus action, once per turn) heals one creature within 30 ft for
  2d6 through a `spell_heal` item.
- **VTT**: each spell has an action-bar icon (`static/spells/spell_<id>.png`) and an effect icon
  (`static/assets/effect/<id>.png`), plus a cast animation in `spell_effects.js` and the 3D
  `spellCatalog.js`. Spirit Guardians draws a 15-ft aura around the caster, an active Call
  Lightning storm shows a halo on the caster (`status_effects.js`), and Sleet Storm squares get a
  `.sleet-storm-marker` overlay.

### NPC Overrides in Maps

When placing NPCs in a map, use `overrides` to customize their behavior
without modifying the base template:

```yaml
legend:
  R:
    name: Rose Durst
    type: npc
    sub_type: ghost
    group: b
    overrides:
      # Identity
      entity_uid: rose_durst         # Unique ID for save/load and controllers
      label: Rose Durst              # Display name

      # Appearance
      token_image: rose_durst.png    # Custom portrait (in assets/)

      # Stats
      hp: 40                         # Override hit points

      # Behavior
      passive: true                  # Won't attack (non-hostile)
      dialog: true                   # Can be talked to

      # Stealth (spawn hidden)
      statuses:
        - hidden
      hidden_stealth: 12             # Stealth check result

      # Conversation
      backstory: |
        You are Rose Durst, a ten year old ghost girl...
      conversation_handler: llm      # "llm" for AI-driven dialog
      conversation_buffer:           # Initial/greeting messages
        - message: "There's a monster in our house!"
          target: all                # "all" = broadcast, or entity_uid
      backstory_buffer:              # Messages to seed LLM context
        - message: "There's a monster in our house!"
          target: all

      # Conversation keywords → game state changes
      converstation_keywords:
        - keyword: "mentioned_basement"
          update_state:
            - map: attic
              target: secret_stairs
              state: opened
            - map: attic
              target: secret_stairs_note
              state: unconcealed
```

#### Override Fields Reference

| Field | Type | Description |
|---|---|---|
| `entity_uid` | string | Unique identifier for the entity |
| `label` | string | Display name override |
| `token_image` | string | Custom token image filename. When omitted, the token is `token_<slug>.png`, where the slug is the lowercased `kind` (or `sub_type`/`name`) with non-alphanumerics turned into `_` (e.g. "Swarm of Bats" → `token_swarm_of_bats.png`). `/assets/` searches the campaign, imported campaigns, expansion packs, the ruleset overlay, then `templates/assets/` |
| `hp` | int | Override max HP |
| `passive` | bool | Non-hostile; won't initiate combat |
| `dialog` | bool | Entity can be talked to |
| `kill_reactions` | bool | Default true for dialog NPCs; `false` stops the NPC from speaking after it kills a PC |
| `backstory` | string | LLM backstory prompt for conversation |
| `outward_appearance` | string | Optional. Physical description (body, face, clothing, notable worn items) for `[OBSERVE]`, Look/perception notes, and NPC self-knowledge in conversation prompts. When omitted, the server derives a short description from race, class, gear, and kind. |
| `conversation_handler` | string | `"llm"` for AI dialog |
| `conversation_buffer` | array | Pre-seeded conversation messages |
| `backstory_buffer` | array | Messages to seed the LLM conversation context |
| `converstation_keywords` | array | Keywords that trigger game state changes |
| `statuses` | array | Initial status conditions (`hidden`, etc.) |
| `hidden_stealth` | int | Stealth roll value if spawned hidden |
| `events` | list | YAML event hooks (`died`, `activate`, …). Same schema as object `events`. |
| `merchant` | object | Shop config: `wares`, `buyback_rate`, `llm_pricing`. Opens the merchant trade UI on talk. See `docs/MERCHANT_TRADING.md`. |

### NPC Dialog & Conversation

NPCs with `dialog: true` can be spoken to via the chat interface. The
conversation system supports:

1. **Simple conversation buffer** — Pre-written messages the NPC says on first
   meeting:
   ```yaml
   conversation_buffer:
     - message: "Hello, traveler!"
       target: all
   ```

2. **LLM-driven conversation** — Set `conversation_handler: llm` and provide
   a `backstory`. The NPC uses the backstory as its system prompt and responds
   dynamically via the configured LLM provider.

3. **Keyword triggers** — When the LLM mentions specific keywords in spoken
   dialogue **or** `[ASIDE: ...]` stage direction, game state changes can be
   triggered:
   ```yaml
   converstation_keywords:
     - keyword: "secret_passage"
       update_state:
         - map: dungeon_1
           target: hidden_door
           state: unconcealed
   ```

The NPC system prompt template (`npc_system_prompt.txt`) is:
```
You play as an NPC named as "{name}" in a Dungeons and Dragons game world.
...
<start_of_backstory>
{backstory}
Your alignment is: {alignment}
```

---

## Sidekick NPCs

Sidekicks stay NPCs (stat block, conversation LLM). What changes is **party membership** and **who drives movement/actions**. Runtime records live in `session.session_state['sidekicks']` (save/load). Mid-game joins do not rewrite `index.json`.

```yaml
# game.yml
character_selection:
  sidekick_slots: 1       # 0 = one hero pick; 1 = one PC and one sidekick
sidekicks:
  - entity_uid: npc_squire
    selectable: true          # appears on login character select
    spawn_with_party: true
    owners: []                # claimed at login
    sidekick_class: sidekick_warrior   # optional; requires expansion pack
    role: attacker
    auto_follow: true         # optional; trails the focused character out of combat
  - entity_uid: npc_guide
    selectable: false
    owners: [gomerin]         # second character for that user
    require_session:          # same pattern as companions
      quest_accepted: true
```

- **Login pick:** `selectable: true` entries appear in a **Sidekicks** section, separate from player characters. With `character_selection.sidekick_slots: 0` (default), the player still picks a single hero from either section. Set `sidekick_slots: 1` (Death House) so each player chooses one PC **and** one sidekick.
- **Second character:** YAML `owners: [username]` joins them after login; they appear as extra POV tokens.
- **Mid-game:** player **Invite to party** (talking distance), NPC tags `[JOIN_PARTY]` / `[LEAVE_PARTY]`, or DM `dm.sidekick` / `POST /admin/sidekick`. A join refreshes the owner's POV picker and shows a toast (`{name} joined the party.`).
- **Control:** owning players move and take actions (`WebController`). Conversation stays on the NPC LLM — players never speak *as* the sidekick.
- **Stat block:** sidekicks keep the NPC creature sheet (not a PC character sheet). Any player can open the full 5e stat block for a player-controlled NPC (sidekick, familiar, or assigned controller). Other NPCs show only portrait, name, and description (description follows `suppress_dialog_descriptions`).
- **Death saves:** in-party sidekicks fall unconscious at 0 HP instead of dying immediately.
- **Travel:** in-party sidekicks follow the party like companions (teleporter / map-set / `place_party`).
- **Auto-follow:** an in-party sidekick with `auto_follow: true` trails the focused (POV) character out of combat, within 5 ft (chained in a line when several sidekicks follow). Toggled by DM via `dm.sidekick` / `POST /admin/sidekick` with `op: auto_follow` (plus `enabled`); the campaign YAML default applies at join. Synced by `webapp/sidekick_follow.py` on POV changes, party membership changes, and the NPC movement worker tick.

Tasha’s Expert / Spellcaster / Warrior tables are **not** in core. Opt in with the `tashas_sidekicks` expansion pack (see [EXPANSION_PACKS.md](EXPANSION_PACKS.md)). Starting level is the average PC level; CR ≤ 1/2 is pack policy (DM `force` can override).

---

## Player Characters

Player character sheets live in `characters/` and define a full D&D 5e
character.

Class features come from the class YAML's `progression` (`level_N.class_features`), so a campaign that overrides `char_classes/<class>.yml` must keep those sections. Otherwise features such as the Fighter's Action Surge and Extra Attack silently disappear. Subclasses are top-level keys on the sheet: `martial_archetype` (Fighter), `roguish_archetype` (Rogue), `arcane_tradition` (Wizard), and `divine_domain` (Cleric).

**Eldritch Knight:** set `martial_archetype: eldritch_knight`, then list wizard cantrips under `cantrips` and known spells under `prepared_spells`. Spell slots follow the PHB third-caster table, keyed under `fighter` (3 first-level slots at Fighter 5). Wizard-list spells are cast from those slots using INT (`Fighter.borrowed_spell_list_classes` → `Entity.spell_list_classes_for`). Weapon Bond and War Magic are not implemented.

### Initial journal entries

PC YAML may include a `journal` (or `initial_journal`) list. Each item is
either a string or an object with `title`, `text`, `kind` (default `quest`),
optional `tags`, and optional `seed_id` for de-duplication across save/load.

Entries are seeded once per `seed_id` and start **unread** so players get a
notification. NPC YAML supports the same `journal` list; hooks are copied to a
PC's journal the first time that PC talks to the NPC.

After any battle that lasts at least one combat round, the NPC LLM writes a
first-person recap into each PC's journal (`kind: combat`) and a memory item
for each conversation-aware NPC (`dialog: true`) on the battle map. Recaps
include world time, map / landmark annotations when available, deaths, and
conversation beats from the fight. Disable per campaign with:

```yaml
battle_combat_recap:
  enabled: false
```

To give the DM time to narrate, AI-controlled combatants (NPCs and AI/LLM
PCs) can wait for the DM to end their turn instead of passing initiative
automatically. A human DM is assumed: if no DM is logged in, the held turn
waits until one logs in and ends it. The DM can also flip it live with the **DM ends AI turns** checkbox in the Battle
Turn Order panel; that choice is saved with the game and overrides this
default:

```yaml
battle_pacing:
  dm_ends_ai_turns: true
```

When a battle starts, the combat log shows the DM (only) a roster:
- HP totals for each team.
- One line per combatant in initiative order, with:
  - starting HP and max HP, AC, speed and passive Perception;
  - equipped weapons and armor (damage, range, AC);
  - NPC attacks with to-hit and damage;
  - conditions, concentration, active buffs, damage defenses, Legendary
    Resistance and beast form.

Each turn also adds a DM-only line with that creature's current HP, AC and
conditions. Both come from `natural20/utils/combat_roster.py` and are logged
with `visibility='dm'`.

Every team that includes a player character also gets a party briefing. Only
that team's members, and the players who control them, can see it:
- `[Party]` lines give full stats for partymates and sidekicks (HP, AC, gear,
  conditions).
- `[Foes]` lines describe each enemy the team can see: size, outward
  appearance (YAML `outward_appearance`, otherwise derived from race, class
  and gear), rough health (unhurt / lightly wounded / bloodied / badly
  wounded / down), visible gear and visible conditions. They never show HP,
  AC, to-hit, defenses or creature type.

Hidden or invisible enemies are left out.

Turn each part off per campaign:

```yaml
combat_log:
  dm_summary: false       # roster at start of combat
  dm_turn_status: false   # HP/conditions line at the start of each turn
  party_briefing: false   # partymates + enemy descriptions for players
```

When a `dialog: true` NPC kills a player character mid-battle, its conversation
LLM is told who it killed and how (attack/spell, damage, critical, massive
damage vs. bled out, who is still standing). It may speak one in-character line
aloud, such as a taunt or lament, or stay silent. Opt an NPC out with
`kill_reactions: false` in its YAML, or turn it off campaign-wide:

```yaml
npc_kill_reactions:
  enabled: false
```

See `docs/CONVERSATION_RAG.md` → "Kill reactions".

**Animate Dead on fallen PCs.** Animate Dead (1-minute cast, so out of combat
only) can raise a dead player character as a zombie or skeleton under the
caster's control. The PC's sheet, inventory, and login assignment are kept, but
its token is hidden while the undead walks around. Destroying the undead drops
the PC's corpse where the undead fell, so it can be looted or revived as usual.

```yaml
journal:
  - seed_id: opening_hook
    title: Why You're Here
    kind: quest
    tags: [hook, opening]
    text: Detective Jaro's summons brought you to the gate tonight.
```

```yaml
---
name: Crysania
race: elf
subrace: high_elf
pronoun: she/her/hers
classes:
  wizard: 2                          # class: level
description: A high elf mage with a mysterious noble background
outward_appearance: A pale high elf in fine but travel-stained robes, ink-stained fingers, and watchful violet eyes.
level: 2
xp: 300                               # Total campaign XP
hit_die: inherit                     # Use class hit die
max_hp: 12

ability:
  str: 10
  dex: 15
  con: 14
  int: 18
  wis: 12
  cha: 8

# Spellcasting
prepared_spells:
  - burning_hands
  - firebolt
  - magic_missile
  - shield
  - mage_hand

spellbook:                           # Wizard spellbook (known spells)
  - mage_armor
  - magic_missile
  - shield
  - find_familiar
  - mage_hand

languages:
  - common
  - elvish
  - goblin

equipped:
  - dagger

inventory:
  - type: healing_potion
    qty: 1
  - type: arcane_focus
    qty: 1
  - type: spellbook
    qty: 1
```

`level` is the total character level and `classes` stores per-class levels.
The XP progression system keeps both values in sync when a level-up is
applied. If `xp` is omitted, the character starts at `0` XP for progression
purposes. Campaigns can also use DM-gated or event-gated level-up grants
instead of XP thresholds. See `docs/DND_5E_2014_PROGRESSION.md` for
thresholds, reward endpoints, progression modes, and level-up behavior.

### Feats, auras and edition overrides

Player-character sheets (and NPCs) may carry these optional keys:

```yaml
feats: [great_weapon_master, blind_fighting, squire_of_solamnia]
feat_editions:                       # play one feat by another edition's rules
  great_weapon_master: 5e-2024
class_features: [abjure_foes, radiant_strikes]  # features the class YAML doesn't grant
channel_divinity_uses: 3             # override the class table
condition_immunities: [frightened]
auras:                               # YAML auras (class auras are built in)
  - name: aura_of_warding
    save_bonus: cha                  # owner's ability modifier (min +1)
    condition_immunity: [charmed]    # only charmed / frightened are aura-warded
    condition_save_advantage: [frightened]  # advantage on saves to avoid/end these
    creature_types: [draconian]      # optional: only creatures of these types/tags
    requires: [see, hear]            # optional: covered creatures must see/hear the owner
    range: 10
```

- **Auras** (`natural20/utils/auras.py`): paladin Aura of Protection, Courage
  and Devotion are built in (10 ft, 30 ft with `aura_expansion`). They apply to
  the owner and friendly creatures in range while the owner is conscious. Save
  bonuses from several auras don't stack; the best one applies.
  `creature_types` matches words in the creature's `race` / `kind` /
  `creature_type` (an aurak's Aura of Command covers only `draconian`s).
  `requires: [hear]` fails for deafened or unconscious creatures, and
  `requires: [see]` fails when the creature is blinded or can't see the owner.
  `condition_save_advantage` is checked by `save_throw` when the caller passes
  `opts={'condition': 'frightened'}` (or `saving_throw_type`).
- **Frightened** (`natural20/utils/fear.py`): fear is tied to its source.
  While the source is in sight, the creature has disadvantage on attacks and
  ability checks. Fear effects can end on damage or limit the creature to one
  of action, bonus action, or movement per turn (2024 Abjure Foes).
- **Great Weapon Master**: after a melee critical hit or dropping a creature to
  0 HP on your turn, a bonus-action "Hew" attack with the same weapon is
  offered. Under 2024 rules, heavy weapon hits also add the proficiency bonus
  to damage. The 2014 −5/+10 option is not modelled.
- **Blind Fighting** gives 10 ft blindsight.

**Feat attack options.** A feat YAML under `feats/<id>.yml` (or an entity's
own properties) may define `attack_options`, which the engine offers as
"before attack" free actions or "on hit" prompts:

```yaml
# feats/vanguard_training.yml
name: Vanguard Training
attack_options:
  - id: guided_strike
    name: Guided Strike
    timing: before_attack            # before_attack | on_hit
    advantage: true
    extra_damage: 1d8                # added on a hit
    uses: proficiency_bonus          # int or proficiency_bonus
    recharge: long_rest
    expend: on_hit                   # on_hit (spent only if the attack hits) | on_use
    once_per_turn: true
  - id: rattling_blow
    name: Rattling Blow
    timing: on_hit
    uses: 1
    recharge: short_rest
    save: {ability: wisdom, dc_abilities: [int, wis, cha]}  # DC 8 + PB + best listed mod
    on_fail: {condition: frightened, rounds: 1}
    on_success: {next_attack_disadvantage: true}
```

Class YAML can declare `attack_options` too (top level or under
`subclasses.<name>`, gated by `feature`). These keys go beyond the feat form:

```yaml
attack_options:
  - id: dreadful_strike
    feature: dread_ambusher
    timing: on_hit
    pool: dreadful_strike            # shared resource pool (default: id)
    uses: ability_mod:wisdom         # also int | proficiency_bonus
    min_uses: 1
    extra_damage: {3: 2d6, 11: 2d8}  # class level -> dice
    damage_type: psychic
    variants:                        # offered together with the base option
      - id: sudden_strike
        feature: stalkers_flurry
        follow_up_attack: {range: 5} # free attack, same weapon, other creature near the target
      - id: mass_fear
        feature: stalkers_flurry
        save: {ability: wisdom, dc_abilities: [wis], radius: 10}  # target + creatures within 10 ft
        on_fail: {condition: frightened, rounds: 0}               # 0 = until the start of your next turn
```

Variants share the base option's pool and once-per-turn slot. On a hit the
controller gets one `select_reaction` choice per option. The follow-up attack
is a `GrantedAttackAction` (`natural20/actions/granted_attack_action.py`). It
costs no action and can only target the recorded creatures. It lapses at the
start of the creature's next turn, and is saved with the battle state
(`granted_attack`).

**Other feat YAML mechanics** (`natural20/utils/feat_mechanics.py`). A feat id
on the sheet with no `feats/<id>.yml` anywhere in the resolution chain is a
no-op (e.g. `wayfarer_ability_score_improvements`; bake ability increases into
the sheet). The same blocks may sit directly in an NPC's YAML.

```yaml
# feats/<id>.yml
resource_pools:                      # limited uses; saved with the creature
  luck_points: {max: proficiency_bonus, restore_on: long_rest}  # max: int | proficiency_bonus | ability_mod:X
weapon_attack_rules:                 # exceptions to weapon-attack rules (never spells)
  - weapons: {type: ranged_attack}   # filter: type, weapon_type (word in id/name), property/properties
    ignore_cover: [half, three_quarters]
    no_long_range_disadvantage: true
    no_adjacent_enemy_disadvantage: true
  - weapons: {weapon_type: crossbow}
    ignore_properties: [loading]
  - weapons: {weapon_type: crossbow, property: light}
    extra_attack_ability_damage: true   # Light-property extra attack adds the ability modifier
luck:                                # natural20/utils/luck_points.py
  pool: luck_points
  self_advantage: true               # after your attack / save / check fails: roll another d20, keep the higher
  impose_disadvantage: true          # after an attack hits you: attacker rolls another d20, keeps the lower
  ai_min_chance: 0.25                # offered only when the extra die can flip the result this often
free_casts:                          # same keys as class free_casts (see Data-driven classes)
  magic_initiate_wizard:
    spell_source: spell_abilities    # pick from the sheet's spell_abilities map...
    spell_level: 1                   # ...the spell of this level...
    spell_list: wizard               # ...on this class list (optional)
    pool: magic_initiate_wizard      # pool from resource_pools above
```

- Luck is asked through the normal reaction prompt, only in combat, and only
  for rolls with a known DC/AC (attacks, `save_throw(opts={'dc': n})`, death
  saves, ability checks given `dc`). Events: `luck_point` in the combat log.
- The halfling reroll-1s trait is `lucky` in race/subrace `race_features` (or
  NPC `attributes`/`class_features`). A `lucky` *feat* on the `feats` list does
  not reroll 1s (`luck_points.has_reroll_ones_trait`).
- The **Loading** property is enforced for player characters
  (`natural20/utils/weapon_loading.py`): one Loading shot per Attack action,
  even with Extra Attack (other weapons may take the remaining attacks).
  Bonus-action, reaction and legendary attacks are single shots. NPC stat-block
  attacks are exempt.
- `spell_abilities: {spell: ability}` on the sheet sets the casting ability of
  feat- or race-granted spells (`Entity.spell_source_ability`). A free-cast
  spell cast inline (e.g. Shield as a reaction) by a creature with no matching
  slot spends the free-cast pool.
- SRD feats (Archery, Magic Initiate) are in `templates/feats/`. Non-SRD 2024
  feats (Lucky, Sharpshooter, Crossbow Expert) are in the
  `players_handbook_2024` expansion pack.

### Data-driven classes (YAML-only)

A class whose `char_classes/<klass>.yml` has no Python mixin
(`initialize_<klass>` on `PlayerCharacter`) is run from YAML alone by
`natural20/entity_class/data_driven.py` (`DataDrivenClass`). The mechanic
blocks are read by `natural20/utils/class_mechanics.py`. Each block can sit at
the class top level or under `subclasses.<name>`. A block only applies once the
character has its `feature` (the id defaults to the block key).

```yaml
spellcasting:
  ability: intelligence
  progression: half_round_up   # full | half | half_round_up | third, or slot_table: {level: [slots...]}
  prepared: true
spell_list: {0: [firebolt], 1: [cure_wounds]}
subclass_property: artificer_specialist   # sheet key naming the subclass
subclasses:
  alchemist:
    features: {3: [experimental_elixir], 5: [alchemical_savant]}
    spells: {3: [healing_word]}           # always prepared from that class level
resource_pools:
  flash_of_genius: {max: ability_mod:intelligence, min: 1, restore_on: long_rest}
save_assists:                             # reaction: add a bonus to an ally's failed save
  flash_of_genius: {bonus: ability_mod:intelligence, pool: flash_of_genius, range: 30}
spell_roll_bonuses:                       # +mod to one damage/heal roll of a spell
  alchemical_savant: {bonus: ability_mod:intelligence, damage_types: [fire], healing: true,
                      requires_items: [alchemists_supplies]}
free_casts:                               # cast without a slot, paid from a pool
  restorative_reagents: {spells: [lesser_restoration], pool: restorative_reagents}
  spell_storing_item: {spell_property: spell_storing_item, pool: spell_storing_item}
rest_items:                               # items created on a rest (random table or fixed)
  experimental_elixir: {count: {3: 1, 6: 2}, table: [elixir_of_healing, ...], expire_on_rest: true}
craft_options:                            # "Craft: <item>" actions paid with a spell slot
  experimental_elixir: {cost: spell_slot, min_slot: 1, items: [...], requires_items: [alchemists_supplies]}
infusions:                                # +N to an item named on the sheet's `infusions`
  enhanced_defense: {magic_bonus: {2: 1, 10: 2}, applies_to: armor}
initiative_bonuses:                       # added to initiative rolls
  - {feature: dread_ambusher, bonus: ability_mod:wisdom}
speed_bonuses:                            # walking speed, optionally lost in some armor
  - {feature: roving, amount: 10, unless_armor: [heavy]}
first_turn_movement:                      # extra movement on the first turn of each combat
  - {feature: dread_ambusher, amount: 10}
senses:                                   # darkvision (or +N on top of existing darkvision)
  - {feature: umbral_sight, darkvision: 60, darkvision_extend: 60, evade_darkvision: true}
feature_actions:                          # self-targeted action paid from a pool
  - {feature: tireless, activation: action, pool: tireless,
     temp_hp: {dice: 1d8, bonus: ability_mod:wisdom, min: 1}}
rest_effects:                             # applied when a rest finishes
  - {feature: tireless, rest: short_rest, reduce_exhaustion: 1}
attunement:                               # raise the magic item attunement limit (default 3)
  - {feature: magic_item_adept, max: 4}
  - {feature: magic_item_savant, max: 5, ignore_prerequisites: true}
```

`evade_darkvision` hides the creature from viewers that rely on darkvision
while it stands in an unlit square (`Map` sight check). Blindsight and
truesight still see it. Note that `on:` can't be used as a YAML key, because
PyYAML reads it as `true`; that is why `rest_effects` uses `rest:`.

**Mixin classes with YAML subclasses.** Classes that do have a Python mixin
(e.g. the ranger) can still declare `subclass_property` + `subclasses` and the
blocks above. Subclass features, always-prepared spells and subclass
`resource_pools` then work the same way as for data-driven classes. The 2024
ranger overlay (`templates/rulesets/5e-2024/char_classes/ranger.yml`) adds
`spellcasting: {progression: half_round_up}`, which replaces the mixin's 2014
slot table.

Sheet keys that go with these blocks:

- `infusions: [{infusion: enhanced_defense, item: shield}]` and
  `spell_storing_item: {spell: cure_wounds, item: rod}`. D&D Beyond doesn't
  export these, so the DM sets them on the sheet.
- `rest_granted_items` records the items made on rests, so they can expire on
  the next rest. Created items carry `crafted_by: <entity_uid>` in the inventory.

**Effect consumables.** `item_class: EffectConsumableItem` items can heal
(`heal`, plus `heal_bonus: creator_ability:intelligence` taken from the maker in
`crafted_by`), grant `buffs` (`speed_bonus`, `fly_speed`, `ac_bonus`,
`attack_die`, `save_die`) for `duration_seconds`, and apply `creator_riders`,
which are gated by the maker's features (e.g. temporary HP from Restorative
Reagents). The buffs are a serializable `ConsumableBuffEffect`. When a granted
fly speed runs out, the creature lands.

**Race keys.** Race and subrace YAML may list `spells` (always prepared;
the casting ability comes from the sheet's `spell_abilities: {spell: ability}`)
and `save_advantage: {source, abilities}` (e.g. 2024 Gnomish Cunning), and
`inspiration_on_long_rest: true` (2024 Human Resourceful: Heroic Inspiration
after every long rest). A sheet
with `race_edition: 5e-2024` loads the race from the 2024 overlay
(`templates/rulesets/5e-2024/races/`) even in a 2014 campaign.

Actions with the class attribute `ai_in_combat = False` (crafting, for
example) are left out of AI option lists while enemies are up.

#### Warlock (SRD 5.2) and the Archfey patron

The 2024 warlock overlay (`templates/rulesets/5e-2024/char_classes/warlock.yml`)
sits on top of the warlock mixin and uses these extra blocks:

```yaml
feature_choices: [eldritch_invocations]   # sheet list whose entries count as class features
free_casts:
  - {feature: contact_patron, spell: contact_other_plane, pool: contact_patron,
     auto_succeed_save: true}
  - {feature: mystic_arcanum, spell_property: mystic_arcanum, spell_key: 6,
     pool: mystic_arcanum_6}               # sheet: mystic_arcanum: {6: summon_fiend}
  - {feature: fiendish_vigor, spell: false_life, at_will: true, maximize: true, self_only: true}
feature_actions:                           # Magical Cunning: regain half the Pact slots
  - {feature: magical_cunning, activation: minute, pool: magical_cunning,
     restore_spell_slots: {class: warlock, fraction: 0.5, full_with_feature: eldritch_master}}
senses: [{feature: devils_sight, devils_sight: 120}]   # see in magical darkness
benefits: [{feature: eldritch_mind, benefit: concentration_advantage}]
cantrip_riders:                            # Agonizing / Repelling Blast
  - {feature: agonizing_blast, spell_property: invocation_spells,
     default_spell: eldritch_blast, damage_bonus: ability_mod:charisma}
  - {feature: repelling_blast, spell_property: invocation_spells,
     default_spell: eldritch_blast, push: 10, max_size: large}
```

When both a free cast and a Pact slot can pay for a spell, the free cast is
used first. The sheet key `class_spells: {warlock: [...]}` adds spells from
other class lists (Pact of the Tome, Book of Ancient Secrets).

The Archfey patron (`expansion_packs/players_handbook_2024/char_classes/warlock.yml`)
adds four more generic blocks:

- `spell_riders` (`natural20/utils/spell_riders.py`): optional riders offered
  when casting the listed spells (Steps of the Fey: Refreshing/Taunting Step;
  Misty Escape: Disappearing/Dreadful Step).
- `reaction_casts` (`natural20/utils/reaction_casts.py`): cast a spell as a
  reaction to a trigger (Misty Escape: Misty Step when hit).
- `hit_reactions`: Uncanny-Dodge style reactions to a hit, with a pool,
  `restore_with_slot`, `halve_damage` and `retaliate` (Beguiling Defenses).
- `condition_immunities: [{feature, conditions}]`.

Taunted creatures (`natural20/utils/taunt.py`) have disadvantage on attacks
against anyone but the taunter until the taunter's next turn. Kender Taunt
(race YAML `taunt`, `TauntAction`) and Taunting Step both use it. The War
Caster `opportunity_attack_spell` benefit (`natural20/utils/reactive_spell.py`)
lets a creature answer an opportunity attack with a one-target action spell.

### Condition-save spells, off-plane creatures and summoned spirits

`ConditionSaveSpell` (`natural20/spell/condition_spells.py`) runs save-or-suffer
spells from a YAML `condition_save` block. It is used by Banishment, Hold
Monster, Hypnotic Pattern, Dominate Beast/Person/Monster, Phantasmal Force and
Calm Emotions. The block supports repeat saves, `off_plane: banished`,
`restrict_actions: [attack, spell]` (an `action_restriction` effect) and
`ally_condition_immunities: [charmed, frightened]`. With the last one, allies
in the area skip the save and get a `condition_immunity` effect instead
(Calm Emotions). The spell ends once no target and no warded ally is left.

**Off-plane creatures** (`natural20/utils/off_plane.py`: Banishment, Blink)
keep their square but can't be targeted and aren't caught by area effects.
The state is in `attributes['off_plane']`. When the creature returns and its
square is taken, it moves to the nearest free square.

**Terrain cost.** Map objects can set `movement_cost` above 2. Each square
then costs the extra amount on top of difficult terrain
(`Map.extra_terrain_cost`). Plant Growth's overgrowth uses `movement_cost: 4`,
so a square costs 4 ft of movement per foot.

**Summoned spirits** (`SummonSpiritSpell`, `natural20/spell/summon_spirit_spell.py`).
A spell YAML `summon_spirit` block names the variants (picked with
`select_choice`), each with an NPC template and base HP. The block also sets
`ac_base`, `hp_per_slot` and `damage_bonus_base`, and the spell scales them by
slot level. Attacks use the caster's spell attack bonus, and `save_dc: spell`
uses the caster's spell save DC. The spirit acts right after the caster in
initiative. It disappears when concentration ends (`SummonSpiritEffect`).
It also vanishes when it drops to 0 HP: the spell sets the NPC property
`vanish_on_death`, and `make_dead` then ends the summoner's spell (and
concentration) through `natural20.utils.summons.vanish_on_death` instead of
leaving a corpse. Any NPC with `vanish_on_death: true` is simply removed when
it dies. The Multiattack count is rewritten as one `{any_of: [...], count: N}`
entry, so a spirit with melee and ranged versions of an attack can mix them.
A `death_throes` block with `on_spell_end: true` also explodes when the spell
ends while the spirit is still alive (the demon spirit).
Summon Fiend (PHB 2024 pack) is the reference implementation; its spirits live
in `expansion_packs/players_handbook_2024/npcs/fiendish_spirit_*.yml` with
tokens in that pack's `assets/`.

**Teleport after an attack.** An NPC attack with `teleport_after_attack: <feet>`
(the yugoloth spirit's Claws) opens a window when it hits or misses. The
creature can then use `PostAttackTeleportAction`
(`natural20/actions/post_attack_teleport_action.py`, action type
`post_attack_teleport`) to teleport for free to an unoccupied square it can see
within that range. The window closes when used, is replaced by the next attack,
and ends at the start of the creature's next turn. AI controllers use it to
reach a new foe while attacks remain, or to escape when badly hurt.

**NPC keys.** `magic_resistance: true` gives advantage on saves against magic.
`death_burst` (alias `death_throes`) is an area save when the creature dies:

```yaml
death_burst: {radius: 10, save: dexterity, dc: 15, damage_die: 2d10,
              damage_type: fire, half_on_success: true}
# Chain lightning variant (aurak draconian): the nearest creature within
# `range`, then up to `arc_targets` more within `arc_range` of it (foes of the
# dying creature first). A failed save adds a condition until the end of the
# target's next turn (`TimedConditionEffect`).
death_throes: {targeting: chain, range: 30, arc_range: 15, arc_targets: 2,
               save: dexterity, dc: 14, damage_die: 2d8, damage_type: lightning,
               on_fail_condition: stunned}
```

Stunned creatures automatically fail Strength and Dexterity saves, and attack
rolls against them have advantage.

### Placing Players in Maps

Players can be placed directly in a map file:

```yaml
player:
  - position: [1, 4]
    sheet: characters/halfling_rogue.yml
    overrides:
      entity_uid: rumblebelly
  - position: [0, 4]
    sheet: characters/high_elf_mage.yml
    overrides:
      entity_uid: crysania
```

Or placed via the `entities` list with a legend reference.

---

## Objects

Objects are interactable map elements defined in `items/objects.yml`. Each
object type has a key that matches the `type` field in legend entries.

### Common Object Properties

| Property | Type | Default | Description |
|---|---|---|---|
| `name` | string | — | Display name |
| `description` | string | — | Flavor text |
| `color` | string | — | ASCII display color |
| `item_class` | string | — | Python class name (in `natural20.item_library.*`) |
| `default_ac` | int | — | Armor class |
| `max_hp` | int | — | Hit points |
| `hp_die` | string | — | Dice expression for random HP |
| `token` | char/array | — | Map character(s) |
| `token_image` | string | — | Image name for web UI |
| `token_image_transform` | string | — | CSS transform for the image |
| `profile_image` | string | — | Portrait image |
| `image_gallery` | list | — | Gallery entries `{id, label, image, description}` for character sheet and JRPG dialog portraits |
| `passable` | bool | varies | Can entities walk through? |
| `placeable` | bool | varies | Can entities stand on this square? |
| `opaque` | bool | false | Blocks line of sight? |
| `wall` | bool | false | Blocks pathfinding? |
| `cover` | string | `"none"` | Cover type: `none`, `half`, `three_quarter`, `total` |
| `allow_hide` | bool | false | Can entities hide here? |
| `movement_cost` | int | 1 | Movement cost multiplier (2 = difficult terrain) |
| `movement_cost_swim` | int | — | Cost for swimming |
| `swimmable` | bool | false | Swimming movement allowed? |
| `interactable` | bool | false | Can entities interact? |
| `interact_distance` | int | 5 | Interaction range (feet) |
| `concealed` | bool | false | Hidden until revealed |
| `secret` | bool | false | Magically hidden |
| `perception_dc` | int | — | DC to notice concealed object |
| `light` | object | — | `{bright: feet, dim: feet}` |
| `image_offset_px` | [x, y] | — | Pixel offset for token image |
| `buttons` | array | — | UI interaction buttons |
| `events` | array | — | Event handlers |
| `damages` | array | — | Damage on trigger |
| `ability_checks` | object | — | Investigation/ability checks |
| `inventory` | array | — | Starting items |
| `notes` | array | — | Discoverable notes |

### Built-in Object Types

These are defined in the default `items/objects.yml`:

| Type Key | Class | Description |
|---|---|---|
| `barrel` | Object | Half cover, interactable container |
| `bottomless_pit` | Object | Passable but not placeable; opaque: false |
| `brazier` | Object | Light source (bright 20, dim 10) |
| `briar` | Object | Difficult terrain, half cover, allows hiding |
| `campfire` | ProximityTrigger | Light source + fire damage on contact |
| `chest` | Chest | Lockable container with open/close UI |
| `ground` | Ground | Default passable terrain |
| `note` | Note | Readable text note |
| `pit_trap` | PitTrap | Concealed trap — fall + spike damage |
| `stone_wall` | StoneWall | Opaque, impassable wall |
| `switch` | Switch | On/off toggle |
| `tree` | Object | Half cover, allows hiding |
| `water` | Object | Swimmable, difficult terrain (movement cost 2) |
| `wooden_door` | DoorObject | Openable/lockable door |
| `door_top` / `door_*` / `corner_door_*` | DoorObjectWall | Directional wall-embedded doors |
| `window_top` / `window_*` / `corner_window_*` | WindowObjectWall | Wall-embedded windows (glass or shutters; see below) |

### Doors

```yaml
legend:
  "=":
    name: front_door
    type: wooden_door
    state: closed                    # "open" or "closed"
    locked: true                     # Optional: locked by default
    key: iron_key                    # Item required to unlock
    buttons:
      - action: open
        label: Open the door
```

Doors auto-detect their orientation (horizontal `-` vs vertical `|`) based on
adjacent walls. Tokens change appearance based on state:

| State | Horizontal | Vertical |
|---|---|---|
| Closed | `=` | `║` |
| Open | `-` | `:` |

### Windows

Wall windows are **DoorWall combos** (`WindowObjectWall`) with an opening on one edge. They share the door-wall placement UI (top/bottom/left/right plus corner variants) and appear in the object spawner under **Windows**.

```yaml
legend:
  "▭":
    name: parlor_window
    type: window_top          # window_top/bottom/left/right or corner_window_*
    state: closed
    cover_pane: glass         # glass (see-through, total cover) or opaque (shutters)
    inside_cover: half        # half (+2 AC) or three_quarter (+5 AC) when open
    window_size: medium       # small | medium | large — prone/"crouching" Medium creatures have total cover
    max_pass_size: any        # any | tiny | small | medium | large | huge | gargantuan — largest creature that can climb through
    barred: false             # barred from the inside; cannot be opened from outside
    difficult_terrain: true   # climbing through an open window costs extra movement (default)
    window_material: wood     # wood | stone | glass | iron (frame / shutter)
    wall_material: stone      # surrounding wall; may differ from the window
```

In **edit mode**, click the window fixture label to edit these fields (open/closed, glass vs shutter, cover, opening size, pass size, bars, difficult terrain, and materials). Painted windows store per-cell overrides on `map.layer_placements` so two `window_top` tiles can differ. Tile mouseover shows the pass-size limit (for example, “Fits Small or smaller”).

Rules of thumb (PHB cover):

- **Closed glass** — creatures can see through, but attacks cannot target through the pane (total cover). Break or open the window first.
- **Closed opaque shutter** — blocks vision and attacks, matching `window_material`.
- **Open** — creatures on the **inside** of the opening have half or three-quarters cover (sill / frame). A prone (crouching) creature of typical size has total cover behind the wall under the sill; Tiny creatures may have total cover even while standing, depending on `window_size`.
- **Barred** — a bar on the inside prevents opening from the outside. Inside creatures can unbar or open (opening clears the bar).
- **Movement** — stepping through an open window is difficult terrain unless `difficult_terrain: false`. `max_pass_size` is a hard cap on who can cross the opening (for example `small` blocks Medium and larger). Walking along the interior cell without crossing the pane is unaffected. Default `any` means no extra size gate.

The existing `window` object type (peek/fall-through to a lower map-stack floor) is unrelated; use `window_top` and friends for wall openings.

### 3D models (VTT `/3d`)

Campaigns can pick a 3D mesh per object type without changing the 2D map. See **`docs/VTT_3D.md`** and skill `.cursor/skills/n20-vtt3d-models/SKILL.md`.

Wall look is separate from object meshes. Set a campaign default in `vtt3d.yml` (`walls.style`: `dungeon`, `cave`, `mansion`, `gothic`, `wood`, or `office`). A map may override with top-level `vtt3d.walls`, or inherit from `render.palette` (`interior` → mansion, `dungeon` → stone, `cave` / `cavern` → organic limestone with stalactites/stalagmites, `office` / `modern` → office drywall). Optional `albedo` points at a repeating texture under campaign `assets/`.

```yaml
# user_levels/<campaign>/vtt3d.yml
walls:
  style: mansion   # dungeon | cave | mansion | gothic | wood | office; maps may override
models:
  portcullis_b:
    kind: portcullis
  dungeon_secret_door1:
    kind: secret_door
```

Or on a legend entry / object YAML:

```yaml
legend:
  "~":
    type: portcullis_b
    vtt3d:
      kind: portcullis
```

Built-in door kinds: `door` (oak), `secret_door` (stone slab), `portcullis` (iron grate), `wall`, `skip`. Floor hatches: `trap_door` / `secret_trapdoor` (wooden hatch; open = hole + lid), `pit_trap` (cracked cover until sprung, then a spiked pit). Types whose name contains `portcullis`, `trapdoor` / `trap_door`, or `pit_trap`, or that are secret doors, infer automatically. Concealed secret hatches and unperceived pits are omitted from the 3D object list until discovered.

Place **stairs** from the terrain palette (`type: stairs`). They are invisible and fully passable on the 2D map. In 3D they become a run of medium-creature steps (about 7.5 in risers) along `squares` from the base to the top. A filled 2-wide strip is meshed as **double stairs**. A 2×2 block, compact L/U (two flights in a small well), or circulating ring is a **circular spiral**: pie-wedge treads around a round newel, so the flights meet without a corner gap. `open_well` (boolean) drops the newel and leaves a hollow shaft; `wall_attached` (boolean) extends treads to the well and adds a square enclosure. Campaigns can default those flags in `vtt3d.yml` under `models.stairs`. `height` is feet of rise (default 8, matching wall height). **To go down**, set `height` to a negative value (for example `-8`) and pick squares from this floor toward the lower end; the first square stays at this floor and later squares step downward, punching the battlemap floor after the base. `style` uses the same materials as walls and doors (`dungeon`, `mansion`, `gothic`, `wood`, `office`, or empty to match the map). `solid` (default true) fills the volume under the treads so the staircase is not see-through. Edit the object and use **Pick squares on map** to click the ordered path (clicks go through walls and other fixtures on those squares).

**Chasms** (`type: chasm`) are open pits in 3D: the floor tile is omitted and a stone shaft sinks below the tabletop (deeper when `fall_distance` is set). Concealed chasms stay hidden until perceived. `bottomless_pit` uses the same mesh.

### Chests

```yaml
legend:
  c:
    name: treasure_chest
    type: chest
    key: iron_key                    # Required key to unlock (optional)
    inventory:
      - type: healing_potion
        qty: 2
      - type: arrows
        qty: 20
    notes:
      - note: "A mysterious chest"
      - note: "Contains a healing potion and arrows"
        investigation_dc: 10         # DC to discover this note
    buttons:
      - action: investigation_check
        label: "Investigate Chest (DC 14)"
      - action: open
        label: "Open Chest"
    ability_checks:
      investigation:
        prompt: "Inspect Chest?"
        success: "You verify that the chest is not trapped."
        dc: 10
    events:
      - event: investigation_check_success
        message: "You find a healing potion and arrows in the chest."
```

### Traps

#### Pit Trap

```yaml
legend:
  T:
    name: pit_trap
    type: pit_trap
    image_offset_px: [30, 30]
    # Inherited from objects.yml defaults:
    # damages:
    #   - attack_name: Fall Damage
    #     damage_die: 1d6
    #     damage_type: bludgeoning
    #   - attack_name: Spike Damage
    #     damage_die: 2d10
    #     damage_type: piercing
    # events:
    #   - event: activate
    #     message: "You fall into a pit trap!"
    #     update_state:
    #       - target: target
    #         state: prone
```

Pit traps are `concealed` by default and trigger when an entity moves onto them.
They have a `perception_dc` for passive detection.

#### Trap Door

```yaml
legend:
  d:
    name: trap_door
    type: trap_door
    target_map: basement_1
    target_position: [3, 3]
    concealed: true
    perception_dc: 15
```

Trap doors combine door + teleporter behavior. When opened and stepped on,
they teleport the entity.

### Teleporters

Teleporters link maps together **within the same map set**. When an entity enters the teleporter's
square, they're moved to the target position (and optionally a different map in that set).
Cross-set travel uses a **party-travel teleporter** (`party_travel: true`) or the DM tools
Activate Map Set / Place Party — see [Map Sets](MAP_SETS.md).

```yaml
legend:
  T1:
    name: stairs_down
    type: teleporter
    target_map: dungeon_1            # Map name from game.yml
    target_position: [3, 7]          # Destination [x, y]
    notes:
      - note: "Stairs leading down"

  # Cross-set exit: confirm, then transport the whole party.
  # Cancel keeps the party on this map; Interact / tile hover retries
  # while still standing on the pad.
  TX:
    name: Leave town
    type: teleporter
    party_travel: true
    target_map: forest_clearing
    prompt_title: Leave town?
    prompt: |
      The entire party will be transported to the forest clearing.
      Continue?

  # Teleporter with event trigger (e.g., reveal something on the target map)
  T2:
    name: secret_passage
    type: teleporter
    entity_uid: secret_teleporter
    target_map: dungeon_1
    target_position: [6, 11]
    events:
      - event: activate
        update_state:
          map: dungeon_1
          target: hidden_door
          state: unsecret,opened

  # Gate entry until session flags are set (e.g. investigation proofs)
  T3:
    name: cathedral_doors
    type: teleporter
    target_map: cathedral
    target_position: [5, 5]
    requires_session:
      any_of: [manor_notes_found, sewer_symbol_found, prison_record_found, magical_proof_rose]
      min_count: 2
      bypass_any: [ophelia_invitation]
      inventory_proofs: [black_rose_pin]
    deny_message: "You need more proof before the doors will open."
    deny_title: "Sealed"
```

`requires_session` is checked in `Teleporter.on_enter` against `session.session_state`.
Use `all_of` for every flag required, or `any_of` + `min_count`. `bypass_any` opens on a single flag (e.g. written invitation). `inventory_proofs` adds +1 toward `min_count` per carried item type. Legacy `visibility_flag: some_flag` is treated as `all_of: [some_flag]`.

To open a door only after a boss dies, put a `died` event on that NPC (see [Triggers & Events](#triggers--events)) with `set_session`, then list the same flag here:

```yaml
# On the boss (map legend overrides or NPC YAML)
events:
  - event: died
    set_session:
      dungeon_cleared: true

# On the exit teleporter
requires_session:
  all_of: [dungeon_cleared]
deny_title: Sealed
deny_message: The door will not open.
```

### Switches

```yaml
legend:
  S:
    name: lever
    type: switch
    state: off
    on_event: open_gate
    off_event: close_gate
    on_message: "You pull the lever. A gate opens!"
    off_message: "You push the lever back. The gate closes."
```

### Proximity Triggers

Trigger effects when entities come within range:

```yaml
legend:
  f:
    name: campfire
    type: campfire
    light:
      bright: 20
      dim: 10
    distance: 0                      # Trigger radius (0 = same square)
    multi_trigger: true              # Can trigger multiple times
    events:
      - event: activate
        message: event.campfire.flames
        damages:
          - attack_name: Fire Damage
            if: "target:!prone"
            damage_die: 1
            damage_type: fire
          - attack_name: Fire Damage
            if: "target:prone"
            damage_die: 1d6
            damage_type: fire
```

---

## Terrain

### Terrain Summary

| Type | Passable | Placeable | Opaque | Cover | Movement Cost |
|---|---|---|---|---|---|
| Ground (`.`) | yes | yes | no | none | 1 |
| Wall (`#`) | no | no | yes | total | — |
| Water | yes | — | no | none | 2 (1 if swimming) |
| Briar | yes | yes | no | half | 2 |
| Tree | yes | yes | no | half | 1 |
| Barrel | — | — | no | half | — |
| Bottomless pit | yes | no | no | none | 1 |

### Difficult Terrain

Any object with `movement_cost: 2` is difficult terrain. Entities spend
double movement to enter these squares. Swimming entities use
`movement_cost_swim` instead for water.

### Cover

Cover provides AC bonuses and affects targeting:

| Cover | AC Bonus | Targeting |
|---|---|---|
| `none` | +0 | Normal |
| `half` | +2 | Normal |
| `three_quarter` | +5 | Normal |
| `total` | — | Cannot be targeted |

---

## Items & Inventory

### Weapons (`items/weapons.yml`)

```yaml
dagger:
  name: Dagger
  type: melee_attack
  subtype: weapon
  proficiency_type: [simple]
  properties: [light, thrown, finesse]
  damage: 1d4
  damage_type: piercing
  range: 5
  cost: 2
  weight: 10
  flavor_text: A small blade, easily concealed.   # optional italic quote on the item card
  description: >-                                 # optional rules/body text on the item card
    A simple weapon favored by rogues and travelers.
  thrown:
    range: 30
    range_max: 120
  meta:
    noise_source: 5
    noise_target: 5
```

The character sheet **Basic Info** tab uses a D&D 5e-style layout for **player characters**: a header
(portrait, name, class/level, race, background, alignment, languages, XP) and
three columns (ability scores / saves / skills / other proficiencies / inspiration;
combat stats, defenses, conditions, and resources; description and features). The
Other Proficiencies panel lists armor, weapons, and tools from class, race, and
background. Defenses always lists resistances, immunities, vulnerabilities, and
condition immunities (or “None”). Conditions lists live `entity.statuses` (internal
flags such as `squeezed` are omitted). Inspiration is a pip next to proficiency
bonus: **Inspiration** on `5e-2014`, **Heroic Inspiration** on `5e-2024`. The DM
can click the pip (or MCP `dm.set_resource` with `resource_type=inspiration`) to
grant or spend the token. Markup lives in
`n20-webapp/webapp/templates/_basic_info_sheet.html` with styles in
`n20-webapp/webapp/static/sheet.css`. Objects without ability scores get a
simpler portrait + AC/HP fallback. DM HP inputs, rest buttons, and resource
controls keep the same element IDs as before.

**NPCs** use a monster-style 5e stat block instead of the PC sheet
(`_npc_stat_block.html`): size/type/alignment, AC, HP, speed, ability scores,
saves/skills/senses, challenge, traits, and actions. Spellcasters include a
Spellcasting trait with ability, **spell save DC** (8 + proficiency + ability
mod), spell attack bonus, and spells grouped by level — the same parenthetical
as a Monster Manual block (`spell save DC 13, +5 to hit with spell attacks`).
YAML `spell_ability` / `spellcasting_ability` selects the ability; optional
`spell_save_dc` / `spell_attack_bonus` override the computed numbers. DMs always see the full
block. Players see the complete block for NPCs they (or the party) control —
sidekicks, familiars, and NPCs with assigned player controllers. For every other
NPC, players get a public card (`_npc_public_card.html`) with portrait, name, and
description only (description still respects `suppress_dialog_descriptions`).
Equipment and rest controls on an NPC sheet stay limited to the DM and that
NPC’s controllers. Access logic lives in
`n20-webapp/webapp/blueprints/helpers/npc_stat_block.py`.

Clicking a weapon or item on the character sheet Equipment tab opens a parchment
item card (icon, rarity, flavor, description, and stats). Container cards also
list stowed contents so players can inspect, use, or equip those items without
taking them out first. Optional YAML keys that appear on the card:

| Key | Shown as |
|---|---|
| `flavor_text` / `flavor` / `lore` | Italic quote under the title |
| `description` | Body text |
| `rarity` | Common / Uncommon / Rare / Very Rare / Legendary |
| `magical`, `magic_bonus` | Magical badge |
| `requires_attunement` | Attunement note, attuned / pending state and Attune / End buttons |
| `weapon_mastery` | Mastery chips when the 2024 ruleset is enabled |
| `content` | Letter body |

Bundled SRD weapons, armor, adventuring gear, and SRD magic items under
`templates/items/` already include `flavor_text` (original short lines for
mundane gear; SRD 5.1 / 5.2 wording for magic-item **descriptions**, CC BY 4.0).
Campaign-unique or non-SRD items belong in `user_levels/<campaign>/items/` or an
expansion pack — do not copy adventure-module boxed text into `templates/`.

**Item icons follow the same ownership.** If an item id exists only in the
campaign (or an imported campaign / expansion pack) and not in
`templates/items/`, its PNG must live at `<owner>/assets/items/<id>.png`. Do
not put campaign-only art in `n20-webapp/webapp/static/assets/items/`. Generic
SRD icons stay in bundled static. The VTT serves `/assets/items/<file>` from
the campaign folder first (then imports, expansion packs, then bundled). Set
`image: <template_slug>` on a campaign alias when it should reuse SRD art
(for example Death House `bulleyes_lantern` → `bullseye_lantern`).

### Equipment packs (`items/equipment_packs.yml`)

Starting kits shown in the character builder. Campaign files merge with
`templates/items/equipment_packs.yml`. Each pack has `name`, `cost`, and
`items` in either of these forms:

```yaml
# Mapping (used by campaign packs such as Monster Hunter's Pack)
monster_hunters_pack:
  name: "Monster Hunter's Pack"
  cost: 33
  items:
    wooden_stake: 3
    torch: 3

# List of single-key dicts (bundled SRD packs)
explorer_pack:
  name: "Explorer's Pack"
  cost: 10
  items:
    - bedroll: 1
    - backpack: 1
```

The builder preview and chargen apply both shapes. A background may set
`default_equipment_pack: monster_hunters_pack` to pre-select a pack.

### Equipment (`items/equipment.yml`)

```yaml
chain_mail:
  name: Chain Mail
  type: armor
  subtype: heavy
  ac: 16
  cost: 75
  weight: 55
  metallic: true
  mod_cap: 2                         # Max DEX modifier to AC
```

### Item mechanics keys

These keys work on any equipped item (armor, weapons, wondrous items):

```yaml
cloak_of_the_glade:
  name: Cloak of the Glade
  type: equipment
  skill_advantage: [stealth]         # advantage on these skill checks while equipped
  resistances: [lightning]           # damage resistances while equipped
  usable: true
  item_class: MagicSpellItem         # cast a spell from the item
  spell: misty_step
  level: 2
  charges: 1
  activation: bonus_action           # action (default) | bonus_action | reaction | free
  on_use: [next_attack_advantage]    # riders after use; next attack before end of turn has advantage

wyrm_spear:
  name: Wyrm Spear
  type: melee_attack
  additional_damage:
    - damage_die: 3d6
      damage_type: force
      target_creature_types: [dragon]  # whole-word match: "dragonborn" doesn't count
```

Items with a non-action `activation` show up as a Use Item option even after
the action is spent, as long as the matching resource is left.

More item keys (Wand of the War Mage, Periapt of Proof against Poison, …):

```yaml
spell_attack_bonus: 1                  # added to spell attack rolls (needs attunement if required)
spell_attack_ignore_cover: [half]      # cover levels ignored by spell attacks
damage_immunities: [poison]            # while equipped
condition_immunities: [poisoned]       # while equipped
alternate_modes: [hoopak_sling]        # the same item can also attack as these weapon ids
```

Item `condition_immunities` are also picked up by the D&D Beyond importer.

#### Passive bonuses and attunement

These keys (read by `natural20/utils/item_mechanics.py`) only work while the
item is *active*: listed in the creature's `equipped` property and, when the
item has `requires_attunement: true`, attuned. Attunement is tracked by the
optional character/NPC property `attuned: [item_key, ...]`. The D&D Beyond
importer and the character builder write it. A sheet without `attuned` treats
every equipped item as attuned (legacy behaviour) until its first attunement
change, which seeds the list from the equipped attunement items.

An item that needs attunement but isn't attuned gives only its nonmagical
benefits. Its `magic_bonus`, `magical` (resistance bypass), `additional_damage`
riders, `resistances`, `skill_advantage`, `save_advantage_against`, protection
`effect`s, `usable` activation and the keys below are all ignored. An optional
`unattuned:` block overrides fields for the mundane form, for example
`unattuned: {damage: 1d8}` on a Flame Tongue.

#### Managing attunement

The rules are in `natural20/utils/attunement.py`. DMG 2014 and DMG 2024 agree
on them, so both rulesets behave the same.

- **Attuning** takes a short rest spent focused on that one item, while the
  creature holds or carries it. A request is queued in
  `attunement_pending: [{item, mode: attune|end}]` and completes at the end of
  the next rest. A short rest completes one change and a long rest two (its two
  hours of light activity).
- **Limit:** a creature can be attuned to at most 3 items. The queue counts
  toward this limit, and only one copy of an item can be attuned. Class YAML
  `attunement` entries raise the limit (Artificer Magic Item Adept/Savant/Master
  in `expansion_packs/tashas_cauldron/`). A sheet can override it with
  `attunement_limit: N`.
- **Prerequisites** come from item YAML: `attunement_class`, `attunement_race`,
  `attunement_alignment` (a string or a list) and `attunement_spellcaster: true`.
  A class `attunement` entry with `ignore_prerequisites: true` waives them.
- **Ending attunement voluntarily** also takes a short rest. It is impossible
  while the item's curse holds (`cursed: true`); Remove Curse ends it.
- **Losing attunement:** it ends when the creature dies, and when the item has
  been out of the creature's possession for 24 hours of campaign time (tracked
  in `attunement_separated`).
- **DM override:** a DM request with `force` applies the change immediately and
  ignores prerequisites. The limit still applies.
- **Campaign rules:** `game.yml` `ruleset_overrides` accepts `attunement_limit`,
  `attunement_requires_rest: false` (house rule: changes are instant outside
  combat), `attunements_per_short_rest` and `attunements_per_long_rest`.

In the VTT, the character sheet's equipment tab has an **Attunement** panel. It
shows the used slots, every attunement item the character carries, and
Attune / End attunement / Cancel buttons (plus DM-only *now* buttons). The item
card has the same controls, and equipped items that lack attunement are marked
*Not attuned*. The panel calls `POST /attunement`, and MCP uses `dm.equipment`
with `op=attune|end_attunement|cancel_attunement`.

```yaml
ioun_stone_of_insight:
  type: accessory
  equippable: true
  requires_attunement: true
  ability_bonus: {wis: 2, max: 20}   # add to scores; max caps the result (never lowers it)

amulet_of_health:
  ability_set: {con: 19}             # the score becomes 19 unless already higher

ioun_stone_of_mastery:
  proficiency_bonus: 1               # added to the proficiency bonus

ioun_stone_of_awareness:
  cannot_be_surprised: true

ioun_stone_of_regeneration:
  regain_hp: {amount: 15, every_seconds: 3600, min_hp: 1}   # heals as the campaign clock advances
```

Item bonuses are applied on top of the stored scores, so `ability:` on a
sheet holds the creature's own scores. Accessories with a `magic_bonus` (Ring
of Protection, Ioun Stone of Protection) add it to AC.

#### Dancing weapons

A weapon with a `dancing` block (the SRD Dancing Sword variants
`dancing_longsword`, `dancing_shortsword`, `dancing_scimitar`,
`dancing_greatsword`, `dancing_rapier`) gives its wielder a bonus action to
toss it:

```yaml
dancing_scimitar:
  type: melee_attack
  requires_attunement: true
  dancing:
    attacks: 4        # strikes before it flies back
    move_feet: 30     # flight per bonus action
    leash_feet: 30    # must stay this close to the wielder
```

`DancingWeaponAction` (`natural20/actions/dancing_weapon_action.py`, registered
through the class-feature registry for PCs and wired in `Npc.available_actions`)
offers three modes:

- **Toss** (bonus action, item equipped and attuned): the weapon leaves the
  wielder's hand, flies to an empty square next to the chosen creature and
  attacks it with the wielder's attack roll and damage (an ordinary
  `AttackAction` with the item, so proficiency, magic bonus and weapon mastery
  apply).
- **Command** (bonus action): the hovering weapon flies again and strikes. After
  the last strike it returns to the wielder's hand, or drops into their
  inventory when no hand is free. If the wielder is more than `leash_feet` away
  when commanding it, it falls to the ground instead.
- **Catch** (free; adjacent in combat, anywhere out of combat): the wielder
  grabs it and it stops dancing.

State lives in `properties['dancing_weapons']` on the wielder; the map marker
is a `DancingWeaponTile` (saved as a `!zone_tile`). The VTT encodes the mode
and item in the action type (`dancing_weapon:<mode>:<item>`).

### Consumables

```yaml
# In a character or object inventory:
inventory:
  - type: healing_potion
    qty: 1
  - type: arrows
    qty: 20
  - type: arcane_focus
    qty: 1
```

### Containers and size limits

Mundane and magical containers declare how much they can hold. Weight and
volume are optional; **`max_item_size`** is the largest creature/item size
the container will accept (`tiny` < `small` < `medium` < `large` < `huge` <
`gargantuan`).

The character sheet Equipment tab lists items stored in carried containers
with an “in Backpack” grouping badge. Players can search and sort that list,
and can inspect, use, or equip nested items without taking them out first.

```yaml
backpack:
  type: container
  weight: 5
  capacity_lbs: 30
  capacity_cu_ft: 1
  max_item_size: small          # rejects medium or larger

bag_of_holding:
  type: container
  extradimensional: true
  capacity_lbs: 500
  capacity_cu_ft: 64
  max_item_size: large          # contents do not add to carry weight
```

Defaults when `max_item_size` is omitted: **small** for normal packs, **large**
for extradimensional bags, **medium** for map objects such as chests and barrels.

Items default to **tiny** (weapons/armor **small**) unless YAML sets `size`.
Dead NPCs and player characters can be picked up (`carry`) and stored like
objects: they use the creature's size and a size-based body weight plus gear.
Carrying requires remaining Strength × 15 lb capacity. Dropping a body onto
the ground places the creature back on the map.

#### Placeable gear (`placeable_object`)

An inventory item with `placeable_object: <object type>` becomes that map object
when it is dropped on the ground (ground **Transfer** dialog). The SRD `chest` gear
item uses this (`placeable_object: chest`, 25 lb, holds 300 lb / 12 cu ft):

- The placed object starts with the item's container contents as its inventory
  and is tagged `portable_item: <item key>`. It then behaves like any map chest
  (open, close, loot, store, lock).
- Any map object with `portable_item` offers **Pick Up**. Picking it up removes
  the object and returns the item, contents and all, to the carrier. It needs
  Strength × 15 lb capacity for the item weight plus everything inside; otherwise
  the button is disabled with the reason.
- To make a hand-placed map chest portable, add `portable_item: chest` to its
  legend entry. Map chests without it stay fixed.

Helpers live in `natural20/utils/portable_object.py`. The drop hook is
`Container._place_object_on_ground`. Stacking two containers of the same item in
one inventory pools their contents.

---

## Triggers & Events

### Object Events

Objects can register event handlers that fire on specific actions:

```yaml
events:
  - event: activate                  # Trigger type
    message: "The trap springs!"     # Display message
    damages:                         # Damage effects
      - attack_name: "Fire Damage"
        damage_die: 2d6
        damage_type: fire
        if: "target:!prone"          # Condition
    update_state:                    # State changes
      - target: target               # "target" = triggering entity
        state: prone
      - map: dungeon_1               # Change state on another map
        target: hidden_door
        state: opened
```

#### Event Types

| Event | When |
|---|---|
| `activate` | Object is activated (trap, trigger) |
| `open` | Door/container opened |
| `close` | Door/container closed |
| `light` | Fireplace lit |
| `put_out` | Fireplace extinguished |
| `on_enter` | Entity enters the square |
| `start_of_turn` | At the start of an entity's turn |
| `investigation_check_success` | Successful ability check |
| `died` | Creature is killed (`Entity.make_dead`). Use on NPC YAML or map `overrides`. |

`update_state` with `target: session` writes keys into `session.session_state` (the same flags `requires_session` reads). Prefer the dedicated `set_session` key — it runs before `campaign_event` so listeners see the new flags:

```yaml
# On an NPC (map legend overrides, or the NPC sheet)
events:
  - event: died
    set_session:
      dungeon_cleared: true          # dict, or a bare string / list of names
    campaign_event: dungeon_cleared  # optional: notify campaign listeners
```

If `game.yml` uses `progression.mode: milestone` (or `event`) and lists that same key under `progression.events`, the engine grants the configured level-ups to all PCs the first time the event fires. See [DND_5E_2014_PROGRESSION.md](DND_5E_2014_PROGRESSION.md).

`set_session` / session `update_state` accept `{flag: true}`, a flag name string, or a list of names.

Campaign `game.yml` can also set the same flags when a fight ends (`battle_end_hooks`: `map`, `require_groups_defeated`, `session_flags`, `once_session_key`). Use that as a backup when the boss is the last enemy in its group.

#### Condition Syntax

The `if` field supports simple condition checks:

| Pattern | Meaning |
|---|---|
| `equipped:item_name` | Entity has item equipped |
| `target:!prone` | Target is NOT prone |
| `target:prone` | Target IS prone |
| `target:!undead` | Target is NOT undead race |

### Notes & Discovery

Objects can have discoverable notes with perception or investigation DCs:

**Edit mode:** Drag a **Note** from the object spawner onto a tile to create one. Click the info-sign or fixture label to edit text, Perception/Investigation/Religion/Arcana DCs, linked images (`static/assets/objects/<filename>`), and the info-sign offset. Drag the info-sign on the map to nudge that offset. Edit mode shows every note, including those that would normally be hidden behind a DC.

```yaml
notes:
  - note: "You notice strange markings on the wall"
    perception_dc: 15              # Passive perception DC to discover
  - note: "The markings form a map to the treasure room"
    investigation_dc: 12           # Requires active investigation check
  - note: "Holy symbols were filed off the altar face"
    religion_dc: 14                # Requires Religion interact check on this object
  - note: "Residual abjuration on the rose sigil"
    arcana_dc: 13                  # Requires Arcana interact check
  - note: "A pit trap!"
    highlight: true                # Visual highlight on discovery
    image: pit_trap_image          # Image to display
```

Place a dedicated note object (`type: note`) when the clue is not attached to another fixture. `image_offset_px: [top, left]` positions the info-sign on the tile (drag in edit mode). `hide_map_token: true` hides the `N` sprite when the art is already in the background.

Play-time **DM notes** (hamburger → DM Notes, or Alt+click a square) are a separate overlay: only the dungeon master can see them, they are not written to map YAML, and NPCs never learn them. See [DM_NOTES.md](DM_NOTES.md).

**NPC-only annotations** (separate from `notes`) are invisible to player characters but visible to NPCs in conversation `[OBSERVE]` / `[ANNOTATIONS]` when perception passes:

```yaml
annotations:
  - text: "Key hangs on the third hook beneath the bar lip."
    viewers: [mara_bartender, pip_barmaid]   # omit to allow any NPC
```

Allowed NPCs see annotations when the object is in line of sight (`[OBSERVE]`, Look, `[ANNOTATIONS]`). Use `perception_dc` on **`notes`**, not annotations, when PCs must roll to discover something.

Use `notes` for clues PCs should discover; use `annotations` for staff knowledge (till codes, key locations, house procedures).

### Edit-mode property schemas (`edit_ui`)

Edit mode uses declarative YAML schemas to drive the fixture property editor. Schemas are **editor-only metadata** — they are not read at runtime during play.

**Where schemas live**

| Location | Use for |
|---|---|
| `items/objects.yml` → `edit_ui:` | Per object-type forms (teleporter, note, chest, …). Merged with bundled templates; campaigns override fields here. |
| `edit/fixtures.yml` → `fixtures:` | Map constructs that are not object catalog entries (e.g. `spawn_point` → `player_spawn_points`). |
| `edit/fixtures.yml` → `mixins.notes` | Reusable notes group auto-appended to every object `edit_ui` unless it already defines `notes` / `image_offset_px`. |

Bundled defaults: `templates/items/objects.yml`, `templates/edit/fixtures.yml`. Campaign files at the same relative paths override templates (imports follow normal campaign merge order).

**Example — object type (`teleporter` in `items/objects.yml`)**

```yaml
teleporter:
  item_class: Teleporter
  token: [T]
  edit_ui:
    label: Teleporter
    scope: [legend, entity]
    groups:
      - id: destination
        label: Destination
        fields:
          - key: target_map
            label: Target map
            type: map_ref
            choices_from: campaign.maps
            required: true
          - key: target_position
            label: Arrival square
            type: point
            relative_to: target_map
            required: true
```

**Example — map fixture (`spawn_point` in `edit/fixtures.yml`)**

```yaml
fixtures:
  spawn_point:
    label: Player spawn
    scope: [player_spawn_points]
    groups:
      - id: placement
        fields:
          - key: name
            type: string
          - key: position
            type: point
            relative_to: current_map
            required: true
```

**Supported field types**

| `type` | Purpose |
|---|---|
| `string`, `text` | Short or multiline text |
| `boolean` | Checkbox |
| `integer` | Whole number |
| `color` | Hex color picker |
| `point` | `[x, y]` tile coordinate; use `relative_to: current_map` or `target_map` |
| `point_list` | Ordered `[[x, y], …]` squares (e.g. stair base → top); pick on the map in edit mode, including tiles that already have walls or other objects |
| `offset_px` | `[top, left]` pixel offset |
| `map_ref` | Campaign map name; use `choices_from: campaign.maps` |
| `enum` | Fixed choices via `choices:` list (`select` is accepted as an alias) |
| `note_list` | Repeatable discoverable notes (text, DCs, image filename) |
| `inventory_list` | Container contents (`[{type, qty}, …]`); autocomplete via `choices_from: campaign.items` |

**Conditional fields:** `visible_when: { field_key: value }` hides a field until another value matches.

Container types (`chest`, `fireplace`, `barrel`, tavern containers, or any object with `inventory:` / `item_class: Chest|Fireplace`) automatically get an **Items in container** group with autocomplete search against equipment, weapons, and magic items (`GET /edit/catalog/items?q=`). Changes persist to the map YAML `inventory` field.

Nested loot is supported via `contents` on container item rows (for example a pouch inside a chest):

```yaml
inventory:
  - type: human_skin_pouch
    qty: 1
    contents:
      - type: gold_piece
        qty: 11
      - type: silver_piece
        qty: 60
```

The pouch item itself should be `type: container` in `items/equipment.yml`. Taking the pouch from the chest preserves its nested coins.

The Python module `natural20/edit_schema.py` resolves dynamic choices (map list, tile bounds, item catalog), validates submissions server-side, and merges notes/inventory mixins — campaigns define **what** is editable, not validation logic.

---

## Groups & Factions

The group system controls which entities are hostile, neutral, or friendly
to each other. Define groups in `game.yml`:

```yaml
groups:
  a:                               # Players
    default: true
    enemies: [b, e]
    neutral: [c]
    allies: [d]
  b:                               # Standard enemies
    enemies: [a, e]
    neutral: [c]
  c:                               # Neutral wildlife
    neutral: [a, b]
  d:                               # Allied NPCs
    allies: [a]
  e:                               # Hostile-to-all faction
    enemies: [a, b, c, d]
```

Assign groups in legend entries:

```yaml
legend:
  g:
    type: npc
    sub_type: goblin
    group: b                       # This goblin is hostile to players
  n:
    type: npc
    sub_type: human_guard
    group: d                       # This guard is allied with players
```

---

## Multi-Map Campaigns

See also [Map Sets](MAP_SETS.md) for partitioning maps into party POV worlds
(random encounters, overland travel). Teleporters may only target maps in the
same set; campaigns with no `map_sets:` key treat every map as the implicit
`root` set.

### Defining Maps

Register all maps in `game.yml`:

```yaml
maps:
  road: maps/road
  entrance: maps/entryway
  basement_1: maps/basement_1
  basement_2: maps/basement_2
  attic: maps/attic
```

### Linking Maps with Teleporters

Use teleporters to create transitions between maps:

```yaml
# In maps/entrance.yml
legend:
  S:
    name: stairs_to_basement
    type: teleporter
    target_map: basement_1           # References the map key in game.yml
    target_position: [0, 4]
    notes:
      - note: "Stairs leading down to the basement"

# In maps/basement_1.yml
legend:
  U:
    name: stairs_to_entrance
    type: teleporter
    target_map: entrance
    target_position: [6, 11]
```

When a player entity steps on a teleporter with a `target_map`, the web UI
automatically switches their view to the new map.

### Map Connections layout

Edit mode **Map Connections** (`GET /edit/map_graph`) shows every campaign map
and its teleporter links. Dragging tiles saves their positions to campaign
`map_graph.yml` so a page reload keeps the arrangement:

```yaml
positions:
  tavern: {x: 80, y: 80}
  road: {x: 360, y: 120}
```

Maps without a saved position are auto-placed. **Reset Layout** recomputes a
force layout and overwrites the file.

### Map-Specific Narrations

Each map can have its own narration that plays when players enter:

```yaml
# maps/road.yml
narration:
  on_enter:
    title: "Old Svalich Road"
    text: "The gravel road leads to a dark village..."
    once: true
```

---

## Complete Example

Here's a minimal but complete campaign:

### Directory Layout

```
my_dungeon/
├── game.yml
├── index.json
├── assets/
│   └── sounds/
│       └── ambient.mp3
├── characters/
│   └── fighter.yml
├── maps/
│   ├── entrance.yml
│   └── cave.yml
└── npcs/
    └── goblin.yml    (or use templates/npcs/goblin.yml)
```

### `game.yml`

```yaml
name: "The Goblin Hideout"
title:
  - "THE GOBLIN HIDEOUT"
title_color: green
description: "A short dungeon crawl"
author: "DM Name"
players: 1
starting_map: maps/entrance.yml
maps:
  entrance: maps/entrance
  cave: maps/cave
player_profiles: characters
groups:
  a:
    default: true
    enemies: [b]
  b:
    enemies: [a]
```

### `index.json`

```json
{
  "tile_size": 75,
  "height": 10,
  "width": 10,
  "title": "The Goblin Hideout",
  "map": "maps/entrance",
  "logins": [
    { "name": "player1", "password": "pass", "role": ["player"] },
    { "name": "dm", "password": "admin", "role": ["dm"] }
  ],
  "selectable_characters": [
    { "name": "fighter", "file": "characters/fighter.png", "description": "A brave fighter" }
  ],
  "default_controllers": [
    { "entity_uid": "fighter", "controllers": ["player1"] }
  ]
}
```

### `maps/entrance.yml`

```yaml
name: Dungeon Entrance
description: The mouth of a dark cave

narration:
  on_enter:
    title: "The Goblin Hideout"
    text: >
      A dark cave mouth yawns before you. The stench of goblins
      wafts from within. You grip your weapon tighter and step
      inside.
    once: true

map:
  illumination: 0.5
  base:
    - "##########"
    - "#........#"
    - "#........#"
    - "#........#"
    - "#....-...#"
    - "#........#"
    - "#........#"
    - "#........#"
    - "#........#"
    - "##########"

  base_1:
    - ".........."
    - ".........."
    - ".........."
    - ".........."
    - ".........."
    - ".........."
    - ".........."
    - ".........."
    - ".......c.."
    - ".........."

  entities:
    - token: T1
      layer: object
      pos: [5, 0]

legend:
  c:
    name: supply_chest
    type: chest
    inventory:
      - type: healing_potion
        qty: 1
  T1:
    name: cave_entrance
    type: teleporter
    target_map: cave
    target_position: [5, 9]
    notes:
      - note: "A narrow passage leads deeper into the cave"

player:
  - position: [4, 8]
    sheet: characters/fighter.yml
    overrides:
      entity_uid: fighter
```

### `maps/cave.yml`

```yaml
name: Goblin Cave
description: A cave inhabited by goblins

default_effect:
  effect: fog
  action: start
  config:
    color: "#666666"
    density: 0.5
    speed: 0.1
    opacity: 0.4

map:
  illumination: 0.0
  base:
    - "##########"
    - "#........#"
    - "#........#"
    - "#........#"
    - "#........#"
    - "#........#"
    - "#........#"
    - "#........#"
    - "#........#"
    - "##########"

  light:
    - ".........."
    - ".........."
    - ".........."
    - ".........."
    - "....A....."
    - ".........."
    - ".........."
    - ".........."
    - ".........."
    - ".........."

  meta:
    - ".........."
    - "...g......"
    - ".........."
    - ".........g"
    - ".........."
    - ".........."
    - ".........."
    - ".........."
    - ".........."
    - ".........."

  entities:
    - token: T1
      layer: object
      pos: [5, 9]
    - token: f
      layer: object
      pos: [4, 4]

lights:
  A:
    bright: 15
    dim: 10

legend:
  g:
    name: _auto_
    type: npc
    sub_type: goblin
    group: b
  f:
    name: campfire
    type: campfire
    light:
      bright: 15
      dim: 10
  T1:
    name: exit
    type: teleporter
    target_map: entrance
    target_position: [5, 1]
    notes:
      - note: "The passage back to the entrance"
```

---

## Available Races

The following races are available in `templates/races/`:

`dwarf`, `elf`, `gnome`, `goliath`, `halfling`, `human`, `kender`

### Race YAML: racial resource pools, level gates and subrace swaps

These race and subrace keys are generic and work for any species:

| Key | Where | Meaning |
|---|---|---|
| `resource_pools.<name>` | race or subrace | `{max: <int or proficiency_bonus>, restore_on: short_rest\|long_rest, features: [...]}`. Registered as a normal `ResourcePool` (same sheet, save/load and rest handling as class pools). The subrace definition wins over the race. A long rest also refills `short_rest` pools. |
| `race_feature_min_level.<feature>` | race or subrace | The character level a race feature needs before `class_feature` reports it. |
| `remove_race_features` | subrace | Base race features this subrace drops. For example, a 2024-style goliath ancestry drops the 2014 `stones_endurance` unless it adds it back. |
| `remove_resistances` | subrace | Base race resistances this subrace drops. |

NPCs can use the same pools by listing the feature under `attributes` and the pool under `properties.resource_pools`.

### Goliath and Giant Ancestry

There are two versions of the goliath, chosen by the campaign ruleset:

- **2014** (`templates/races/goliath.yml`): speed 30, Stone's Endurance once per short rest, cold resistance.
- **2024 / SRD 5.2** (`templates/rulesets/5e-2024/races/goliath.yml`, used when `ruleset: 5e-2024`): speed 35, Large Form at level 5+, Powerful Build, and one Giant Ancestry boon picked as a subrace.

The subrace keys are `cloud_giant`, `fire_giant`, `frost_giant`, `hill_giant`, `stone_giant` and `storm_giant`. The 2014 file accepts the same keys. They turn a 2014 goliath into the 2024 version: speed 35, the ancestry boon, Large Form and Powerful Build, and they drop cold resistance.

Every ancestry boon draws from one `giant_ancestry` pool. It holds uses equal to your proficiency bonus and refills on a long rest. All of the logic lives in `natural20/utils/giant_ancestry.py`.

| Boon | How it works in the engine |
|---|---|
| Cloud's Jaunt | `CloudsJauntAction`: a bonus action that teleports you to an unoccupied square you can see within 30 ft. |
| Fire's Burn / Frost's Chill / Hill's Tumble | Optional on-hit riders that run through the `on_attack_hit` hook. The player is asked under the async reaction type `giant_ancestry`, so the prompt doesn't collide with smites. Frost's Chill uses the weapon-mastery Slow state (−10 ft until the start of your next turn). Hill's Tumble only works on Large or smaller targets. |
| Stone's Endurance | Before temp HP is applied in `Entity.take_damage`, it spends your reaction to cut the damage by 1d12 + Con. 2014 uses `Ruleset.stones_endurance_uses_model()`: once per short rest. 2024 shares the PB pool. |
| Storm's Thunder | In `after_take_damage_hook`, it spends your reaction to deal 1d8 thunder to the attacker if it is within 60 ft. |
| Large Form | `LargeFormAction`: a bonus action, once per long rest, lasting 10 minutes. You become Large (the token footprint is restamped and there must be room), get +10 ft speed and get advantage on Strength checks. |
| Powerful Build | Advantage on checks to escape a grapple (`EscapeGrappleAction` passes `purpose: escape_grapple`), and double carrying capacity. |

The damage reactions (Stone's Endurance and Storm's Thunder) can't pause the damage pipeline. Like Hellish Rebuke and Wrath of the Storm, they fire automatically whenever you have a use and your reaction. AI controllers make these choices through their usual `select_reaction`. A creature with no controller uses the first option it is offered. Cloud's Jaunt is only offered to the AI to close distance to melee, or to escape melee at half HP or lower.

## Available Classes

The following classes are available in `templates/char_classes/`:

`bard`, `cleric`, `fighter`, `paladin`, `ranger`, `rogue`, `warlock`, `wizard`

## Available NPC Templates

The following NPC types ship with the base templates (`templates/npcs/`):

`animated_armor`, `animated_broom`, `bat`, `bugbear`, `cat`, `goblin`,
`hobgoblin`, `human_guard`, `ogre`, `owl`, `owlbear`, `skeleton`,
`specter`, `wolf`

Campaigns can add custom NPCs by placing YAML files in their own `npcs/`
directory.

---

## Procedural Dungeons

For generated layouts (BSP, room graphs, cellular caves) **when there is no
source battlemap**, see **[DUNGEON_GENERATOR.md](DUNGEON_GENERATOR.md)**. If the
user already provided map art, use battlemap import instead.

```bash
python scripts/generate_dungeon.py --theme sewer --seed 42 \
  --objective relic:symbol:treasure:far \
  -o maps/generated.yml --render assets/maps/generated.png
```
LLM/tool schema: `python scripts/generate_dungeon.py --print-schema`

---

## Battlemap import (image → YAML)

**Prefer this whenever battlemap art already exists** (user-provided image,
`assets/maps/`, scanned floorplan, VTT underlay). Do not invent ASCII from a
whole-image glance and do not run the procedural dungeon generator for those
maps. Agent skill: `.cursor/skills/n20-import-battlemap/SKILL.md`
(also `.github/skills/natural20-import-battlemap`). Full flags:
**[BATTLEMAP_IMPORTER.md](BATTLEMAP_IMPORTER.md)**.

```bash
python scripts/import_battlemap.py assets/maps/tavern_22x17.png \
  --provider ollama --model llava \
  --adventure notes/tavern.md \
  --workdir /tmp/tavern_import \
  -o maps/tavern.yml
```

Do not ask an LLM to layout the whole image in one shot — the importer slices
tiles and keeps an identification log for consistency checks. Pages with several
floors (church + basement, Death House sheet) are split first (`--split-panels`);
use `--no-split-panels` when the file is already a single map.

---

## Campaign-Specific Event Listeners

Campaigns can register custom event listeners by placing a `webapp/custom_listeners.py`
file inside the campaign root directory. The webapp bootstrap will auto-discover
and load it.

### Pattern

1. Create `user_levels/<campaign>/webapp/custom_listeners.py`.
2. Implement a function named `register_campaign_listeners(event_manager)` that
   registers event listeners:

```python
"""Campaign custom event listeners.

Any campaign can place this file to register handlers for custom events.
The webapp bootstrap calls ``register_campaign_listeners(event_manager)``
if the function exists.
"""

def handle_thing_happened(event: dict) -> None:
    from webapp.blueprints.helpers.runtime_state import (
        get_current_game,
        get_socketio,
    )
    current_game = get_current_game()
    if current_game is None:
        return
    session = current_game.game_session
    socketio = get_socketio()

    # ... handle the event ...

def register_campaign_listeners(event_manager) -> None:
    """Entry point — called from webapp/app.py bootstrap."""
    event_manager.register_event_listener('thing_happened', handle_thing_happened)
```

### Example: Crypt Chambers (Death House)

The death_house campaign implements crypt chambers where placing child skeletal
remains in coffins causes the ghosts to find peace. The implementation uses:

- **Engine core** (`natural20/item_library/crypt_coffin.py`): A reusable `CryptCoffin`
  class that extends `Chest` and fires events when specific items are placed inside.
- **Campaign YAML** (`user_levels/death_house/items/objects.yml`): Object definitions
  that configure which items the coffin accepts and which event to fire.
- **Campaign listeners** (`user_levels/death_house/webapp/custom_listeners.py`): Event
  handlers that remove ghost NPCs from the game world.

**YAML object definition** (`user_levels/death_house/items/objects.yml`):

```yaml
rose_coffin:
  color: brown
  default_ac: 5
  item_class: CryptCoffin
  max_hp: 10
  name: Rose Durst Crypt Coffin
  passable: true
  placeable: true
  opaque: false
  interact_distance: 0
  token_image: objects/coffin
  description: >-
    An empty coffin resting on a stone bier, etched with the name Rosavalda.
    The child's remains might find peace here.
  accepted_items:
    - rose_remains
  on_accept: rose_ghost_peaced
  buttons:
    store:
      label: Place in coffin
      prompt: Place an item in the coffin
    loot:
      label: Take from coffin
      prompt: Take an item from the coffin
    give:
      label: Give to coffin
      prompt: Give an item to the coffin
```

**Map legend entry** (`user_levels/death_house/maps/basement_1.yml`):

```yaml
R:
  name: Rose's Crypt Coffin
  type: rose_coffin
  entity_uid: rose_coffin
  label: Rose Durst Crypt Coffin
  image_offset_px: [0, 30]
  notes:
    - note: An empty coffin resting on a stone bier, etched with the name Rosavalda Durst.
  events:
    - event: rose_ghost_peaced
      message: You place the remains of Rosavalda "Rose" Durst into the coffin. ...
      update_state:
        target: rose_coffin
        state: activated
    - event: rose_ghost_peaced
      message: The remains of Rosavalda "Rose" Durst are already at rest.
      if: "state:activated"
```

**Event handler** (`user_levels/death_house/webapp/custom_listeners.py`):

```python
_GHOST_ENTITY_UIDS = {
    'rose_ghost_peaced': 'rose_durst',
    'thorn_ghost_peaced': 'thorn_durst',
}

def handle_ghost_peaced(event: dict) -> None:
    # Find and remove ghost entity from all maps
    # Emit SocketIO notification for UI refresh

def register_campaign_listeners(event_manager) -> None:
    for event_name in _GHOST_ENTITY_UIDS:
        event_manager.register_event_listener(event_name, handle_ghost_peaced)
```

### Custom Object Classes (Engine Core)

When a campaign needs new object types, add them to the engine core under
`natural20/item_library/` and register them in `natural20/utils/serialization.py`:

```python
# natural20/item_library/crypt_coffin.py
from natural20.item_library.chest import Chest

class CryptCoffin(Chest):
    """A coffin that triggers events when specific remains are placed inside."""

    def __init__(self, session, map, properties=None):
        super().__init__(session, map, properties or {})
        self.accepted_items = properties.get('accepted_items', []) or []
        self.on_accept_event = properties.get('on_accept', '') or ''
        self._peaced = False

    def add_item(self, item_name, qty, source_item=None):
        super().add_item(item_name, qty, source_item)
        if item_name in self.accepted_items:
            if not self._peaced and self.on_accept_event:
                self._peaced = True
                self.resolve_trigger(self.on_accept_event)
```

```python
# natural20/utils/serialization.py
from natural20.item_library.crypt_coffin import CryptCoffin

CLASS_TAG_MAPPING = {
    # ... existing entries ...
    CryptCoffin: '!crypt_coffin',
}
```

**Rule:** Object classes that are generic (usable across campaigns) belong in
the engine core. Campaign-specific logic (like entity removal) should live in
the campaign's `webapp/` folder as event listeners.
