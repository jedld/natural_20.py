# Tortle Race Implementation

Tortle is a player race from *Monsters of the Multiverse* (SRD-compatible). This document describes the implementation in natural20.

## Files

| File | Purpose |
|------|---------|
| [`expansion_packs/races/tortle.yml`](../expansion_packs/races/tortle.yml) | Canonical race definition (SRD pool) |
| [`user_levels/death_house/races/tortle.yml`](../user_levels/death_house/races/tortle.yml) | Campaign copy (loaded from campaign directory) |
| [`natural20/actions/shell_defense_action.py`](../natural20/actions/shell_defense_action.py) | Shell Defense / Emergence action classes |
| [`natural20/player_character.py`](../natural20/player_character.py) | Wiring: import, ACTION_LIST, `available_actions` handler, `equipped_ac()` override, serialization |
| [`natural20/actions/attack_action.py`](../natural20/actions/attack_action.py) | Tortle claws damage type override (slashing) |

## Tortle Racial Traits

| Trait | Implementation |
|-------|---------------|
| **Creature Type** | Humanoid (default) |
| **Size** | Medium (configurable via YAML `size`) |
| **Speed** | 30 ft (`base_speed: 30`) |
| **Claws** | `tortle_claws` feature flag → unarmed strikes deal 1d6+STR slashing (not bludgeoning) |
| **Hold Breath** | `hold_breath` feature flag (1 hour) |
| **Natural Armor** | `natural_armor` feature flag → `equipped_ac()` returns 17 + shield bonus (no DEX mod); blocks wearing armor |
| **Nature's Intuition** | `natures_intuition` → skill choice (Animal Handling, Medicine, Nature, Perception, Stealth, Survival) — set `skills: [nature]` in YAML; DM picks via character builder |
| **Shell Defense** | `shell_defense` feature flag → action enters/exits shell state |

### Shell Defense Mechanics

- **Enter Shell** (action): `_in_shell = True`, `_prone = True`, movement = 0, +4 AC bonus
- **Exit Shell** (bonus action): `_in_shell = False`, `_prone = False`, movement restored
- While in shell: advantage on STR/CON saves, disadvantage on DEX saves, no reactions
- AC during shell: 21 (17 base + 4 shell) + shield bonus

## YAML Schema

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

## How It Works

1. **Race loading**: `PlayerCharacter.__init__()` loads `races/<race>.yml` via `load_campaign_resource_path()`.
2. **Feature flags**: `class_feature('shell_defense')` returns True if the feature is in `race_features`.
3. **AC calculation**: `equipped_ac()` checks `class_feature('natural_armor')` and returns base 17 (+ 4 if `_in_shell`) + shield + accessory bonus.
4. **Claw damage**: `AttackAction._get_attack_info()` checks `class_feature('tortle_claws')` and overrides damage type to slashing for unarmed strikes.
5. **Shell Defense action**: `ShellDefenseAction.can()` returns True if tortle has `shell_defense` and is not already in shell. `apply()` sets `_in_shell = True`, `_prone = True`. `EmergenceAction` reverses this.
6. **Serialization**: `_in_shell` is saved in `to_dict()` and restored in `from_dict()`.

## Adding Tortle to a New Campaign

1. Copy from expansion_packs:
   ```bash
   cp expansion_packs/races/tortle.yml user_levels/<campaign>/races/tortle.yml
   ```
2. Tortle will appear in the character builder race list.

## Testing

```bash
# Verify race loading
python -c "from natural20.yaml_loader import load_campaign_resource_path; print(load_campaign_resource_path('user_levels/death_house', 'races/tortle.yml'))"

# Verify action import
python -c "from natural20.actions.shell_defense_action import ShellDefenseAction, EmergenceAction; print('OK')"
```
