# Tasha’s Sidekicks (expansion pack)

Opt-in overlay that turns a CR ≤ 1/2 NPC stat block into an Expert, Spellcaster, or Warrior sidekick.

This pack contains class tables from **Tasha’s Cauldron of Everything** (Wizards of the Coast). It is **not SRD** and is **not** bundled in `templates/` or `natural20/`. Campaigns must opt in via `index.json`:

```json
{
  "expansion_packs": {
    "tashas_sidekicks": "tashas_sidekicks"
  }
}
```

Resolution order (see `docs/EXPANSION_PACKS.md`):

1. `<campaign>/expansion_packs/tashas_sidekicks`
2. `<campaign_parent>/expansion_packs/tashas_sidekicks` (shared across `user_levels/`)
3. repo `expansion_packs/tashas_sidekicks`

Without this pack, Natural20 still supports party membership and player control of NPC sidekicks. Class overlays (`apply_sidekick_class`) no-op when the YAML is missing.

Spell lists include **only** slugs implemented in `templates/items/spells.yml`. Ability Score Improvements are stored as `pending_asi` for the DM to apply via the ability-score UI or `dm.set_property`.

Attribution: Tasha’s Cauldron of Everything. Not part of the Systems Reference Document.
