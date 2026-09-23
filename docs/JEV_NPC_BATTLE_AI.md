# JEV (TypeSafe "System One") NPC Battle AI

The JEV-powered NPC battle AI turns the LLM from a flat "pick an index" selector
into a **decision model that picks one fully-parameterized leaf action per
turn**. The planner flattens the action space into every currently-executable,
fully-materialized action (attacks with weapon + target, spells with slot +
target, strategic pre-pathed move destinations, ...) plus a guaranteed
`pass (end turn)` leaf, and asks JEV to pick exactly one in a **single
`decide_action()` call**.

- Provider: `JevProvider` in `n20-webapp/webapp/llm_handler.py`
  (`decide_action(state, options)` → `{index, choice, confidence, probabilities}`).
- Planner: `JevActionPlanner` / `jev_select_action()` in
  [`natural20/utils/jev_decision.py`](../natural20/utils/jev_decision.py).
- Wiring: `LlmMcpController.select_action()` and `LlmMcpController.move_for()`
  in [`natural20/llm_controller.py`](../natural20/llm_controller.py).
- Pass leaf: `EndTurnAction` in
  [`natural20/actions/end_turn_action.py`](../natural20/actions/end_turn_action.py).
- Tests: [`tests/test_npc_battle_ai.py`](../tests/test_npc_battle_ai.py).

## How a turn flows

When the controller's attached provider is an available `JevProvider`:

1. **Leaves from current state.** The planner enumerates fully-specified,
   currently-executable leaf actions:
   - *Battle-loop path* (`select_action`): the loop's pre-built
     `available_actions` is the authoritative set (raw move actions are
     excluded — movement is the loop's `move_for` job).
   - *Auto-build path* (`move_for`): every legal action class is auto-built
     to its leaves via the action builder (`autobuild`), plus the strategic
     movement leaves. Eligibility uses `_class_can()`, which tolerates both
     `Action.can` signatures — subclasses such as `MoveAction`,
     `DodgeAction`, and `HelpAction` override `can(entity, battle)` (2-arg)
     while the base class declares `can(entity, battle, options=None)` (3-arg).
   - Infeasible leaves are rejected (`_is_executable`: action/bonus/reaction
     resources, weapon and range checks, legal targets, usable items/objects).
2. **Strategic movement leaves.** Movement is offered as pre-pathed strategic
   options instead of raw neighbour squares:
   - `move -> <enemy>` — close to an enemy so it is in melee range (only
     offered when such a square is reachable and legal);
   - `move -> defensive square` — cover and/or away from enemies, ranked by
     cover, opportunity-attack risk, and distance to the nearest foe;
   - `move -> hide` — a reachable hiding spot;
   - `move -> offensive square` — in melee reach of at least one foe, ideally
     without provoking an OA.

   Only intents that currently have legal options are offered (an open map
   with no cover offers no defensive/hide intents, which is correct). Each
   leaf is a `MoveAction` carrying its full path.
3. **Guaranteed pass.** A final `pass (end turn)` leaf (`EndTurnAction`) is
   appended *after* capping, so the model can always choose to end the turn
   instead of acting.
 4. **One question.** `select()` renders a compact state string once (entity
     HP/position/movement, Armor Class, ability modifiers, visible enemies with
     HP/AC/distance and unconscious markers, allies with HP/AC, spell slots,
     usable items, active buffs/effects, spent resources, and the POV combat
     log of entries witnessed since the entity's last turn — see **State
     format** below) and makes a **single**
   `decide_action(state, options)` call over the
   ranked, capped leaf list (`MAX_JEV_LEAVES` total, `MAX_JEV_OPTIONS` per
   type). A tree that prunes down to a single leaf — which, since pass is
   always offered, means "nothing to do but end the turn" — is auto-selected
   without a round-trip.
5. **Commit.** The chosen leaf is returned as a fully-parameterized `Action`:
   - `move_for` returns movement leaves with their path simplified, returns
     **`None`** for a chosen `pass` (the turn loop ends the turn), and returns
     every other leaf (attacks, dodge, disengage, interact, ...) as-is for the
     loop to commit — mirroring `GenericController.move_for` semantics.
   - `select_action` likewise maps a chosen `pass` to `None`, and — when JEV
     is live — does **not** short-circuit a one-action menu, so the model
     still weighs the single offered action against pass.

### Why flattened (and a bug this fixed)

The original design descended the action tree recursively (one
`decide_action` call per level: type → weapon → target → square). Two
problems:

- **Cost:** ~25 round-trips per side per round in a duel.
- **Wrong actions got executed:** `LlmMcpController.move_for` only handled
  leaves with a `move_path` (`MoveAction`). Any non-move pick (e.g. an
  attack) raised `AttributeError`, which the `except` caught and turned into
  `GenericController.move_for` — the heuristic fallback, which typically
  returns *attack*. So JEV's non-move decisions were silently discarded and
  replaced by the generic AI. The flattened design fixes this by construction:
  every leaf is immediately committable, so what JEV picks is what executes.

Related fix: `DisengageAction.build()` and `DodgeAction.build()` carried
`action_type='attack'` (copy-paste), which misrouted `battle.commit`'s
event/VTT-animation dispatch (it branches on `action.action_type`); they now
build with their own types, and `DisengageBonusAction.build` no longer
inherited the non-bonus builder.

## State format

`JevActionPlanner._render_state` renders one line per field:

```text
Entity: Krizzit; HP 7/7; AC 15; pos [1, 5]; movement 30 ft; speed 30 ft
 mods: str-1 dex+2 con+0 int+0 wis-1 cha-1
 statuses: poisoned, prone
 visible enemies: Velka hp 45/45 ac 14 4 ft melee, Gort hp 3/7 ac 13 14 ft (unconscious)
allies: Noke hp 22/22 ac 14
spell slots: L3 2/2, L4 1/1
items: Potion of Healing, Healing Potion x2
effects: Haste 60s
 resources: action=0, bonus=0
 since last turn:
 - Velka attacked Krizzit (7/7), d6(1) + 2 dmg
 - Noke cast Shield on Noke (22/22)
 Task: choose the single best option index from the full list of actions
available this turn. Prefer actions that win the fight and keep the entity
alive.
```

Lines are optional and omitted when empty: `statuses: ...` and
`concentrating` (when active), `spell slots:`, `items:`, `effects:`,
`resources:`, and the `since last turn:` block. AC is folded into the
`Entity:` header and each enemy/ally entry rather than given its own line.

- **mods** — the entity's six ability modifiers, so the model can reason
   about attack/save expectations instead of only seeing HP.
 - **statuses** — the entity's current conditions, merged from two sources:
   the per-turn action markers (``dodge``/``disengage``) held in the battle
   state, and the standing conditions on ``entity.statuses`` (``poisoned``,
   ``prone``, ``grappled``, ``hidden``, ``unconscious``, …) — the same list
   every condition check (``entity.poisoned()``, ``prone()``, …) reads.
   Without the merge the model was blind to its own conditions; only the
   per-turn markers ever appeared. ``dead`` is dropped (a dead entity never
   renders state anyway).
 - **visible enemies** — each visible hostile with HP, **AC**, and distance
   (plus a ` melee` tag at 5 ft or less). An incapacitated foe — most notably
   one knocked down to 0 HP — is flagged ` (unconscious)`: the enemy filter
   only excludes `dead()` creatures, so without the marker a downed (but
   stable) enemy reads as a healthy target.
 - **allies** — visible non-hostile allies with HP and AC. Previously broken:
   the line referenced an undefined variable (`ent` instead of `entity`), the
   `NameError` was silently swallowed, and allies always rendered as
   `none`.
 - **AC** — the entity's own Armor Class on the `Entity:` header, and each
   enemy's/ally's AC on their entries, so the model can weigh hit-chance,
   not just HP. AC comes from `entity.armor_class()`, which already folds in
   active `ac_bonus` effects (Haste +2, Shield +5, ...) and class features —
   so a hasted target's boosted AC is what shows.
 - **spell slots** — current/max per level (`L3 2/2`), rendered for both
   `PlayerCharacter` and NPC spellcasters (both track
   `spell_slots_count`/`max_spell_slots`).
 - **items** — usable inventory (max 6 entries; the `x{qty}` suffix is
   printed only when the quantity exceeds 1), so the model can weigh
   `use <item>` leaves (potions, scrolls) against other actions.
 - **effects** — the named timed buffs/effects currently active on the
   entity (e.g. `effects: Haste 60s`). Many buff spells (Shield, Mage Armor,
   Bless, Haste, ...) register their mechanics on `entity.effects` *without*
   adding a status, so this is the only place the model learns a buff is up.
   Entries are deduplicated by spell name (Haste registers both a speed and an
   AC mechanic) and carry their remaining duration in seconds when bounded;
   expired entries are skipped and raw mechanism entries with no named spell
   are omitted.
 - **resources** — the action/bonus-action budget, rendered only once a
  resource has been spent, to keep the default state short.
- **since last turn (POV combat log)** — one line per *witnessed*
  `battle_log` entry since the entity's previous turn, e.g.
  `- Velka attacked Krizzit (7/7), d6(1) + 2 dmg` or
  `- Noke cast Haste on Noke (22/22)`. This gives the model a
  short-term memory of what happened (who hit whom, what was cast, recent
  movement) instead of only a static snapshot. How it works:
  - `Battle.start_turn()` records a per-entity mark
    (`turn_log_len` → previous value moved to `last_turn_log_len`) in the
    entity's battle state, so the planner can slice
    `battle_log[last_turn_log_len:]` for "since your last turn". On a
    creature's first turn the mark falls back to the whole log.
  - An entry is *witnessed* (`_pov_witnessed`) if the entity acted, was
    targeted, or `can_see` the actor/target — so hidden or out-of-sight
    events are not revealed.
  - Each entry is rendered by `_pov_line` (class-dispatched, like the leaf
    descriptions): attacks name the weapon/target and roll, spells name the
    spell and target, movement/self-buffs are short, and plain end-of-turn
    entries are skipped. The most recent `MAX_JEV_POV_LOG` (default 10)
    lines are kept, oldest first.
- **Name disambiguation** — when the acting entity's name collides with a
  listed name (exact or substring, case-insensitive — e.g. a renamed
  "Meringo (fighter2)" PC next to a goblin named "Meringo"), the colliding
  entry gets an `@[x, y]` position suffix. The same name map is threaded
  into leaf descriptions (move/attack/cast/use targets), so the state and
  the options stay consistent.
- **Spell names** — cast leaves use the spell's display name
  (`cast Haste (level 3) on Noke (22/22)`), not the YAML slug
  (`haste`): `SpellAction.spell_action.properties['name']` carries the
  label while `short_name()` derives from the slug.
- **Item leaves** — `use <item>` / `use <item> on <target>` leaves name
  the actual item (`use healing potion`), not a bare `use item`.

## Guarantees and fallbacks

- The tactical **state string** is rendered once per turn and shared by the
  single decision.
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
export TYPESAFE_API_KEY=...
# optional: TYPESAFE_BASE_URL, TYPESAFE_MODEL (default jev-latest), JEV_TIMEOUT
```

**Recommended for the VTT:** run JEV *only* for battle decisions and keep DM
narration and NPC dialogue on a generative model:

```bash
export BATTLE_LLM_PROVIDER=jev     # battle "LLM" controllers -> JEV
export LLM_PROVIDER=llamacpp       # DM sidebar chat (unchanged)
export NPC_LLM_PROVIDER=llamacpp   # NPC /talk (unchanged)
```

See **Using JEV as the default battle AI in the VTT** below for the full
setup, per-entity and campaign-default wiring, and verification.

(For a headless sim or a single controller you can still assign an
`LlmMcpController` with the JEV provider directly: `dm.set_controller
kind=llm` or `default_controllers` in `index.json`.) Jev cannot narrate —
keep NPC `/talk` on a generative provider.

## Using JEV as the default battle AI in the VTT

Jev is a *decision* model, not a prose generator, so the clean setup is to run
it **only** for battle decisions while DM narration and NPC dialogue stay on a
generative model. The webapp has a dedicated **battle provider** slot for this.

### 1. Environment (in `n20-webapp/webapp/.env`)

```bash
pip install typesafe-sdk

# Battle decisions -> JEV
BATTLE_LLM_PROVIDER=jev
TYPESAFE_API_KEY=***
# optional overrides (fall back to the shared TYPESAFE_* above):
# BATTLE_TYPESAFE_API_KEY=
# BATTLE_TYPESAFE_BASE_URL=http://your-collector:8901
# BATTLE_TYPESAFE_MODEL=jev-latest

# DM + NPC stay generative (unchanged from your normal config)
LLM_PROVIDER=llamacpp
NPC_LLM_PROVIDER=llamacpp
```

`BATTLE_LLM_PROVIDER` is the only new variable. `configure_battle_provider_from_environment`
(`webapp/blueprints/helpers/llm_init.py`) reads it at startup and initializes
`llm_handler.battle_provider` as a `JevProvider`. If it is unset, the battle
provider is `None` and everything behaves exactly as before (battle "LLM"
controllers use the DM provider). Any value other than `jev` is ignored with a
warning.

### 2. How a battle "LLM" controller resolves its provider

Every code path that builds an `LlmMcpController` for kind `llm` now calls
`llm_handler.battle_llm_provider()`, which returns the battle provider when set
and falls back to the DM provider otherwise:

- `/battle` start (per-entity `controller: "llm"` in the turn order)
- `POST /update_controller` (blueprint `dm.py` and legacy `app.py`)
- `GameManagement.build_combat_controller_for_entity` / `effective_npc_combat_controller`
- MCP `dm.set_controller` (`kind=llm`)

`LlmMcpController` prefers Jev's typed `decide_action` API when the provider
exposes it, and silently falls back to `GenericController` heuristics on any
call failure — so a wedged JEV endpoint degrades to heuristics, never to a
crash or a frozen turn.

### 3. Make JEV the default for a campaign's NPCs

The battle provider decides *which model* an `llm` controller uses; the
existing switches decide *which entities* use an `llm` controller:

- **Per entity:** in battle, set an NPC's controller to **LLM** (the
  `controller-select` in the combat UI, or `dm.set_controller kind=llm`).
- **Campaign default:** in the **AI** tab, set **Default NPC controller = LLM**.
  This persists `npc_default_controller: llm` into the campaign `index.json`
  and is used for every NPC that does not have an explicit controller.
- **Force all NPCs:** `NPC_LLM_COMBAT_ENABLED=1` makes
  `effective_npc_combat_controller()` return `llm` for every NPC regardless of
  the per-entity/campaign setting.

So the minimal "JEV is the default battle brain" setup is:

```bash
BATTLE_LLM_PROVIDER=jev
NPC_LLM_COMBAT_ENABLED=1          # or set the AI-tab default to LLM per campaign
```

### 4. Verify it is active

`GET /ai/provider-info` (DM role) now includes a `battle_provider` block:

```json
"battle_provider": {
  "initialized": true,
  "provider_type": "JevProvider",
  "current_model": "jev-latest",
  "base_url": "http://your-collector:8901"
}
```

`POST /ai/initialize-from-env` re-applies `BATTLE_LLM_PROVIDER` (alongside the
DM/NPC vars) and returns `battle_provider_ready`.

### 5. Fallbacks and safety

- `BATTLE_LLM_PROVIDER` unset → `battle_provider` is `None`; battle "LLM"
  controllers use the DM provider (no behavior change).
- `TYPESAFE_API_KEY` missing or `typesafe_sdk` not installed → the battle
  provider fails to initialize, logs an error, and battle falls back to the DM
  provider (controllers then use the DM model, or heuristics if the DM provider
  also has no battle path).
- A JEV call that times out or errors mid-turn → `LlmMcpController` falls back
  to `GenericController` heuristics for that turn.
- Jev is never used for DM narration or NPC `/talk`; those keep their own
  generative providers.

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

### Follow-up: vanilla 7 HP goblins + LLM comparison arm

To make controller quality visible, the follow-up swaps the goblins to
vanilla SRD stats (`--goblin-hp 7`, default 40 is the Krizzit-fixture
buff) and adds a third NPC arm: `--npc-ai llm` runs the same
`LlmMcpController` against an OpenAI-compatible chat model (`--llm-url`,
default `http://jedld-strix:8081`, a llama.cpp server hosting
`Qwen3.8-27B-UD-Q5_K_XL-nv-split`), so the decision-specialized JEV model
can be compared directly with a general-purpose chat model driving the
same battle. All arms share identical maps, seeds, and round caps.

- `--npc-ai generic`: heuristic control (no API calls).
- `--npc-ai jev`: the JEV recursive action-tree planner decides every
  action through `LlmMcpController.move_for`.
- `--npc-ai llm`: the chat model's `select_action` path
  (`_ask_llm_for_choice` -> provider `send_message`, flat action index,
  heuristic fallback on parse failure) is driven per action. The menu
  offered is the controller's standard action menu (auto-targeted
  attacks/specials) plus a compact set of full-speed, pre-pathed move
  destinations (squares adjacent to enemies + retreat squares, via
  `PathCompute`) — the same decision shape the JEV planner sees, instead
  of the engine's 8 single-step moves.

  Note: in the standard webapp flow (and pre-JEV) a chat-LLM
  provider's `move_for` falls back to heuristics and the LLM is only
  consulted for reactions — so this arm deliberately drives
  `select_action` directly to make the chat model the actual combat
  decision-maker.

```bash
# one background job per arm (seeds 20260921-25 generic / 20261921-25 random)
python scripts/jev_battle_sim.py --npc-ai generic --goblin-hp 7 \
    --opponent both --repeat 5 --max-rounds 10 --out sim_vanilla_control.json --quiet
python scripts/jev_battle_sim.py --npc-ai jev --goblin-hp 7 \
    --opponent both --repeat 5 --max-rounds 10 --out sim_vanilla_jev.json --quiet
python scripts/jev_battle_sim.py --npc-ai llm --goblin-hp 7 \
    --opponent both --repeat 5 --max-rounds 10 --out sim_vanilla_llm.json --quiet
```

Results (2026-09-22, vanilla 7 HP goblins, 5 games per opponent):

| NPC squad | vs deterministic AI (generic) | vs random policy |
|---|---|---|
| JEV (live) | 4W / 1L / 0D (80%) | 4W / 0L / 1D (80%) |
| heuristic (control) | 4W / 0L / 1D (80%) | 4W / 0L / 1D (80%) |
| chat LLM (Qwen3.8-27B via llama.cpp) | 0W / 0L / 5D (0%) | 0W / 0L / 5D (0%) |

JEV: 5,761 decision calls, 0 failures. Chat LLM: 741 (generic) /
1,107 (random) calls, 0 failures; every game ran to the 10-round cap
(14-20 min/game).

Reading:

- **JEV ≈ heuristic** at vanilla stats too: same 80%/80% win rate, but JEV
  took its first-ever loss (vs generic, seed 20260925) and wins slightly
  slower (avg 7.8/8.8 rounds vs 6.2/7.0).
- **The chat LLM is markedly more cautious**: all 10 games were draws at
  the round cap — the Qwen goblins survive (kite to corners, hide,
  disengage) but never commit to a kill. It neither wins nor loses.
- So the 7-HP swap did not discriminate between JEV and heuristics; the
  LLM arm is the one that shows a distinct behavioral profile (pure
  survival play).

### Variety simulation: five scenarios, flattened planner (2026-09-22)

To exercise the flattened single-call planner across roster shapes —
including PC spellcasters on the JEV side — the sim runs five scenarios
(5 seeds each, goblins at the 40-HP fixture buff, side B on JEV, side A on
the deterministic `GenericController`):

- `pc_vs_npc` 1 PC vs 4 NPCs · `duel` 1 PC vs 1 NPC · `npc_vs_npc` 3 vs 3
  NPCs · `pc_vs_pc` 2 vs 2 PCs · `team_pvp` 3 vs 3 PCs. JEV controls the
  NPCs in the first three scenarios and the PCs in the last two, so every
  roster kind (NPC, PC melee, PC caster) plays through the planner.

```bash
python scripts/jev_battle_sim.py \
    --scenario pc_vs_npc,duel,npc_vs_npc,pc_vs_pc,team_pvp \
    --side-a-ai generic --side-b-ai jev --goblin-hp 40 \
    --repeat 5 --max-rounds 10 --out sim_variety_flat.json
```

| scenario | JEV wins | generic wins | draws | avg rounds | JEV calls |
|---|---|---|---|---|---|
| pc_vs_npc | 5/5 (100%) | 0/5 | 0 | 1.6 | 163 |
| duel | 2/5 (40%) | 3/5 | 0 | 3.0 | 123 |
| npc_vs_npc | 3/5 (60%) | 1/5 | 1 | 5.4 | 349 |
| pc_vs_pc | 2/5 (40%) | 2/5 | 1 | 6.4 | 306 |
| team_pvp | 2/5 (40%) | 2/5 | 1 | 7.4 | 494 |

1,435 live `decide_action` calls, **0 failures**. 14 JEV-side spell casts
occurred, all in the two PC scenarios (self-buffs plus offensive spells on
enemy PCs); the JEV-side NPCs in the other three scenarios have no spells.

Reading:

- **Reliability holds at scale:** 0 failures across 1,435 calls on the
  flattened planner — what JEV picks is what executes, every turn.
- **Numbers still dominate** (`pc_vs_npc` 5/5): a 4-NPC squad at 40 goblin
  HP overwhelms a lone level-1 PC regardless of controller.
- **Even matchups are a wash** (duel 2/5, npc_vs_npc 3/5, pc_vs_pc 2/5,
  team_pvp 2/5): no win-rate edge over the heuristics yet, consistent with
  the earlier squad-vs-fighter measurements — the arena and stat spread
  mask controller quality.
- **Spellcasting works end-to-end through the planner:** PC casters on the
  JEV side genuinely cast (the `spell slots:`/`items:`/`mods:` state lines
  give the model the context to weigh a cast against an attack), and the
  enriched state is what the 14 casts were decided from.

### Validation after state enrichment (Armor Class, statuses, active buffs)

After `ac` was added to the `Entity:` / `visible enemies:` / `allies:` lines and
the optional `effects:` line was introduced, the same five-scenario matrix was
re-run (3 seeds each, side B on JEV, side A on `GenericController`, goblin HP
40) to confirm the enriched state does not regress reliability or win rates:

| scenario | JEV wins | generic wins | draws | avg rounds | JEV calls |
|---|---|---|---|---|---|
| pc_vs_npc | 3/3 (100%) | 0/3 | 0 | 1.7 | 107 |
| duel | 2/3 (67%) | 1/3 | 0 | 4.0 | 91 |
| npc_vs_npc | 1/3 (33%) | 1/3 | 1 | 6.0 | 264 |
| pc_vs_pc | 2/3 (67%) | 1/3 | 0 | 6.0 | 164 |
| team_pvp | 1/3 (33%) | 1/3 | 1 | 8.0 | 294 |

920 live `decide_action` calls, **0 failures**, call-weighted average latency
0.37 s/call. Read against the 5-seed baseline above, the per-scenario win rates
are within n=3 noise: `pc_vs_npc` still sweeps 100%; `duel` and `pc_vs_pc` tick
up (40% → 67%); `npc_vs_npc` and `team_pvp` tick down (60% → 33% and 40% →
33%) but those are each a single game at n=3. Net read: **no regression, no
clear win-rate edge yet, reliability still perfect**.

This run hit `https://api.typesafe.ai` directly (a `TYPESAFE_BASE_URL`
override). The 8901 passthrough collector was returning `403 error code: 1010`
at the time — upstream (Cloudflare) was WAF-blocking the proxy's default
`Python-urllib/...` User-Agent. The proxy now sends an SDK-style UA, so
collection runs can route through it again once the collector is restarted.

### Repeat-10 benchmark through the passthrough collector (2026-09-23)

After the collector User-Agent fix, the full five-scenario matrix was re-run
with **10 seeds per scenario**, all JEV traffic routed through
`http://jedld-strix:8901` (side A `GenericController`, side B JEV, goblin HP
40, `--max-rounds 10`):

| scenario | JEV wins | generic wins | draws | sign-test p | avg rounds | JEV calls |
|---|---|---|---|---|---|---|
| pc_vs_npc | 9/10 | 1/10 | 0 | 0.021 | 3.2 | 433 |
| duel | 5/10 | 5/10 | 0 | 1.000 | 2.7 | 207 |
| npc_vs_npc | 5/10 | 3/10 | 2 | 0.727 | 6.4 | 734 |
| pc_vs_pc | 3/10 | 4/10 | 3 | 1.000 | 7.5 | 671 |
| team_pvp | 4/10 | 2/10 | 4 | 0.688 | 8.1 | 932 |
| **overall** | **26/50 (52%, 95% CI 39–65%)** | 15/50 | 9/50 | — | — | **2977** |

2,977 live `decide_action` calls through the collector: **0 failures**,
call-weighted average latency 0.372 s/call. Sign test = exact two-sided test
on the non-draw pairs within each scenario.

Read of the numbers:

- **pc_vs_npc** is the only scenario with a statistically significant JEV edge
  (9–1, p≈0.02). It is numbers-dominated (4 NPCs vs 1 PC), and JEV's
  focus-fire + disengage loop is exactly what converts an outnumbered fight.
- **duel** is a coin flip (5–5).
- **npc_vs_npc** and **team_pvp** lean JEV (5–3 and 4–2 + 4 draws);
  **pc_vs_pc** leans generic (4–3 + 3 draws). None is significant at n=10.
- Overall, 52% (CI 39–65%) is **not distinguishable from a coin flip**
  against the hand-tuned heuristics. JEV's value at this sample size is
  reliability and play-shape, not win rate.

Behavioral profile (per entity, all 50 games):

| metric | generic (side A) | JEV (side B) |
|---|---|---|
| attacks/ent | 3.39 | 2.71 |
| hit rate | 0.58 | 0.52 |
| damage/ent | 13.58 | 9.04 |
| casts/ent | 0.90 | 0.53 |
| move steps/ent | 9.07 | 14.81 |
| distance/ent | 11.46 | 15.87 |
| focus-fire (top-target dmg share) | 0.79 | 0.87 |
| disengage/ent | 0.00 | 1.35 |
| help/ent | 0.34 | 0.03 |
| interact/ent | 1.28 | 0.08 |

The two arms play visibly different games: generic is aggressive and
support-heavy (more attacks, damage, casts, help, interact), while JEV is
maneuver-heavy (≈60% more move steps, near-universal disengage use, tighter
focus fire). The maneuver style does not convert into a win-rate edge against
generic at this sample size, but it is the style that wins the numbers fight
(pc_vs_npc).

### Engine bugs found and fixed by the benchmark

Two latent engine bugs surfaced while running the AI arms:

- **Grapple drag underflow** — `MoveAction` resolved grappled drags with
  `grappled_movement.pop()` on a shared path list; short paths or multiple
  grappled targets could underflow (`IndexError: pop from empty list`). Fixed
  in `natural20/actions/move_action.py` with safe slicing
  (`source_path[:-lag]`) that preserves the "each dragged target lags one
  more step" behavior.
- **Missing `Action.build()` classmethods** — `autobuild(...)`
  (`natural20/utils/action_builder.py`) calls `action_class.build(session,
  entity)`, but `BardicInspirationAction` had none. Any AI-controlled bard
  (generic, JEV, or the LLM arm) crashed its entire action menu with
  `type object 'BardicInspirationAction' has no attribute 'build'`, leaving
  the entity unable to act. Added the `build` classmethod
  (regression test in `tests/test_bardic_inspiration.py`).
  `DashAction` had the same gap on the JEV full-auto-build path (silently
  skipped); added there too.
- **Debug `print` in armor-proficiency hot path** —
  `Entity.proficient_with_equipped_armor()` printed
  `not proficient with <item>` on every call; LLM-arm prompt building
  called it hundreds of times per game, flooding sim logs. Removed
  (`natural20/entity.py`).

### Generative-LLM comparison arm (2026-09-23)

`scripts/jev_battle_sim.py --side-a-ai llm` drives the `LlmMcpController`
chat path (OpenAI-compatible endpoint) against JEV on side B. The 27B
llama.cpp server at `jedld-strix:8081` was wedged (repeated 180 s provider
timeouts), so the comparison ran against a local
`qwen3-vl:8b-instruct` on Ollama (CPU-bound: ~1.2 GB of the 12 GB model in
VRAM, 8–10 s per chat call). 8 games (duel ×4, pc_vs_pc ×4), `--max-rounds 10`:

| scenario | JEV wins | LLM wins | draws | LLM chat calls (fail) | JEV calls (fail) |
|---|---|---|---|---|---|
| duel | 3/4 | 0/4 | 1/4 | 213 (0) | 105 (0) |
| pc_vs_pc | 2/4 | 0/4 | 2/4 | 358 (0) | 197 (22) |
| overall | 5/8 | 0/8 | 3/8 | 571 (0) | 302 (22) |

Call latency: LLM 8.0–10.7 s/call; JEV 0.35–0.99 s/call in clean games. One
pc_vs_pc game ran under heavy CPU contention (Ollama saturating the box):
21 of its 38 JEV calls timed out and fell back to the generic heuristic for
the rest of that game — that side still won. (For reference, the 2,977-call
repeat-10 run through the collector had **0** failures.)

The headline result is behavioral: **the LLM-side entities never attacked in
any game** — 0 melee/ranged attacks and 0–2 spells across all 7 games where
they had turns. Instead they moved 37 steps/entity, hid 6.1×/entity, and
interacted (talking to enemies) 5.4×/entity, while JEV dealt 8.4 dmg/entity
with 1.08 casts and 0.86 focus-fire. All three draws hit the round cap with
the LLM side surviving by hiding. This is a systematic failure mode of the
generative arm in this arena — RP bias toward safe/flavor options instead of
damage — independent of the specific model, since it is a property of
free-form index selection over a flattened menu.

Caveats: n=8 (three of four duel seeds drew the same bard fixture); the 8B
CPU model is the weakest comparison target (a stronger generative model may
attack, and the 27B server was unavailable); the LLM arm's parse failures
fall back to the generic heuristic, which *would* attack — so the no-attack
pattern means the model's responses parsed fine and it genuinely chose
hide/move/interact.

### Is JEV the best AI solution? (analysis, 2026-09-23)

Put together, the three-way picture (same arena, goblin HP 40, max 10 rounds)
is:

| matchup | result | significant? |
|---|---|---|
| JEV vs generic (50 games) | 26–15, 9 draws (52% vs 30%) | no (CI 39–65% includes coin flip) |
| JEV vs generic, pc_vs_npc (10) | 9–1 | yes (p≈0.02) |
| JEV vs 8B LLM (8 games) | 5–0, 3 draws | directional only (n=8) |

So by raw win rate, **JEV is statistically tied with the hand-tuned generic
heuristics overall**, with a real edge only in the numbers-dominated
pc_vs_npc scenario, and it beats the local generative-LLM arm decisively
(albeit against a weak model at n=8). "Best" therefore depends on the
criterion:

- **Win rate on even fixtures**: generic heuristics are as good as JEV. The
  heuristics are well-tuned; JEV does not clearly beat them head-to-head.
- **Outnumbered fights**: JEV's focus-fire + disengage style wins
  (pc_vs_npc 9/10).
- **Reliability**: JEV wins. Structured API, typed choices, safe fallback to
  heuristics on any failure; 0 failures across 3,279 calls except one
  CPU-saturated game where 21 calls timed out (still won). The generative arm
  requires free-form index/tool-call parsing and its RP bias produced
  combatants that never attacked.
- **Latency/cost**: JEV wins ~25× (0.37 s vs 8–10 s per decision; a full game
  costs ~20–60 s of JEV API time vs 5–25 min of LLM inference).
- **Local deployment**: JEV has a path (NanoJEV distillation through the
  passthrough collector); the generative arm's local option (8B on CPU) is
  too slow, and the 27B GPU server proved unstable under load.
- **Play shape**: JEV is maneuver-heavy (≈60% more move steps, near-universal
  disengage, tighter focus fire); generic is aggressive and support-heavy.
  Neither style dominates the other at this sample size.

Net recommendation: keep **JEV as the default AI brain with the generic
heuristic as the fallback** — that pairing is at least as strong as either
side alone and is the only configuration that never dead-airs a turn. Do not
route tactical decisions through a generative chat LLM in this deployment
(keep it for narration). The highest-leverage next step is distillation
(NanoJEV): a local JEV-small would keep the decision quality while removing
the hosted-API dependency, latency, and cost.

Caveats for all of the above: single arena shape, level-1/2 fixture roster,
per-scenario n≤10 (sign tests are underpowered outside pc_vs_npc), and the
stat distribution (e.g., 6-HP level-1 wizards who die before their first
turn) masks controller quality in some games.

### Routing JEV traffic through the passthrough collector

For distillation data collection, JEV can be pointed at a passthrough
collector (nanollm `python/jev_api_server.py --passthrough`, port 8901)
instead of the hosted API. It forwards each `POST /v1/systemone` to the
real upstream JEV (with its own upstream key) and appends the
(request, response) pair to `data/jev/passthrough/interactions.jsonl`:

```bash
# n20-webapp/webapp/.env
# The SDK appends /v1/systemone to the base URL, so set the host only.
# Point it at whichever box is running the collector:
TYPESAFE_BASE_URL=http://jedld-strix:8901   # -> http://jedld-strix:8901/v1/systemone
# (or http://127.0.0.1:8901 for a local collector)
# keep TYPESAFE_API_KEY set: JevProvider refuses to initialize without
# one (the collector ignores it and uses its own upstream key)
```

Then convert a collected batch into NOUL training rows:

```bash
python3 scripts/passthrough_to_noul_rows.py \
    --input data/jev/passthrough/interactions.jsonl \
    --out data/jev/dnd_passthrough --emit-soft
```
