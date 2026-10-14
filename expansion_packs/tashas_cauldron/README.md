# Tasha's Cauldron (expansion pack)

Opt-in content from **Tasha's Cauldron of Everything** (Wizards of the Coast). It is **not SRD** and is not bundled in `templates/` or `natural20/`.

Contents:

- `char_classes/artificer.yml`: the Artificer class with the Alchemist specialist.
- `items/equipment.yml`: the Alchemist's experimental elixirs.

Campaigns opt in via `index.json`:

```json
{
  "expansion_packs": {
    "tashas_cauldron": "tashas_cauldron"
  }
}
```

The class has no Python mixin. It is loaded as a data-driven class (`natural20/entity_class/data_driven.py`), and its features use the generic class-YAML mechanics in `natural20/utils/class_mechanics.py`:

| Feature | Mechanic |
|---|---|
| Spellcasting (INT, half caster rounding up) | `spellcasting.progression: half_round_up` |
| Alchemist spells (always prepared) | `subclasses.alchemist.spells` |
| Flash of Genius | `save_assists` (reaction, `flash_of_genius` pool) |
| Spell-Storing Item | `free_casts` with `spell_property: spell_storing_item` (sheet `spell_storing_item: {spell, item}`) |
| Infuse Item | `infusions` catalogue + sheet `infusions: [{infusion, item}]` |
| Tool Expertise | `tool_expertise` feature (doubles proficiency on tool checks) |
| Experimental Elixir | `rest_items` (random elixirs after a long rest) + `craft_options` (spend a slot) |
| Alchemical Savant | `spell_roll_bonuses` (needs alchemist's supplies) |
| Restorative Reagents | elixir `creator_riders` temp HP + `free_casts` Lesser Restoration |

Simplifications:

- Flash of Genius only boosts saving throws, because ability checks with a DC don't go through a shared hook.
- Spell-Storing Item is used by the artificer, not by whoever holds the item.
- The Elixir of Transformation is cosmetic.
- Infusions other than the `+N` ones listed in the catalogue are just recorded on the sheet.

Spell lists include only slugs defined in `templates/items/spells.yml`.

Attribution: Tasha's Cauldron of Everything. Not part of the Systems Reference Document.
