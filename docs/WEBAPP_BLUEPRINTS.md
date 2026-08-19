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
| `navigation` | `blueprints/navigation.py` | `/`, `/command`, `/path`, `/switch_map`, `/update`, `/map_state`, `/party/invite` | `navigation.*` |
| `character` | `blueprints/character.py` | `/character_builder/*`, `/character_editor/*`, journal CRUD, `/inventory/container/*`, `/inventory/use` | `character.*` |
| `notebook` | `blueprints/notebook.py` | `/notebook`, `/notebook/items`, `/notebook/folders`, `/notebook/shared/<id>` — player/campaign notes (SQLite) | `notebook.*` |
| `battle` | `blueprints/battle.py` | `/start`, `/action`, `/target`, `/actions`, `/actions/batch`, turn order, combat log | `battle.*` |
| `dm` | `blueprints/dm.py` | `/admin/*`, `/spawn_*`, inventory, `/equipment`, `/item_card`, `/rest`, audio, entity admin, `/update_resource_pool`, `/update_inspiration`, `/admin/map_sets`, `/admin/map_set/*`, `/admin/sidekick`, `/dm/notes`, `/admin/illumination` | `dm.*` |
| `edit` | `blueprints/edit.py` | `/edit/session`, `/edit/overlay`, `/edit/move`, `/edit/map_graph`, `/edit/map_graph/layout` (campaign YAML authoring; per-DM-session edit mode) | `edit.*` |
| `merchant` | `blueprints/merchant.py` | `/merchant`, `/merchant/preview`, `/merchant/trade` | `merchant.*` |
| `client_3d` | `blueprints/client_3d.py` | `/3d` — Three.js VTT sibling (see [VTT_3D.md](VTT_3D.md)) | `client_3d.*` |
| *(none)* | `blueprints/socketio_handlers.py` | `connect`, `register`, `message`, `disconnect`, `request_effects` | N/A (SocketIO) |
| `mcp` | `mcp/` package | `POST /mcp` (Streamable HTTP JSON-RPC), `/mcp/manifest`, `/mcp/tools/list`, `/mcp/tools/call` | `mcp.*` |

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
| `effects.py` | Effect caches, `register_effect_listeners()` (battle-end narration, control override), `register_battle_end_hook_handlers()` (campaign hooks + combat recap) |
| `special_effects.py` | Client effect payload filtering |
| `journal_utils.py` | `_record_narration_for_pcs` (shared by effects and battle) |
| `character_builder_utils.py` | Character builder/import helpers |
| `character_builder_restrictions.py` | Campaign min/max level and class/spell/feat/ability blacklists |
| `character_selection.py` | Login PC vs sidekick partition and `character_selection.sidekick_slots` |
| `pvp.py` | PvP team config and battle autofill |
| `map_sets.py` | Activate / create / assign / place-party / party-travel for campaign map sets (`docs/MAP_SETS.md`) |
| `party_travel.py` | Confirmation prompt when a PC steps on a `party_travel` teleporter; Interact / tile hover retries after cancel |
| `sidekick_control.py` | Join/leave party sidekicks and WebController owner registration |
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
4. LLM / conversation / PvP helpers, then `register_battle_end_hook_handlers(...)` (campaign `battle_end_hooks` plus post-combat journal/memory recaps)
5. `register_perf_instrumentation()`
6. Register blueprints
7. `register_socketio_handlers(socketio)`

`wire_conversation_service` uses **live getters** (`lambda: current_game`) so tests can monkeypatch `app.current_game` after import.

## Campaign edit mode

Logged-in DMs can enter and leave campaign edit mode at any time from the VTT hamburger menu (**Enter Edit Mode** / **Exit Edit Mode**), including mid-game. Edit chrome (fixture overlays, landmarks panel, YAML spawners, Map Connections) is limited to **that DM's Flask session**; other players keep a normal play session.

Bottom-of-map chrome is stacked in two docks so panels do not cover each other: `#map-chrome-left` (zoom controls, then landmarks above them in edit mode) and `#map-chrome-right` (minimized local chat above DM notes). The DM POV portrait dock is content-sized and centered between those columns.

The hamburger (`#floating-menu`) uses the same dark chrome. DM entries are grouped as Combat, Table, Spawn, Authoring (edit mode, map pins, AI assistant), then Session (notes, journal, combat log, world time, log out). Icons are Glyphicons already used elsewhere in the VTT.

`POST /edit/session` with `{ "enabled": true|false }` toggles `session['edit_mode']`. YAML mutations (`/edit/move`, place/remove, etc.) still write `maps/*.yml` via `natural20/map_editor.py` and reload the live map, so the world changes are shared — only the authoring UI is session-scoped.

`GET /edit/overlay` is rebuilt from map YAML on each request. It must not call `Session.load_object()` for NPC/PC legend types: those names are missing from `items/objects.yml`, and a catalog miss used to reload the whole YAML file once per entity (about 1.5s on tavern). The client also coalesces overlay reloads so a tile refresh does not fire the endpoint twice.

`--edit` / `N20_EDIT_MODE=1` is optional: it no longer auto-logs anyone in or grants DM to every user. After a real DM login, that session starts already in edit mode. The DM menu includes **Map Connections** (`GET /edit/map_graph`, opens in a new tab) while edit mode is on. Dragging map tiles persists their positions to campaign `map_graph.yml` via `POST /edit/map_graph/layout`; reload restores that layout.

## Related docs

- `AGENTS.md` — agent orientation, MCP catalogue, battle/spell conventions
- `docs/CONVERSATION_RAG.md` — NPC `/talk` RAG pipeline
- `plans/app_refactor_plan.md` — original refactor plan (completed)
- `plans/pr_status.md` — PR-by-PR extraction log
