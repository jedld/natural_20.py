# Changelog: llm_support → master Merge

**Merge Date:** 2026-05-29
**Source Branch:** `llm_support`
**Target Branch:** `master`
**Total Commits:** 210 (non-merge)
**Files Changed:** 9,746 (+1,053,291 insertions, -5,274 deletions)

---

## Table of Contents

1. [Core Engine Changes](#1-core-engine-changes)
2. [LLM & MCP Integration](#2-llm--mcp-integration)
3. [Character Classes & Spells](#3-character-classes--spells)
4. [Battle System](#4-battle-system)
5. [Web Application (Flask Blueprints)](#5-web-application-flask-blueprints)
6. [VTT Frontend (JavaScript/CSS)](#6-vtt-frontend-javascriptcss)
7. [AI & Pathfinding](#7-ai--pathfinding)
8. [Entity System](#8-entity-system)
9. [Actions](#9-actions)
10. [Spells Package](#10-spells-package)
11. [UI/UX Improvements](#11-uiux-improvements)
12. [Performance Optimizations](#12-performance-optimizations)
13. [Testing & CI/CD](#13-testing--cicd)
14. [Campaign Content & Templates](#14-campaign-content--templates)
15. [Documentation](#15-documentation)
16. [Bug Fixes](#16-bug-fixes)

---

## 1. Core Engine Changes

### New Modules
- **`natural20/concurrency.py`** — Thread-safe concurrency utilities for battle loop and LLM operations.
- **`natural20/entity_registry.py`** — Centralized UID-based entity registry replacing scattered lookup patterns.
- **`natural20/background.py`** — D&D 5e background support (Acolyte, Charlatan, Criminal, Folk Hero, Guild Artisan, Hermit, Outlander, Sailor).
- **`natural20/combat_script.py`** — Script-based combat sequencing for scripted encounters.
- **`natural20/companion.py`** — Companion entity handling (find_familiar, animal_companion).
- **`natural20/campaign_log_db.py`** — Persistent campaign logging database for session history.

### Session & Battle Loop
- **`natural20/battle.py`** — Major rewrite (+1,073 lines):
  - Full short-rest support in engine (`Battle.rest()`)
  - Legendary action evaluation loop (`eval_legendary_action()`)
  - Opportunity attack windows (`trigger_opportunity_attack()`)
  - Resource tracking (`Battle.consume()`, `do_distract()`, `dismiss_help_for()`)
  - Control-override integration for LLM DM assistant
  - Event manager integration for `start_of_turn`, `end_of_turn`, `movement`, `end_of_combat`
  - Persist combat logs across save/load cycles
- **`natural20/session.py`** — Enhanced entity registration, map switching, and serialization.

### Die Roll System
- **`natural20/die_roll.py`** — Complete rewrite (+311 lines):
  - Advanced die notation parser (e.g., `2d8 + 1d8`)
  - Advantage/disadvantage support
  - Critical hit/fail handling
  - Language-aware combat log output

---

## 2. LLM & MCP Integration

### MCP Tool Surface (New)
Complete Model Context Protocol implementation for LLM-driven game control:

- **`webapp/mcp/routes.py`** — Flask blueprint with three discovery endpoints:
  - `GET /mcp/manifest` — MCP server manifest
  - `GET /mcp/tools/list` — Tool catalog
  - `POST /mcp/tools/call` — Tool execution
- **`webapp/mcp/tool_registry.py`** — Central tool registration and dispatch.
- **`webapp/mcp/context.py`** — MCP context management.

#### Tool Categories
| Module | Tools |
|--------|-------|
| `tools_world` | `world.list_maps`, `world.get_map`, `world.list_entities`, `world.get_entity`, `world.get_battle`, `world.list_npc_types` |
| `tools_dm` | `dm.set_hp`, `dm.heal`, `dm.damage`, `dm.add_status`, `dm.remove_status`, `dm.set_property`, `dm.add_item`, `dm.remove_item`, `dm.equipment`, `dm.set_resource`, `dm.spawn_npc`, `dm.spawn_object`, `dm.remove_entity`, `dm.teleport`, `dm.battle_admin`, `dm.set_controller`, `dm.rest`, `dm.save_load`, `dm.effect`, `dm.sound`, `dm.advance_time` |
| `tools_actions` | `actions.list_available`, `actions.execute`, `actions.move`, `actions.end_turn`, `actions.start_battle`, `actions.end_battle` |

### LLM Controller
- **`natural20/llm_controller.py`** — `LlmMcpController` with:
  - Prompt building with compact map + action list rendering
  - MCP tool call parsing (function-call JSON + integer index fallback)
  - Safe fallback to heuristic `GenericController`
  - Prompt truncation (`N20_LLM_PROMPT_MAX_CHARS`)
  - Bridge to external MCP server (`N20_MCP_URL`)

### Provider Adapters
- **`webapp/llm_handler.py`** — Multi-provider support:
  - Ollama (default), OpenAI, Anthropic, Mock
  - Thinking tag cleanup
  - Function-call token enforcement (`[FUNCTION_CALL: get_map_info()]`)
  - Session logging

### RAG (Retrieval-Augmented Generation)
- **`webapp/entity_rag_handler.py`** — Entity-aware context retrieval for LLM conversations.
- **`docs/CONVERSATION_RAG.md`** — RAG architecture documentation.
- NPC RAG capabilities with language-aware responses.
- Deduplication and context window management.

### DM Assistant
- LLM-powered DM assistant with roster management, spawn fallbacks, and control overrides.
- Control-override notifications via SocketIO.

---

## 3. Character Classes & Spells

### New Classes (Natural 20 Engine)
| Class | Module | Key Features |
|-------|--------|-------------|
| **Monk** | `natural20/entity_class/monk.py` | Martial arts, flurry of blows, step of the wind |
| **Barbarian** | `natural20/entity_class/barbarian.py` | Rage, patient defense, feline agility |
| **Bard** | `natural20/entity_class/bard.py` | Bardic inspiration, spellcasting |
| **Druid** | `natural20/entity_class/druid.py` | Wild shape, spellcasting |
| **Sorcerer** | `natural20/entity_class/sorcerer.py` | Spellcasting, sorcery points |
| **Warlock** | `natural20/entity_class/warlock.py` | Eldritch blast, pact magic |
| **Ranger** | `natural20/entity_class/ranger.py` | Spellcasting, favored enemy |

### Enhanced Classes
- **Cleric** — Level 2+ support, new spells (Guiding Bolt, Inflict Wounds, Spiritual Weapon, Turn Undead)
- **Paladin** — Divine Smite refinement, Lay on Hands fixes, spellcasting
- **Fighter** — Action surge, spell effects, second wind
- **Wizard** — Spell slot accounting improvements
- **Dragonborn** — Breath weapon action support

### New Spells (Python Classes + YAML)
| Spell | Class | Type | Key Features |
|-------|-------|------|-------------|
| Thunderwave | Wizard/Sorcerer | AoE Cube | 15ft directional cube, CON save, push 10ft |
| Burning Hands | Wizard/Sorcerer | AoE Cone | 15ft cone, DEX save, fire damage |
| Chromatic Orb | Wizard | Ranged | Multi-element random damage |
| Misty Step | Wizard/Sorcerer | Teleport | 30ft self-teleport, bonus action |
| Eldritch Blast | Warlock | Ranged | Scaling beam, cantrip |
| Hellish Rebuke | Warlock | Reaction | Fire damage to attacker |
| Darkness | Wizard/Sorcerer | AoE | 15ft radius magical darkness |
| Guidance | Bard/Druid | Buff | +1d4 to ability checks |
| Bane | Bard/Cleric | Debuff | -1d6 to attack rolls |
| Resistance | Cleric | Buff | +1d4 to saves |
| Spare the Dying | Cleric | Healing | Stabilize dying creature |
| Mage Hand | Wizard | Utility | Floating hand, interact |
| Silvery Barbs | Bard | Reaction | +1d4 to roll or save |
| Chromatic Orb | Wizard | Ranged | Random element damage |
| Turn Undead | Cleric | Exclusion | Force undead to flee |

### Spell Effects System
- **`webapp/static/spell_effects.js`** — 3,553 lines of client-side spell animation effects
- **`webapp/static/status_effects.js`** — 344 lines of status effect rendering
- Centralized effects package with toggle support
- Visual effects for: Thunderwave, Burning Hands, Bane, Bless, Darkness, Eldritch Blast, Misty Step, Spiritual Weapon, and more

### Character Builder
- **`webapp/templates/character_builder.html`** — Full character creation UI
- **`webapp/static/js/character_builder.js`** — 1,029 lines of builder logic
- **`webapp/static/js/character_builder_images.js`** — Asset management for character tokens
- D&D Beyond importer (`scripts/beyond_importer.py`)
- Magic item support in character builder

---

## 4. Battle System

### Initiative & Turn Management
- DM initiative reorder UI (`tests/test_reorder_initiative.py`)
- `Battle.start()` seeds initiative with `entity.initiative(...)`
- `Battle.while_active()` turn runner with resource resets
- Round/turn event lifecycle: `start_of_turn` → action → `end_of_turn` → `next_turn()`

### Resource Management
- Per-entity resource tracking: `action`, `bonus_action`, `movement`, `spell_slots`
- `Battle.consume()` for resource deduction
- DM resource editing endpoints (`/update_action_resources`, `/update_spell_slots`)
- Persistent resource state in `to_dict`/`from_dict` serialization

### Rest System
- Short rest support (`/rest` endpoint, `Battle.rest()`)
- Long rest support with full resource recovery
- Hit die spending controller
- Arcane spell pick support for wizards

### Combat Log
- Language-aware combat log (gibberish for unknown languages)
- Persistent combat logs across save/load
- Combat log HTML template improvements

---

## 5. Web Application (Flask Blueprints)

### Blueprint Architecture
See **`docs/WEBAPP_BLUEPRINTS.md`** for full architecture.

| Blueprint | Module | Purpose |
|-----------|--------|---------|
| `assets` | `blueprints/assets.py` | Map uploads, asset serving |
| `auth` | `blueprints/auth.py` | Login, character selection |
| `ai` | `blueprints/ai.py` | AI endpoints |
| `navigation` | `blueprints/navigation.py` | Routes, map switching |
| `character` | `blueprints/character.py` | Character builder, journal |
| `battle` | `blueprints/battle.py` | Battle loop, actions, turns |
| `dm` | `blueprints/dm.py` | DM admin, spawning, effects |
| `socketio` | `blueprints/socketio_handlers.py` | Real-time events |

### Helper Modules (`webapp/blueprints/helpers/`)
- `runtime_state.py` — Lazy getters for app globals
- `auth_utils.py` — Authentication utilities
- `action_utils.py` — Action resolution helpers
- `effects.py` / `special_effects.py` — Effect system
- `character_builder_utils.py` — Character creation helpers
- `pvp.py` — PvP mode support
- `campaign_config.py` — Campaign configuration
- `cors_config.py` — CORS settings
- `perf.py` — Performance monitoring
- `conversation_wiring.py` — LLM chat routing

### New Endpoints
- `/character_builder/*` — Character creation flow
- `/rest` — Short/long rest
- `/mcp/*` — MCP tool surface (3 endpoints)
- `/admin/effect` — Visual effect control
- `/tracks`, `/sound`, `/volume`, `/seek` — Audio management
- `/admin/save`, `/admin/load`, `/admin/saves` — Save persistence

---

## 6. VTT Frontend (JavaScript/CSS)

### Core Engine
- **`webapp/static/engine.js`** — Major rewrite (+7,802 lines):
  - Multi-object action bar support
  - Target selection modal
  - AoE targeting (cones, cubes, directional)
  - Spell effect rendering integration
  - Movement path arrows that follow map during pan/zoom
  - Keyboard movement mode with spacebar commit
  - POV switching improvements
  - Out-of-combat pathfinding

### New JavaScript Modules
| File | Lines | Purpose |
|------|-------|---------|
| `webapp/static/js/chat.js` | 773 | Chat UI with LLM integration |
| `webapp/static/js/local_conversation.js` | 852 | Entity conversation system |
| `webapp/static/js/character_builder.js` | 1,029 | Character builder logic |
| `webapp/static/spell_effects.js` | 3,553 | Spell animation effects |
| `webapp/static/status_effects.js` | 344 | Status effect rendering |
| `webapp/static/sfx.js` | 350 | Sound effects manager |
| `webapp/static/perf.js` | 330 | Performance monitoring |
| `webapp/static/path_compute.js` | 348 | Client-side pathfinding |
| `webapp/static/utils_optimized.js` | 552 | Optimized utility functions |

### CSS
- **`webapp/static/styles.css`** — +2,459 lines:
  - Character selection screen
  - Character builder UI
  - Narration popups
  - Toaster messages
  - Target selection modal
  - Combat log improvements
  - Visual effects overlay

### Templates
- **`webapp/templates/character_selection.html`** — 1,475 lines (new)
- **`webapp/templates/character_builder.html`** — 558 lines (new)
- **`webapp/templates/target_selection_modal.html`** — 71 lines (new)
- **`webapp/templates/manage_saves.html`** — 162 lines (new)
- **`webapp/templates/info.html.jinja`** — 1,606 lines (major rewrite)
- **`webapp/templates/index.html`** — 1,399 lines (major rewrite)

---

## 7. AI & Pathfinding

### Pathfinding System
- **`natural20/ai/path_compute.py`** — Complete rewrite (+378 lines):
  - A* pathfinding with terrain cost awareness
  - Chasm avoidance
  - Door navigation (hybrid pathing)
  - Out-of-combat pathfinding
  - Polygon support for complex obstacles
- **`natural20/ai/pathfinding_cost_map.py`** — 291 lines (new):
  - Precomputed cost maps for faster pathfinding
  - Difficult terrain marking

### AI Controller Improvements
- **`natural20/controller.py`** / **`natural20/generic_controller.py`**:
  - Forfeit movement when engaged in combat
  - Coalesce move animations
  - Improved action selection heuristics
  - Help/multiattack rule enforcement
  - Secret door discovery improvements

---

## 8. Entity System

### Core Entity (`natural20/entity.py`)
- +1,215 lines of changes:
  - Mutable resource persistence (`to_dict`/`from_dict`)
  - Stealth and help tracking
  - Status effect management
  - Language support for entities
  - Container concern integration
  - Push mechanics (`Entity.push_from()`)
  - Equipment management

### Entity Concerns
- **`natural20/concern/container.py`** — Container mechanics (opening, closing)
- **`natural20/concern/inventory.py`** — Inventory management
- **`natural20/concern/notable.py`** — Notable entity markers

### Map Objects
- **Chasm** — Pathfinding avoidance, forced-movement falls
- **Pit Traps** — Disarm mechanic
- **Secret Doors** — Improved visibility, discovery mechanics
- **Doors** — Break down support, hybrid navigation, partial visibility

---

## 9. Actions

### New Actions (`natural20/actions/`)
| Action | Module | Description |
|--------|--------|-------------|
| Bardic Inspiration | `bardic_inspiration_action.py` | Grant inspiration die |
| Breath Weapon | `breath_weapon_action.py` | Dragonborn breath attack (395 lines) |
| Divine Smite | `divine_smite_action.py` | Paladin smite |
| Feline Agility | `feline_agility_action.py` | Barbarian movement boost |
| Flurry of Blows | `flurry_of_blows_action.py` | Monk bonus attacks |
| Mage Hand | `mage_hand_action.py` | Floating hand utility (241 lines) |
| Martial Arts Bonus Attack | `martial_arts_bonus_attack_action.py` | Monk attack |
| Patient Defense | `patient_defense_action.py` | Barbarian dodge |
| Rage | `rage_action.py` | Barbarian rage (181 lines) |
| Ready Action | `ready_action.py` | Hold action for trigger |
| Speak Action | `speak_action.py` | Verbal communication |
| Step of the Wind | `step_of_the_wind_action.py` | Monk dash/disengage |
| Turn Undead | `turn_undead_action.py` | Cleric exclusion (230 lines) |
| Wild Shape | `wild_shape_action.py` | Druid transformation (201 lines) |
| Witch Bolt Sustain | `witch_bolt_sustain_action.py` | Concentration sustain |

### Enhanced Actions
- **`attack_action.py`** — +182 lines: Multi-target, attack lines, melee/ranged packages
- **`move_action.py`** — +157 lines: Jump rules (5e), path arrow rendering
- **`hide_action.py`** — +51 lines: Improved stealth mechanics
- **`interact_action.py`** — +42 lines: Object interaction, door handling
- **`lay_on_hands_action.py`** — +332 lines: Paladin healing pool
- **`spell_action.py`** — +82 lines: Animation payloads, AoE targeting

---

## 10. Spells Package

### Spell Infrastructure
- **`natural20/spell/`** — Comprehensive spell class library
- **`natural20/utils/spell_loader.py`** — Dynamic spell class loading
- **`templates/items/spells.yml`** — YAML spell definitions

### Targeting Modes
| Mode | Description | YAML Key |
|------|-------------|----------|
| `select_target` | Single entity target | — |
| `select_empty_space` | Ground target | — |
| `select_cone` | Cone AoE | `range_cone` |
| `select_cube` | Directional cube AoE | `range_cube` |

### Spell Extensions (`natural20/spell/extensions/`)
- Shared targeting primitives
- Damage application helpers
- Save DC calculations
- Resource consumption (`Spell.consume`)

---

## 11. UI/UX Improvements

### Visual Effects
- Centralized effects system with toggle
- Spell-specific animations (Thunderwave, Burning Hands, etc.)
- Status effect overlays
- Weather effects (rain, snow)
- Water effects
- Darkness effect masking
- Toaster messages for notifications

### Audio System
- Sound manager with track listing
- Volume control and seeking
- Audio UI improvements
- Sound effect library (`sfx.js`)

### Navigation & Interaction
- Character selection screen
- Narration popups with area descriptions
- Reset narrations button
- Insight checks with DM-private results
- Target selection modal
- Multi-object action bar
- Keyboard movement mode with hotkey hints
- Spacebar commit for movement
- Minimized chat state

### Asset Optimization
- Image minification script (`scripts/minify.mjs`)
- Asset size optimization (many assets reduced 50-90%)
- WebP format migration for select assets
- Font fixes

---

## 12. Performance Optimizations

### Server-Side
- `/update` endpoint 4x speedup
- Copy-on-write support for map data
- Selective tile-based updates
- Lazy global state accessors (`runtime_state.py`)
- Concurrency utilities for battle loop

### Client-Side
- `utils_optimized.js` — Optimized utility functions
- `perf.js` — Performance monitoring
- Minification pipeline
- Attack line drawing disabled (temporarily)
- Firefox-specific fixes (stuttering, performance)

---

## 13. Testing & CI/CD

### Python Tests
- Migrated to `pytest` (from `unittest`)
- `conftest.py` — Shared test fixtures
- XFAIL markers for known failures
- Webapp parity tests (`tests/webapp/test_*_parity.py`)
- New tests: reorder initiative, push mechanics, object spawner

### JavaScript Tests
- Jest test framework (`jest.setup.js`)
- `webapp/static/engine.test.js` — 1,114 lines
- `webapp/static/path_compute.test.js` — 95 lines

### CI/CD Workflows
- **`.github/workflows/python-tests.yml`** — Python test workflow
- **`.github/workflows/js-tests.yml`** — JavaScript test workflow
- Docker support (`Dockerfile`, `.dockerignore`)

### Baseline Artifacts
- `scripts/generate_baseline_artifacts.py` — Route/endpoint baseline generation
- `plans/artifacts/` — Baseline JSON files for parity checks

---

## 14. Campaign Content & Templates

### New Campaigns
- **`user_levels/wild_sheep_chase/`** — Full campaign with maps, NPCs, items
- **`docs/ADVENTURE_WILD_SHEEP_CHASE.md`** — Adventure documentation

### Templates Added
- Backgrounds: Acolyte, Charlatan, Criminal, Folk Hero, Guild Artisan, Hermit, Outlander, Sailor
- Character classes: All 12 core D&D 5e classes
- Spells: 30+ spells with YAML definitions and Python classes
- Map objects: Chasm, Pit Trap, Secret Doors, Doors with break-down
- Items: Magic items, equipment, consumables

### Asset Tokens
- New character tokens (Betty, Chestnut Latchlifter, etc.)
- Spell tokens (all new spells)
- NPC tokens (Goblin, Hobgoblin, Ogre, Owlbear, etc.)
- Item tokens (weapons, armor, potions, etc.)
- Map tile assets (walls, doors, terrain)

---

## 15. Documentation

### New Documentation
| File | Purpose |
|------|---------|
| `docs/CAMPAIGN_BUILDING.md` | 1,630 lines — Complete campaign creation guide |
| `docs/CONVERSATION_RAG.md` | 484 lines — RAG architecture and usage |
| `docs/WEBAPP_BLUEPRINTS.md` | 118 lines — Blueprint architecture guide |
| `OBJECT_SPAWNER_README.md` | 92 lines — Object spawner usage |
| `AGENTS.md` | 152 lines — AI agent development guide |
| `.github/copilot-instructions.md` | 91 lines — Copilot configuration |

### Updated Documentation
- **`README.md`** — +276 lines: Updated setup, workflows, LLM integration
- **`Dockerfile`** — +62 lines: Production Docker configuration

---

## 16. Bug Fixes

### Critical Fixes
- Fix `NoneType` error in `GenericEventHandler` after save/load
- Fix `select_cube` autobuild for Thunderwave
- Fix controller fallback chain (LLM → Generic → Error)
- Fix sync lock file handling
- Fix auto-concentration spell refresh
- Fix Lay on Hands resource tracking
- Fix secret door visibility and interaction
- Fix secret trapdoor visibility
- Fix grapple movement ordering
- Fix POV switching bugs (multiple)
- Fix Firefox performance issues (stuttering)
- Fix map refresh after effects
- Fix effect re-enable bug
- Fix movement path arrows during pan/zoom
- Fix teleporting animations
- Fix multi-targeting bugs
- Fix languages being set to `None` instead of `[]`
- Fix event manager not triggering
- Fix proximity trigger firing multiple times
- Fix path drawing offset when changing maps
- Fix line doubling issue
- Fix CORSS configuration
- Fix log file creation
- Fix OPENAI LLM interface
- Fix RAG interaction issues
- Fix propagation issues in entity conversation

### UI Fixes
- Fix character selection screen
- Fix notes modal not showing
- Fix command console
- Fix side panel issues
- Fix door passability and opacity
- Fix audio-related bugs (multiple)
- Fix Ollama dropdown box
- Fix thinking model improvements

---

## Migration Notes

### For Developers
1. **Blueprint migration:** Domain routes moved from `webapp/app.py` to blueprints. Update `url_for(...)` calls with blueprint prefixes.
2. **Action imports:** Actions now live under `natural20/actions/`, not `natural20.action`.
3. **Entity registry:** Use `Session.entity_by_uid()` for centralized lookup.
4. **MCP tools:** New surface at `/mcp/*` with token auth (`X-MCP-Token`).
5. **Spell targeting:** New modes `select_cone` and `select_cube` require UI handlers.

### For Campaign Authors
1. **Backgrounds:** New background YAML format in `templates/backgrounds/`.
2. **Spells:** Use `range_cone`/`range_cube` for AoE ranges.
3. **Classes:** New class mixins in `natural20/entity_class/`.
4. **Map objects:** Chasm and pit traps require new YAML keys.

### Environment Variables
| Variable | Purpose | Default |
|----------|---------|---------|
| `LLM_PROVIDER` | LLM backend | `ollama` |
| `OLLAMA_BASE_URL` | Ollama endpoint | `http://localhost:11434` |
| `OLLAMA_MODEL` | Ollama model | — |
| `OPENAI_API_KEY` | OpenAI key | — |
| `ANTHROPIC_API_KEY` | Anthropic key | — |
| `N20_MCP_URL` | MCP bridge URL | — |
| `N20_MCP_DM_TOKEN` | MCP auth token | — |
| `N20_LLM_PROMPT_MAX_CHARS` | Prompt truncation | — |

---

## Statistics Summary

| Category | Files Changed | Lines Added | Lines Removed |
|----------|--------------|-------------|---------------|
| Core Engine (`natural20/`) | ~120 | ~15,000 | ~2,000 |
| Web Application (`webapp/`) | ~200 | ~25,000 | ~3,000 |
| Templates & Assets | ~5,000 | ~1,000,000 | ~200 |
| Tests | ~30 | ~3,000 | ~100 |
| Documentation | ~10 | ~2,500 | ~50 |
| **Total** | **9,746** | **1,053,291** | **5,274** |

---

*Generated during merge of `llm_support` → `master` on 2026-05-29.*
