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
6. [Player Characters](#player-characters)
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

---

## Campaign Directory Structure

A campaign is a directory that mirrors the `templates/` layout. The engine
resolves resources by first checking the campaign directory and then falling
back to `templates/`.

```
my_campaign/
├── game.yml                  # Campaign configuration (required)
├── index.json                # Web UI / level configuration (required for webapp)
├── npc_system_prompt.txt     # LLM system prompt template for NPC dialog (optional)
├── entity_token_map.csv      # Entity → token-image mapping (optional)
├── spell_token_map.csv       # Spell → token-image mapping (optional)
├── weapon_token_map.csv      # Weapon → token-image mapping (optional)
├── assets/                   # Images, sounds, backgrounds
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
├── npcs/                     # NPC template YAML files
│   ├── goblin.yml
│   └── custom_boss.yml
├── races/                    # Race definitions
│   └── elf.yml
└── locales/                  # i18n strings
    └── en.yml
```

### Running a Campaign

```bash
# Development
cd webapp && python -m flask run

# With a custom campaign directory
cd webapp && TEMPLATE_DIR=../user_levels/my_campaign python -m flask run

# Or using the start script
cd webapp && ./start_web.sh ../user_levels/my_campaign/
```

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
maps:
  entrance: maps/entrance
  dungeon_1: maps/dungeon_level_1
  dungeon_2: maps/dungeon_level_2

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
| `character_selection_background` | string | Image for character selection |
| `autosave` | bool | Enable automatic save |
| `selectable_characters` | array | Characters players can pick at login |
| `soundtracks` | array | Background music tracks |
| `logins` | array | User accounts (`role`: `"player"` or `"dm"`) |
| `default_controllers` | array | Which users control which entities |

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
| `map` | object | — | Map data (layers, entities, size, illumination) |
| `legend` | object | — | Character → object/NPC mapping |
| `lights` | object | — | Static light source definitions |
| `triggers` | object | — | Area-wide triggers |
| `extensions` | object | — | Web-specific extensions |

### Map Layers

The `map` object contains the grid layers and configuration:

```yaml
map:
  illumination: 0.5              # Base light level (0.0–1.0)
  size: [26, 14]                 # Explicit dimensions [width, height]
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
| `token_image` | string | Custom token image filename |
| `hp` | int | Override max HP |
| `passive` | bool | Non-hostile; won't initiate combat |
| `dialog` | bool | Entity can be talked to |
| `backstory` | string | LLM backstory prompt for conversation |
| `conversation_handler` | string | `"llm"` for AI dialog |
| `conversation_buffer` | array | Pre-seeded conversation messages |
| `backstory_buffer` | array | Messages to seed the LLM conversation context |
| `converstation_keywords` | array | Keywords that trigger game state changes |
| `statuses` | array | Initial status conditions (`hidden`, etc.) |
| `hidden_stealth` | int | Stealth roll value if spawned hidden |

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

3. **Keyword triggers** — When the LLM mentions specific keywords in its
   response, game state changes can be triggered:
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

## Player Characters

Player character sheets live in `characters/` and define a full D&D 5e
character.

```yaml
---
name: Crysania
race: elf
subrace: high_elf
pronoun: she/her/hers
classes:
  wizard: 2                          # class: level
description: A high elf mage with a mysterious noble background
level: 2
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
| `corner_door_*` | DoorObjectWall | Directional wall-embedded doors |

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

Teleporters link maps together. When an entity enters the teleporter's
square, they're moved to the target position (and optionally a different map).

```yaml
legend:
  T1:
    name: stairs_down
    type: teleporter
    target_map: dungeon_1            # Map name from game.yml
    target_position: [3, 7]          # Destination [x, y]
    notes:
      - note: "Stairs leading down"

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
  thrown:
    range: 30
    range_max: 120
  meta:
    noise_source: 5
    noise_target: 5
```

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

```yaml
notes:
  - note: "You notice strange markings on the wall"
    perception_dc: 15              # Passive perception DC to discover
  - note: "The markings form a map to the treasure room"
    investigation_dc: 12           # Requires active investigation check
  - note: "A pit trap!"
    highlight: true                # Visual highlight on discovery
    image: pit_trap_image          # Image to display
```

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
