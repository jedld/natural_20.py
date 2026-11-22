# Encounter simulation

Headless, seeded battles for a fixed party and a fixed set of monsters. This is the encounter-balance report. Controller-versus-controller sweeps stay in `scripts/s1_battle_sim.py`. Training stays on the Gymnasium env.

## Run

```bash
python scripts/encounter_sim.py \
    --scenario benchmarks/encounters/fighters_vs_goblins.yml \
    --trials 1000 --seed 1000

python scripts/encounter_sim.py --suite benchmarks/suite.yml
```

`--trials` defaults to 1 for one scenario and to the `trials` value in the suite file (2). One thousand trials is an explicit flag. `--jobs N` runs each trial in its own process so the global dice RNG is not shared. Reports land in `logs/encounter_sim/<id>.report.json` unless `--out` or `--out-dir` is set.

`generic@1` pathfinds on every step, and it often moves one square at a time. The eight-goblin fight is the slow one (about half a minute for two rounds on the small field). The other three scenarios are a few seconds for the same cap. Use `--jobs` when you raise `--trials`. A 1,000-trial goblin report is an overnight run, not an interactive one.

The terminal table and the JSON report include:

- party win rate, monster win rate, timeout rate
- party wipe rate and monster wipe rate (every member of that side is dead)
- mean, median, and 90th percentile of `Battle.round`
- per-creature survival rate and mean HP left (dead creatures count as 0 HP)
- mean spell slots spent by level, and mean uses of resource pools
- mean damage dealt and taken
- encounters per second

`Battle.round` is the engine counter. It stays 0 through the opening initiative pass and increments when initiative wraps back to the top.

## Scenario file

Scenarios live under `benchmarks/encounters/`. The session root is the nearest parent directory that contains `game.yml` (`benchmarks/`).

```yaml
id: fighters_vs_goblins
map: open_field          # key in benchmarks/game.yml maps:
max_rounds: 30
sides:
  party:
    controller: generic  # generic | random
    policy: generic@1
    members:
      - template: fighter
        name: Fighter
        count: 4
        positions: [[1, 3], [1, 4], [2, 3], [2, 4]]
  monsters:
    controller: generic
    policy: generic@1
    members:
      - npc: goblin
        name: Goblin
        count: 8
        positions: [[9, 1], [10, 1], [9, 2], [10, 2], [9, 4], [10, 4], [9, 5], [10, 5]]
```

`template` loads `benchmarks/characters/<template>.yml`. `npc` loads a campaign NPC, then `templates/npcs/`. `positions` is required and must have one `[x, y]` per creature. Sides are the battle groups `party` and `monsters`, which oppose each other in `benchmarks/game.yml`.

The suite is four fights:

| File | What it measures |
|---|---|
| `fighters_vs_goblins.yml` | Four level-2 fighters against eight goblins on a small open field, already inside shortbow range. Focus fire and closing. |
| `wizard_fighter_vs_zombies.yml` | A wizard and a fighter against six zombies, with a one-square gap in a wall. |
| `party_vs_breath.yml` | Four adventurers against `breath_wyrm`, a cone `area_save` with recharge. Not a published dragon. |
| `party_vs_legendary.yml` | Four adventurers against `legendary_sentinel`, which has legendary actions and legendary resistance. Not a published legendary monster. |

## Seed contract

A trial calls `natural20.sim.seed.seed_process` before it builds the session. That seeds the global `random` module, which is what `natural20.die_roll` reads, and replaces `uuid.uuid4` with a generator fixed by the same seed. Trial `i` of a batch uses `seed + i`.

Two processes that run the same scenario at the same seed with `generic` on both sides write the same action trace: round, actor name, action type, target, and the hit, miss, and damage rows on the action result. Names come from the scenario, so they do not depend on uuid. Wall-clock fields are not part of the trace.

`--explain` adds the top three `generic@1` alternatives on the action the controller committed. That list is part of the trace, so an explained run will not match an unexplained one.

`random` is reproducible only for as long as the legal-action list is built in a stable order. LLM and JEV controllers are not part of this runner. They stay non-reproducible in `scripts/s1_battle_sim.py` and `scripts/simulate_priest_quarters.py`.

The pin replaces `uuid.uuid4` on the process. Do not call `seed_process` inside the web server.

## What a trial does

The runner builds the roster, places every creature, snapshots spell slots and resource pools, then runs the same turn shape as `Battle.while_active`: skip dead turns, start the turn, let the controller act until it passes, resolve legendary actions, advance. Combat-recap, kill-reaction dialogue, and callout phrasing are not registered.

Slot spend is the drop in remaining slots at each level of 1 or higher. Pool spend is the drop in `character_resource_pools`, `second_wind_count`, `action_surge_count`, and remaining legendary resistance.
