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
| `ai` | `blueprints/ai.py` | `/ai/*` | `ai.*` |
| `navigation` | `blueprints/navigation.py` | `/`, `/command`, `/path`, `/switch_map`, `/update` | `navigation.*` |
| `character` | `blueprints/character.py` | `/character_builder/*`, `/character_editor/*`, journal CRUD | `character.*` |
| `battle` | `blueprints/battle.py` | `/start`, `/action`, `/target`, `/actions`, `/actions/batch`, turn order, combat log | `battle.*` |
| `dm` | `blueprints/dm.py` | `/admin/*`, `/spawn_*`, inventory, `/rest`, audio, entity admin, `/update_resource_pool` | `dm.*` |
| `edit` | `blueprints/edit.py` | `/edit/overlay`, `/edit/move`, `/edit/map_graph` (campaign YAML authoring; requires `N20_EDIT_MODE=1`) | `edit.*` |
| `merchant` | `blueprints/merchant.py` | `/merchant`, `/merchant/preview`, `/merchant/trade` | `merchant.*` |
| *(none)* | `blueprints/socketio_handlers.py` | `connect`, `register`, `message`, `disconnect`, `request_effects` | N/A (SocketIO) |
| `mcp` | `mcp/` package | `/mcp/manifest`, `/mcp/tools/list`, `/mcp/tools/call` | `mcp.*` |

Conversation routes (`/talk`, etc.) are registered by `conversation_service.register_conversation_routes` via `helpers/conversation_wiring.py`, not a blueprint.

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
| `effects.py` | Effect caches, `register_effect_listeners()` (battle-end narration, control override) |
| `special_effects.py` | Client effect payload filtering |
| `journal_utils.py` | `_record_narration_for_pcs` (shared by effects and battle) |
| `character_builder_utils.py` | Character builder/import helpers |
| `character_builder_restrictions.py` | Campaign min/max level and class/spell/feat/ability blacklists |
| `pvp.py` | PvP team config and battle autofill |
| `llm_init.py` | LLM handler init, game-context function registration |
| `campaign_config.py` | Campaign path / index loading |
| `cors_config.py` | CORS origins, SocketIO async mode |
| `perf.py` | Request timing instrumentation |
| `conversation_wiring.py` | `ConversationService` setup and `/talk` route registration |

Blueprints read shared state through `runtime_state` accessors, **not** by importing from `webapp.app`.

### Campaign character builder limits

Set in `user_levels/<campaign>/game.yml` (or `index.json`) under `character_builder`:

```yaml
character_builder:
  min_level: 1
  max_level: 3
  blacklist:
    classes: [warlock, paladin]
    spells: [fireball, wish]
    feats: [sharpshooter]
    abilities: [action_surge]   # class features / subclasses by slug
```

`game.yml` overrides `index.json` when both define the same keys. The builder UI and `/create_character` / `/update_character` enforce these limits server-side.

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
4. LLM / conversation / PvP helpers
5. `register_perf_instrumentation()`
6. Register blueprints
7. `register_socketio_handlers(socketio)`

`wire_conversation_service` uses **live getters** (`lambda: current_game`) so tests can monkeypatch `app.current_game` after import.

## Campaign edit mode

Start with `./webapp/start_web.sh --edit <campaign_dir>` or `N20_EDIT_MODE=1`. This auto-logs in as the campaign DM, highlights doors/teleporters/walls/spawn points, and persists drag-and-drop moves directly to `maps/*.yml` via `natural20/map_editor.py` and `/edit/move`. The DM menu includes **Map Connections** (`GET /edit/map_graph`, opens in a new tab): a teleporter graph across all registered maps with click-to-switch for editing.

## Related docs

- `AGENTS.md` — agent orientation, MCP catalogue, battle/spell conventions
- `docs/CONVERSATION_RAG.md` — NPC `/talk` RAG pipeline
- `plans/app_refactor_plan.md` — original refactor plan (completed)
- `plans/pr_status.md` — PR-by-PR extraction log
