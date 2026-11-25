# Player instructions (System One step-by-step)

Lets a human player type a **free-text instruction** for their character —
"open the door and walk into the room", "attack the goblin with your rapier
then back away" — and have the JEV / "System One" decision model carry it
out **one action at a time**, with live progress and a Stop button.

Design rule: this is a *decision-model* feature. There is **no
generative-LLM fallback**. The Instruct button and the endpoints only
exist while a decision provider (any provider exposing
`decide_action(state, options) -> {index, ...}`, e.g. `JevProvider`) is
live for that entity. Without one, nothing renders and the API answers
`503`.

## Engine core — `natural20/utils/instruction_follow.py`

- `InstructionPlanner(JevActionPlanner)` — one instruction step per
  `select_step(battle, available_actions)` call:
  - builds the same flattened leaf-action menu the NPC battle AI uses
    (attacks, spells, items, shove/grapple, interactions, move leaves;
    `_move_leaves` has an out-of-combat branch that offers plain legal
    destinations when there is no battle);
  - the state block is the normal JEV state block plus
    `The player instructed you (their human): ...`, an
    `already done for this instruction:` history, and a task line that
    says to follow the instruction rather than its own tactics and to
    choose **stop** when nothing fits;
  - the always-present "pass (end turn)" leaf is removed and replaced by
    loop-control sentinels (never committed as actions):
    - `InstructionStop` — always offered (last option); the model can
      refuse or declare the instruction complete at any step;
    - `InstructionEndTurn` — offered **only** when the instruction text
      matches "end/finish/close (the|your|my...) turn";
    - `InstructionReady` — offered in combat while `ReadyAction.can(...)`;
      choosing it turns the whole instruction into a Ready (hold) action.
  - returns `(action_or_sentinel, description)`; the action is fully
    auto-targeted/enriched and can be committed as-is.
- `follow_instruction_step(...)` — one-step convenience entry point.
- `provider_can_follow_instructions(provider)` — availability gate
  (`is_available` + callable `decide_action`).
- `parse_player_instruction(...)` — the System One Ready parser: two flat
  Choice questions ("which trigger event?" over
  `natural20.ready_action.SUPPORTED_TRIGGER_EVENTS`, "which action?" over
  the entity's actual weapons/spells/items) return normalized
  `trigger` / `action_spec` structures. Two Choice calls cost far less
  than prose generation and cannot invent equipment the entity lacks.
- Budgets: `DEFAULT_INSTRUCTION_BUDGET = 8` steps per run,
  `MAX_INSTRUCTION_HISTORY = 12` completed steps echoed into the state.

## Webapp wiring

- Helper: `webapp/blueprints/helpers/instruction_follow.py`
  - `instruction_decision_provider(entity)` — resolves like battle AI
    (`ai_config.combat_llm_provider_for`: per-NPC `.ai.yaml` →
    `combat.llm_provider` → battle provider → DM provider), then gates
    with `provider_can_follow_instructions`.
  - `start_instruction` / `run_instruction_step` / `stop_instruction` —
    ownership (`current_user in entity_owners(entity)` or DM), turn
    gating, commit through `GameManagement.commit_and_update`, sentinel
    handling.
  - Run state: `session_state['active_instructions'][entity_uid]`
    (instruction, done labels, step count) — shared with MCP; the Flask
    session stores only the entity pointer.
- Routes (`blueprints/battle.py`):
  - `POST /instruction` `{id, instruction}` → first step;
  - `POST /instruction/step` `{id?}` → next step;
  - `POST /instruction/stop` `{id?}` → cancel.
  - Responses: `{status: 'step', step{label}, steps, remaining}`,
    `{status: 'done', reason}`, `{status: 'end_turn', ...}` (the route
    then runs the normal end-turn path), or an error with a message.
- Turn gating (mirrors the action bar):
  - out of combat — any time;
  - in combat — only the creature's own turn or its legendary-action
    phase; refused while a reaction / bardic-inspiration prompt is open;
  - out-of-turn intent in combat is expressed via the Ready action
    (the planner's `ready` sentinel, or a normal `ReadyAction` from the
    action bar).
- Action bar: `action_bar.py` adds the `instruction_available` context
  flag (never for map objects, dead or incapacitated creatures);
  `_action_tabs.html` renders an **Instruct** button next to End Turn.
- UI: `openInstructionModal` in `static/engine.js` — textarea + Run, a
  live step list fed by socket refreshes, Stop/Close that POST
  `/instruction/stop`. Steps auto-continue while the status is `step`.

## Ready (Hold) is System One too

`webapp/ready_action_handler.parse_ready_action_request` now prefers
`parse_player_instruction` when a decision provider is live for the
entity, keeping the generative-LLM path and the rule-based heuristic
purely as fallbacks, and always re-validating with
`_validate_5e_legality`.

## MCP mirror

`actions.instruction` (`webapp/mcp/tools_actions.py`),
`op=start|step|stop` with `entity_uid` and `instruction`; runs as `dm`.
`end_turn` results advance the turn like `actions.end_turn` does.

## Configuration

Same switches as the battle LLM (see `docs/JEV_NPC_BATTLE_AI.md` and
`docs/AI_CONFIG.md`): `BATTLE_LLM_PROVIDER=jev` + `TYPESAFE_*` (or
`BATTLE_TYPESAFE_*`), or any `.ai.yaml` combat profile whose provider
exposes `decide_action`.

## Tests

- `tests/test_instruction_follow.py` — leaf pick, stop/end-turn/ready
  sentinels, history in state, out-of-combat moves, ready parse call
  budget, provider gating.
- `n20-webapp/tests/webapp/test_instruction_follow.py` — Ready parsing
  prefers System One (and never calls the generative provider),
  fallback path intact, `/instruction` route wiring (400 / 404 / 503).
