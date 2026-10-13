# Attacking unseen creatures

Implements the 5e *Unseen Attackers and Targets* rule: when you can't see a
creature (invisible, hidden, in darkness you can't see through) you can still
attack the square you think it is in.

| Rule | Engine behaviour |
|---|---|
| Attack a guessed square | `AttackAction.target_square = (x, y)` with `target = None`. |
| Disadvantage | The `target_unseen` condition (`weapons.target_advantage_condition`; logged as "Target is unseen"). |
| Sight-based abilities | NPC actions with `force_hit` or `no_damage` (e.g. a vampire's Charm) don't make an attack roll and need a target the user can see, so they can't be aimed at a square (`makes_attack_roll`, validation key `validation.unseen.needs_sight`). |
| Nothing there → automatic miss | `blind_miss` result, no attack against anything. |
| DM doesn't reveal if the guess was right | Both kinds of miss emit a `blind_miss` event: "X attacked an unseen spot at [x, y] … and missed". The target isn't named, and the animation points at the square. |
| Invisible but not hidden → location known | Observers who can hear (not deafened, unconscious or silenced) within `hearing_range_ft` sense the square. |
| Attacking reveals your location | `Battle.commit` calls `note_noise(source)` for attacks and spells. Observers that can't see the attacker remember its square. |

A hit names the creature as usual, because you now know something was there.

## Engine API (`natural20/utils/unseen_targets.py`)

- `sensed_creatures(battle, observer)` lists the unseen creatures the observer knows about. Each entry has kind `heard` (live square) or `last_known` (remembered square, which expires after `memory_rounds`). The observer's memory is stored in the battle entity state under `unseen_memory`, so it survives save/load.
- `markers_for(battle, viewers)` returns square → marker for the renderer. Markers never carry names or UIDs, and allies are excluded.
- `blind_attack_issue(battle, attacker, action, square)` returns a validation key, or None when the attack is allowed. The result never depends on what is actually in the square. Checks: in bounds, not a wall, not your own square, within weapon range or reach, and an unobstructed path (light doesn't matter).
- `blind_attack_variants(battle, attacker, actions)` builds square-targeted copies for AI controllers. Each copy carries `blind_confidence` (1.0 when heard, 0.35 when last known). These copies are appended to `NPC.generate_npc_attack_actions` and `PlayerCharacter._player_character_attack_actions`, but only when `auto_target=True` and the attack is not an opportunity attack.
- `AttackAction.ai_value` / `compute_hit_probability` score a blind attack as confidence × the chance to hit an assumed AC 14 with disadvantage.

JEV leaves and LLM prompts describe blind attacks as:

```
attack unseen creature at square [x, y] (heard there now) with <weapon> (disadvantage; misses if nothing is there)
```

Target enrichers (`_enrich`, `_maybe_enrich_action_targets`) leave a `target_square` attack alone.

## Campaign switch (`game.yml`)

```yaml
unseen_targets:
  enabled: true         # false disables blind attacks and markers
  hearing_range_ft: 60  # unhidden unseen creatures are heard within this range
  memory_rounds: 2      # rounds a last-known marker stays on the map
```

## VTT UX

1. **Markers.** Squares holding a sensed unseen creature show a pulsing dashed "?" ring when heard, or a faded ring for a last-known position, with a tooltip. The renderer sets `tile['unseen_presence']`, and `map.html` draws `.unseen-presence-marker`.
2. **Target mode.** When an attack enters `select_target`, the server sends `unseen_squares`, and the client outlines them with `.unseen-target-candidate`.
3. **Hover preview** (`/target`). Any square without a visible target returns the same blind-attack preview: `valid_target`, `blind_attack: true`, `adv_info: [[], ['unseen_target']]`, and a `blind_hint`. An occupied square and an empty square look identical. Before this change, hovering an invisible creature returned "not an enemy", which leaked its presence. `sensed` says whether the player hears something there. Invalid squares (out of range, wall, no path) show the reason.
4. **Click.** Sensed squares attack right away. A square with nothing seen or heard asks for confirmation first (`confirmBlindAttackGuess`), so a stray click doesn't waste the attack.
5. **`/action`.** Coordinate targets with no visible target become `AttackAction.target_square`. The engine resolves what is actually there.

Opportunity attacks and spell attacks (e.g. Fire Bolt) don't support square targeting yet.
