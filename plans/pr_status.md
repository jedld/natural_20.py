# PR Status Overview

## Completed (PR 1 - Baseline Parity Harness)
- `plans/artifacts/routes_baseline.json` ✅
- `plans/artifacts/socketio_events_baseline.json` ✅
- `plans/artifacts/endpoints_baseline.json` ✅
- `tests/webapp/test_route_inventory_parity.py` ✅
- `tests/webapp/test_socketio_event_parity.py` ✅
- `tests/webapp/test_endpoint_name_parity.py` ✅

## Completed (PR 2 - Helper Extraction Foundation)
- `webapp/blueprints/__init__.py` ✅
- `webapp/blueprints/helpers/__init__.py` ✅
- `webapp/blueprints/helpers/auth_utils.py` ✅
- `webapp/blueprints/helpers/template_globals.py` ✅ (+ `visible_log_messages_for_username`)
- `webapp/blueprints/helpers/action_utils.py` ✅
- `webapp/blueprints/helpers/runtime_state.py` ✅ (+ `get_tile_px`, `get_map_padding`)
- `webapp/blueprints/helpers/character_builder_utils.py` ✅
- `webapp/blueprints/helpers/llm_init.py` ✅
- `webapp/blueprints/helpers/pvp.py` ✅
- `webapp/blueprints/helpers/effects.py` ✅
- `webapp/blueprints/helpers/special_effects.py` ✅ (new — effect payload filtering)
- `app.py` imports from helpers ✅

## Completed (PR 3 - Assets Blueprint Extraction)
- `webapp/blueprints/assets.py` ✅ (9 routes)
- `tests/webapp/test_assets_blueprint.py` ✅

## Completed (PR 4 - Auth Blueprint Extraction)
- `webapp/blueprints/auth.py` ✅ (4 routes)
- `url_for` references updated to `auth.*` / `navigation.*` ✅
- `tests/webapp/test_auth_blueprint.py` ✅

## Completed (PR 5 - AI Blueprint Extraction)
- `webapp/blueprints/ai.py` ✅ (13 routes)
- `tests/webapp/test_ai_blueprint.py` ✅

## Completed (PR 6 - Navigation Blueprint Extraction)
- `webapp/blueprints/navigation.py` ✅ (12 routes)
- `tests/webapp/test_navigation_blueprint.py` ✅

## Completed (PR 7 - Character Blueprint Extraction)
- `webapp/blueprints/character.py` ✅ (10 routes + journal CRUD)
- `webapp/blueprints/helpers/journal_utils.py` ✅ (`_record_narration_for_pcs` shared with effects/battle)
- Old routes removed from `app.py` ✅
- Baseline artifacts regenerated ✅
- `tests/webapp/test_character_blueprint.py` ✅ (4 smoke tests)
- Parity tests: 10/10 passed ✅

## Completed (PR 8 - Battle Blueprint Extraction)
- `webapp/blueprints/battle.py` ✅ (~1,256 lines, combat/actions/turn routes)
- `tests/webapp/test_battle_blueprint.py` ✅ (4 smoke tests)
- `tests/webapp/test_action_type_resolution.py` import updated to `action_utils` ✅
- Baseline artifacts regenerated ✅

## Completed (PR 9 - DM Blueprint Extraction)
- `webapp/blueprints/dm.py` ✅ (~1,980 lines, admin + entity + inventory + rest routes)
- `runtime_state.py` extended with `set_game_session`, `get_perf_lock`, `get_perf_stats` ✅
- Duplicate `/health` route removed from app.py ✅
- `tests/webapp/test_dm_blueprint.py` ✅ (4 smoke tests)
- Baseline artifacts regenerated (129 routes) ✅
- Parity tests: 10/10 passed ✅

## Completed (PR 10 - SocketIO & Effects Extraction)
- `webapp/blueprints/socketio_handlers.py` ✅ (`connect`, `request_effects`, `register`, `message`, `disconnect`)
- `emit_active_effects_for_client()` shared helper in `helpers/effects.py` ✅
- `register_effect_listeners()` now wired from `app.py` (battle-end narration, control override, etc.) ✅
- Duplicate template globals and auth helpers removed from `app.py` ✅
- `describe_terrain`, `t`, `process_action_hash` registered via `template_globals.py` ✅
- `tests/webapp/test_socketio_handlers.py` ✅
- SocketIO parity tests pass ✅

## Completed (PR 11 - Cleanup and Hardening)
- `webapp/app.py` slimmed to **~320 lines** (bootstrap only)
- New helpers: `campaign_config.py`, `cors_config.py`, `perf.py`, `conversation_wiring.py`
- Removed duplicate template-global and auth helper code from `app.py`
- Smoke tests: `test_assets_blueprint.py`, `test_auth_blueprint.py`, `test_ai_blueprint.py` ✅
- `AGENTS.md` updated with blueprint architecture table ✅
- `docs/WEBAPP_BLUEPRINTS.md` added ✅
- Backward-compat re-exports kept on `app` module (`PlayerCharacter`, `autofill_pvp_battle_turn_order`, effect filters, `origin_allowed`, …)
- Full webapp suite: **180 passed** (1 pre-existing LLM router failure)

## Refactor complete

All planned PRs (1–11) are done. `app.py` is the composition root; domain logic lives in blueprints and helpers.

## Current app.py size
320 lines (down from 8090)

## Blueprint modules
| Module | Lines | Routes |
|---|---|---|
| `blueprints/assets.py` | ~397 | 9 |
| `blueprints/auth.py` | ~187 | 4 |
| `blueprints/ai.py` | ~500 | 13 |
| `blueprints/navigation.py` | ~599 | 12 |
| `blueprints/character.py` | ~890 | 10 + journal |
| `blueprints/battle.py` | ~1256 | ~25 |
| `blueprints/dm.py` | ~1980 | ~40 |
| `blueprints/socketio_handlers.py` | ~80 | 5 events |
