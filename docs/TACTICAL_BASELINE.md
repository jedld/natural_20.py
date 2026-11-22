# Tactical baseline `generic@1`

`GenericController.POLICY_ID` is `generic@1`. Encounter reports cite that name. A change to the scores below is a new policy id, so older reports stay comparable.

The controller is the heuristic used when a creature's battle controller is `generic`. It is not a learned policy. `scripts/encounter_sim.py --explain` records the top three scored options on each committed choice. The scores themselves are unchanged by that flag.

## What it picks

`move_for` builds the legal list in `_compute_available_moves` (attacks, spells, movement, Dash, Disengage, Dodge, Hide, items, and the other types in `VALID_AI_MOVE_TYPES`), drops unbuilt spell stubs, then sorts that list in `_sort_actions_with_scores`.

- An attack scores with `AttackAction.ai_value`.
- A damaging spell scores hit probability times average damage. A support spell uses the support-spell score instead.
- An NPC area ability (`npc_area_ability`, including a recharge cone) and a summon score with that action's `ai_value`.
- A move scores the destination from `PathCompute`: progress toward an enemy, a penalty for squares just visited, and a penalty when the path provokes an opportunity attack. A negative move is skipped while an enemy is already in melee, so a creature that has finished attacking does not walk out of reach.
- Second Wind, items, Help, shove, and grapple have their own scores. Hide scores only when no visible enemy can see the creature. Dash, Disengage, and Dodge sit at a low default so they lose to an attack.

The highest score is taken. Ties break by sort stability, which follows the order the legal list was built.

`select_action` uses the same sort for reactions, including opportunity attacks. Legendary actions use a separate pass (`select_legendary_action`) that still calls `ai_value` and divides by the legendary action's cost. That pass is part of `generic@1` but it does not write the `--explain` list.

## What it refuses

Two filters run before this scorer, and they also apply to JEV and LLM option lists:

- `natural20.utils.friendly_fire` removes harmful options aimed at the actor's own side.
- `natural20.utils.pointless_actions` drops options that cannot help: Second Wind at full HP, looting while an enemy is up, Hide while already hidden, attacking a downed foe while a standing foe can be targeted, and the other cases listed in that module.

A creature that must flee (`apply_fear(..., must_flee=True)`) Dashes away instead of entering the scorer. A cornered creature falls through to the normal sort.

## What it does not do

`generic@1` has no separate aggressive or cautious profile. It does not conserve spell slots for a later fight, and it does not coordinate focus fire beyond what `ai_value` already prefers. Retreat is the fear path and the movement score, not an HP threshold.
