# Webapp Blueprint Architecture

The Natural 20 web VTT was refactored from a monolithic `webapp/app.py` (~8,000 lines) into domain Flask blueprints and shared helpers. **HTTP paths and runtime behavior are unchanged**; only module layout changed.

## Composition root

`webapp/app.py` (~320 lines) is the bootstrap only:

- Flask / Flask-Session / CORS / SocketIO setup
- Campaign load (`load_campaign_config`, `Session`, `GameManagement`)
- `register_globals(...)` — wires lazy getters for shared runtime state
- Helper registration: template globals, effect listeners, LLM init, perf hooks
- `wire_conversation_service(...)` — registers `/talk` and related conversation helpers
- Blueprint registration (see table below)
- `register_socketio_handlers(socketio)` — SocketIO event handlers
- MCP blueprint registration
- Backward-compat re-exports on the `app` module for tests and lazy imports

Do **not** add new HTTP routes to `app.py` unless they are bootstrap-only (health checks, wiring). Put domain routes in the appropriate blueprint.

## Blueprint map

| Blueprint | Module | Example routes | Endpoint prefix |
|---|---|---|---|
| `assets` | `blueprints/assets.py` | `/assets/*`, `/create_map`, `/upload_map_background`, `/delete_map` | `assets.*` |
| `auth` | `blueprints/auth.py` | `/login`, `/logout`, `/character_selection`, `/select_character` | `auth.*` |
| `ai` | `blueprints/ai.py` | `/ai/*`, including `/ai/config*` (DM Console → AI Settings; `.ai.yaml` via `webapp/ai_config.py`, see [AI_CONFIG.md](AI_CONFIG.md)) | `ai.*` |
| `navigation` | `blueprints/navigation.py` | `/`, `/command`, `/path`, `/switch_map`, `/update`, `/map_state`, `/party/invite`, `/party/sidekick_follow` | `navigation.*` |
| `character` | `blueprints/character.py` | `/character_builder/*`, `/character_editor/*`, journal CRUD, `/inventory/container/*`, `/inventory/use` | `character.*` |
| `notebook` | `blueprints/notebook.py` | `/notebook`, `/notebook/items`, `/notebook/folders`, `/notebook/shared/<id>` — player/campaign notes (SQLite) | `notebook.*` |
| `battle` | `blueprints/battle.py` | `/start`, `/action`, `/target`, `/actions`, `/actions/batch`, turn order, combat log | `battle.*` |
| `dm` | `blueprints/dm.py` | `/admin/*`, `/spawn_*`, inventory, `/equipment`, `/item_card`, `/rest`, audio, entity admin, `/update_resource_pool`, `/update_inspiration`, `/admin/map_sets`, `/admin/map_set/*`, `/admin/sidekick`, `/dm/notes`, `/admin/illumination`, `/move_entity`, `/delete_entity`, `/undo_delete_entity` (DM Delete-key + Ctrl+Z), `/admin/users` + `/admin/manage_users` (login/role/PC-assignment management, backed by `webapp/user_management.py`) | `dm.*` |
| `edit` | `blueprints/edit.py` | `/edit/session`, `/edit/overlay`, `/edit/move`, `/edit/map_graph`, `/edit/map_graph/layout` (campaign YAML authoring; per-DM-session edit mode) | `edit.*` |
| `merchant` | `blueprints/merchant.py` | `/merchant`, `/merchant/preview`, `/merchant/trade` | `merchant.*` |
| `client_3d` | `blueprints/client_3d.py` | `/3d` — Three.js VTT sibling (see [VTT_3D.md](VTT_3D.md)) | `client_3d.*` |
| *(none)* | `blueprints/socketio_handlers.py` | `connect`, `register`, `message`, `disconnect`, `request_effects` | N/A (SocketIO) |
| `mcp` | `mcp/` package | `POST /mcp` (Streamable HTTP JSON-RPC), `/mcp/manifest`, `/mcp/tools/list`, `/mcp/tools/call` | `mcp.*` |

Conversation routes (`/talk`, etc.) are registered by `conversation_service.register_conversation_routes` via `helpers/conversation_wiring.py`, not a blueprint.

## Roll Initiative (`POST /battle`)

- The `Battle` is built from the maps the combatants stand on (`_battle_maps_for`), not the campaign's starting map, so battles on maps created or edited at runtime work. Unknown combatant UIDs return 400.
- `_validate_opposing_groups` checks the battle roster (`battle.entities`) before `battle.start()`; `combat_order` is empty until initiative is rolled. The battle is only installed as current after validation passes.
- `controller: "manual"` entries use `GameControllerRegistry.manual_controller_for_entity`: the existing `WebController` (assigned players keep control) or a new one; whenever no user is attached, `dm` is added so the DM drives the turn.

## Pathfinding in battle mode

The webapp uses a **server-client pathfinding architecture** for combat movement:

1. **Server-side** (`natural20/ai/path_compute.py`): Full A* pathfinding with `map.passable()` which checks `map.tokens[]` for battle entities. Respects DnD 5e creature blocking rules (you cannot move through another creature's space unless two sizes larger or squeezing).
2. **Client-side** (`webapp/static/path_compute.js`): Lightweight A* using a **pathfinding snapshot** built by `natural20/ai/pathfinding_cost_map.build_pathfinding_snapshot()`. The snapshot precomputes tile flags (blocked, difficult, hazard, passability bitmasks) for O(1) client-side lookups.

### Battle entity blocking

When `build_pathfinding_snapshot()` receives a `battle` argument, it collects opposing combatant positions and marks them as blocked in the snapshot's `blocked` array and passability bitmasks. This ensures client-side A* avoids walking through enemies — the same behavior as server-side pathfinding.

**Key implementation details:**

- `navigation.py:compute_path()` (line ~544) calls `PathCompute(battle, battle_map, entity)` for server-side paths.
- `navigation.py:path_cost_map()` (line ~741) calls `build_pathfinding_snapshot(battle_map, entity, battle)` for client-side cost maps.
- `build_pathfinding_snapshot()` filters combatants by: `battle.opposing()`, `incapacitated()` check, and `token_size()` for multi-tile entities.
- Enemies at `battle.entity_or_object_pos(combatant)` positions are marked in the `blocked` array and excluded from `pass_normal`/`pass_squeeze` bitmasks.
- The `ignore_opposing` flag (used for out-of-combat movement) skips enemy blocking entirely.

### Movement distance computation

Server-side `PathCompute.trim_path_by_movement()` correctly converts grid distance to feet:

```python
# distances[px][py] = grid steps from source
grid_steps = distances[px][py]
available_movement_cost = grid_steps * self.map.feet_per_grid
# Compare against entity's available movement (feet)
if available_movement_cost > entity.available_movement(battle):
    # Trim path here
```

This conforms with DnD 5e where movement is measured in feet (5 ft = 1 grid square by default).

### Tests

- `tests/test_pathfinding_cost_map.py` — parity between `PathCompute` and `SnapshotPathCompute`
- `tests/test_pathfinding_battle_entities.py` — battle combatant blocking verification (mock + real `Battle` object tests)

## Shared helpers

`webapp/blueprints/helpers/` holds cross-cutting logic. Helpers must **not** import blueprint modules (avoid cycles).

| Module | Role |
|---|---|
| `runtime_state.py` | Lazy getters/setters: `get_current_game()`, `get_socketio()`, `get_event_manager()`, tile/map padding, etc. |
| `auth_utils.py` | `logged_in`, `roles_for_username`, `user_role` |
| `template_globals.py` | Jinja globals/filters (`t`, `describe_terrain`, `process_action_hash`, …) |
| `action_utils.py` | Action class resolution, battle action helpers |
| `effects.py` | Effect caches, `register_effect_listeners()` (battle-end narration, control override), `register_battle_end_hook_handlers()` (campaign hooks + combat recap + NPC kill reactions) |
| `special_effects.py` | Client effect payload filtering |
| `journal_utils.py` | `_record_narration_for_pcs` (shared by effects and battle) |
| `character_builder_utils.py` | Character builder/import helpers |
| `character_builder_restrictions.py` | Campaign min/max level and class/spell/feat/ability blacklists |
| `character_selection.py` | Login PC vs sidekick partition and `character_selection.sidekick_slots` |
| `pvp.py` | PvP team config and battle autofill |
| `map_sets.py` | Activate / create / assign / place-party / party-travel for campaign map sets (`docs/MAP_SETS.md`) |
| `party_travel.py` | Confirmation prompt when a PC steps on a `party_travel` teleporter; Interact / tile hover retries after cancel |
| `sidekick_control.py` | Join/leave party sidekicks, WebController owner registration, and the auto-follow toggle (`set_auto_follow_and_control`) |
| `npc_stat_block.py` | 5e creature stat-block payload, NPC sheet access (`/info`) |
| `llm_init.py` | LLM handler init, game-context function registration |
| `object_spawner_utils.py` | Object catalog categories for the object spawner |
| `npc_spawner_utils.py` | NPC catalog CR labels, unique flags, and live map-set presence |
| `asset_utils.py` | Static URL helpers; `/assets/items` and `/assets/objects` resolve campaign (then imports / expansion packs) before bundled static |
| `campaign_config.py` | Campaign path / index loading |
| `cors_config.py` | CORS origins, SocketIO async mode |
| `perf.py` | Request timing instrumentation |
| `conversation_wiring.py` | `ConversationService` setup and `/talk` route registration |

Blueprints read shared state through `runtime_state` accessors, **not** by importing from `webapp.app`.

### LLM providers

Provider adapters live in `webapp/llm_handler.py` behind an `LLMProvider` ABC. `LLMHandler` owns a
`providers` registry (`ollama`, `openai`, `anthropic`, `llama_cpp`, `mock`, and `jev`) and
instantiates the configured one via `_instantiate_provider(name)`. Env wiring for the DM provider is in
`configure_llm_handler_from_environment()` and for the NPC provider in
`configure_npc_provider_from_environment()` (both in `blueprints/helpers/llm_init.py`).

`JevProvider` (TypeSafe "System One") is a **decision** provider, not a prose generator:

- Native API: `decide_action(state, options)` → `{index, choice, confidence, probabilities}` and
  `decide_bool(state, question)` → `{noul, confidence}`, wrapping `TypeSafeClient.system_one` with
  `Choice` / `Noul` questions.
- `send_message()` intentionally returns a note (Jev cannot narrate); keep NPC `/talk` on a
  generative provider (`ollama`/`openai`/`llama_cpp`).
- **NPC battle AI (recursive action tree):** when the attached provider is a `JevProvider`,
  `LlmMcpController.select_action` / `move_for` route through `JevActionPlanner` in
  `natural20/utils/jev_decision.py`, which recommends the action *type* first (attack, spell,
  move, help, dodge, ...) and then recursively formulates the full tree —
  `attack -> weapon -> target`, `spell -> spell name (and level) -> target`, and special
  movement handling `move -> entity (melee range) | defensive square | hide | offensive square`.
  See `docs/JEV_NPC_BATTLE_AI.md`. Any planner failure falls back to the flat `decide_action`
  index path (`_ask_llm_for_choice`) or the generic heuristic controller.
- Requires `pip install typesafe-sdk`; degrades gracefully (provider reports unavailable) if the SDK
  or `TYPESAFE_API_KEY` is missing. Env: `LLM_PROVIDER=jev`, `TYPESAFE_API_KEY`, `TYPESAFE_BASE_URL`
  (default `https://api.typesafe.ai`), `TYPESAFE_MODEL` / `TYPESAFE_DEFAULT_MODEL` (default
  `jev-latest`), `JEV_TIMEOUT` (default `8`).
- Tests: `tests/webapp/test_jev_provider.py` (provider) and `tests/test_npc_battle_ai.py`
  (recursive planner + controller wiring).

### Campaign character builder limits

Set in `user_levels/<campaign>/game.yml` (or `index.json`) under `character_builder`:

```yaml
character_builder:
  min_level: 1
  max_level: 3
  # Optional allow-list. Omit or leave empty to offer every loaded
  # background (campaign + templates). A non-empty list hides the rest.
  # allowed_backgrounds: [haunted_one]
  blacklist:
    classes: [warlock, paladin]
    spells: [fireball, wish]
    feats: [sharpshooter]
    abilities: [action_surge]   # class features / subclasses by slug
    backgrounds: []             # optional denylist (used when no allow-list)
```

`game.yml` overrides `index.json` when both define the same keys. The builder UI and `/create_character` / `/update_character` enforce these limits server-side. Death House omits `allowed_backgrounds` so Haunted One and the SRD template backgrounds are all selectable.

Login character select can also require a companion. In `game.yml`:

```yaml
character_selection:
  sidekick_slots: 1   # 0 = one hero; 1 = one PC and one sidekick
```

The UI splits **Player Characters** and **Sidekicks**. Death House sets `sidekick_slots: 1`.

## Adding or moving routes

1. Pick the blueprint by domain (combat → `battle`, DM admin → `dm`, etc.).
2. Keep the **same URL path and HTTP method** unless intentionally changing the API.
3. Use blueprint-local `@<bp>.route(...)`; endpoint names become `<blueprint>.<function_name>`.
4. Update templates/JS `url_for(...)` if endpoint names change (prefer keeping function names stable).
5. For DM-only endpoints, extend the matching MCP tool in `webapp/mcp/tools_dm.py` and update `AGENTS.md` catalogue.
6. Regenerate parity baselines and run parity tests (below).

### Import conventions

- Action classes: `from natural20.actions.attack_action import AttackAction` (not `natural20.action`).
- Session/game: `get_current_game()` from `runtime_state`, not module-level `app.current_game` inside blueprints.
- Optional lazy imports from `webapp.app` remain for MCP and legacy tests; prefer `runtime_state` in new code.

## Parity harness

Route and SocketIO inventories are frozen in `plans/artifacts/`:

- `routes_baseline.json` — URL rules and endpoint names
- `endpoints_baseline.json` — Flask endpoint map
- `socketio_events_baseline.json` — SocketIO event names

Regenerate after route moves:

```bash
python scripts/generate_baseline_artifacts.py
```

Run parity tests:

```bash
pytest -q tests/webapp/test_route_inventory_parity.py \
       tests/webapp/test_endpoint_name_parity.py \
       tests/webapp/test_socketio_event_parity.py
```

Blueprint smoke tests live in `tests/webapp/test_*_blueprint.py` and `tests/webapp/test_socketio_handlers.py`.

## Bootstrap wiring checklist

When adding startup-side behavior, wire it from `app.py` in this order (approximate):

1. `register_globals(...)`
2. `register_template_globals(app)`
3. `register_effect_listeners(...)` — required for battle-end narration and control-override events
4. LLM / conversation / PvP helpers, then `register_battle_end_hook_handlers(...)` (campaign `battle_end_hooks`, post-combat journal/memory recaps, and the `died` listener for NPC kill reactions in `webapp/npc_kill_reaction.py`)
5. `register_perf_instrumentation()`
6. Register blueprints
7. `register_socketio_handlers(socketio)`

`wire_conversation_service` uses **live getters** (`lambda: current_game`) so tests can monkeypatch `app.current_game` after import.

## Campaign edit mode

Logged-in DMs can enter and leave campaign edit mode at any time from the VTT hamburger menu (**Enter Edit Mode** / **Exit Edit Mode**), including mid-game. Edit chrome (fixture overlays, landmarks panel, YAML spawners, Map Connections) is limited to **that DM's Flask session**; other players keep a normal play session.

Bottom-of-map chrome is stacked in two docks so panels do not cover each other: `#map-chrome-left` (zoom controls, then landmarks above them in edit mode) and `#map-chrome-right` (minimized local chat above DM notes). The DM POV portrait dock is content-sized and centered between those columns.

The hamburger (`#floating-menu`) uses the same dark chrome. DM entries are grouped as Combat, Table, Spawn, Authoring (edit mode, map pins, AI assistant), then Session (notes, journal, combat log, world time, log out). Icons are Glyphicons already used elsewhere in the VTT.

`POST /edit/session` with `{ "enabled": true|false }` toggles `session['edit_mode']`. YAML mutations (`/edit/move`, place/remove, etc.) still write `maps/*.yml` via `natural20/map_editor.py` and reload the live map, so the world changes are shared — only the authoring UI is session-scoped. Tokens with no YAML entry (party members added with `/add`, spawned NPCs) are moved live instead (`_move_live_entity`; the response has `persisted: false`), so the position lasts until the map reloads unless the game is saved.

`GET /edit/overlay` is rebuilt from map YAML on each request. It must not call `Session.load_object()` for NPC/PC legend types: those names are missing from `items/objects.yml`, and a catalog miss used to reload the whole YAML file once per entity (about 1.5s on tavern). The client also coalesces overlay reloads so a tile refresh does not fire the endpoint twice.

`--edit` / `N20_EDIT_MODE=1` is optional: it no longer auto-logs anyone in or grants DM to every user. After a real DM login, that session starts already in edit mode. The DM menu includes **Map Connections** (`GET /edit/map_graph`, opens in a new tab) while edit mode is on. Dragging map tiles persists their positions to campaign `map_graph.yml` via `POST /edit/map_graph/layout`; reload restores that layout.

## DM entity delete (Delete / Ctrl+Z)

DMs can remove the currently focused entity — the active action-bar entry, or the
POV entity when no bar is open — by pressing **Delete**, and restore the most
recent removal with **Ctrl+Z** (Cmd+Z on macOS).

- `POST /delete_entity` (`blueprints/dm.py`) captures undo state *before* removal:
  map, square, group, battle membership + initiative, and whether the DM's POV
  was on the entity. State is kept in `session_state['entity_delete_undo']`
  (per-DM in-memory stack, newest last, capped at 20).
- `POST /undo_delete_entity` restores the token to its original square (nearest
  free square via spiral search if it is now occupied), re-adds it to the active
  battle with its saved initiative when it was deleted mid-battle, and restores
  the DM POV if it had pointed at the removed entity. Emits `initiative`,
  `turn`, and `refresh_map`.
- Client side lives in `webapp/static/engine.js` (`keydown.dmEntityDelete`
  handler + `DmDeleteUndo` surface). The hotkeys are suppressed while typing in
  inputs/modals, while targeting/movement selection is active, and while
  binding action-bar hotkeys (where Backspace/Delete clears the pending
  binding). In campaign edit mode the Delete key still removes the map YAML
  fixture via `window.EditMode.removeFixture(...)` (persisted, not undo-stack).
- Players get 403 on both routes; only the DM of a session sees the hotkeys act.
- Tests: `n20-webapp/tests/webapp/test_entity_delete_undo.py` (server round-trips)
  and the `DM Delete / Ctrl+Z` block in `n20-webapp/webapp/static/engine.test.js`.

## Create new map (unified form)

The map-picker's **Create New Map** tile (`#create-new-map` inside `#mapModal`)
opens a single unified Bootstrap modal (`#newMapModal`, DM-only, sibling of
`#mapModal` in `webapp/templates/index.html`) instead of four sequential
`window.prompt()` dialogs plus a separate image upload. One form configures
everything and posts one multipart request:

- Fields: map **name** (slug-validated on the client), **width/height**
  (2–100 tiles), **illumination** slider (0–100% → `0..1`), **description**,
  **map set** select (existing sets from the `map_sets` render context +
  `+ New map set…` which reveals a label input), and a **background image**
  dropzone (file browse + drag-drop, live `URL.createObjectURL` preview,
  clear button).
- Submit: `NewMapForm` (`webapp/static/engine.js`) builds a `FormData`
  (`name`, `width`, `height`, optional `description` / `illumination` /
  `map_set` / `map_set_label` / `image`) and `$.ajax`-posts it (multipart;
  `ajaxPost` cannot) to `POST /create_map` (`blueprints/assets.py`).
- Server: writes `maps/<name>.yml` (with `description`,
  `map.illumination`, and `background_image` when an image is uploaded),
  saves the image as PNG under `assets/maps/<name>.png` (PIL RGBA
  conversion, raw-save fallback) or generates a placeholder thumbnail,
  registers the map via `Session.register_map(..., map_set=...)`, and
  persists `maps` + `map_sets` to `game.yml` (new sets are pre-created with
  the user-supplied label via `MapSetRegistry.ensure_set` so the label is
  not lost to the default) and `other_maps` to `index.json`. Returns
  `{status: 'ok', name: <map_id>}`; errors are 400s with `{error}`.
- Post-create (client): inserts/refreshes the map tile with a cache-busted
  thumbnail, then `Utils.switchMap(...)` to the new map and re-centers the
  POV entity — the legacy behavior of the prompt flow is preserved.
- Tests: `TestCreateMapBlueprint` in
  `n20-webapp/tests/webapp/test_assets_blueprint.py` (multipart round-trips,
  placeholder, new map-set label persistence, name/duplicate rejection).

## Autosave error toaster (DM)

When background autosave (`autosave: true`) fails, the DM sees a dismissible
error toaster with the full error details — no need to dig through server
logs.

- Server: `GameManagement._emit_autosave_error` (`webapp/utils.py`) is called
  from the save worker's failure paths and emits a SocketIO `message` with
  `type: 'autosave_error'` to the SIDs of all logged-in DMs. The payload
  carries `title`, `error_type`, `error`, the last 4000 chars of the
  traceback, `target_file`, `save_dir`, and the `autosave` flag. Emitting
  never breaks the save worker (double-guarded).
- Client: the `EventQueue` `autosave_error` case
  (`webapp/static/engine.js`) renders via `showAutosaveErrorToaster(msg)` —
  a red toast in the toast container with the error summary (type, message,
  target file, save dir), the full traceback in a `<pre>` block, and a close
  button; it auto-expires after 60 s (longer than normal toasts). Players are
  never shown the toaster (defensive `isDmUser()` check on top of the
  server-side DM-only targeting).
- Tests: `n20-webapp/tests/webapp/test_autosave_error_emit.py` (payload shape,
  DM-only targeting, worker non-interruption).

## Combat turn loop and reaction resume

`GameManagement.game_loop()` (`webapp/utils.py`) runs turns via `_run_turns`:
`Battle.skip_dead_turns()` (dead creatures get no turn, no end-of-turn
effects and no legendary window), `start_turn()`, `ai_loop()` for conscious
combatants (unconscious ones only roll their death save), then `_finish_turn`
(`end_turn()` → legendary actions, `next_turn()`). Do not call
`entity.resolve_trigger('end_of_turn')` before `battle.end_turn()`: `end_turn`
already does it, and `next_turn` skips its own `end_of_turn` event when
`end_turn` fired one for the same slot.

State changed outside `commit_and_update` (legendary actions and end-of-turn
effects in `end_turn()`, regeneration and death saves in `start_turn()`) must
bump the `/update` render epoch, or clients get cached tiles with tokens in
their old squares. `push_end_of_turn_animations` and `emit_current_turn_state`
do this. `push_end_of_turn_animations` emits only the `move` event. Don't add
a `refresh_map` after it: that refresh runs outside the client's event queue,
and its sprite cleanup cuts the walk animation short. The client refreshes the
tiles itself once the animation finishes.

An `AsyncReactionHandler` (Shield, opportunity attack, ...) pauses the loop.
`end_turn_state` records where: `True` when it was raised while the turn was
ending (e.g. a legendary attack at the end of someone else's turn), `False`
mid-turn (and for `/action`). After `/reaction` commits the choice,
`schedule_after_reaction` → `resume_after_reaction()` either lets the active
combatant finish its turn (mid-turn; never replays `start_turn`/`reset_turn`)
or goes straight to `next_turn()` (end of turn), checking `battle_ends()`
first so a reaction-window knockout can still end the fight. Tests:
`tests/webapp/test_reaction_resume.py`.

## Battle pacing: DM ends AI turns

Optional pause so the DM can narrate before combat moves on. When enabled, an
AI/LLM/JEV combatant (anything not a `WebController`) acts as usual, but its
turn is *held* instead of ended. The hold does not depend on a DM being
online: a human DM is assumed, and the turn waits until a DM logs in and ends
it.

- Setting: `GameManagement.dm_ends_ai_turns()`. The runtime toggle in
  `session_state['battle_pacing']['dm_ends_ai_turns']` (saved with the game)
  overrides the campaign default in `game.yml`:

  ```yaml
  battle_pacing:
    dm_ends_ai_turns: true
  ```

- Hold: `_run_turns` and the mid-turn branch of `resume_after_reaction` call
  `_hold_for_dm(battle, entity)` after `ai_loop()`. It sets
  `GameManagement.dm_turn_hold` (entity UID, not persisted) and returns before
  `_finish_turn`. While held, `game_loop()` and `resume_after_reaction()` are
  no-ops, so nothing replays the turn. Dead/unconscious combatants are not held.
- Release: `release_dm_turn_hold()` runs `_finish_turn` and `_run_turns` in a
  background task (waits for the game-loop task slot). Triggers: `/end_turn` or
  `/next_turn` from a DM (players get 409), MCP `actions.end_turn` and
  `dm.battle_admin` `next_turn`, and turning the toggle off. A DM
  disconnecting does not release it. Battle end and save load clear the hold.
- Routes: DM-only `GET/POST /battle_pacing` (`{dm_ends_ai_turns: bool}`) returns
  `{dm_ends_ai_turns, dm_connected, held_uid}`. MCP: `dm.battle_admin`
  `op=pacing` (optional `enabled`).
- SocketIO `message` types: `dm_turn_hold` (`{id, label}`),
  `dm_turn_hold_end` (`{id}`), `battle_pacing` (state); the client refreshes the
  turn order panel.
- UI: `battle.html` renders a DM-only pacing bar (checkbox
  `.dm-pacing-toggle`, and during a hold a banner with `.end-held-turn`);
  players see "Waiting for the DM to end this turn…". The existing **Next Turn** button also
  ends a held turn.
- Tests: `tests/webapp/test_dm_turn_hold.py`.

## Legendary action phase (manual legendary creatures)

When a legendary creature uses the manual (`WebController`) controller, the
end of every other creature's turn opens a *legendary action phase* instead
of advancing initiative (AI/LLM controllers still auto-pick in the engine).

- Engine: `Battle.eval_legendary_action` resets the queue; the controller's
  `legendary_action_listener` calls `Battle.queue_legendary_phase(entity)`.
  `Battle.begin_legendary_phase()` / `end_legendary_phase()` /
  `legendary_phase_entity()` / `in_legendary_phase(entity)` manage
  `battle.legendary_phase` (a UID, serialized with the battle). While the
  phase is open, `NPC.available_actions` returns only legendary attacks plus a
  legendary `MoveAction`, and `Entity.available_movement` returns full speed
  when a `type: move` option is affordable (so `/path` budgets work).
- Server: `GameManagement.begin_legendary_phase(battle)` is called after
  `end_turn()` in `game_loop`, `/end_turn` and `/next_turn`; when it returns
  True the caller stops before `next_turn()`. `commit_and_update` converts the
  creature's action with `prepare_legendary_phase_action` (rejecting anything
  that isn't a legendary option), commits it, flushes animations, then calls
  `advance_legendary_phase` (next queued creature, else `next_turn()` +
  `schedule_continue_game_loop()`). `/end_turn` during a phase ("End
  Legendary Action") also advances; only the creature's controller or the DM
  may end it. Attack builders in `blueprints/battle.py` flag
  `action.legendary_action` so target validation uses the legendary pool.
  The `/path` and cost-map caches include the phase in their keys.
- SocketIO `message` types: `legendary_phase` (`{id, label, remaining}`) and
  `legendary_phase_end` (`{id}`); the client refreshes the turn panel and
  initiative list and closes a stale action bar for that creature.
- UI: `turn.jinja` (gold banner, `LA` pool indicator, **End Legendary Action**
  button reusing `#player-end-turn`), `_action_tabs.html` (phase banner and
  `action-end-legendary` end button), `_action_button.html` (`L<cost>` badge),
  `battle.html` (`legendary-phase` row class). `action_bar.py` hides spells and
  items during the phase.
- Tests: `tests/test_legendary_actions.py::TestManualLegendaryPhase`,
  `n20-webapp/tests/webapp/test_legendary_phase.py`.

## Attacking unseen squares (blind attacks)

`blueprints/battle.py` lets attack target mode aim at a square instead of a creature (5e unseen targets; engine side in `docs/UNSEEN_TARGETS.md`).

- `_blind_attack_target_square(...)` decides when a hover or click is a blind attack: no creature the attacker can see is there, and there is no targetable object. The decision never depends on what is actually in the square.
- `/target` returns `_blind_attack_preview(...)`. It has `blind_attack`, `sensed`, `adv_info: [[], ['unseen_target']]` and `blind_hint`, or the `validation.unseen.*` reason the square can't be attacked (out of range, wall, no path).
- `/action`: a coordinate target becomes `AttackAction.target_square`. The `select_target` step returns `unseen_squares` (squares the attacker hears) and `blind_attacks` (whether the campaign allows blind attacks).
- `engine.js`:
  - `highlightUnseenTargetSquares` outlines the sensed squares while in target mode.
  - The validation cache keeps `blind_attack` / `sensed` / `blind_hint`.
  - `confirmBlindAttackGuess` asks before attacking a square where the player neither sees nor hears anything.
- `map.html` renders `tile.unseen_presence` as `.unseen-presence-marker` (heard: pulsing; last known: faded).
- Tests: `n20-webapp/tests/webapp/test_unseen_target_attack_route.py`, `tests/test_unseen_targets.py`.

## Grapple indicators (who is grappling whom)

The 2D VTT shows grapples three ways: a chain drawn between the grappler and the
grappled creature, a chain badge on each token, and the tile hover hint.

- Engine: `natural20/web/grapple_info.py` builds the summary from
  `entity.grapples` (creatures grappling this one) and `entity.grappling_targets()`
  (creatures it grapples), adding `escape_dc` from
  `attributes['grapple_escape_dcs']` when a fixed escape DC applies.
  `grapple_tile_attributes(entity)` adds `grappled`, `grappled_by`, `grappling`
  (`[{id, name, escape_dc?}]`) and `grapple_tooltip` to token tiles. Both
  `JsonRenderer` and `stack_renderer._apply_overlay_entity_to_tile` call it.
  `map_state.entities_from_tiles` forwards the IDs (`grappled_by`, `grappling`)
  and `grapple_tooltip` to the 3D client.
- Hover hint: `terrain_tooltip._thing_descriptions` lists
  "Grappled by X (escape DC N)" or "Grappling Y" instead of a bare "Grappled".
- Templates: `map.html` and `map_overlay_tiles.html` put `data-token-squares`
  plus JSON `data-grappled-by` / `data-grappling` on `.entity`, add an
  `is-grappled` class, and include `_grapple_token_badge.html` (badge with a
  native `title` tooltip).
- Client: `static/grapple_links.js` (`window.GrappleLinks`) reads those
  attributes and draws an SVG chain layer (`#grapple-links-layer`, z-index
  1115, above tokens and below quick-interact buttons) inside
  `.tiles-container`. Each chain also gets a midpoint badge whose `title` reads
  "X is grappling Y (escape DC N)". The layer uses layout offsets, not bounding
  rects, so it stays correct under map zoom. A `MutationObserver` on
  `.tiles-container` redraws it after both full and optimized `/update`
  refreshes; a position/pair signature skips no-op redraws. A chain is drawn
  only when both tokens are rendered (fog of war hides the other end).
- Tests: `tests/test_grapple_info.py`, `webapp/static/grapple_links.test.js`.

## Reset saves at startup (`--reset`)

Booting the webapp with `--reset` (or `N20_RESET_SAVES=1`) wipes the
persisted save state so the campaign starts fresh from its YAML templates:

```bash
./start_web.sh wild_sheep_chase --reset     # flag before or after campaign
./start_web.sh --edit --reset death_house   # composes with --edit
```

- **Shell**: `n20-webapp/start_web.sh` scans all arguments for `--edit` /
  `--reset` (position-independent); the first non-flag argument is the
  campaign. It exports `N20_RESET_SAVES=1` (and `N20_EDIT_MODE=1` for
  `--edit`). The root `start_web.sh` passes arguments through unchanged.
- **App**: `webapp/app.py` resolves the flag via `_reset_saves_requested()`
  (env `N20_RESET_SAVES` or `--reset` in `sys.argv`), passes
  `reset_saves=` into `GameManagement(...)`, and reports it in the
  `[Boot] ... reset_saves=%s` log line.
- **Engine**: `GameManagement.__init__` (`webapp/utils.py`) accepts
  `reset_saves=False`. When set, it runs `_wipe_save_state()` *after* the
  save dir is finalized but *before* the sqlite DBs are opened and before the
  autosave autoload block, so `campaign_logs.sqlite` / `notebook.sqlite`
  start empty and no stale save is loaded. `_wipe_save_state()` deletes under
  `SAVE_DIR/<game>/`: `save_*.yml[.gz]`, `last_save.txt`,
  `*.log.json` / `*.read_notes.json`, both sqlite files, and the
  `notebook_files/` directory (unrelated files are preserved), then resets
  `save_states` / `current_save_index`. NPC memory files
  (`<campaign>/npc_memories/*.json`) are cleared via the existing
  `_clear_npc_memory_files()` right after the memory store is created. All
  wipe work is exception-guarded — a failure logs and never blocks boot.
  This is distinct from the in-game `POST /admin/campaign/reset`
  (`reset_to_fresh_campaign`), which reloads a fresh `Session` at runtime
  without deleting the sqlite DBs.
- **Tests**: `n20-webapp/tests/webapp/test_reset_saves.py` (wipe scope,
  preservation of unrelated files, empty/missing dir no-ops, NPC memory
  clear, flag resolution from env and argv).

## Sidekick auto-follow toggle (portrait dock)

Players who control an in-party sidekick (assigned owners, or the DM) can
toggle its auto-follow directly from the lower-left portrait dock: hovering a
sidekick portrait reveals a road-icon button in the existing
`.portrait-quick-actions` hover overlay. The button glows green (`.is-on`)
while auto-follow is active.

- **Context**: `pov_utils.sidekick_follow_state()` maps
  `entity_uid → {auto_follow, can_control}` for in-party sidekicks and is
  included as `sidekick_follow` in `build_portrait_render_context()` (both
  the full index render and `GET /refresh-portraits`), so the dock always
  shows server-rendered state.
- **Endpoint**: `POST /party/sidekick_follow` (`blueprints/navigation.py`,
  endpoint `navigation.party_sidekick_follow`) accepts
  `{entity_uid, enabled?}` — when `enabled` is omitted it toggles (inverts)
  the current state. Only the DM or a listed owner may call it (403
  otherwise; 404 for unknown entities; 400 for non-sidekicks). It delegates
  to `sidekick_control.set_auto_follow_and_control`, which updates the record,
  realigns `mode='follow'` tasks, and emits `party_membership` +
  `refresh_map` — every client then re-renders the dock via
  `Utils.refreshPortraits()` (same loop as party join/leave).
- **Client**: the click handler in `webapp/static/engine.js` posts via
  `ajaxPost(..., isJSON=true)`, applies the returned state to the button
  locally (`applySidekickFollowState`), and triggers the portrait refresh.
  Styles: `.portrait-quick-action-sidekick-follow` in `webapp/static/styles.css`.
- **Tests**: `n20-webapp/tests/webapp/test_sidekick_follow.py` (endpoint
  auth/permission/toggle paths) and the `sidekick_follow_state` /
  `build_portrait_render_context` cases in
  `n20-webapp/tests/webapp/test_pov_utils.py`.

## Related docs

- `AGENTS.md` — agent orientation, MCP catalogue, battle/spell conventions
- `docs/CONVERSATION_RAG.md` — NPC `/talk` RAG pipeline
- `plans/app_refactor_plan.md` — original refactor plan (completed)
- `plans/pr_status.md` — PR-by-PR extraction log
