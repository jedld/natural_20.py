# JEV (TypeSafe "System One") NPC Battle AI

The JEV-powered NPC battle AI turns the LLM from a flat "pick an index" selector
into a **recursive decision model** that walks the action builder's tree and
materializes a fully-parameterized `Action` — one `decide_action()` call per
level of the tree.

- Provider: `JevProvider` in `n20-webapp/webapp/llm_handler.py`
  (`decide_action(state, options)` → `{index, choice, confidence, probabilities}`).
- Planner: `JevActionPlanner` / `jev_select_action()` in
  [`natural20/utils/jev_decision.py`](../natural20/utils/jev_decision.py).
- Wiring: `LlmMcpController.select_action()` and `LlmMcpController.move_for()`
  in [`natural20/llm_controller.py`](../natural20/llm_controller.py).
- Tests: [`tests/test_npc_battle_ai.py`](../tests/test_npc_battle_ai.py).

## How a turn flows

When the controller's attached provider is an available `JevProvider`:

1. **Choices from current state.** The planner groups the entity's candidate
   actions by top-level *type*. It either groups the battle loop's pre-built
   `available_actions` list, or rebuilds every legal action class through the
   action builder (`autobuild`) so the tree is fully materializable.
   Eligibility uses `_class_can()`, which tolerates both `Action.can`
   signatures — subclasses such as `MoveAction`, `DodgeAction`, and
   `HelpAction` override `can(entity, battle)` (2-arg) while the base class
   declares `can(entity, battle, options=None)` (3-arg).
2. **The model recommends the action *type*.** Level 1 offers one option per
   group, e.g. `attack (weapons: Scimitar, Shortbow)`, `cast a spell (haste,
   polymorph)`, `move (reposition: engage, defensive, hide, or offensive
   square)`, `help an ally ...`, `dodge ...`, `hide ...`, `look`, `shove`,
   `grapple`, ...
3. **Recursive descent into the chosen type.**
   - `attack` → **weapon** → **target**
     (descends `AttackAction.build_map()` level by level via `build_params`).
   - `spell` → **spell name (and level)** → **target / AoE anchor**
     (e.g. `Haste (level 3)` → target).
   - `help` → **ally**
   - `move` → **strategic intent** → **concrete destination square**
     (special handling, see below).
   - Parameter-less types (`dodge`, `hide`, `look`, ...) resolve in one level.
   - If the `build_map` descent fails, the planner falls back to a single JEV
     choice among that type's pre-built leaf actions.

Movement is the special case:

4. **`move` has its own intent subtree** (not the raw neighbour-square list):
   - `move -> entity` — close to an enemy so it is in our melee range
     (only offered when such a square is reachable and legal);
   - `move -> defensive square` — cover and/or away from enemies, ranked by
     cover, opportunity-attack risk, and distance to the nearest foe;
   - `move -> hide` — a reachable hiding spot;
   - `move -> offensive square` — in melee reach of at least one foe, ideally
     without provoking an OA.

   Only intents that currently have legal options are offered (an open map
   with no cover offers no defensive/hide intents, which is correct). The
   second decision picks the concrete destination within the chosen intent.

## Guarantees and fallbacks

- A compact **state string** (entity HP/position/movement, visible enemies with
  distance, allies, spell slots) is rendered once and prepended to every
  decision so each level sees the same tactical context.
- A **decision budget** (`DEFAULT_MAX_DECISIONS`) caps round-trips per turn.
- The planner returns `None` on *any* failure (provider error, budget
  exhaustion, empty options, bad index). The controller then falls through to:
  the flat `decide_action` index path (`select_action`), or the generic
  heuristic controller (`move_for` / `GenericController`).
- If the SDK or `TYPESAFE_API_KEY` is missing, `JevProvider.is_available` is
  `False` and the JEV path is never entered — the controller degrades to its
  usual behavior.

## Enabling it

```bash
pip install typesafe-sdk
export LLM_PROVIDER=jev            # or NPC_LLM_PROVIDER=jev for NPC turns only
export TYPESAFE_API_KEY=...
# optional: TYPESAFE_BASE_URL, TYPESAFE_MODEL (default jev-latest), JEV_TIMEOUT
```

Assign an `LlmMcpController` with the JEV provider to the NPC
(`dm.set_controller kind=llm` or `default_controllers` in `index.json`).
Jev cannot narrate — keep NPC `/talk` on a generative provider.

## Headless battle simulation (win-rate analysis)

`scripts/jev_battle_sim.py` runs a full battle headlessly (no Flask) to
measure how JEV-controlled NPCs perform against baseline controllers:

- Party: the L7 fighter fixture (`tests/fixtures/high_elf_fighter.yml`) run
  by `--opponent generic` (deterministic `GenericController` heuristics,
  seeded dice) or `--opponent random` (uniform random over legal actions).
- NPCs: 3 goblins (40 HP) + 1 ogre, each with its own `LlmMcpController`
  backed by one shared live `JevProvider`.
- Map: `tests/fixtures/jev_arena.yml` — an empty 10x8 arena (no meta
  entities or spawners, so nothing uncontrolled joins the fight).
- The turn loop mirrors `Battle.while_active` + the webapp `ai_loop`
  (`move_for` -> `action` -> `commit` until no actions remain).

```bash
python scripts/jev_battle_sim.py --opponent both --repeat 5 \
    --max-rounds 10 --out sim_result.json
# -> per-game log + JSON, plus a win-rate summary per opponent:
#    vs generic  JEV wins X/N ...
#    vs random   JEV wins X/N ...
```

Every JEV round-trip is counted (`decide_action`/`decide_bool` calls,
failures, latency) and reported per game; failures fall back to the
heuristic controller, so a non-zero failure count means part of a game was
played by the fallback, not JEV. `--seed` makes the dice (and random NPC
names) reproducible; each game in a `--repeat` batch uses `seed + i`
(generic) or `seed + 1000 + i` (random).

First live measurement (10 games each side, 2026-09-21, `jev-latest`,
~6.7k API calls, **0 failures** — the heuristic fallback never triggered).
Control group: the identical NPC squad on `GenericController`
(`--npc-ai generic`, no API calls).

| NPC squad | vs deterministic AI (generic) | vs random policy |
|---|---|---|
| JEV (live) | 4W / 0L / 1D (80%) | 2W / 0L / 3D (40%) |
| heuristic (control) | 4W / 0L / 1D (80%) | 4W / 0L / 1D (80%) |

Reading:

- **Reliability:** 100% — 0 failures across ~6.7k live `decide_action`
  calls; every NPC action was a genuine JEV decision.
- **Never lost:** JEV NPCs lost 0 of 10 to either baseline.
- **No measurable edge in this matchup.** The squad is stat-heavy
  (goblins at 40 HP, per the Krizzit fixture), so the NPC side wins or
  stalls regardless of controller; the open arena lets the L7 fighter
  kite at longbow range, which caps the NPC win rate. Against the random
  kiter, the heuristic actually finishes games faster (80% vs 40%); JEV
  draws 3/5 there.
- A more discriminating follow-up: vanilla 7-HP goblins (no stat buff)
  or a larger/more varied squad, where controller quality should show up
  in the win rate instead of being masked by HP.
