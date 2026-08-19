# Campaign rulesets (5e 2014 / 5e 2024)

Natural20 supports **campaign-scoped** D&D 5e edition selection. The ruleset is
owned by the campaign (`game.yml`), not by individual play sessions or save
files.

## Setting the ruleset

In `user_levels/<campaign>/game.yml`:

```yaml
ruleset: 5e-2014   # default if omitted
# or:
# ruleset: 5e-2024

# optional fine-grained overrides (advanced):
# ruleset_overrides:
#   weapon_mastery_enabled: true
```

Accepted aliases: `2014`, `2024`, `srd-5.1`, `srd-5.2`.

At Session load, `Session.ruleset` is a read-through of that field via
`natural20.ruleset.factory.get_ruleset`. Saves do **not** own a diverging
edition; reloading always re-reads the campaign `game.yml`.

## Content overlays

| Path | Role |
|------|------|
| [`templates/`](../templates/) | 2014 / SRD 5.1 baseline (unchanged default) |
| [`templates/rulesets/5e-2024/`](../templates/rulesets/5e-2024/) | SRD 5.2 overlays (only files that differ) |

When `ruleset: 5e-2024`, YAML resolution order is:

1. Campaign local  
2. Campaign imports  
3. Expansion packs  
4. `templates/rulesets/5e-2024/`  
5. `templates/` (fallback)

Missing overlay files fall back to 2014 templates (with no hard error).

**Campaign-local files win.** If a campaign ships its own `char_classes/fighter.yml`
(or race/background), that file shadows the ruleset overlay. Prefer omitting
local copies and relying on templates + overlays, or `inherit: "@templates/..."`
and add only campaign-specific deltas (including any needed 2024 features).

## Impact surfaces

A campaign ruleset must affect:

1. **Weapons / items** — weapon mastery (Push, Sap, Vex, Nick, …), TWF/Nick, item overlays  
2. **Character creation** — ASI from background vs species, origin feats, HP default, filtered pickers  
3. **Spells / abilities** — spell overlays, Counterspell resolution, class feature gates  
4. **Core mechanics** — surprise/initiative, Exhaustion −2/level on D20 Tests, Heroic Inspiration, grapple/shove saves  

### Inspiration / Heroic Inspiration

Gated by `Ruleset.heroic_inspiration_enabled()` (on for `5e-2024`). Both editions
use the same boolean token on the entity (`properties.inspiration`, via
`Entity.has_inspiration()` / `set_inspiration()` / `consume_inspiration()`).

| | 2014 (SRD 5.1) | 2024 (SRD 5.2) |
|---|---|---|
| **Sheet label** | Inspiration | Heroic Inspiration |
| **Token** | One yes/no pip (DM-granted) | Same |
| **Spending on a roll** | Not auto-applied yet (token only) | Not auto-applied yet (token only) |

The Basic Info sheet shows the pip next to proficiency bonus. The DM grants or
clears it from the sheet or with `dm.set_resource` (`resource_type=inspiration`,
value `0` or `1`). Do not enable the 2024 label under `5e-2014`.

### Grapple / Shove

| | 2014 (SRD 5.1) | 2024 (SRD 5.2) |
|---|---|---|
| **Resolution** | Strength (Athletics) contested by the target’s Athletics or Acrobatics (target chooses; engine picks the better modifier) | Target Strength or Dexterity **saving throw** vs DC `8 + STR + PB` |
| **Tie** | Situation unchanged (attacker does not win) | Save succeeds on a tie (`roll >= DC` keeps the target unmoved) |
| **Effect** | Knock prone **or** push 5 feet (attacker chooses; two action buttons) | Same |
| **Limits** | Target no more than one size larger; within **5-ft reach** (weapon Reach does not apply) | Same |

Hook: `Ruleset.grapple_shove_resolution()` → `contested_check` or `target_saving_throw`.

### Weapon Mastery (SRD 5.2)

Gated by `Ruleset.weapon_mastery_enabled()` (on for `5e-2024`). Weapon properties live in [`templates/rulesets/5e-2024/items/weapons.yml`](../templates/rulesets/5e-2024/items/weapons.yml). Class feature overlays: Fighter (3 known at 1st), Barbarian / Paladin / Ranger / Rogue (2 at 1st).

| Mastery | When | Engine |
|---------|------|--------|
| **Push** | Optional after a hit vs Large or smaller | Push 10 ft (`push_from` + `move_to`); web players are prompted |
| **Topple** | Optional after a hit | CON save DC `8 + attack ability + PB` or Prone |
| **Sap** | After a hit | Disadvantage on the target's next attack, until the start of *your* next turn |
| **Vex** | After a hit | Advantage on *your* next attack vs that creature, until the end of *your* next turn |
| **Slow** | After a damaging hit | −10 ft Speed until the start of *your* next turn (does not stack) |
| **Graze** | On a miss | Damage equal to the attack ability modifier |
| **Nick / Cleave** | YAML only in this slice | TWF rewrite / extra attack not implemented yet |

Chargen (2024 classes with the feature) asks the player to pick that many mastery properties. Stored as `known_weapon_masteries` on the PC YAML. Legacy sheets with the feature but no list still receive every mastery on weapons they are proficient with. 2014 campaigns ignore `weapon_mastery` on items.

Attack buttons and the character sheet show the mastery when the campaign ruleset enables it. Combat log events use `event: weapon_mastery`.

## Spells (ruleset)

Under `ruleset: 5e-2024`, [`templates/rulesets/5e-2024/items/spells.yml`](../templates/rulesets/5e-2024/items/spells.yml)
overlays SRD 5.2 text/metadata onto the shared spell catalogue.

| Spell | 2014 behavior | 2024 behavior |
|-------|---------------|---------------|
| **Counterspell** | Auto-succeed if slot ≥ target level; else INT check | Target makes **CON save** vs your spell save DC |
| **Divine Smite** | Free after melee weapon hit (slot only) | **Bonus action** spell after melee/unarmed hit; no 5d8 base dice cap |
| **True Strike** | Concentration advantage cantrip | Weapon attack using spellcasting ability; optional radiant; cantrip upgrade d6s |
| **Hex** | Same core curse (SRD 5.2 text in catalogue) | Extra 1d6 necrotic on attack hits + ability-check disadv (concentration) |
| **Searing Smite** | Not offered as post-hit BA | **Bonus action** after melee/unarmed hit; ongoing fire + CON save to end (not concentration) |

Campaign-local `items/spells.yml` entries still win over the overlay for matching keys.


## Changing edition mid-campaign

Edit `game.yml` only. Treat it as a **migration**: rebuild or re-check PCs
(ability scores are baked at chargen). Not a mid-session toggle.

## Legal

SRD 5.2 content is CC BY 4.0 — see [`docs/ATTRIBUTION_SRD.md`](ATTRIBUTION_SRD.md).
Do not copy non-SRD copyrighted PHB/MM text into `templates/` or `natural20/`.
