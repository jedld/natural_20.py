---
name: n20-add-spell
description: >-
  Add or extend a D&D spell in Natural20 end-to-end: YAML SRD entry, Python spell
  class, spell_loader registration, class spell lists, tests, and VTT visuals
  (cast animation, persistent token overlay, effect icon). Use when adding a new
  spell, implementing spell fidelity fixes, wiring concentration/debuff/buff
  effects, or when the user asks how to add spells to the engine or web UI.
---

# Natural20 — add a spell

Read [reference.md](reference.md) for file paths, archetype templates, and VTT wiring detail.

## Before coding

1. Read the **SRD / spell card text** (casting time, range, components, duration, save, upcast, concentration).
2. Pick a **reference spell** in `natural20/spell/` with the same pattern (see archetypes below).
3. Confirm the slug: YAML key = snake_case (`hold_person`), class = `HoldPersonSpell`, animation key = slug.

## Checklist (copy and track)

```text
Engine
- [ ] templates/items/spells.yml — entry (components, duration_seconds, concentration, spell_class)
- [ ] natural20/spell/<slug>_spell.py — build_map, resolve, apply (+ hooks/dismiss if needed)
- [ ] natural20/utils/spell_loader.py — import + spell_classes dict entry
- [ ] templates/char_classes/*.yml — spell_list level slot (if new to a class)
- [ ] tests/test_<slug>_spell.py or extend tests/test_spell_action.py

VTT (buff/debuff/concentration — skip for pure instant damage with no ongoing effect)
- [ ] webapp/static/assets/effect/<slug>.png — tile/portrait icon
- [ ] webapp/static/spell_effects.js — register('<slug>', cast animation)
- [ ] webapp/static/status_effects.js — EFFECT_CLASS + CSS if persistent overlay while active
- [ ] npm run build:assets

Verify
- [ ] pytest tests/test_<slug>_spell.py -q
- [ ] Spell short_name() matches animation key (action_animator uses spell_action.short_name())
- [ ] apply() uses effect=self (Spell instance), not a string, for dismiss/concentration
```

## Pick an archetype

| Pattern | Reference files | apply() event |
|---------|-----------------|---------------|
| Spell attack + damage | `firebolt_spell.py`, `guiding_bolt_spell.py` | `spell_damage` via resolve items |
| Save for damage | `sacred_flame_spell.py`, `thunderwave_spell.py` | `spell_damage` / `spell_miss` |
| Buff + concentration | `bless_spell.py`, `shield_of_faith_spell.py` | `spell_buf` + `add_casted_effect` |
| Debuff + concentration + repeat save | `slow_spell.py`, `hold_person_spell.py` | `spell_debuff` + `end_of_turn` hook |
| AoE point/cube/cone | `grease_spell.py`, `burning_hands_spell.py` | zone or per-target saves |
| Self only | `mage_armor_spell.py`, `expeditious_retreat_spell.py` | target = caster |

**Concentration debuffs** — copy `SlowSpell` / `HoldPersonSpell` structure:
- `SaveCheck.make` for initial and repeat saves (not raw `DieRoll` + hardcoded ability).
- `source.add_casted_effect`, `start_concentration` / `concentration_on`.
- `target.register_effect(..., effect=self, ...)`.
- `target.register_event_hook('end_of_turn', ...)` when SRD says repeat save at end of turn.
- `dismiss()` removes statuses and modifiers.

**Upcasting** — in `build_map`: `additional = max(0, orig_action.at_level - base_level)`; set `num` targets or damage dice accordingly. Validate cluster range in `resolve` when SRD requires targets within N ft of each other.

**Targeting filters** — `require_humanoid: True` in `build_map` param (see `action_builder.acquire_targets`); or filter in `resolve`.

## Engine conventions (do not invent alternatives)

- Spell classes live in `natural20/spell/`, registered only via `spell_loader.py`.
- YAML: `spell_class: Natural20::FooSpell` matches `FooSpell` in loader dict.
- `resolve` returns typed result items (`type: 'hold_person'`, `spell_damage`, etc.); `apply` checks that type and returns the target (not `None`) when handled.
- Line-of-sight targeting: `acquire_targets` uses `map.can_see` when `range` is set on `select_target`.
- Serialize-friendly: effect objects must be Spell instances with stable `id` from YAML properties.
- After webapp JS edits: `npm run build:assets` (updates `*.min.js` + `manifest.assets.json`).

## SRD fidelity spot-check

- Correct save ability and caster `spell_save_dc` ability (use `_caster_spell_ability` pattern from `hold_person_spell.py` / `light_spell.py`, not hardcoded `wisdom` unless always that class).
- Concentration + `duration_seconds: 60` for “up to 1 minute”.
- Material component in YAML `components` + `material:` when SRD lists one.
- Condition side effects: paralyzed → incapacitated turn skip, attack advantage, melee crit within 5 ft (`weapons.py`, `attack_action.py`) — extend engine only when the **condition** is new, not per spell.

## Tests (minimal useful set)

- YAML loads; `load_spell_class('FooSpell')` not None.
- Resolve: save success vs failure (mock `save_throw` with `result()` and `__lt__` for `SaveCheck`).
- apply: concentration, status, end-of-turn dismiss on successful repeat save.
- Targeting: humanoid filter, upcast count, cluster distance if applicable.

## Docs

- Update `AGENTS.md` spell/extension notes only if you introduce a **new** targeting param or MCP surface.
- Optional human doc: `docs/SPELLS.md` one-liner only if the team wants a catalog entry (not required per spell).

## Related

- `AGENTS.md` — AoE targeting (`select_cone`, `select_cube`), battle loop, save/load.
- `docs/CAMPAIGN_ASSET_GENERATOR.md` — `scripts/generate_game_icons.py` for spell/effect PNGs.
- `.cursor/skills/n20-add-spell/reference.md` — VTT and code templates.
