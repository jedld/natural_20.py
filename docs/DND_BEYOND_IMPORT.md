# D&D Beyond Import Support

The web character builder imports D&D Beyond sheets through
`scripts/beyond_importer.py` and writes campaign-ready character YAML. The
importer only preserves items and spells that the engine can load, so extending
support for a high-level sheet usually means adding data or spell classes before
regenerating the character.

Useful extension points:

- Add spell YAML to `templates/items/spells.yml` and to campaign-local spell
  catalogues when the target campaign has its own `items/spells.yml`.
- Add implemented spell classes under `natural20/spell/` and register them in
  `natural20/utils/spell_loader.py`.
- Add item definitions to `templates/items/equipment.yml`,
  `templates/items/weapons.yml`, `templates/items/objects.yml`, or
  `templates/items/magic_items.yml`. The importer's known-item scan includes all
  four files.
- Campaign-specific items (setting artifacts, named gear) belong in the
  campaign's own `items/*.yml`. Pass `--campaign user_levels/<name>` on the CLI
  (the webapp route passes the active campaign automatically) so those items
  and spells, plus imported campaigns and expansion packs, count as known.
- If the imported sheet has a background and the campaign validates imports,
  ensure the campaign has that background under `backgrounds/`.

Name resolution: `Shield, +1` maps to `shield_plus_one` when that id exists,
and `Base (Variant)` names try `base_variant` and then `base` (so
`Dragon Scale Mail (Bronze)` becomes `dragon_scale_mail_bronze`). More rules:

- `_ITEM_ALIASES` in the importer covers DDB names that differ from engine ids,
  e.g. `Crossbow, Light` → `light_crossbow`, `Crossbow, Heavy` →
  `heavy_crossbow`, `Robe` → `robes`, `Plate Armor` → `plate`.
- `Mithral <armor>` and `Mithral Armor (<armor>)` become `mithral_<armor id>`
  (`Mithral Plate Armor` → `mithral_plate`). The SRD mithral variants live in
  `templates/items/magic_items.yml` (breastplate, chain shirt, scale mail, ring
  mail, half plate, chain mail, splint, plate). They inherit from
  `mithral_breastplate`, keep the base armor's AC and weight, and set
  `stealth_disadvantage: false`.
- A leading bracketed count (`[5] Elixir of Flight`) is stripped before
  slugging, and entries with quantity 0 are skipped.
- Artisan's tools and supplies use apostrophe-free ids (`alchemists_supplies`,
  `tinkers_tools`, `smiths_tools`, `calligraphers_supplies`) with
  `type: tool` in `templates/items/equipment.yml`.

Damage
resistances that DDB attributes to an equipped item are dropped from the
character-level `resistances` list when that item's YAML already grants them,
so unequipping the item removes the resistance. Unconditional condition
immunities become `condition_immunities`; situational ones (auras, "while
raging") are left to the engine features that grant them.

2024 lineage choices that DDB stores as race options, such as the goliath's
`Hill's Tumble (Hill Giant)`, become `subrace: hill_giant` when the race YAML
defines that subrace.

Importing a 2024 sheet into a campaign on another ruleset: when the campaign
`game.yml` is not `ruleset: 5e-2024`, the importer records the 2024 pieces the
campaign's class YAML won't provide:

- `feat_editions: {great_weapon_master: 5e-2024}` for 2024-sourced feats whose
  rules differ by edition (see `natural20/utils/great_weapon_master.py`).
- `class_features` for 2024-only class features the sheet has unlocked (paladin
  `abjure_foes`, `radiant_strikes`, `weapon_mastery`).
- `channel_divinity_uses` for 2024 paladins (2 uses, 3 from level 11).
- `race_edition: 5e-2024` for a 2024 race that has an overlay under
  `templates/rulesets/5e-2024/races/` (e.g. the 2024 gnome). Its lineage option
  (e.g. "Rock Gnome") becomes the `subrace`.

The importer also records:

- `spell_abilities: {spell: ability}` for race, feat and background spells,
  read from DDB's `spellCastingAbilityId`.
- Data-driven classes from expansion packs, such as the Tasha's artificer. The
  subclass is written to the class YAML's `subclass_property` (e.g.
  `artificer_specialist: alchemist`). Spell slots follow the YAML
  `spellcasting.progression`.
- Not recorded: artificer infusions and the Spell-Storing Item spell, because
  DDB doesn't export them. Add `infusions` and `spell_storing_item` to the sheet
  by hand (see [CAMPAIGN_BUILDING.md](CAMPAIGN_BUILDING.md#data-driven-classes-yaml-only)).

Duplicate stacks are merged, `Class Feature: ...` placeholder items are
skipped, coins become `copper_piece` / `silver_piece` / `electrum_piece` /
`gold_piece` / `platinum_piece` stacks,
and only one body armor stays equipped (attuned first, then magic, then highest
AC). DDB weapon-mastery options such as `Lance (Topple)` become
`known_weapon_masteries` (only active under the `5e-2024` ruleset).

```bash
python scripts/beyond_importer.py 142861711 --campaign user_levels/dragonlance -o /tmp/char.yml
```

For Dragonlance character `142861711` (Zavra Stonecrown, level 11 goliath
Oath of Devotion paladin), the SRD `lance` and several SRD adventuring-gear
items were added to `templates/`. The setting content (the Knight of Solamnia
background, the Squire of Solamnia and Knight of the Sword feats, the
`dragonlance` weapon, and the Kagonesti Forest Shroud) lives in
`user_levels/dragonlance/`. The sheet is saved as
`user_levels/dragonlance/characters/goliath_paladin.yml`.

Engine support added for that sheet (all generic and YAML-driven):

- Paladin features through level 11: Aura of Protection, Aura of Courage, Aura
  of Devotion (`natural20/utils/auras.py`), Divine Health, Improved Divine
  Smite / 2024 Radiant Strikes (`natural20/utils/feature_hit_riders.py`),
  Channel Divinity as a pool, Sacred Weapon, and 2024 Abjure Foes.
- Frightened as a real condition with a source (`natural20/utils/fear.py`):
  disadvantage on attacks and checks while the source is in sight, plus
  optional end-on-damage and one-of-action/bonus/move limits.
- Great Weapon Master (2014: Hew bonus attack after a crit or kill; 2024: also
  +PB damage with heavy weapons) and Blind Fighting (10 ft blindsight).
- Feat attack options from YAML (`attack_options`), used by the Squire of
  Solamnia's Precise Strike and the Knight of the Sword's Demoralizing Strike.
- Items: `target_creature_types` on weapon `additional_damage` (the
  dragonlance's force damage against dragons), bonus-action item activation and
  `on_use` riders (the Forest Shroud), and the dragon scale mail colour
  variants.
- Spells: Shining Smite, Remove Curse, Daylight, Beacon of Hope, and Aura of
  Vitality. Goliath giant ancestries with Large Form and Powerful Build.

For Dragonlance character `143994108` (an artificer), the SRD gear the sheet
carries was added to `templates/items/equipment.yml`: `flask`, `robes`,
`shovel`, the `amber` and `pearl` gemstones, the four artisan's tools above,
`platinum_piece` / `electrum_piece` coins, and `alchemists_fire`. Alchemist's
Fire uses the generic `ThrownFlaskItem` item class
(`natural20/item_library/thrown_flask.py`): a `UseItemAction` that throws the
flask up to `thrown_range` feet as an improvised ranged attack (d20 + Dex, no
proficiency). On a hit, its YAML `burning` block (`damage`, `damage_type`,
`extinguish_dc`) applies `BurningEffect` (`natural20/effects/burning_effect.py`),
which deals the damage at the start of each of the target's turns. Burning
doesn't stack, and it is saved as a plain `!effect_object`. The flames go out when
a creature uses `ExtinguishFlamesAction` on itself or an ally within 5 feet and
passes a Dexterity check against the DC. The Dragonlance `fargab` lives in
`user_levels/dragonlance/items/equipment.yml`.

Class-feature options picked on DDB are read by `_extract_feature_choices`:

- When a class feature's slug is listed in the class YAML `feature_choices`
  (the 2024 warlock lists `eldritch_invocations`), its picks become that sheet
  list.
- `Agonizing Blast (Eldritch Blast)` also records the cantrip in
  `invocation_spells`.
- Spells granted by a picked option (Pact of the Tome) go to
  `class_spells: {warlock: [...]}`.
- `Mystic Arcanum (Level N Spell)` spells become `mystic_arcanum: {N: slug}`.
  The warlock overlay's `free_casts` then casts them once per long rest.

For Dragonlance character `144357252` (Chestnut Latchlifter, a level 11 kender
Archfey warlock), the sheet is saved as
`user_levels/dragonlance/characters/chestnut_latchlifter.yml`. Content went to:

- SRD (`templates/`): Wand of the War Mage, Periapt of Proof against Poison,
  Blade Ward, Blink, Calm Emotions, Contact Other Plane, Detect Evil and Good,
  Detect Poison and Disease, Dominate Beast/Person, Hold Monster, Hypnotic
  Pattern, Phantasmal Force, Plant Growth and Seeming. The SRD 5.2 warlock
  overlay (Magical Cunning, Contact Patron, Mystic Arcanum, invocations) is in
  `templates/rulesets/5e-2024/`.
- PHB 2024 pack: the Archfey patron, Summon Fiend with its three spirit NPCs,
  and the 2024 Blade Ward.
- Xanathar's pack: Thunder Step and Synaptic Static.
- `user_levels/dragonlance/`: the hoopak, the Mage of High Sorcery background
  and the Initiate of High Sorcery feat.

See [CAMPAIGN_BUILDING.md](CAMPAIGN_BUILDING.md#warlock-srd-52-and-the-archfey-patron)
for the class blocks and [RULESETS.md](RULESETS.md#warlock-and-archfey-spells-edition-differences)
for spell details and limits. The hoopak's sling mode needs `pellet` ammunition,
which isn't defined yet.

For Death House character `14191568`, support was added for `booming_blade`,
`boots_of_striding_and_springing`, `instrument_of_illusions`, and `mawsse`, then
the generated sheet was saved as
`user_levels/death_house/characters/rumblebelly_ddb_14191568.yml`.

That sheet is a level 15 Swashbuckler rogue. The importer preserves Martial
Adept maneuver choices from D&D Beyond action entries named `Maneuvers: ...` and
writes `maneuvers`, `superiority_die`, and `superiority_dice` fields. Current
engine support covers this character's selected maneuvers (`riposte` and
`disarming_attack`) plus core high-level rogue features such as Reliable Talent,
Evasion, Uncanny Dodge, Fancy Footwork, Rakish Audacity, and Sentinel's
opportunity-attack movement stop.

The web UI surfaces these features in the character info sheet, character
selection details, current-turn resource indicators, and DM resource controls.
Generic `ResourcePool` values such as `superiority_dice` can be adjusted through
`/update_resource_pool` or MCP `dm.set_resource` with
`resource_type=resource_pool`.

For Death House character `14154385`, support was added for `Crysania`, a level
15 High Elf School of Abjuration wizard. The generated sheet is saved as
`user_levels/death_house/characters/crysania_ddb_14154385.yml` and the Death
House character selector points `crysania` at that import.

This import exercises a much larger wizard spellbook. Spell catalog entries and
Python spell classes now cover Crysania's prepared combat spells such as
`fireball`, `scorching_ray`, `lightning_bolt`, `chain_lightning`,
`disintegrate`, `maze`, `wall_of_force`, `stinking_cloud`,
`protection_from_energy`, `melfs_acid_arrow`, and `teleport`, plus utility or
ritual spell representations for the rest of the imported spellbook.

School of Abjuration features are represented through wizard subclass metadata
and engine hooks:

- `arcane_ward` is a generic `ResourcePool` with max HP equal to
  `wizard_level * 2 + int_mod`. It is created or recharged by level 1+ Abjuration
  spells and absorbs damage before normal HP loss.
- `projected_ward` lets a nearby Abjurer spend their reaction to absorb damage
  for an ally with remaining ward HP.
- `improved_abjuration` adds proficiency to `counterspell` and `dispel_magic`
  ability checks.
- `spell_resistance` grants advantage on magical saves and resistance to spell
  damage.

Crysania's charged magic items (`wand_of_magic_missiles`,
`necklace_of_fireballs`, and `staff_of_defense`) use generic item charge
resources and the existing `UseItemAction` flow. Consumables such as greater
healing, invisibility, fire breath, vitality potions, and a level-2 spell scroll
are importable and usable. Utility items such as `bag_of_holding` and
`bag_of_beans` are import-complete even where their broad narrative effects are
not fully automated.
