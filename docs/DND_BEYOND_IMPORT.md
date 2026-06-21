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
- If a campaign has local item catalogues, add the same item definitions there
  so imported sheets load in that campaign session.
- If the imported sheet has a background and the campaign validates imports,
  ensure the campaign has that background under `backgrounds/`.

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
