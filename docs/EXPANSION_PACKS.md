# Expansion Packs

> Import SRD, third-party, or campaign-agnostic content without duplicating files in the core engine or campaign directories.

## Overview

Expansion packs let a campaign declare external resource directories that are merged into its YAML lookups.  Files in an expansion pack are checked **after** local campaign files but **before** bundled `templates/`, giving a clean override path without copying SRD content.

## Directory layout

```
user_levels/<campaign>/
├── game.yml
├── index.json
├── expansion_packs/
│   └── <pack_name>/          # e.g. monsters_of_the_multiverse
│       ├── races/
│       │   └── tortle.yml
│       ├── npcs/
│       │   └── dragon.yml
│       └── char_classes/
│           └── warlock.yml
```

Each pack id in `index.json` is resolved in order (first existing directory wins):

1. `<campaign>/expansion_packs/<pack_id>`
2. `<campaign_parent>/expansion_packs/<pack_id>` (shared across `user_levels/`)
3. repo `expansion_packs/<pack_id>` (for packs shipped with Natural20, e.g. `tashas_sidekicks`)

## Declaring expansion packs

Add an `expansion_packs` object to **`index.json`**:

```json
{
  "tile_size": 70,
  "title": "My Campaign",
  "expansion_packs": {
    "monsters_of_the_multiverse": "monsters_of_the_multiverse"
  }
}
```

Each key is an arbitrary pack identifier (used for reference).  The value can be:

| Format | Example | Resolved path |
|---|---|---|
| String (bare name) | `"monsters_of_the_multiverse"` | `<campaign>/expansion_packs/monsters_of_the_multiverse/` |
| Object with `path` | `{"path": "custom_pack_dir"}` | `<campaign>/expansion_packs/custom_pack_dir/` |

Multiple packs are supported:

```json
"expansion_packs": {
  "monsters_of_the_multiverse": "monsters_of_the_multiverse",
  "tasha_cauldron_guide": "tashas"
}
```

## Supported categories

Expansion packs support the same category subdirectories as bundled templates:

| Category | Example path | Consumer |
|---|---|---|
| `races/` | `races/tortle.yml` | [`Session.load_races()`](natural20/session.py) |
| `char_classes/` | `char_classes/warlock.yml` | [`Session.load_classes()`](natural20/session.py) |
| `npcs/` | `npcs/dragon.yml` | [`Session.load_npcs()`](natural20/session.py) |
| `backgrounds/` | `backgrounds/acolyte.yml` | [`Session.load_backgrounds()`](natural20/session.py) |
| `items/weapons/` | `items/weapons.yml` | [`load_campaign_yaml()`](natural20/yaml_loader.py) |
| `items/equipment/` | `items/equipment.yml` | [`load_campaign_yaml()`](natural20/yaml_loader.py) |
| `items/spells/` | `items/spells.yml` | [`load_campaign_yaml()`](natural20/yaml_loader.py) |
| *(any)* | *(arbitrary)* | [`load_campaign_resource_path()`](natural20/yaml_loader.py) |

## YAML inheritance from expansion packs

YAML inherit references support `@expansion/` and `@expansions/` prefixes:

```yaml
# races/tortle_override.yml
label: "Tortle (Variant)"
inherit: "@expansion/monsters_of_the_multiverse/races/tortle"
base_speed: 30
```

This resolves to `<campaign>/expansion_packs/monsters_of_the_multiverse/races/tortle.yml`.

## Resolution order (precedence)

When loading a YAML resource, the engine checks these locations in order (highest priority first):

1. **Campaign local files** — `<campaign>/<category>/<resource>.yml`
2. **Imported campaigns** — `<imported_campaign>/<category>/<resource>.yml` (via `game.yml` `imports`)
3. **Expansion packs** — `<campaign>/expansion_packs/<pack_name>/<category>/<resource>.yml`
4. **Bundled templates** — `<templates_root>/<category>/<resource>.yml`

For **item catalogues** (weapons, equipment, magic_items, objects, spells, equipment_packs), template data is merged with campaign and expansion pack overrides using `deep_merge`.

For **category files** (races, npcs, backgrounds, char_classes), the first matching file wins (no merging).

## Example: Tortle race from Monsters of the Multiverse

Given `user_levels/expansion_packs/monsters_of_the_multiverse/races/tortle.yml`:

```yaml
label: Tortle
base_speed: 30
size: medium
attribute_bonus:
  str: 2
  wis: 1
skills:
  - nature
language:
  - common
race_features:
  - tortle_claws
  - hold_breath
  - natural_armor
  - natures_intuition
  - shell_defense
```

And `user_levels/my_campaign/index.json`:

```json
{
  "title": "My Campaign",
  "expansion_packs": {
    "monsters_of_the_multiverse": "monsters_of_the_multiverse"
  }
}
```

A character sheet can now reference `tortle` as a race without duplicating the YAML:

```yaml
# characters/my_tortle.yml
name: Shellshock
race: tortle
level: 1
```

## Programmatic access

The `expansion_pack_roots()` function returns resolved paths:

```python
from natural20.yaml_loader import expansion_pack_roots

roots = expansion_pack_roots("user_levels/my_campaign")
# [PosixPath('/home/user/natural20/user_levels/my_campaign/expansion_packs/monsters_of_the_multiverse')]
```

## Rules and conventions

- **No campaign-specific names in engine**: Expansion packs should contain generic, SRD-compatible content. Named characters, story beats, and adventure-specific objects belong in the campaign directory.
- **SRD/public domain content**: Use expansion packs for SRD material, public domain spells, and campaign-agnostic entities.
- **Copyrighted expansion material**: Per AGENTS.md rules, copyrighted material from sources like "Monsters of the Multiverse" that aren't in the SRD should live in expansion packs, not in `natural20/` or `templates/`.
- **Single pack per declaration**: Each `expansion_packs` key maps to one directory. Don't use nested keys beyond `path`.

## Testing

Verify expansion pack loading:

```python
from natural20.session import Session

session = Session("user_levels/my_campaign")
races = session.load_races()
assert "tortle" in races
print(races["tortle"]["label"])  # "Tortle"
```

Or from the YAML loader directly:

```python
from natural20.yaml_loader import load_campaign_yaml

data = load_campaign_yaml("user_levels/my_campaign", "races", "tortle")
print(data)  # {'label': 'Tortle', 'base_speed': 30, ...}
```

## Tasha’s Sidekicks pack

Repo path: `expansion_packs/tashas_sidekicks/` (Expert / Spellcaster / Warrior class YAML). **Not SRD** — Tasha’s Cauldron of Everything. Campaigns opt in:

```json
"expansion_packs": {
  "tashas_sidekicks": "tashas_sidekicks"
}
```

Without the pack, sidekick **membership and player control** still work. `apply_sidekick_class` no-ops when the class YAML is missing. CR ≤ 1/2 is pack policy (warn + DM override), not a core hard fail. See [CAMPAIGN_BUILDING.md](CAMPAIGN_BUILDING.md#sidekick-npcs).
