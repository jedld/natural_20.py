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

**Per-character race edition.** A sheet with `race_edition: 5e-2024` loads its race from `templates/rulesets/5e-2024/races/` even when the campaign runs another ruleset. For example, a 2024 gnome imported from D&D Beyond into a 2014 campaign keeps Gnomish Cunning (`save_advantage`) and its lineage `spells`.

**2024 Ranger and Human.** The ranger overlay casts from level 1 with half-caster slots rounding up (`spellcasting.progression: half_round_up`), and has the 2024 progression: Favored Enemy as free Hunter's Mark casts, Deft Explorer, Roving (+10 ft speed unless in heavy armor), Expertise and Tireless (temporary HP action, and a short rest removes one Exhaustion level). Subclasses go under `subclasses.<name>` keyed by `ranger_archetype`. The Gloom Stalker ships in the `players_handbook_2024` pack. The 2024 Human has no ability bonuses and gets Heroic Inspiration after each long rest (`inspiration_on_long_rest`). The D&D Beyond importer rounds single-class half-caster levels up (2014 rangers and paladins get no slots at level 1) and also rounds them up for multiclass characters in 2024 campaigns.

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

#### Grappler-side rules (`natural20/utils/grappling.py`)

| | 2014 | 2024 |
|---|---|---|
| **Dragging** | Each square costs 1 extra (speed halved) unless the grappled creature is two or more sizes smaller | Same, and Tiny creatures are also exempt (`phb_2024_grapple_move_cost()`) |
| **Release** | Free, any time (no action) | Same |
| **Grapple ends** | Grappler incapacitated, grappled creature dies, or it ends up out of the grappler's reach | Same |
| **Attacks** | No penalty for grappler or grappled | Grappled creature has disadvantage on attacks against anyone but its grappler (`grappled_attack_disadvantage()`) |

`Entity.make_dead` releases every grappler holding the creature, and `Battle.start_turn` calls
`prune_invalid_grapples` for the acting creature and its grapplers. Releases log
`drop_grapple` with a `reason` (e.g. "target died"). A `grapple_instead` hit deals no damage,
so it never calls `take_damage` (no death-save failure on an unconscious target).

AI: `GenericController.grapple_release_action` frees held creatures that are dead, unconscious,
or not hostile before choosing anything else (also before legendary actions). NPCs get one
`DropGrappleAction` per held creature in `available_actions`, so LLM / JEV controllers can
choose "release grapple on X (free)". The LLM sheet, the JEV state, and the LLM path tools
(`movement_cost_ft`, reachable squares) include the doubled drag cost via
`grapple_status_text` / `drag_cost_multiplier`.

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

### Weapon properties and 2024 feats (all editions)

- **Loading** is enforced for player characters in both editions: one Loading shot per Attack action, whatever Extra Attack allows (`natural20/utils/weapon_loading.py`). Feat `weapon_attack_rules` `ignore_properties: [loading]` waives it.
- **Long range** compares the distance in feet with the weapon's normal `range` (the `thrown.range` for thrown weapons).
- **Archery** adds +2 to ranged weapon *attack rolls* only, not damage.
- 2024 Lucky (luck points), Sharpshooter and Crossbow Expert are YAML in the `players_handbook_2024` expansion pack; the mechanics are generic (`feat_mechanics.py`, `luck_points.py`). See `docs/CAMPAIGN_BUILDING.md` → "Other feat YAML mechanics". Lucky is offered after the d20 is rolled, with the same odds as spending it beforehand.

### Paladin and feats

| Feature | 2014 | 2024 |
|---------|------|------|
| Channel Divinity | 1 use, all back on a short rest | 2 uses (3 at 11th), one back on a short rest |
| Sacred Weapon (`Ruleset.sacred_weapon_model`) | Action, 1 minute | Part of the Attack action (no action cost), 10 minutes |
| Improved Divine Smite / Radiant Strikes | +1d8 radiant on melee weapon hits (11th) | Same, renamed Radiant Strikes |
| Abjure Foes | — | 9th level Channel Divinity option |
| Great Weapon Master | Hew bonus attack | Hew plus +PB damage with heavy weapons |

A character can use one feat's rules from another edition through
`feat_editions` (for example `great_weapon_master: 5e-2024` in a 2014
campaign). 2024 class features that the campaign's class YAML doesn't grant can
be listed under `class_features`, and `channel_divinity_uses` overrides the
Channel Divinity table. The D&D Beyond importer writes all three for 2024
sheets imported into 2014 campaigns.

### Magic item attunement (both editions)

The attunement rules are the same in DMG 2014 and DMG 2024: attuning takes a
short rest focused on one item while holding it, a creature can be attuned to
at most three items (one copy of each), and attunement ends on death, after 24
hours away from the item, or after another short rest (not while the item is
cursed). Both rulesets therefore share the defaults:

| Hook | Default | `ruleset_overrides` key |
|------|---------|-------------------------|
| `attunement_limit()` | 3 | `attunement_limit` |
| `attunement_requires_rest()` | `true` | `attunement_requires_rest` (`false`: instant outside combat) |
| `attunements_per_rest('short_rest' / 'long_rest')` | 1 / 2 | `attunements_per_short_rest` / `attunements_per_long_rest` |

Class features raise the limit through class YAML `attunement` entries. The
Artificer from `tashas_cauldron` goes to 4, 5 and 6 items. Without attunement,
an item gives only its nonmagical benefits. See `docs/CAMPAIGN_BUILDING.md` →
"Managing attunement".

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
| **Shining Smite** | Offered as post-hit BA (no 2014 counterpart, so not gated) | Same: 2d6 radiant (+1d6/slot above 2nd), target glows, attacks vs it have advantage, no Invisible benefit |
| **Aura of Vitality** | Cast as an action, no heal on cast; BA heal usable the same turn | Cast as a **bonus action** and heals one creature on cast (that turn's pulse); Cleric/Druid/Paladin list |

| **Cure Wounds** | 1d8 + mod, +1d8 per slot above 1st | 2d8 + mod, +2d8 per slot above 1st |
| **Healing Word** | 1d4 + mod, +1d4 per slot above 1st | 2d4 + mod, +2d4 per slot above 1st |

Campaign-local `items/spells.yml` entries still win over the overlay for matching keys.

Slot healing dice are YAML-driven: `heal_dice` (base) plus `heal_dice_per_slot` times the levels above the spell's base level (`slot_healing_dice` in `natural20/spell/cure_wounds_spell.py`).

### Spells per turn

`Ruleset.spells_per_turn_model()` sets the limit, and `natural20/utils/spell_requirements.py` `spells_this_turn_issue` enforces it from `SpellAction.can_cast`. Each action or bonus-action cast is recorded in the turn state as `casted_spells` (level and resource).

| Ruleset | Model | Rule |
|---------|-------|------|
| `5e-2014` | `bonus_action_spell` | After casting a bonus-action spell, you can only cast a cantrip with a casting time of 1 action. A bonus-action spell is also blocked if you already cast a leveled spell or a non-cantrip with your action this turn. |
| `5e-2024` | `one_slot_per_turn` | You can spend only one spell slot per turn. Cantrips are unrestricted. |

Reactions (Shield, Counterspell) are not counted.

### Counterspell reaction window

`SpellAction.resolve` runs `natural20/utils/counterspell.py`'s `run_counterspell_window` before a spell takes effect during a battle. Any **hostile** creature on the same map gets a `select_reaction` prompt (event `type: counterspell`, with `caster`, `spell`, `target_spell_level`) if it meets all of these conditions:

- It is conscious.
- It has `counterspell` prepared.
- It still has a reaction and a 3rd-level-or-higher slot.
- It can see the caster within 60 ft.

- **Choices:** one Counterspell action per slot level the creature can spend. The VTT shows them in `reactions/counterspell.html`. `GenericController` (and LLM/JEV, which inherit it) uses `choose_counterspell`: it never counters cantrips. Under 2014 rules it upcasts to the lowest slot that auto-succeeds; under 2024 rules it always uses the lowest slot.
- **Outcome:** a successful counter replaces the spell's result with the check events plus `spell_countered`. The caster still loses the action. Under 2014 rules the caster's slot is also spent; under 2024 rules it isn't. A failed counter lets the next eligible creature try, then the spell resolves normally.
- **Async players:** `WebController` prompts raise `AsyncReactionHandler(reaction_type='counterspell')`. Progress is cached on the action (`_counterspell_state`), so re-resolving after the prompt doesn't re-ask or re-charge creatures that already reacted. `Action.add_reaction` stores answers per source, so several creatures can be asked during one action.
- **Not modelled:** countering a Counterspell (the counter resolves directly, not through `SpellAction.resolve`), and readied spells being released (`skip_consume_at_resolve`).

### Dispel Magic

`DispelMagicSpell` (`natural20/spell/wizard_spells.py`) works the same in both editions. `natural20/utils/dispel.py` `spells_on(target, battle)` finds the leveled spells *on* the target: effects registered on it, plus any combatant's `casted_effects` entry that targets it. That covers a held Polymorph, Bless, Shield and so on. Spells the target cast on others are not included. Each spell at or below the slot level ends. A higher-level spell needs a check with the caster's spellcasting ability (plus proficiency with Improved Abjuration) against DC 10 + the spell's level. `end_spell_on` ends a single-target concentration spell through the caster's `dismiss_effect`, so the caster's concentration drops and a Polymorph reverts. Otherwise it removes the effect from the target only. The log reads "X casts Dispel Magic on Y with a level 3 slot: Polymorph (level 4) holds (check ... vs DC 14)." AI options are dropped unless the target carries a spell cast by an opponent (`worth_dispelling`).

### Casting a second concentration spell

Both editions end your current concentration as soon as you cast another concentration spell, whether or not the new spell lands. `SpellAction.resolve` handles this generically: when a spell with `concentration: true` in its YAML goes off (it isn't countered and didn't fail to cast), it puts a `concentration_replaced` item ahead of the spell's own results. At commit, `SpellAction.apply` dismisses the old effect through `dismiss_effect`, which also lifts it from its targets, so a held Polymorph reverts. This only happens if the caster is still concentrating on that same effect. Spells therefore only need to call `battle.start_concentration` on success, and a passed save still costs the caster the old spell.


### Mirror Image

`Ruleset.mirror_image_model()` picks the mechanic; `natural20/spell/mirror_image_spell.py` (`MirrorImageSpell.check_attack`) implements both. Weapon attacks (`AttackAction`) and spell attacks (`evaluate_spell_attack`) call it.

| Ruleset | Model | Behaviour |
|---------|-------|-----------|
| `5e-2014` | `d20_redirect` | Every attack rolls a separate d20: 6+ / 8+ / 11+ with 3 / 2 / 1 duplicates redirects it. The attack roll is then compared to the duplicate's AC (10 + caster Dex mod; a natural 20 always hits it, a natural 1 always misses). A hit destroys the duplicate. Either way, a redirected attack never hits the caster. |
| `5e-2024` | `d6_on_hit` | Only when the attack hits: roll a d6 per remaining duplicate. If any die shows 3+, a duplicate takes the hit and is destroyed. |

Attackers who are blinded, can't see the caster, or perceive the caster with `blindsight` / `truesight` in range are unaffected. A diverted attack logs a `mirror_image_duplicate` event in place of the plain miss line: "...but struck one of X's Mirror Image duplicates instead (duplicate roll ...). The duplicate vanishes (2 left)." The VTT tile carries `mirror_images` (duplicates left). `status_effects.js` draws one drifting, translucent copy of the token per duplicate, and the 3D client shows a pale-blue ring.

Spells that make several attack rolls in one cast (Scorching Ray, Eldritch Blast) pass `opts['attack_index']` to `evaluate_spell_attack`. Each ray then gets its own roll, cached per index for re-resolves. One-shot advantage such as Guiding Bolt's is used up by the first ray only.

### Targeting wards, action restrictions and spell follow-ups

These generic hooks work the same in both editions. Any spell, item or monster trait can reuse them.

**Targeting wards** (`natural20/utils/targeting_ward.py`). An effect registers `targeting_ward` with a handler that returns `{'save_type', 'dc', 'label'}`. A creature that targets the warded creature makes that save first:

- An attack checks the ward in `AttackAction.resolve`. On a failed save the attack is spent but never rolled.
- A harmful spell (per `friendly_fire.is_harmful`) checks it in `SpellAction.resolve`. A failed save drops the warded creature from the spell's targets. If no creature target is left, the spell and its slot are lost.
- Area spells aimed at a point are not blocked.
- Every save logs a `targeting_ward` line: "Ogre tests Crysania's Sanctuary (wisdom save ...) and loses the attack."

Sanctuary (`natural20/spell/sanctuary_spell.py`) uses the ward. It ends when the warded creature attacks (`attack_resolved` hook), casts a spell that affects an enemy (`spell_cast`), or deals damage (`dealt_damage`, which `damage_event` fires on the source).

**Action restrictions** (`natural20/utils/action_restrictions.py`). A stacked `action_restriction` effect returns forbidden kinds. `attack`, `spell`, `speak` and `interact` are checked by `AttackAction.can`, `SpellAction.can_cast`, `SpeakAction.can` and `InteractAction.can`. Gaseous Form (`natural20/spell/gaseous_form_spell.py`) forbids all four. It also gives a 10 ft fly speed (`fly_speed` + `speed_override`), resistance to nonmagical bludgeoning, piercing and slashing damage, and advantage on STR/DEX/CON saves.

**Bonus-action follow-ups.** Flaming Sphere (`natural20/spell/flaming_sphere_spell.py`) places a `FlamingSphereZone`, a persistent zone over the 3×3 squares around the sphere. Any creature whose turn ends there makes a DEX save for half damage. While the caster concentrates on it, `FlamingSphereAction` is offered once per turn as a bonus action:

- It is a `select_radius` whose `origin` is the sphere's square, with a range of 30 ft.
- Picking an occupied square moves the sphere next to that creature and rams it, forcing the same save.
- Picking an empty square just moves the sphere.

PCs get the action from `class_feature_registry` and NPCs from `Npc.available_actions`. The VTT marks the sphere's square with `flaming_sphere_marker`.

**Other small SRD spells:**

- Faerie Fire outlines creatures in a 20-foot cube that fail a DEX save. Attackers that can see an outlined creature get advantage (`targeted_advantage_override`), it can't benefit from invisibility (`invisibility_suppressed`), and it sheds dim light.
- Lesser Restoration ends paralyzed > blinded > poisoned > deafened > a `disease*` status, in that order, unless `opts['condition']` names one.
- Ray of Sickness poisons a creature that fails its CON save until the end of the caster's next turn.
- Melf's Acid Arrow deals delayed acid damage at the end of the target's next turn (`AcidArrowBurn`). A miss deals half the initial damage and nothing later.
- Feather Fall, Prestidigitation, Mending and Identify (`natural20/spell/utility_spells.py`) log an event. Feather Fall's `feather_fall` status also cancels fall damage in `map_stack_descent`.

Entity event hooks are not saved. Effects that need them define `restore_hooks()`, which `relink_spell_entities` calls after a load.

### Ranger and utility spells (edition differences)

| Spell | 2014 (templates) | 2024 (`templates/rulesets/5e-2024/` or pack) |
|---|---|---|
| Ensnaring Strike | Bonus-action cast, then fires on the next weapon hit (`weapon_hit.timing: next_hit`) | Bonus action right after a weapon hit (`after_hit`) |
| Hail of Thorns (pack only) | Not in the SRD. Template entry is a stub (`ExpansionPackOnly`) | `expansion_packs/players_handbook_2024/`: after a ranged hit, 2d10 (+1d10 per slot), no concentration |
| Magic Weapon | Concentration, +2 at 4th, +3 at 6th | No concentration, +2 at 3rd, +3 at 6th |

How weapon-hit spells work (`natural20/spell/extensions/weapon_hit_spell.py`):

- With `after_hit`, the hit offers `WeaponHitSpellCastAction` through the reaction prompt, and the spell is not on the normal cast list.
- With `next_hit`, the cast arms the caster, and the first qualifying hit fires the spell.

Ensnaring Strike: the target makes a STR save, with advantage if it is Large or bigger. On a failure it is restrained and takes 1d6 piercing per slot level at the start of each of its turns. `BreakFreeAction` makes the escape check (Athletics against the spell DC) for the target or for an adjacent ally.

Other spells added alongside (the same in both editions):

- **Spike Growth.** Difficult terrain, plus 2d4 piercing per 5 ft moved inside. Only voluntary combat movement triggers it.
- **Silence.** Blocks verbal spells, speech and hearing inside, and grants thunder immunity. Creatures are not given the Deafened status.
- **Pass without Trace.** +10 Stealth, but only for creatures chosen at cast time (the 2024 emanation is simplified the same way).
- **Disguise Self.** Cosmetic. Observers see through it with an Investigation check against the spell DC (`see_through_disguise`).
- **Rope Trick.** Out of combat only. Members can't be targeted and can't attack or cast.
- **Fear.** 30-ft cone, WIS save or frightened with forced flight. The creature repeats the save at the end of its turn only when it can't see the caster. Victims don't drop held items.
- Xanathar's pack (`expansion_packs/xanathars_guide/`):
  - **Zephyr Strike.** No opportunity attacks, plus one surge: advantage, +1d8 force on a hit, +30 ft of movement after the attack roll.
  - **Gust.** STR save or a Medium-or-smaller creature is pushed 5 ft. Its object and sensory uses are narrative only.

Magic Weapon's bonus does not make the weapon count as magical for resistance.

### Warlock and Archfey spells (edition differences)

| Spell | 2014 (templates) | 2024 (`templates/rulesets/5e-2024/` or pack) |
|---|---|---|
| Blink | d20 at the end of each turn, 11+ goes ethereal | d6, 4+ goes ethereal |
| Phantasmal Force | 1d6 psychic per turn | 2d8 psychic per turn |
| Blade Ward | Resistance to bludgeoning, piercing and slashing from weapons for 1 round (`blade_ward.mode: resistance`) | PHB 2024 pack: concentration, attackers subtract 1d4 from attack rolls against you (`mode: attack_penalty`) |

Notes on the other spells (the same in both editions):

- **Banishment, Blink.** The target goes off-plane (`natural20/utils/off_plane.py`). Blink returns you to your own square, or to the nearest free one if it is taken. You don't choose the square. Banishment's "native to another plane" rule isn't modelled.
- **Hypnotic Pattern, Hold Monster, Dominate spells.** Use `ConditionSaveSpell`. Shaking a creature awake from Hypnotic Pattern isn't modelled.
- **Calm Emotions.** Allies become immune to charmed and frightened. The ward doesn't suppress a charm or fear that is already on them.
- **Detect Evil and Good / Detect Poison and Disease.** At the start of each turn, logs the matching creatures within range that the caster has line of sight to.
- **Contact Other Plane.** INT save, or the caster takes damage and is incapacitated. Contact Patron's free cast succeeds automatically.
- **Plant Growth.** Overgrowth covers the whole area (`movement_cost: 4`). The rule that lets you exclude some creatures isn't modelled.
- **Seeming.** Disguise Self for up to 6 creatures. Unwilling targets make a CHA save.
- Xanathar's pack: **Thunder Step** (teleport, plus 3d10 thunder to creatures near the departure square; bringing a passenger isn't modelled) and **Synaptic Static** (8d6 psychic, and failed saves become Muddled: −1d6 on attack rolls and concentration saves, INT save at the end of each turn to end it; the ability-check penalty isn't modelled).
- PHB 2024 pack: **Summon Fiend** (demon, devil or yugoloth spirit). The demon's Death Throes fire at 0 HP or when the spell ends, the devil has Devil's Sight and can mix Fiery Strike melee and ranged, and the yugoloth can teleport 30 ft after each Claws attack. The spirit vanishes at 0 HP, which ends the spell. Climb speed isn't modelled.
- **Dimension Door** (SRD). Uses `MistyStepSpell` with YAML `range: 500` and `require_los: false`, so any empty square in range works. `ai_max_destinations` caps how many squares AI auto-targeting considers. Bringing a willing creature along and the 4d6 damage for an occupied destination aren't modelled; occupied squares can't be picked.
- **Sending** (SRD). Picks a creature on the same map and logs a `sending` event, with the text taken from `spell_action.message` when set. Creatures with INT 1 or lower get the meaning but not the words (`understood: false`). It is a non-combat spell (`ai_in_combat: false`).

## Changing edition mid-campaign

Edit `game.yml` only. Treat it as a **migration**: rebuild or re-check PCs
(ability scores are baked at chargen). Not a mid-session toggle.

## Legal

SRD 5.2 content is CC BY 4.0 — see [`docs/ATTRIBUTION_SRD.md`](ATTRIBUTION_SRD.md).
Do not copy non-SRD copyrighted PHB/MM text into `templates/` or `natural20/`.
