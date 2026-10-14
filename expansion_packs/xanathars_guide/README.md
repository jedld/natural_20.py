# Xanathar's Guide (expansion pack)

Opt-in content from **Xanathar's Guide to Everything** (Wizards of the Coast). It is **not SRD** and is not bundled in `templates/` or `natural20/`.

Contents:

- `items/spells.yml`: the Zephyr Strike, Gust, Thunder Step and Synaptic Static spells.

Campaigns opt in via `index.json`:

```json
{
  "expansion_packs": {
    "xanathars_guide": "xanathars_guide"
  }
}
```

The spells have no pack-specific Python. They run on generic engine classes configured by spell YAML:

| Spell | Feature | Mechanic |
|---|---|---|
| Zephyr Strike | No opportunity attacks against you | `no_opportunity_attacks: true` → `no_opportunity_attacks` effect (`natural20/utils/movement.py`) |
| Zephyr Strike | Once: advantage, +1d8 force on a hit, +30 ft speed | `attack_surge` block → `StrikeSurgeSpell` + `AttackSurgeAction` (no action cost, armed before the attack) |
| Gust | Push a Medium or smaller creature 5 ft (Strength save) | `PushCreatureSpell` with `save`, `push_distance`, `max_size` |
| Thunder Step | Teleport 90 ft, thunder damage around the departure square (CON save for half) | `ThunderStepSpell` (Misty Step teleport plus `departure_radius` damage) |
| Synaptic Static | 20-ft sphere, 8d6 psychic (INT save for half), failed saves become Muddled | `SynapticStaticSpell` (`AreaSaveSpell`) and `MuddledEffect`: −1d6 on attack rolls and concentration saves, INT save at the end of each turn to end it |

Simplifications:

- Thunder Step can't bring a willing passenger along.
- Muddled's −1d6 on ability checks isn't applied.

- Gust's object-push and sensory options are narrative only (the description mentions them, but the engine only resolves the creature push).
- Zephyr Strike's speed bonus is added as extra movement for the rest of the turn after the empowered attack roll, hit or miss.

Class spell lists live in class YAML. These spells are not added to `templates/char_classes/*`, so campaigns that want them on the ranger or wizard lists must add them in their own class overrides.

Attribution: Xanathar's Guide to Everything. Not part of the Systems Reference Document.
