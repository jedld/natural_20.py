## Quick orientation for AI coding agents

This repository is a D&D simulation and VTT used for AI research. Focus on two layers:

- Core engine (Python package `natural20/`) — game models, map, battle loop, controllers, and entity registry. Key files: `natural20/session.py`, `natural20/battle.py`, `natural20/entity.py`, `natural20/controller.py`, `natural20/generic_controller.py`, `natural20/llm_controller.py`.
- Web layer (Flask + small JS VTT) — `webapp/` contains the Flask app, LLM provider adapters, and the DM/chat handlers. Key files: `webapp/app.py`, `webapp/llm_handler.py`, `webapp/llm_conversation_handler.py`, `webapp/*` tests.

Core patterns and conventions (do not invent alternatives):

- Session-centered data: a `Session(root_path)` loads `game.yml` and YAML resources (maps, npcs, characters). Use `Session.register_entity` and `Session.entity_by_uid` for UID-based lookup; the centralized `EntityRegistry` is the canonical lookup.
- Controllers implement `select_action(battle, entity, available_actions)` and `move_for(entity, battle)`. `GenericController` provides heuristics; `LlmMcpController` (in `natural20/llm_controller.py`) delegates to an LLM and falls back safely to heuristics.
- Actions resolve via subclasses in `natural20/actions/`: each action builds intent with `build_map()`, gets auto-targeted by `natural20.utils.action_builder.autobuild`, and resolves through `Action.resolve` to enqueue battle events.
- Spells pair YAML definitions (`templates/items/spells.yml`) with Python classes in `natural20/spell/`; `SpellAction` loads the class through `natural20/utils/spell_loader.py`, applies resource costs via `Spell.consume`, and emits damage/miss events for the battle log.
  - AoE targeting primitives:
    - Cones: use `select_cone` in a spell's `build_map()` and preview squares via `Map.squares_in_cone(...)` (server returns `target_squares` from `/target`).
    - Directional cubes (e.g., Thunderwave): use `select_cube` in `build_map()`. The web UI will send `mode: 'cube'` with a clicked direction; the server previews with `Map.squares_in_adjacent_cube((caster_x, caster_y), (x, y), size_squares=3)` and returns `target_squares`. YAML typically provides `range_cube` (15 for Thunderwave).
- LLM integration: webapp uses provider adapters (`webapp/llm_handler.py`) with explicit function-call tokens like `[FUNCTION_CALL: get_map_info()]`. `LlmMcpController._build_prompt(...)` still expects a single integer index or an MCP tool call response.
- Make sure new objects/spells/items/entities can be properly serialized for save/load game support.

Developer workflows and commands (verified in repo README):

- Python deps: `pip install -r requirements.txt`.
- Run webapp (dev):
  - copy `webapp/env.example` → `webapp/.env` and set provider vars, or export env vars
  - `cd webapp && python -m flask run` (defaults to port 5000)
  - production gunicorn example in README: `gunicorn --worker-class eventlet --workers 1 --bind 0.0.0.0:5001 --timeout 120 app:app` with `TEMPLATE_DIR` env.
- Tests:
  - Python: `pytest` (supports `-n auto` for parallel runs)
  - JS unit tests for `webapp/static/engine.js`: `npm install` then `npx jest` (Node 18+ recommended). See README section "JavaScript tests".

Important environment variables (used by code):

- LLM_PROVIDER (ollama|openai|anthropic|mock) — default `ollama` in the controller.
- OLLAMA_BASE_URL, OLLAMA_MODEL — defaults used by `webapp/llm_handler.py` and `natural20/llm_controller.py`.
- OPENAI_API_KEY / ANTHROPIC_API_KEY — used by providers.
- N20_MCP_URL — optional MCP bridge URL used by `LlmMcpController._call_mcp_tool(prompt, n_actions)` (POST {prompt, n_actions} → {index}).
- N20_MCP_DM_TOKEN — optional shared secret. When set, callers can hit the in-process MCP tool surface at `/mcp/*` by sending header `X-MCP-Token: <value>` instead of an authenticated DM session. The surface is implemented in `webapp/mcp/` as a Flask blueprint with three discovery endpoints (`GET /mcp/manifest`, `GET /mcp/tools/list`, `POST /mcp/tools/call`) and tools split across `tools_world` (inspection), `tools_dm` (mutations) and `tools_actions` (list/execute actions, movement, end_turn, start/end battle). Tools are wrapped in MCP-style envelopes (`{"isError": bool, "content": [...]}`).

MCP tool catalogue (keep this list in sync with `webapp/mcp/tools_*.py`). Design rule: prefer one `op`-discriminated tool over many specialised tools to keep the surface small for token-constrained LLMs.
  - `tools_world`: `world.list_maps`, `world.get_map`, `world.list_entities`, `world.get_entity`, `world.get_battle`, `world.list_npc_types`.
  - `tools_dm` (DM mutations — mirror every DM-only Flask endpoint):
    - HP: `dm.set_hp`, `dm.heal`, `dm.damage`.
    - Status & properties: `dm.add_status`, `dm.remove_status`, `dm.set_property`.
    - Inventory: `dm.add_item`, `dm.remove_item`, `dm.equipment` (op=equip|unequip).
    - Resources: `dm.set_resource` (resource_type=action|bonus_action|reaction|spell_slot|temp_hp; op=set|add|subtract; spell_slot also takes character_class+level) — replaces `/update_action_resources`, `/update_spell_slots`, and the temp_hp branch of `/update_hp`.
    - Spawning / placement: `dm.spawn_npc`, `dm.spawn_object`, `dm.remove_entity`, `dm.teleport`.
    - Battle admin: `dm.battle_admin` (op=add_combatant|remove_combatant|reorder|set_group|next_turn) — mirrors `/add`, `/remove_from_battle`, `/reorder_initiative`, `/update_group`, and the DM-side `/next_turn`. `add_combatant` rolls initiative and slots the entity right after the current turn.
    - Controller assignment: `dm.set_controller` (kind=manual|ai|llm) — mirrors `/update_controller` set; lazy-imports `WebController` / `GenericController` / `LlmMcpController` and registers handlers.
    - Rest: `dm.rest` (type=short|long, optional `force`, `arcane_picks`, `hit_die_picks`) — mirrors `/rest` including the inline pick controller.
    - Persistence: `dm.save_load` (op=save|load|list) — mirrors `/admin/save`, `/admin/load`, `/admin/saves`; on load, refreshes the current battle map and re-emits `refresh_map`.
    - Effects: `dm.effect` (effect, action=start|stop|update, optional `config`, `scope`=global|map, optional `map_name`) — mirrors `/admin/effect`, persists into the module-level `active_effects` / `active_effects_map` caches.
    - Audio: `dm.sound` (op=list|play|volume|seek) — mirrors `/tracks`, `/sound`, `/volume`, `/seek`.
    - Time: `dm.advance_time` (op=add|set, `seconds`) — wraps `Session.increment_game_time` for narrative time skips.
  - `tools_actions`: `actions.list_available`, `actions.execute` (for `InteractAction` with `target`, `entity_uid` optional — omit or `dungeon_master` for DM-direct door/object interaction), `actions.move`, `actions.end_turn`, `actions.start_battle`, `actions.end_battle`.

  When adding a new DM-only Flask endpoint, also extend the matching `tools_dm` tool (preferring an extra `op` value over a brand-new tool) and update this catalogue.

Prompt/response patterns to preserve when changing LLM logic:

- `webapp/llm_handler.py` cleans thinking tags and enforces function-call responses. Keep that behavior when editing provider logic.
- `LlmMcpController._build_prompt(...)` renders a compact map + action list and expects the model to either: (a) return a zero-based index integer, or (b) call the MCP tool (function) with JSON {index, why}. If you change prompt format, keep the final instruction: "Return either a single integer index (0-based) or call choose_action with that index." (see code for exact wording).

Battle loop touchpoints:

- `Battle.start()` seeds initiative (`entity.initiative(...)` or custom), emits `start_of_combat`, and primes `current_turn_index` for `Battle.current_turn()`.
- `Battle.while_active()` is the core turn runner: invokes `start_turn()` (death saves, effects, `start_of_turn` event), asks the active controller (`begin_turn`, `select_action`, `move_for`), then calls `next_turn()` which advances rounds, triggers `top_of_the_round`, and checks `battle_ends()`.
- Actions flow through `Battle.execute_action` → `Action.resolve(...)` (maps, auto-targeting) → `Battle.commit(...)`, which applies `Action.apply` hooks, records animation payloads, and appends to `battle_log`.
- `Battle.trigger_event(...)` hits registered battlefield handlers and `Map.activate_map_triggers`; `event_manager` broadcasts `start_of_turn`, `end_of_turn`, `movement`, `end_of_combat`, etc.
- Entity state lives in `Battle.entities` (`EntitiesUIDMap`): tracks resources (`action`, `bonus_action`, `movement`), stealth, help, statuses; manipulate via `Battle.consume(...)`, `do_distract(...)`, `dismiss_help_for(...)`.
- Legendary and opportunity windows: `eval_legendary_action()` loops non-active entities for `legendary_action_listener`, while `trigger_opportunity_attack()` resolves reactions before normal queueing.

Files to check for implementation examples and extension points:

- `natural20/session.py` — loading resources, entity registry, save/load patterns.
- `natural20/llm_controller.py` — detailed prompt building, parsing, MCP bridge, fallback rules.
- `webapp/llm_handler.py` — provider adapters, session logging, function-call parsing and execution.
- `templates/` and `samples/` — example maps, characters, and level configs used by `Session` and the web UI.
- `natural20/map.py` — targeting helpers: `squares_in_cone(...)` and `squares_in_adjacent_cube(...)` (cardinal, face-adjacent 3x3 cube used by Thunderwave).

Extending spells and character classes:

- New spells require: YAML entry in `templates/items/spells.yml` (with `spell_list_classes` and optional `spell_class` override), a matching class in `natural20/spell/` implementing `build_map` and `resolve`, and registration inside `natural20/utils/spell_loader.py`. Reuse `natural20/spell/extensions/` helpers for shared targeting/damage logic.
  - UI targeting map params you can use in `build_map()`:
    - `select_target`, `select_empty_space`, `select_cone`, and `select_cube`.
    - For `select_cube`, return `{ 'type': 'select_cube', 'range': <feet>, 'num': 1 }` and then accept a 2D point in the subsequent `next(target)`.
  - YAML AoE keys: use `range_cone` for cones and `range_cube` for cubes.
  - Thunderwave specifics (baseline reference): 15‑ft cube originating from the caster (directional), CON save, half damage on success and no push, failed save pushes 10 ft away using `Entity.push_from(...)`, damage `2d8 + 1d8` per slot above 1st.
- To add a player class, create a mixin in `natural20/entity_class/` (see `wizard.py` for slot tables and rest hooks), add a YAML config in `templates/char_classes/`, and update `PlayerCharacter` usage if the class introduces custom actions or resources. Slot accounting should integrate with `PlayerCharacter.spell_slots` and class-specific `initialize_<klass>` routines.

Small gotchas discovered in the repo:

- Prompts can be long; `N20_LLM_PROMPT_MAX_CHARS` truncation logic is present in `LlmMcpController` — preserve or respect it when modifying prompt construction.
- Some LLM providers are optional; code defensively checks for provider availability. When adding imports depend on optional libs, prefer lazy imports and clear error messages.
- Many YAML-driven resources live under the `templates/` or `samples/` directories — tests and the web UI assume specific file names (e.g., `templates/index.json`, `game.yml`).
  - If you add new targeting modes for spells, ensure both sides are wired:
    - Web UI: add a handler in `webapp/static/engine.js` (e.g., for `select_cube`) and post `mode` along with `target`.
    - Server: update `/target` (preview squares) and the generic `/action` builder to recognize the new selector type and `mode` (e.g., treat `'cube'` like `'cone'` for coordinate targets).

If you change LLM behavior, unit tests to update or add:

- `tests/webapp/test_llm_logging.py`, `tests/webapp/test_real_response.py`, and other `tests/webapp/*` exercise provider parsing and function-call behavior. Update them if you alter the response-cleaning or function-call format.

If anything here is unclear or you want this shortened/expanded for a specific agent style (e.g., code-only vs. conversational), tell me which sections to refine and I'll iterate.
