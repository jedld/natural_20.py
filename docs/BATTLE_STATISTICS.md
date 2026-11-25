# Battle statistics

End-of-combat numbers computed from the battle log — who damaged whom, with
what, how often they hit, and how the fight ended.

## Engine API

- `Battle.statistics()` → JSON-safe dict (also importable as
  `natural20.utils.battle_statistics.collect_statistics(battle)`).
- `format_statistics_lines(battle, prefix='[DM]')` → the human-readable
  report rows.
- Emitted automatically at `end_of_combat` (`Battle.next_turn`) as a
  `battle_statistics` event; the `standard_cli` handler logs the pre-built
  lines with the event's visibility. A `battle_statistics` handler in any
  custom output pipeline receives `event['lines']` and `event['visibility']`.

## What it collects

From every committed action's `result` items in `battle.battle_log`:

| Item types | Counted as |
|---|---|
| `damage`, `spell_damage`, `additional_damage` | damage per source→target pair, per damage type; attack hits + criticals when the item carries an `attack_roll`; save passed/failed when it carries `save_failed`; spell names per caster |
| `miss`, `blind_miss` | misses (blind attacks record `-> a guessed square`) |
| `spell_heal` / `heal` / `use_item` (`hp_gain_roll`) | healing done |

Damage totals use the **`_applied_damage`** annotation that
`Entity.take_damage` writes back onto the log item, so resistance,
vulnerability, temp HP routing and reduction (Uncanny Dodge, Arcane Ward...)
are reflected rather than raw rolls. Because everything is recomputed from
`battle_log`, there is **no new state to serialize**: save/load keep the
statistics for free.

Round-level and outcome data come from battle state directly:

- `rounds`, `fates` (standing / downed / dead with final HP), `kills`
  (victim, killer, cause and finishing attack from `death_info`),
- `teams` aggregates keyed by battle group (`dealt` / `taken`),
- `totals` (damage, hits, crits, misses, healing, saves).

## Campaign switch (`game.yml`)

```yaml
battle_statistics:
  enabled: true        # emit the report at combat end (default true)
  visibility: dm       # 'dm' (default) or 'all' to also show players
```

`false` also works as shorthand for `enabled: false`. With `visibility: dm`
the report lines are `[DM]`-prefixed DM-only combat-log lines, like the
start-of-combat roster from `combat_roster.py`; with `all` they log to
everyone without the prefix.

## Example

```
[DM] Battle statistics after 4 rounds:
[DM] Combatants — damage dealt / taken / hits-crits-misses / healing / saves passed:
[DM]   RumbleBelly: 34 dealt, 27 taken, 2-1-2 hits/crits/misses
[DM]   Count Strahd von Zarovich: 68 dealt, 22 taken, 5-2-3 hits/crits/misses [standing]
[DM] Damage by matchup:
[DM]   Count Strahd von Zarovich -> Gomerin: 41 (3 hits, 1 crit) [24 slashing, 17 necrotic]
[DM] Damage types: necrotic 45, slashing 30, force 14, fire 14
[DM] Team totals: team a: dealt 96, taken 68; team b: dealt 68, taken 96
[DM] Kills:
[DM]   malachi killed by Count Strahd von Zarovich with Unarmed Strike (killed)
[DM] Totals: 164 damage dealt, 12 hits (4 critical), 7 misses, 21 healing, 6/9 saves passed
```

## UI / integration notes

- The VTT combat log shows the report because it replays engine events; no
  webapp wiring is needed. The recap (prose) and the statistics (numbers)
  are separate features (`webapp/battle_combat_recap.py` vs this module).
- For UIs or MCP: call `Battle.statistics()` (dict, JSON-safe) instead of
  parsing the log lines.
- Tests: `tests/test_battle_statistics.py`.
