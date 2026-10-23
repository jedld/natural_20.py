## Quick orientation for AI coding agents

This repository is a D&D simulation and VTT used for AI research. Focus on two layers:

- Core engine (Python package `natural20/`) — game models, map, battle loop, controllers, and entity registry. Key files: `natural20/session.py`, `natural20/battle.py`, `natural20/entity.py`, `natural20/controller.py`, `natural20/generic_controller.py`, `natural20/llm_controller.py`.
- Web layer (Flask + small JS VTT) — `n20-webapp/webapp/` (submodule) contains the Flask app, LLM provider adapters, and the DM/chat handlers. Key files: `n20-webapp/webapp/app.py`, `n20-webapp/webapp/blueprints/*`, `n20-webapp/webapp/llm_handler.py`, `n20-webapp/tests/webapp/*`.

**Repository layout:** The VTT and campaigns are **git submodules**:

- `n20-webapp/` → `git@github.com:jedld/n20-webapp.git` (Flask app under `n20-webapp/webapp/`)
- `user_levels/` → `git@github.com:jedld/n20-campaigns.git`

Clone with `git clone --recurse-submodules`. Run `./start_web.sh [campaign]`. See **`docs/REPOSITORY_SPLIT.md`**.

### Webapp layout (post-refactor)

See **`docs/WEBAPP_BLUEPRINTS.md`** for the full architecture guide (blueprint map, helper modules, parity harness, wiring checklist).

`webapp/app.py` is the composition root (~320 lines): Flask/SocketIO setup, campaign load, `GameManagement` init, helper registration, blueprint registration, MCP wiring, and perf hooks. **Do not add domain HTTP routes here** — use blueprints.

| Blueprint | Module | Routes (examples) |
|---|---|---|
| `assets` | `blueprints/assets.py` | `/assets/*`, `/create_map`, `/upload_map_background`, `/delete_map` |
| `auth` | `blueprints/auth.py` | `/login`, `/logout`, `/character_selection`, `/select_character` |
| `ai` | `blueprints/ai.py` | `/ai/*` |
| `navigation` | `blueprints/navigation.py` | `/`, `/command`, `/path`, `/switch_map`, `/update`, `/map_state`, `/party/invite`, `/party/sidekick_follow` (portrait-dock auto-follow toggle) |
| `character` | `blueprints/character.py` | `/character_builder/*`, journal CRUD |
| `notebook` | `blueprints/notebook.py` | `/notebook/*` — player/campaign notes (SQLite; see `docs/NOTEBOOK.md`) |
| `battle` | `blueprints/battle.py` | `/start`, `/action`, `/target`, `/actions`, combat log, turn order, `/battle_pacing` (DM ends AI turns) |
| `dm` | `blueprints/dm.py` | `/admin/*`, `/spawn_*`, `/available_objects`, inventory, `/attunement`, `/rest`, audio, `/move_entity`, `/delete_entity`, `/undo_delete_entity` (VTT Delete / Ctrl+Z) |
| `edit` | `blueprints/edit.py` | `/edit/*` — campaign map edit mode (per-DM-session toggle), drag-and-drop authoring, terrain/layer placement |
| `merchant` | `blueprints/merchant.py` | `/merchant` — NPC merchant trading with discount and session management |
| `client_3d` | `blueprints/client_3d.py` | `/3d` — Three.js tabletop VTT sibling (see `docs/VTT_3D.md`) |
| SocketIO | `blueprints/socketio_handlers.py` | `connect`, `register`, `message`, `disconnect`, `request_effects` |
| *(conversation)* | `helpers/conversation_wiring.py` + `conversation_service.py` | `/talk` (registered at bootstrap, not a blueprint) |

Shared helpers under `webapp/blueprints/helpers/`:

- `runtime_state.py` — lazy getters/setters for app globals (`get_current_game()`, `get_socketio()`, …)
- `auth_utils.py`, `template_globals.py`, `action_utils.py`, `effects.py`, `special_effects.py`, `journal_utils.py`
- `character_builder_utils.py`, `pvp.py`, `llm_init.py`
- `campaign_config.py`, `cors_config.py`, `perf.py`, `conversation_wiring.py`

Conventions:

- Blueprints must not import each other; use `runtime_state` accessors instead of importing from `webapp.app`.
- Flask endpoint names are prefixed by blueprint (e.g. `battle.start_battle`, `dm.admin_save`). Update `url_for(...)` when moving routes.
- Action classes live under `natural20/actions/` (e.g. `natural20.actions.attack_action`), not `natural20.action`.
- `register_effect_listeners(...)` must be called from bootstrap (battle-end narration, control-override SocketIO events).
- After route moves: `python scripts/generate_baseline_artifacts.py`, then run `tests/webapp/test_*_parity.py`.

Core patterns and conventions (do not invent alternatives):

- Session-centered data: a `Session(root_path)` loads `game.yml` and YAML resources (maps, npcs, characters). Use `Session.register_entity` and `Session.entity_by_uid` for UID-based lookup; the centralized `EntityRegistry` is the canonical lookup.
- Campaign resource imports are supported from `game.yml` via `imports` (also `import_campaigns` or `campaign_imports`). Resolution order is: current campaign -> imported campaigns (earlier entries win) -> bundled `templates/`. This applies to items, characters, classes, races, NPCs, and backgrounds.
- YAML inherit references also support cross-campaign forms `@campaign/<name>/...`, `@campaigns/<name>/...`, and `campaigns/<name>/...` (resolved relative to the current campaign parent directory).
- Controllers implement `select_action(battle, entity, available_actions)` and `move_for(entity, battle)`. `GenericController` provides heuristics; `LlmMcpController` (in `natural20/llm_controller.py`) delegates to an LLM and falls back safely to heuristics.
- Actions resolve via subclasses in `natural20/actions/`: each action builds intent with `build_map()`, gets auto-targeted by `natural20.utils.action_builder.autobuild`, and resolves through `Action.resolve` to enqueue battle events.
- **Knocking a creature out (PHB/SRD):** melee attacks (not ranged or thrown) can drop a creature to 0 HP unconscious and stable instead of killing them. Killing is the default. The VTT action bar has a **Kill / Knock** toggle next to melee attacks; when Knock is on, `/action` opts include `knock_unconscious: true`. `AttackAction.can_knock_unconscious()` gates the flag; `Entity.take_damage` honors it (including massive damage on that blow). MCP `actions.execute` accepts the same opt.
- Spells pair YAML definitions (`templates/items/spells.yml`) with Python classes in `natural20/spell/`; `SpellAction` loads the class through `natural20/utils/spell_loader.py`, applies resource costs via `Spell.consume`, and emits damage/miss events for the battle log.
  - AoE targeting primitives:
    - Cones: use `select_cone` in a spell's `build_map()` and preview squares via `Map.squares_in_cone(...)` (server returns `target_squares` from `/target`).
    - Directional cubes (e.g., Thunderwave): use `select_cube` in `build_map()`. The web UI will send `mode: 'cube'` with a clicked direction; the server previews with `Map.squares_in_adjacent_cube((caster_x, caster_y), (x, y), size_squares=3)` and returns `target_squares`. YAML typically provides `range_cube` (15 for Thunderwave).
- LLM integration: webapp uses provider adapters (`webapp/llm_handler.py`) with explicit function-call tokens like `[FUNCTION_CALL: get_map_info()]`. `LlmMcpController._build_prompt(...)` still expects a single integer index or an MCP tool call response.
- Make sure new objects/spells/items/entities can be properly serialized for save/load game support. Plain `natural20.*` effect objects without a dedicated tag (e.g. effect markers stored in `entity.effects`) fall back to `!effect_object` in `natural20/utils/serialization.py`. That saves the class plus its attributes; entity attributes are stored as UIDs and relinked on load by `relink_spell_entities`, and session/battle/map handles are dropped. Give an effect its own representer if it needs more than that. Persistent spell zones (`PersistentAoEZone`) use `!persistent_zone` and their map tiles subclass `natural20/spell/objects/zone_tile.py` (`!zone_tile`); `relink_persistent_zones` re-registers them with the battle or environment on load.
- Ensure UI/Engine features are designed for maximum reusability with regards to similar spells/abilities as well as being able to reuse UI with minimal changes.
- Spells/Classes/Items/Abilities that are part of the SRD should also be defined in the templates folder.

## Notes on Campaign Specific features and Copyrighted Material

* For copyright/trademark and management reasons, *DO* not wire or reference campaign specific objects, items and events in the core webapp and natural20 engine. These should live in the campaign specific folders (user_levels), if a new ability, event, or trigger is needed, add a new yaml attribute in the item/entity or new yaml file type and add generic support in the webapp or engine - The goal is for future campaigns with similar mechanics to be able to take advantage of it. Campaign specifc names like "Strahd Von Sarovich" should not show up in the main core engine or webapp - while generic terms like vampire is permissable.

* Features found in the SRD, DM guide, or Player's handbook can and should be incorporated in the webapp or engine. Campaign specific features include named characters, story beats, overly specific abilities, items that are very specific to the campaign (and not found in the SRD) and have little use outside of it. However specific ability features like granting invisiblity can have the invisibility mechanic implemented as part of the core engine feature when there is an obvious gap. Public Domain, spells, NPCs, items, races, abilities etc and generated assets should be placed under the templates folder.

* NPCs, Spells/Races/Features/Abilities/Images/Narration that are explicitly part of a paid and copyrighted expansion material like "Monsters of the Multiverse", "Fixban's Treasury of Dragons" and have not been promoted to public domain via the SRD but are not specifically part of one campaign should be defined in instead in the expansion_packs folder, campaigns that use them should then import these. However when implementing spells and there is clearly a gap in the engine to support these, non-specific enhancements should be performed on the webapp and engine.

* Use web search or other agentic research tools to verify which category content should be classified as.

Developer workflows and commands (verified in repo README):

- Python deps: `pip install -r requirements.txt`.
- Run webapp (dev):
  - copy `n20-webapp/webapp/env.example` → `n20-webapp/webapp/.env` and set provider vars
  - `git submodule update --init --recursive && pip install -e . && pip install -e ./n20-webapp`
  - `./start_web.sh wild_sheep_chase` (or `./n20-webapp/start_web.sh` with `N20_CAMPAIGNS_DIR`)
  - Optional startup flags (position-independent, before/after the campaign): `--reset` wipes persisted save state at boot (saves, campaign logs, notebook + attachments, NPC memories) so the campaign starts fresh; `--edit` pre-enables campaign edit mode for a DM session after login; `--new` scaffolds a missing campaign directory first (`natural20/campaign_scaffold.py`: `index.json`, `game.yml`, an empty `maps/start.yml`, and DM login `dm`/`admin`). See `docs/WEBAPP_BLUEPRINTS.md` → "Reset saves at startup" / "New campaign at startup".
- Run webapp (production with gunicorn):
  - `N20_USE_GUNICORN=1 ./start_web.sh user_levels/<level>` with `CORS_ORIGINS` as needed
- Run webapp + ngrok in tmux (production remote access):
 1. `tmux new-session -d -s n20`
 2. `tmux send-keys -t n20 './webapp/start_ngrok.sh ../user_levels/<level>' Enter`
  3. `tmux split-window -t n20 -v`
  4. `tmux send-keys -t n20.1 'ngrok http 5001' Enter`
  5. Check ngrok URL: `tmux capture-pane -t n20.1 -p` (look for `Forwarding https://...`)
  6. Attach to view: `tmux attach -t n20`
- Tests:
  - Python: `pytest` (supports `-n auto` for parallel runs)
  - JS unit tests for `webapp/static/engine.js`: `npm install` then `npx jest` (Node 18+ recommended). See README section "JavaScript tests".
  - GitHub Actions CI (deploy keys for private submodules, engine job sizing/timeouts, webapp env determinism): see `docs/GITHUB_CI.md`.
- Web asset optimization: `npm run build:assets` (minify JS/CSS → `*.min.js` / `*.min.css` + `manifest.assets.json`); `npm run optimize:images` (tiered raster passes: general 1024px, UI icons 256px, large assets 512px, campaign `user_levels/` 2048px); `npm run optimize:assets` (both). Templates use `asset_url('engine.js')`; production serves minified bundles when `FLASK_ENV=production` or `N20_USE_MINIFIED_ASSETS=1`.

### Campaign image-gen prompts (do not put campaign flavor in `natural20/`)

- **Generic builders** live in `natural20/image_gen/prompts.py` (CLIP helpers, SRD item/spell/action icon hints, default fantasy scenes).
- **Campaign-specific** token/portrait styles, login splash scenes, and named portrait backdrops belong in **`user_levels/<campaign>/asset_prompts.yml`**, loaded via `natural20.image_gen.campaign_prompt_profile`.
- **`game.yml` → `asset_theme`**: short mood string only (e.g. one line of atmosphere); not story text, not style paragraphs.
- **Never** add campaign names, locations, or adventure-specific scene strings to `natural20/image_gen/prompts.py`. Copy `asset_prompts.yml` from `death_house` or `wild_sheep_chase` when starting a new campaign.
- Generator: `python scripts/generate_campaign_assets.py --campaign user_levels/<name>`. See **`docs/CAMPAIGN_ASSET_GENERATOR.md`**.

**AI configuration file (`.ai.yaml`)**: the DM Console → **AI Settings** panel (`webapp/ai_config.py`, `/ai/config*`, MCP `dm.ai_config`) configures provider profiles (dm/npc/battle + custom), combat controllers (deterministic `ai` / `llm` / `manual`), NPC conversation + task AI, sidekick defaults and per-NPC overrides (keyed by `entity_uid` or NPC type). Precedence: `<campaign>/.ai.yaml` → legacy `game.yml`/`index.json` → `webapp/.ai.yaml` (`N20_AI_CONFIG_PATH`) → the env vars below. Both files are git-ignored (may hold keys; prefer `api_key_env`). See **`docs/AI_CONFIG.md`**.

Important environment variables (used by code; fallbacks when `.ai.yaml` does not set a value):

- LLM_PROVIDER (ollama|openai|anthropic|mock) — default `ollama` in the controller.
- OLLAMA_BASE_URL, OLLAMA_MODEL — defaults used by `webapp/llm_handler.py` and `natural20/llm_controller.py`.
- OPENAI_API_KEY / ANTHROPIC_API_KEY — used by providers.
- **NPC LLM** (optional): dedicated provider for NPC conversations — allows a fast/cheap model for
  NPC chat while keeping the DM AI on a larger model. Variables:
  - `NPC_LLM_ENABLED` – ``1`` (default) or ``0``/``no``/``false`` to disable.
  - `NPC_LLM_PROVIDER` – ``ollama`` (default), ``openai``, ``anthropic``, ``llama_cpp``, ``mock``.
  - `NPC_BASE_URL` / `NPC_OLLAMA_BASE_URL` / ``NPC_<PROVIDER>_BASE_URL`` – endpoint URL (falls back
    to the DM provider's ``<PROVIDER>_BASE_URL`` when unset).
  - `NPC_MODEL` / `NPC_OLLAMA_MODEL` / ``NPC_<PROVIDER>_MODEL`` – model name (falls back to DM model).
  - `NPC_API_KEY` / ``NPC_<PROVIDER>_API_KEY`` – API key (falls back to DM key).
  - **NPC context budget** (`webapp/llm_context_budget.py`): monitors prompt size and compacts NPC history before `/talk` LLM calls. Resolution order: ``NPC_LLM_CONTEXT_SIZE`` / ``N20_NPC_CONTEXT_SIZE`` (admin override) → provider ``context_window`` → auto-detect from llama.cpp ``/props`` or Ollama ``/api/show`` (when ``N20_LLM_CONTEXT_AUTO_DETECT=1``) → provider default (32K llama.cpp, 8K Ollama). Tunables: ``N20_LLM_CONTEXT_SAFETY_MARGIN`` (reserved tokens, default 512), ``N20_LLM_CONTEXT_COMPACT_PCT`` (compact threshold, default 85), ``N20_NPC_CONTEXT_KEEP_RECENT_TURNS`` (default 6). DM override at runtime: ``POST /ai/set-context-window`` with ``{"context_window": 32768, "target": "npc"}``. Provider info: ``GET /ai/provider-info`` includes ``npc_provider.resolved_context_limit``.
  - When `NPC_LLM_ENABLED=0`, NPC conversations automatically fall back to the DM provider.
  - `N20_NPC_BACKGROUND_LLM` – ``1`` (default) or ``0``/``no``/``false`` to skip NPC LLM calls during out-of-combat environment ticks (`webapp/npc_environment_ticks.py`) and long-rest NPC simulation (`webapp/long_rest_npc_simulation.py`). Player-initiated `/talk` is unaffected. Per-feature override in `game.yml`: `npc_environment_ticks.llm_enabled` / `long_rest_npc_simulation.llm_enabled`, or global `npc_background_llm.enabled`.
- **Battle LLM** (optional): dedicated provider for battle *decisions* — runs combat `LlmMcpController`s on a decision model (e.g. JEV / TypeSafe System One) while DM narration and NPC dialogue stay on generative providers. See **`docs/JEV_NPC_BATTLE_AI.md`** ("Using JEV as the default battle AI in the VTT").
  - `BATTLE_LLM_PROVIDER` – ``jev`` (only supported value). When set, `configure_battle_provider_from_environment` (`webapp/blueprints/helpers/llm_init.py`) initializes `llm_handler.battle_provider` as a `JevProvider` at startup. Unset → `battle_provider` is `None` and battle "llm" controllers use the DM provider (no behavior change).
  - `BATTLE_TYPESAFE_API_KEY` / `BATTLE_TYPESAFE_BASE_URL` / `BATTLE_TYPESAFE_MODEL` – JEV endpoint overrides, falling back to the shared `TYPESAFE_*` vars.
  - All battle "llm" controller build sites (`/battle`, `/update_controller`, `GameManagement.build_combat_controller_for_entity`, MCP `dm.set_controller`) resolve the provider via `ai_config.combat_llm_provider_for(handler, entity)`: per-NPC `.ai.yaml` profile → `combat.llm_provider` → `llm_handler.battle_llm_provider()` (battle provider if set, else DM provider). Never `from webapp.app import llm_handler` (under `python -m webapp.app` that loads a second app); use `runtime_state.get_llm_handler()`.
  - Which entities use an "llm" controller: per-entity `controller-select`, per-NPC `.ai.yaml` `npcs.<uid|type>.combat.controller`, the campaign default (`.ai.yaml` `combat.npc_controller`, legacy `index.json` `npc_default_controller`), or `NPC_LLM_COMBAT_ENABLED=1` / `combat.force_llm` (forces all NPCs). `GET /ai/provider-info` includes a `battle_provider` block for verification.
- N20_MCP_URL — optional MCP bridge URL used by `LlmMcpController._call_mcp_tool(prompt, n_actions)` (POST {prompt, n_actions} → {index}). Also used by `python -m webapp.mcp.stdio` as the Streamable HTTP target (default `http://127.0.0.1:5001/mcp`).
- N20_MCP_DM_TOKEN — optional shared secret for DM-privileged MCP access. Callers may send `Authorization: Bearer <value>` or `X-MCP-Token: <value>` instead of a DM session cookie. External hosts (Cursor, Claude Code) use Streamable HTTP JSON-RPC at `POST /mcp` (spec 2026-07-28, with 2025-era `initialize` fallback). The in-app LLM still uses legacy REST (`GET /mcp/manifest`, `GET /mcp/tools/list`, `POST /mcp/tools/call`). Tools live in `webapp/mcp/tools_*.py`. See **`docs/MCP.md`**.

MCP tool catalogue (keep this list in sync with `webapp/mcp/tools_*.py`). Design rule: prefer one `op`-discriminated tool over many specialised tools to keep the surface small for token-constrained LLMs.
  - `tools_world`: `world.list_maps`, `world.get_map`, `world.list_entities`, `world.get_entity`, `world.get_battle`, `world.list_npc_types`.
  - `tools_dm` (DM mutations — mirror every DM-only Flask endpoint):
    - HP: `dm.set_hp`, `dm.heal`, `dm.damage`.
    - Status & properties: `dm.add_status`, `dm.remove_status`, `dm.set_property`.
    - Inventory: `dm.add_item`, `dm.remove_item`, `dm.equipment` (op=equip|unequip|attune|end_attunement|cancel_attunement, optional `force` to apply attunement changes immediately) — mirrors `/equip` and `/attunement`.
    - Resources: `dm.set_resource` (resource_type=action|bonus_action|reaction|spell_slot|temp_hp|resource_pool|inspiration; op=set|add|subtract; spell_slot also takes character_class+level; resource_pool also takes resource_name such as superiority_dice; inspiration is a 0/1 Inspiration / Heroic Inspiration token) — replaces `/update_action_resources`, `/update_spell_slots`, generic `/update_resource_pool`, the temp_hp branch of `/update_hp`, and `/update_inspiration`.
    - Rewards/progression: `dm.award_xp` — mirrors `/award_xp` for manual/quest XP awards to one, many, or all PCs; `dm.grant_level_up` — mirrors `/grant_level_up` and `/grant_event_level_up` for DM-gated, event-gated, or milestone campaign progression (`game.yml` `progression.mode`).
    - Spawning / placement: `dm.spawn_npc` (unique NPCs already on the same map set are moved, not duplicated), `dm.spawn_object`, `dm.remove_entity` (mirrors `/delete_entity`; removals are recorded on the per-user undo stack), `dm.undo_remove_entity` (mirrors `/undo_delete_entity` — restores position, battle membership/initiative, and POV; the MCP backend shares the VTT Delete-key undo stack under user `dm`), `dm.teleport`.
    - Battle admin: `dm.battle_admin` (op=add_combatant|remove_combatant|reorder|set_group|next_turn|pacing) — mirrors `/add`, `/remove_from_battle`, `/reorder_initiative`, `/update_group`, the DM-side `/next_turn`, and `/battle_pacing`. `add_combatant` rolls initiative and slots the entity right after the current turn. `pacing` (optional `enabled`) reads/sets "DM ends AI turns": AI combatants' turns are held after they act until a DM ends them (even if no DM is logged in yet) (`next_turn` / `actions.end_turn` release a held turn). Campaign default: `game.yml` `battle_pacing.dm_ends_ai_turns`. See `docs/WEBAPP_BLUEPRINTS.md` → "Battle pacing".
    - Controller assignment: `dm.set_controller` (kind=manual|ai|llm) — mirrors `/update_controller` set; lazy-imports `WebController` / `GenericController` / `LlmMcpController` and registers handlers.
    - Rest: `dm.rest` (type=short|long, optional `force`, `arcane_picks`, `hit_die_picks`) — mirrors `/rest` including the inline pick controller.
    - Persistence: `dm.save_load` (op=save|load|list) — mirrors `/admin/save`, `/admin/load`, `/admin/saves`; on load, refreshes the current battle map and re-emits `refresh_map`.
    - Effects: `dm.effect` (effect, action=start|stop|update, optional `config`, `scope`=global|map, optional `map_name`) — mirrors `/admin/effect`, persists into the module-level `active_effects` / `active_effects_map` caches.
    - Illumination: `dm.illumination` (op=get|set|reset, `illumination` 0–1, optional `map_name`) — 3D global ambient override; YAML `map.illumination` is the default. Visual only (does not change fog or `Map.light_at`). Mirrors `POST /admin/illumination`.
    - Audio: `dm.sound` (op=list|play|volume|seek) — mirrors `/tracks`, `/sound`, `/volume`, `/seek`.
    - Time: `dm.advance_time` (op=add|set, `seconds`) — wraps `Session.increment_game_time` for narrative time skips.
    - Map landmarks: `dm.map_landmark` (op=list|upsert|delete, optional `map_name`, `annotation`, `annotation_id`) — YAML `map_annotations` for NPC navigation/LLM place context. See `docs/MAP_ANNOTATIONS.md`.
    - DM notes: `dm.note` (op=list|upsert|delete|move, optional `map_name`, `note_id`, `x`, `y`, `text`, `title`) — play-time pins stored in `session.session_state['dm_notes']`. Invisible to PCs and NPCs. See `docs/DM_NOTES.md`.
    - Campaign/player notebook: `dm.notebook` (op=list|get|search|create|update|delete|mkdir|move|share; optional `scope` campaign|player, `owner`, `item_id`, `folder_id`, `title`, `content`, `query`, `usernames`) — login- and campaign-level notes/files in SQLite (`notebook.sqlite`), not tied to a PC or NPC. See `docs/NOTEBOOK.md`.
    - User accounts: `dm.user_admin` (op=list|create|update|delete|assign_character|unassign_character; `username`, `password`, `roles`, `character_uid`, optional `spawn`) — mirrors `GET/POST /admin/users`; persists `logins` and `default_controllers` to campaign `index.json`.
    - Map sets: `dm.map_set` (op=list|activate|create|assign_map|place_party) — party POV worlds; `create`/`assign_map` persist `game.yml`. See `docs/MAP_SETS.md`.
    - Sidekicks: `dm.sidekick` (op=join|leave|assign_owner|auto_follow|list) — party NPC membership and player owners; `auto_follow` (with `enabled`) toggles out-of-combat auto-follow (sidekicks trail the focused character, chained in a line) synced by `webapp/sidekick_follow.py`; mirrors `POST /admin/sidekick`. See `docs/CAMPAIGN_BUILDING.md`.
    - AI settings: `dm.ai_config` (op=get|save|set_npc|reload; `scope` campaign|webapp, `config`, `key`, `settings`) — `.ai.yaml` providers, combat/conversation/task AI and per-NPC overrides; mirrors `GET/POST /ai/config`, `/ai/config/npc`, `/ai/config/reload`. API keys are masked on read. See `docs/AI_CONFIG.md`.
  - `tools_actions`: `actions.list_available`, `actions.execute` (for `InteractAction` with `target`, `entity_uid` optional — omit or `dungeon_master` for DM-direct door/object interaction; melee knockout via `opts.knock_unconscious`), `actions.move`, `actions.end_turn`, `actions.start_battle`, `actions.end_battle`.
  - `tools_npc` (NPC spatial awareness):
    - `npc.get_location` — returns an NPC's current map position and the enclosing hierarchy of area annotations (most specific to broadest). Allows the NPC LLM to know its location context (e.g., behind_bar → taproom → tavern_ground_floor).
    - `npc.query_area` — queries a map annotation by id and returns its details plus child sub-areas contained within it. Use to understand spatial layout and discover nested places.

  When adding a new DM-only Flask endpoint, also extend the matching `tools_dm` tool (preferring an extra `op` value over a brand-new tool) and update this catalogue.

Prompt/response patterns to preserve when changing LLM logic:

- `webapp/llm_handler.py` cleans thinking tags and enforces function-call responses. Keep that behavior when editing provider logic.
- `LlmMcpController._build_prompt(...)` renders a compact map + action list and expects the model to either: (a) return a zero-based index integer, or (b) call the MCP tool (function) with JSON {index, why}. If you change prompt format, keep the final instruction: "Return either a single integer index (0-based) or call choose_action with that index." (see code for exact wording).

Battle loop touchpoints:

- `Battle.start()` seeds initiative (`entity.initiative(...)` or custom), emits `start_of_combat`, and primes `current_turn_index` for `Battle.current_turn()`.
- `Battle.while_active()` is the core turn runner: invokes `start_turn()` (death saves, effects, `start_of_turn` event), asks the active controller (`begin_turn`, `select_action`, `move_for`), then calls `next_turn()` which advances rounds, triggers `top_of_the_round`, and checks `battle_ends()`.
- Actions flow through `Battle.execute_action` → `Action.resolve(...)` (maps, auto-targeting) → `Battle.commit(...)`, which applies `Action.apply` hooks, records animation payloads, and appends to `battle_log`.
- Dead combatants have no turn: loops call `Battle.skip_dead_turns(max_rounds=None)` before `start_turn()` (no death save, no end-of-turn effects, no legendary window). Unconscious combatants still take their turn. `Battle.while_active(max_rounds, callback)` enforces the round cap on **both** advance paths: `skip_dead_turns` forwards `max_rounds` to `_advance_turn_index`, and `while_active` re-checks `battle.round > max_rounds` after each skip — without the skip-path check, battles where dead combatants cluster at the initiative wrap (the index only wraps while skipping dead turns) ran past `max_rounds` indefinitely. After an async reaction the webapp resumes via `GameManagement.resume_after_reaction()` (mid-turn vs `end_turn_state`); never replay `start_turn()` for a turn already in progress. See `docs/WEBAPP_BLUEPRINTS.md` → "Combat turn loop and reaction resume".
- Reaction spells that change the triggering attack's outcome (Shield's +5 AC) return `'force_miss'` from `after_attack_roll`; `AttackAction` and `evaluate_spell_attack` honor it, since the effect itself is only applied at `commit`. A reaction spell built inline (Shield, Silvery Barbs) must check `SpellAction.can_cast`, pick a slot, and call `consume(battle)` once chosen. Shield isn't offered while one is already up (`ShieldSpell.is_active_on`). Wrath of the Storm (Tempest) fires from `after_take_damage_hook` via `wrath_of_the_storm_reaction`. Uncanny Dodge halves the whole hit, including Sneak Attack and `additional_damage` riders (shared `_hit_state`).
- Mirror Image is edition-aware (`Ruleset.mirror_image_model`: 2014 d20 redirect vs 2024 d6-on-hit), checked by `MirrorImageSpell.check_attack` from both weapon and spell attacks, and logged as a `mirror_image_duplicate` event. Multi-ray spells pass `opts['attack_index']` to `evaluate_spell_attack` so each ray rolls separately. See `docs/RULESETS.md` → "Mirror Image".
- Counterspell is a real reaction: `SpellAction.resolve` runs `natural20/utils/counterspell.py`'s `run_counterspell_window` before a spell takes effect. Hostile casters in range get offered a reaction (event `type: counterspell`), and the AI picks via `choose_counterspell`. See `docs/RULESETS.md` → "Counterspell reaction window".
- DM combat log summaries: `start_of_combat` logs a DM-only roster (team HP totals; per combatant starting HP, AC, gear, NPC attacks, conditions) and each `start_of_turn` logs the creature's current HP, AC and conditions, via `natural20/utils/combat_roster.py` with `visibility='dm'`. The `start_of_combat` and `start_of_turn` events carry `battle`. Teams with a PC also get a party briefing scoped to their members (`visibility={'kind': 'entities', ...}`): full partymate/sidekick stats, plus numbers-free descriptions (appearance, rough health, visible gear) of enemies they can see. Toggle with `game.yml` `combat_log.dm_summary` / `dm_turn_status` / `party_briefing`.
- `Battle.trigger_event(...)` hits registered battlefield handlers and `Map.activate_map_triggers`; `event_manager` broadcasts `start_of_turn`, `end_of_turn`, `movement`, `end_of_combat`, etc.
- Death attribution: `natural20/utils/death_info.py` records the last damaging blow, who downed a creature, and `attributes['death_info']` (also on the `died` event; causes `massive_damage` / `damage_while_dying` / `failed_death_saves` / `killed` / `unknown`). Pass `cause=` to `make_dead` from damage paths. `webapp/npc_kill_reaction.py` uses it so a `dialog: true` NPC that kills a PC can speak one in-character line (taunt/lament or `[NO_RESPONSE]`) via `ConversationService.handle_npc_kill_reaction`; opt out with `kill_reactions: false` (NPC) or `npc_kill_reactions.enabled: false` (`game.yml`). See `docs/CONVERSATION_RAG.md` → "Kill reactions".
- After a fight with at least one combat round, `webapp/battle_combat_recap.py` uses the NPC LLM to write a first-person recap (when/where, deaths, conversation beats) into each PC journal and each dialog NPC's memory store. Wired from `register_battle_end_hook_handlers`. Disable with `battle_combat_recap.enabled: false` in `game.yml`.
- Entity state lives in `Battle.entities` (`EntitiesUIDMap`): tracks resources (`action`, `bonus_action`, `movement`), stealth, help, statuses; manipulate via `Battle.consume(...)`, `do_distract(...)`, `dismiss_help_for(...)`.
- Legendary and opportunity windows: `eval_legendary_action()` (called from `Battle.end_turn()` and `while_active`) loops non-active entities for `legendary_action_listener`, while `trigger_opportunity_attack()` resolves reactions before normal queueing. Legendary YAML (`legendary_actions` with per-option `cost`, `type: move`, and `legendary_action_count`) is documented in `docs/CAMPAIGN_BUILDING.md` → "Legendary Actions"; helpers live in `natural20/utils/legendary_actions.py`. The webapp calls `GameManagement.push_end_of_turn_animations(battle)` after `end_turn()` so legendary moves/attacks animate immediately. Manually controlled (`WebController`) legendary creatures queue a *legendary action phase* instead of auto-picking: after `end_turn()` the webapp calls `GameManagement.begin_legendary_phase(battle)` (game loop, `/end_turn`, `/next_turn`) and pauses before `next_turn()` while `battle.legendary_phase` is set; `commit_and_update` converts the creature's action via `prepare_legendary_phase_action` and then `advance_legendary_phase` moves on. Socket events: `legendary_phase`, `legendary_phase_end`.
- SRD monster traits are YAML-driven (`natural20/utils/monster_traits.py`, documented in `docs/CAMPAIGN_BUILDING.md` → "Monster traits and advanced NPC attacks"): `legendary_resistance` (spent on any save rolled with a DC — always pass `opts={'dc': n}` to `save_throw` for real saves, never for probability estimates), `regeneration`, `misty_escape`, `undead_fortitude` (checked in `Entity.take_damage`; `bypass` damage types), `cannot_speak`, multiattack combo lists (names may repeat; `{any_of: [...], count: N}` expands to every combination), and NPC action keys `additional_damage` (with `life_drain`), `grapple_instead`, `target_if`, `target_creature_types`, `no_damage`, plus the source-linked `status:charmed` rider and the `effect:no_healing` rider (`natural20/effects/no_healing_effect.py`, blocks `Entity.heal` until the attacker's next turn). Heuristic attack scoring goes through `AttackAction.ai_value`.
- More YAML-driven monster mechanics (see `docs/CAMPAIGN_BUILDING.md` → "Breath weapons and other area abilities", "Innate spellcasting", "Glide"):
 - NPC `actions` entries with `type: area_save` (breath weapons) run through `NpcAreaAction` (`natural20/actions/npc_area_action.py`, action type `npc_area_ability`). They support cone/line/radius shapes, `recharge: 5-6` (rolled in `Battle.start_turn` via `roll_recharges`), `on_fail` riders (`exhaustion:N`, `condition:<name>`) and `success_immunity`. They are excluded from `Npc.attack_options`.
 - `innate_spellcasting` (`natural20/utils/innate_spellcasting.py`) gives at-will and N/day spells. Each N/day spell has a long-rest pool `innate:<spell>` spent through the `free_casts` path, with a fixed DC and attack bonus and `no_material`.
 - `death_burst` / `death_throes` also support `targeting: chain` and `on_fail_condition`. The condition lasts until the end of the target's next turn (`natural20/effects/timed_condition_effect.py`).
 - Auras also take `creature_types`, `requires: [see, hear]` and `condition_save_advantage`.
 - `glide` reduces fall damage.
 - Stunned creatures auto-fail STR/DEX saves and grant advantage to attackers.
 - Dimension Door reuses `MistyStepSpell` (YAML `require_los: false`, `ai_max_destinations` caps AI destination choices). Sending is a logged telepathic message (`SendingSpell`).
- Monster summons (SRD Vampire *Children of the Night* and similar) are a top-level NPC YAML `summons` list (uses/day, `blocked_by`, `requires: [outdoors|night|indoors]`, arrival rounds, duration, dismiss cost, per-option `npc`/`count`). The helpers are in `natural20/utils/summons.py` and the actions are `SummonCreaturesAction` / `DismissSummonsAction`. Pending arrivals spawn in `Battle.start_turn`, and summons leave on summoner death (`make_dead`), on expiry, or on long rest. Map property `outdoors: true` gates outdoor-only options. See `docs/CAMPAIGN_BUILDING.md` → "Summoning allies".
- Polymorph-style beast forms live in `natural20/utils/polymorph.py`. PCs reuse the Wild Shape overlay with `source: polymorph`, and NPCs snapshot their stats into `properties.polymorph_state`. When a beast form (Polymorph or Wild Shape) drops to 0 HP, `Entity.take_damage` reverts it and carries the excess damage over. Spell YAML keys are `beast_form` and `hostile_beast_form`. See `docs/CAMPAIGN_BUILDING.md` → "Polymorph and beast forms".
- AI friendly fire: `natural20/utils/friendly_fire.py` removes harmful options (attacks, damaging or enemy-only spells, damaging items and scrolls) aimed at the actor's own side from JEV and LLM option lists. Spell/item YAML `hostile: true|false` overrides the classification. Keep this filter when adding new AI option builders.
- Wasteful AI options: `natural20/utils/pointless_actions.py` drops these options for both JEV and LLM:
 - Second Wind at full HP.
 - Looting or pickups while any conscious enemy is present, even an invisible one.
 - Look unless a conscious enemy is actually hidden.
 - Disengage when not threatened in melee or unable to move afterwards.
 - Help on itself or on an ally that isn't asleep, grappled or restrained.
 - Voluntary prone or pickpocketing mid-fight.
 - Action Surge before the action is spent.
 - Dash when no enemy is visible, heard or remembered.
 - Dash while in an enemy's melee reach, not disengaged and above half HP.
 - Dash above half HP when every known enemy is already reachable with the movement left. After a Dash, JEV's move phase drops "pass" while dashed movement is unspent.
 - Dash by a caster or skirmisher (Cunning Action, Nimble Escape) that already spent its action, isn't in melee and is above half HP. The move planner offers it no reposition, so the movement is wasted.
 - Spare the Dying on a creature that isn't dying (above 0 HP, already stable or dead). The spell also has no effect on such a target.
 - Harmful options aimed only at a foe held in a Polymorph cast by the actor's own side, while another standing foe can be targeted. Hitting the beast form ends the control. `AttackAction.ai_value` down-weights these for legendary and heuristic picks.
 - Attacks or harmful spells aimed only at downed foes while a standing foe can be targeted. YAML `finish_downed: true` opts out. `AttackAction.ai_value` also down-weights these attacks for heuristic and legendary picks.
 - Spare the Dying on a creature that a slot healing spell on the list would also bring back.
 - Spells with YAML `ai_in_combat: false` (non-combat utility spells) while enemies are up.
 - Recasting a YAML `ai_no_recast: true` spell (Spirit Guardians, Call Lightning, Sleet Storm, Beacon of Hope, Aura of Vitality, Flaming Sphere) the caster is already concentrating on.
 - Hide while already hidden, or in plain view of a foe whose passive Perception beats a natural 20.
 - Dispel Magic on a creature with no spell cast by an opponent on it (`natural20/utils/dispel.py` `worth_dispelling`).
 - The on-turn Wrath of the Storm action (it only picks a damage type; the reaction fires by itself).
 - Any action class with `ai_in_combat = False` (e.g. `CraftItemAction`) while enemies are up.

 AoE auto-targeting scores only enemies the caster sees or senses (downed foes count half), so it never aims at a hidden creature's true square.

 JEV's auto-build path only builds classes that `available_actions` offers (so polymorph and Wild Shape gating applies), and it suppresses jittery or OA-provoking movement leaves. `autobuild` drops NPC attacks whose `target_if` / `target_creature_types` the target fails. See `docs/JEV_NPC_BATTLE_AI.md`.
- JEV state context (`JevActionPlanner._render_state`): the actor's own resources and state, an entity-centered ASCII POV map (default `30 ft`, `N20_JEV_MAP_RADIUS_FT`; header shows the rendered window's top-left/bottom-right coordinates; `*` actor, `A-Z` visible allies, `0-9` visible enemies, `?` in-bounds dark/unseen, `.` empty, `#` blocked/outside-the-map wall, `-` visible closed door, `+` visible open door, `o` visible cover object, `~` difficult terrain, `!` hazard), visible enemies (including regeneration and the damage type that blocks it), unseen enemies (heard or last-known squares), every ally (including out-of-sight, dying and fallen ones), damage dealt so far, heard callouts, recent conversation, and the witnessed combat log from earlier turns and since the last turn. It is capped by `N20_JEV_STATE_MAX_CHARS`, which trims the oldest history first.
- Casting a concentration spell ends the caster's current concentration even if every target saves. `SpellAction.resolve` queues a generic `concentration_replaced` item, so spells only call `battle.start_concentration` on success. Legendary Resistance on concentration checks follows the NPC YAML `legendary_resistance_policy` (by default, only spells of level 3+ that affect an enemy, keeping one use in reserve). See `docs/RULESETS.md` and `docs/CAMPAIGN_BUILDING.md`.
- Combat coordination: AI combatants (LLM/JEV) communicate through `natural20/utils/combat_comms.py` — 5e "brief utterance on your own turn" (one callout per turn, word cap, must be able to speak/hear, language comprehension, enemies in earshot overhear, telepathy via `telepathy: <ft>`). All in-battle `send_conversation` speech (including player chat) lands in listeners' `battle.entities[e]['heard_callouts']`. Decision quality scales with INT via `natural20/utils/combat_intelligence.py` tiers (`instinct`/`simple`/`tactical`/`mastermind`, YAML override `tactics:`). JEV picks a strategic callout from `natural20/utils/combat_strategy.py`'s combat-data menu (`jev_select_callout`). Callouts without explicit words are voiced in character by the phraser hook (`combat_comms.set_callout_phraser`; the webapp installs `webapp/combat_callout_phrasing.py`, which uses the NPC conversation LLM). Both are toggled by `game.yml` `combat_communication.strategic_callouts` / `llm_phrasing`, and per creature by `callout_phrasing: false`. Ally-directed callouts (`combat_comms.ALLY_DIRECTED_KINDS`: focus, heal, warn, ...) are refused with `no_listening_ally` when no ally can hear and understand them, and the strategic "heal" call is offered only when some ally can actually heal (`_can_heal_others`). The phraser gets the speaker's and allies' recent lines (`recent_lines`) so it doesn't repeat them. See `docs/COMBAT_COMMUNICATION.md`.
- Spells per turn are edition-aware (`Ruleset.spells_per_turn_model`: 2014 bonus-action-spell rule vs 2024 one slot per turn), enforced by `spell_requirements.spells_this_turn_issue` from `SpellAction.can_cast`. Slot healing dice come from YAML `heal_dice` / `heal_dice_per_slot` (2024 overlay doubles Cure Wounds / Healing Word). See `docs/RULESETS.md`.
- `Entity.take_damage` defers its follow-up events (`DAMAGE_FOLLOWUP_EVENTS`: unconscious, died, death_fail, concentration checks) through `EventManager.deferring(...)` so the combat log shows the damage line first. A creature dying from its third failed death save logs `death_fail` before `died` and gets no `start_of_turn`. The DM turn status line is a separate `turn_status` event, emitted by `Entity.reset_turn` after start-of-turn hooks (Shield ends) and effect cleanup. `make_unconscious` clears `stable`, so a creature that drops again is dying again. Item use (`use_item`, with `hp_gain_roll` for potions) and Arcane Ward absorption (`arcane_ward_absorb`) are logged.
- Attacking unseen creatures (5e "Unseen Attackers and Targets") lives in `natural20/utils/unseen_targets.py`.
  - `AttackAction.target_square` is a guessed square: an empty square is an automatic `blind_miss`, and an occupied one is attacked with disadvantage.
  - A miss is logged the same way whether or not anything was there, so the log never says if the guess was right.
  - Invisible creatures that aren't hidden are heard at their square, and attackers leave a last-known position in `battle.entities[e]['unseen_memory']`.
  - In the VTT, sensed squares get "?" markers (`tile['unseen_presence']`). The `/target` preview treats every square without a visible target the same way, and `/action` turns coordinate targets into blind attacks.
  - AI controllers get blind-attack variants from `blind_attack_variants`.
  - Campaign switch: `game.yml` `unseen_targets`. See `docs/UNSEEN_TARGETS.md`.
- Frightened is source-linked (`natural20/utils/fear.py` `apply_fear`): disadvantage on attacks/checks while the source is in sight, optional `ends_on_damage` and `action_limit` (enforced in `Battle.commit`). Auras (paladin Protection/Courage/Devotion plus YAML `auras:`) live in `natural20/utils/auras.py` and feed `_roll_save_throw` and `immune_to_condition`. Effects can add to-hit bonuses via a stacked `attack_roll_bonus` effect (Sacred Weapon). Feat or class YAML `attack_options` (`natural20/utils/attack_options.py`, `AttackOptionAction`) cover before-attack and on-hit riders, including shared pools, level-scaled dice, `variants` offered together, radius saves and `follow_up_attack` (a free `GrantedAttackAction` against a creature near the target); flat on-hit class riders (Improved Divine Smite / Radiant Strikes) are in `feature_hit_riders.py`; Great Weapon Master and the Hew bonus attack are in `great_weapon_master.py` / `HewAttackAction`, edition-picked by `feat_editions`. Feat YAML also supports `resource_pools`, `weapon_attack_rules` (ignore cover / long-range / adjacent-enemy disadvantage, `ignore_properties: [loading]`, Light-crossbow extra-attack damage; `natural20/utils/feat_mechanics.py`), `luck` (2024 luck points via the reaction prompt; `natural20/utils/luck_points.py`; the halfling reroll-1s trait comes only from race features, never the `feats` list) and `free_casts`. Feat ids with no YAML are no-ops. Loading is enforced for PCs (`natural20/utils/weapon_loading.py`, one shot per Attack action). Non-SRD 2024 feats live in `expansion_packs/players_handbook_2024/`. See `docs/CAMPAIGN_BUILDING.md` → "Feats, auras and edition overrides".
- Passive item mechanics (`natural20/utils/item_mechanics.py`; see `docs/CAMPAIGN_BUILDING.md` → "Passive bonuses and attunement"): item YAML `ability_bonus` (`{wis: 2, max: 20}`), `ability_set` (`{con: 19}`), `proficiency_bonus`, `cannot_be_surprised`, `regain_hp`. They apply while the item is equipped and, if `requires_attunement`, listed in the optional `attuned` property (no `attuned` list = everything equipped counts as attuned).
 - Attunement management lives in `natural20/utils/attunement.py`. Both editions use the same rules.
 - Requests queue in `attunement_pending` and complete on a rest (`Entity.short_rest` / `long_rest`). The limit is 3 (`Ruleset.attunement_limit`), and class YAML `attunement` entries can raise it. Prerequisites come from `attunement_class|race|alignment|spellcaster`.
 - Attunement ends on death and after 24 hours of separation (`tick_attunement`). It can't be ended voluntarily while the item is cursed.
 - An unattuned item gives only its mundane benefits. Use `effective_item_meta` (YAML `unattuned:` overrides) and `_to_item['magic_active']`.
 - The UI is the sheet's Attunement panel plus item card buttons, posting `POST /attunement`. `Entity.ability_scores` is a property that overlays item changes on the stored scores (`properties['ability']` stays the creature's own scores; writes go through to it; `copy.deepcopy` returns the base). The D&D Beyond importer leaves out DDB item score bonuses that the engine applies itself, so they aren't counted twice.
- Dancing weapons (item YAML `dancing: {attacks, move_feet, leash_feet}`, SRD Dancing Sword variants): `DancingWeaponAction` (toss / command / catch, registered via `class_feature_registry` + an `Npc.available_actions` branch) reuses `AttackAction` with `_free_attack` for the strike. State is in `properties['dancing_weapons']`, and the map marker is a `DancingWeaponTile` (`!zone_tile`). The VTT action type is `dancing_weapon:<mode>:<item>`.
- Generic spell-effect hooks (see `docs/RULESETS.md` → "Targeting wards, action restrictions and spell follow-ups"):
 - `targeting_ward` effect (`natural20/utils/targeting_ward.py`, used by Sanctuary): anyone targeting the warded creature with an attack (`AttackAction.resolve`) or a harmful spell (`SpellAction.resolve`, via `friendly_fire.is_harmful`) saves first or loses the attack/spell. Area spells aimed at a point are not blocked.
 - `action_restriction` effect (`natural20/utils/action_restrictions.py`, used by Gaseous Form): a stacked handler returns forbidden kinds (`attack`, `spell`, `speak`, `interact`), checked by `AttackAction.can`, `SpellAction.can_cast`, `SpeakAction.can` and `InteractAction.can`.
 - `damage_event` fires a `dealt_damage` entity trigger on the source before damage lands (Sanctuary ends on it).
 - Spells with a bonus-action follow-up that the caster controls (Flaming Sphere → `FlamingSphereAction`) register through `class_feature_registry` (PCs pick it up automatically) plus a small `Npc.available_actions` branch. Import the action module at load time so `Battle.commit` sees its `apply`.
 - Entity event hooks are not saved. Effects that rely on them define `restore_hooks()`, which `relink_spell_entities` calls after a load (Sanctuary, Ray of Sickness, Melf's Acid Arrow, Ensnaring Strike, Fear). Player-character `attributes` are not saved either, so keep spell state on the spell object (scalars, or lists stored as comma-separated uid strings), as Disguise Self does.
 - Weapon-hit spells (YAML `weapon_hit: {weapon: ranged|melee|any, timing: after_hit|next_hit}`, base class `natural20/spell/extensions/weapon_hit_spell.py` `WeaponHitSpell`). With `after_hit` (2024), a hit by a PC offers `WeaponHitSpellCastAction` (bonus action, one per usable slot) through `controller.select_reaction` (event `type: weapon_hit_spell`), and the spell can't be cast from the list. With `next_hit` (2014), the spell is cast normally and arms the caster (`weapon_hit_spell_armed`). Subclasses implement `on_weapon_hit(...)` (Ensnaring Strike, Hail of Thorns).
 - Magical restraints that can be escaped register an `escapable_restraint` effect exposing `escape_dc`, `escape_skill` and an optional `break_free(creature, by)`. `BreakFreeAction` (`natural20/actions/break_free_action.py`) offers the check to the restrained creature and to allies within 5 ft.
 - Silence areas: map objects with `silenced: true` (`natural20/utils/silence.py`) block speech and hearing (`combat_comms`) and verbal spells (`spell_requirements.environment_issue` → `silenced`). The Silence spell's `SilenceWard` adds thunder immunity through `immunity_override` while the creature stands in the area. Spike Growth tiles set `movement_cost: 2`, and the zone's `on_movement_step` deals damage per square moved.
 - Small generic effect keys: `no_opportunity_attacks` (checked by `retrieve_opportunity_attacks`), `item_enhancement` (Magic Weapon; summed by `class_mechanics.effect_enhancement_bonus` into attack and damage), `skill_check_bonus` (Pass without Trace; stacked handler gets `opts['skill']`), and spell YAML `requires: [out_of_combat]` (Rope Trick).
 - `apply_fear(..., must_flee=True)` (Fear) makes AI controllers Dash and then move away via `fear.flee_choice`. A cornered creature acts normally.
 - Generic spell classes driven by YAML: `StrikeSurgeSpell` (`no_opportunity_attacks` plus a once-per-casting `attack_surge` armed by `AttackSurgeAction`: advantage, extra damage, speed bonus; used by Zephyr Strike) and `PushCreatureSpell` (`save`, `push_distance`, `max_size`; used by Gust).
 - `class_feature_registry` builders that declare a `battle` keyword get the live battle. Don't rely on `combat_comms.battle_for`, which can match a stale battle by entity uid. `Battle.commit` refreshes its cached action-subclass list when new action modules are imported.
- Grappler-side rules (drag cost and size exception, free release, grapple ending on death / incapacitation / out of reach, 2024-only grappled attack disadvantage) live in `natural20/utils/grappling.py`; see `docs/RULESETS.md` → "Grappler-side rules". AI controllers release pointless grapples via `GenericController.grapple_release_action`, and LLM/JEV prompts show the drag penalty through `grapple_status_text`.
- Save-or-suffer spells (Banishment, Hold Monster, Hypnotic Pattern, Dominate *, Phantasmal Force, Calm Emotions) use `ConditionSaveSpell` with a YAML `condition_save` block (`off_plane`, `restrict_actions`, `ally_condition_immunities`). Generic hooks that came with them:
 - Off-plane creatures (`natural20/utils/off_plane.py`, used by Banishment and Blink) keep their square, but `Entity.allow_targeting` returns False, so `Map.thing_at` and AoE gathering skip them.
 - A stacked `condition_immunity` effect is read by `Entity.immune_to_condition`.
 - Map objects with `movement_cost` > 2 add `Map.extra_terrain_cost` on top of difficult terrain (Plant Growth).
 - NPC YAML `magic_resistance: true` gives advantage on magical saves. `death_burst` (alias `death_throes`) is an area save fired from `make_dead` (`monster_traits.trigger_death_burst`).
 - `SummonSpiritSpell` (`summon_spirit` YAML; Summon Fiend) scales a spirit NPC by slot level and removes it when concentration ends. Spirits get `vanish_on_death` (`natural20/utils/summons.py`: dying ends the summoner's spell instead of leaving a corpse), and `death_throes.on_spell_end: true` explodes a live spirit when the spell ends.
 - NPC attack key `teleport_after_attack: <feet>` opens a window after the attack hits or misses. `PostAttackTeleportAction` (`natural20/actions/post_attack_teleport_action.py`, type `post_attack_teleport`) is then a free teleport to a visible unoccupied square. The window closes at the creature's next `reset_turn`.
 - `autobuild` passes the *value* of `select_choice` `[label, value]` pairs, the same as the web UI does. Spells that store the choice on the action must copy it in `clone()` (Hex, `SpellAction.summon_variant`).
 - `hit_reaction_window` returns early for creatures that aren't in the battle or have no `hit_reactions`.
- 2024 warlock (`templates/rulesets/5e-2024/char_classes/warlock.yml`) and Archfey patron (PHB 2024 pack) blocks: `feature_choices` (the sheet's invocations count as features), `free_casts` (`at_will`, `spell_property`/`spell_key` for Mystic Arcanum, `auto_succeed_save`; free casts are used before Pact slots), `cantrip_riders`, `spell_riders`, `reaction_casts`, `hit_reactions`, `condition_immunities`, plus sheet `class_spells`. Taunt is in `natural20/utils/taunt.py`, and War Caster's spell-as-opportunity-attack is in `natural20/utils/reactive_spell.py`. See `docs/CAMPAIGN_BUILDING.md` → "Warlock (SRD 5.2) and the Archfey patron".

Files to check for implementation examples and extension points:

- `natural20/session.py` — loading resources, entity registry, save/load patterns.
- `natural20/llm_controller.py` — detailed prompt building, parsing, MCP bridge, fallback rules.
- `webapp/llm_handler.py` — provider adapters, session logging, function-call parsing and execution.
- `docs/WEBAPP_BLUEPRINTS.md` — where to add routes, helper modules, parity tests after webapp changes.
- `templates/` and `samples/` — example maps, characters, and level configs used by `Session` and the web UI.
- `natural20/map.py` — targeting helpers: `squares_in_cone(...)` and `squares_in_adjacent_cube(...)` (cardinal, face-adjacent 3x3 cube used by Thunderwave).
- `natural20/map_import/` — battlemap image → map YAML (tile-wise VLM). CLI: `python scripts/import_battlemap.py`. See `docs/BATTLEMAP_IMPORTER.md` and `.cursor/skills/n20-import-battlemap/SKILL.md`. **Prefer the importer whenever battlemap art already exists**; do not transcribe a whole battlemap by eyeballing it or run the procedural dungeon generator for those maps. Multi-floor pages (several plans on one image) are cropped automatically (`--split-panels`, default on).

Extending spells and character classes:

- **Routine workflow**: follow project skill `.cursor/skills/n20-add-spell/SKILL.md` (YAML + Python + loader + tests + VTT cast animation / persistent overlay / effect icon checklist).
- New spells require: YAML entry in `templates/items/spells.yml` (with `spell_list_classes` and optional `spell_class` override), a matching class in `natural20/spell/` implementing `build_map` and `resolve`, and registration inside `natural20/utils/spell_loader.py`. Reuse `natural20/spell/extensions/` helpers for shared targeting/damage logic.
  - UI targeting map params you can use in `build_map()`:
    - `select_target`, `select_empty_space`, `select_cone`, and `select_cube`.
  - `select_square` accepts `require_corpse: true` (plus optional `require_humanoid`, `corpse_sizes`) so auto-targeting only offers squares holding matching dead creatures (see `natural20/utils/corpses.py`, used by Animate Dead). Player-character corpses are valid remains, but are never removed: `animate_remains_into` keeps the PC registered on its map without a token (`attributes['body_moved_to']`; `Map.place` honours it, so webapp respawn paths can't redraw or re-materialize the PC). When the undead dies, `restore_animated_remains` (called from `make_dead`) puts the PC corpse back at the undead's square. `Map.remove` only clears token cells the entity occupies.
  - Spells whose `casting_time` is not action/bonus_action/reaction (e.g. `1:minute`) are uncastable while a battle is ongoing (`SpellAction.can_cast`).
    - For `select_cube`, return `{ 'type': 'select_cube', 'range': <feet>, 'num': 1 }` and then accept a 2D point in the subsequent `next(target)`.
  - YAML AoE keys: use `range_cone` for cones and `range_cube` for cubes.
  - Thunderwave specifics (baseline reference): 15‑ft cube originating from the caster (directional), CON save, half damage on success and no push, failed save pushes 10 ft away using `Entity.push_from(...)`, damage `2d8 + 1d8` per slot above 1st.
- Classes without a Python mixin run from YAML alone as data-driven classes (`natural20/entity_class/data_driven.py`):
 - `spellcasting.progression` (full / half / half_round_up / third or `slot_table`) sets the slots.
 - Supported mechanic blocks: `resource_pools`, `save_assists`, `spell_roll_bonuses`, `free_casts`, `rest_items`, `craft_options`, `infusions`, `initiative_bonuses`, `speed_bonuses`, `first_turn_movement`, `senses` (darkvision, `evade_darkvision`), `feature_actions` (`ClassFeatureAction`), `rest_effects` and `attack_options`, at the class top level or under `subclasses.<name>`. They are interpreted by `natural20/utils/class_mechanics.py`.
 - Mixin classes (e.g. the ranger) may also declare `subclass_property` + `subclasses`; subclass features, spells and pools then work as for data-driven classes. A class YAML `spellcasting` block overrides the mixin's slot table (2024 ranger overlay).
 - Reference implementations: the artificer in `expansion_packs/tashas_cauldron/` and the Gloom Stalker ranger in `expansion_packs/players_handbook_2024/`.
 - See `docs/CAMPAIGN_BUILDING.md` → "Data-driven classes". Prefer extending these blocks over writing a new mixin for a class whose features fit them.
- To add a player class, create a mixin in `natural20/entity_class/` (see `wizard.py` for slot tables and rest hooks), add a YAML config in `templates/char_classes/`, and update `PlayerCharacter` usage if the class introduces custom actions or resources. Slot accounting should integrate with `PlayerCharacter.spell_slots` and class-specific `initialize_<klass>` routines.

Documentation

For Agents and Humans alike please add,edit or update related information in the docs folder. Update it when information useful to humans and agents alike will benefit from dedicated documentation as well as to update or correct misleading entries. Also create skills for routine tasks.

Webapp changes: update `docs/WEBAPP_BLUEPRINTS.md` when blueprint layout, helpers, or parity workflow changes.

Small gotchas discovered in the repo:

- Prompts can be long; `N20_LLM_PROMPT_MAX_CHARS` truncation logic is present in `LlmMcpController` — preserve or respect it when modifying prompt construction.
- Some LLM providers are optional; code defensively checks for provider availability. When adding imports depend on optional libs, prefer lazy imports and clear error messages.
- Many YAML-driven resources live under the `templates/` or `samples/` directories — tests and the web UI assume specific file names (e.g., `templates/index.json`, `game.yml`).
  - If you add new targeting modes for spells, ensure both sides are wired:
    - Web UI: add a handler in `webapp/static/engine.js` (e.g., for `select_cube`) and post `mode` along with `target`.
    - Server: update `/target` (preview squares) and the generic `/action` builder to recognize the new selector type and `mode` (e.g., treat `'cube'` like `'cone'` for coordinate targets).
- Multi-target spells can carry their `action.target` as a **tuple** (the auto-targeting builder, `natural20/utils/action_builder.py`, wraps `combinations(...)` results in tuples) as well as a list (web UI) or a single entity. Any code that walks `effect.action.target` (e.g. `Entity.dismiss_effect`) must branch on `isinstance(target, (list, tuple, set))`, not just `list` — a failed concentration check on a multi-target spell (e.g. Beacon of Hope) otherwise crashes with `AttributeError: 'tuple' object has no attribute 'remove_effect'`.

If you change LLM behavior, unit tests to update or add:

- `tests/webapp/test_llm_logging.py`, `tests/webapp/test_real_response.py`, and other `tests/webapp/*` exercise provider parsing and function-call behavior. Update them if you alter the response-cleaning or function-call format.

If anything here is unclear or you want this shortened/expanded for a specific agent style (e.g., code-only vs. conversational), tell me which sections to refine and I'll iterate.
