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
