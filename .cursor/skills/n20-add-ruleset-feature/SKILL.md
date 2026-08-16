---
name: n20-add-ruleset-feature
description: >-
  Add or extend a D&D 5e ruleset divergence (2014 vs 2024) in Natural20: Ruleset
  hooks, campaign game.yml, YAML overlays under templates/rulesets/5e-2024/, and
  call-site wiring. Use when implementing edition-specific weapons, chargen,
  spells, initiative/saves, or when the user asks how to support 2024 rules
  without breaking 2014 campaigns.
---

# Natural20 — add a ruleset feature

Read [docs/RULESETS.md](../../../docs/RULESETS.md) first.

## Before coding

1. Confirm the delta is real in **SRD 5.1 vs SRD 5.2** (not a false PHB rumor).
2. Decide: **YAML overlay** (content) vs **Ruleset hook** (behavior) vs both.
3. Campaign ownership: edition comes from `game.yml` `ruleset:` only.

## Checklist

```text
- [ ] Prefer templates/rulesets/5e-2024/<category>/ for content overrides
- [ ] Add Ruleset method only if 2014 and 2024 math diverge for the same feature
- [ ] Implement on Ruleset2014 (default) and override on Ruleset2024
- [ ] Gate call sites via session.ruleset — never hardcode edition strings in random modules
- [ ] 2014 campaigns with no ruleset: key must remain inert / identical
- [ ] tests/test_ruleset/ covering both editions
- [ ] Update docs/RULESETS.md if a new impact surface appears
```

## Where things live

| Kind | Location |
|------|----------|
| Hooks | `natural20/ruleset/base.py`, `ruleset_2014.py`, `ruleset_2024.py` |
| Factory | `natural20/ruleset/factory.py` |
| Campaign config | `game.yml` → `ruleset:` / `ruleset_overrides:` |
| Overlay content | `templates/rulesets/5e-2024/` |
| Loader | `natural20/yaml_loader.py` (`campaign_ruleset_id`, overlay merge) |

## Do not

- Add per-session or per-save ruleset selection.
- Invent hooks for rules that are identical across editions (reactions/round, ASI levels, sneak attack die, etc.).
- Put campaign-named or non-SRD copyrighted text in overlays.
- Enable Weapon Mastery / Heroic Inspiration / 2024 Exhaustion under `5e-2014`.
