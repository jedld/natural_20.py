# Natural20 Documentation Index

This directory contains the core documentation for the Natural20 D&D simulation engine and VTT.

## Quick Links

| Document | Purpose |
|----------|---------|
| [AGENTS.md](../AGENTS.md) | AI agent orientation, MCP catalogue, battle/spell conventions (primary reference) |
| [DM_NOTES.md](DM_NOTES.md) | Play-time DM-only map pins (invisible to PCs and NPCs) |
| [NOTEBOOK.md](NOTEBOOK.md) | Player/campaign notes, journals, files (SQLite; not tied to a PC) |
| [.cursor/skills/n20-add-spell](../.cursor/skills/n20-add-spell/SKILL.md) | End-to-end checklist for adding a spell (engine + VTT visuals) |
| [.cursor/skills/n20-import-battlemap](../.cursor/skills/n20-import-battlemap/SKILL.md) | **Prefer** when battlemap art already exists: image → map YAML (tile-wise VLM; multi-floor pages split automatically) |
| [.cursor/skills/n20-add-sidekick](../.cursor/skills/n20-add-sidekick/SKILL.md) | Campaign sidekick NPCs, join tags, Tasha pack opt-in |
| [CHANGELOG](CHANGELOG_llm_support_merge.md) | Merge changelog from `llm_support` → `master` (210 commits) |
| [WEBAPP_BLUEPRINTS.md](WEBAPP_BLUEPRINTS.md) | Flask blueprint architecture, helper modules, parity workflow |
| [VTT_3D.md](VTT_3D.md) | Three.js sibling VTT at `/3d` (JSON `/map_state`, extruded tabletop, campaign `vtt3d.yml`) |
| [CAMPAIGN_BUILDING.md](CAMPAIGN_BUILDING.md) | Complete campaign creation guide (maps, NPCs, characters, items) |
| [BATTLEMAP_IMPORTER.md](BATTLEMAP_IMPORTER.md) | Battlemap image → map YAML (tile-wise VLM) |
| [CONVERSATION_RAG.md](CONVERSATION_RAG.md) | NPC conversation RAG pipeline architecture |
| [ADVENTURE_WILD_SHEEP_CHASE.md](ADVENTURE_WILD_SHEEP_CHASE.md) | Wild Sheep Chase adventure documentation |

## Architecture Documents

### Web Application
- **WEBAPP_BLUEPRINTS.md** — Blueprint map, helper modules, parity harness, wiring checklist
- **VTT_3D.md** — Three.js VTT at `/3d`, `GET /map_state`, camera/controls
- **MCP.md** — Streamable HTTP MCP for Cursor/Claude (DM tools on a running instance)
- **DM_NOTES.md** — Play-time DM-only map pins (not landmarks)
- **NOTEBOOK.md** — Player/campaign notes and journals (SQLite, folders, sharing)
- **CONVERSATION_RAG.md** — Entity RAG handler, NPC conversation flow, context management

### Game Engine
- **AGENTS.md** — Core patterns, battle loop, LLM controller, spell/class extension points
- **CAMPAIGN_BUILDING.md** — YAML-driven resource creation, map editing, entity design
- **BATTLEMAP_IMPORTER.md** — Tile-wise VLM import from battlemap images

## Developer Workflows

### Running the Webapp
```bash
# Development
cd webapp && python -m flask run

# Production with gunicorn + ngrok (see AGENTS.md for full tmux setup)
cd webapp && TEMPLATE_DIR=../user_levels/<level> gunicorn --worker-class eventlet --workers 1 --bind 0.0.0.0:5001 --timeout 120 app:app
```

### Testing
```bash
# Python tests
pytest
pytest -n auto  # parallel

# JavaScript tests
npm install && npx jest

# Parity tests (after route moves)
python scripts/generate_baseline_artifacts.py
pytest tests/webapp/test_*_parity.py
```

### MCP Tool Surface

External hosts (Cursor, Claude Code) use Streamable HTTP JSON-RPC:

```
POST /mcp
Authorization: Bearer <N20_MCP_DM_TOKEN>
```

Legacy REST (in-app LLM) is unchanged: `GET /mcp/manifest`, `GET /mcp/tools/list`, `POST /mcp/tools/call`. Full setup: [MCP.md](MCP.md).

## Key Directories

| Directory | Contents |
|-----------|----------|
| `natural20/` | Core engine (session, battle, entity, controllers, actions) |
| `natural20/actions/` | Action implementations (attack, spell, movement, class abilities) |
| `natural20/entity_class/` | Character class mixins (Fighter, Rogue, Wizard, etc.) |
| `natural20/spell/` | Spell class implementations |
| `webapp/` | Flask web application, blueprints, templates, static assets |
| `webapp/mcp/` | MCP tool surface implementation |
| `templates/` | YAML-driven resources (maps, characters, NPCs, spells, items) |
| `expansion_packs/` | Opt-in third-party packs (e.g. Tasha’s sidekicks); not SRD |
| `user_levels/` | Campaign folders (Wild Sheep Chase, PVP, etc.) |
| `tests/` | Test suite (pytest + Jest) |
| `scripts/` | Utility scripts (baseline generation, importers, asset tools) |

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `LLM_PROVIDER` | LLM backend (ollama/openai/anthropic/mock) | `ollama` |
| `OLLAMA_BASE_URL` | Ollama endpoint URL | `http://localhost:11434` |
| `OLLAMA_MODEL` | Ollama model name | — |
| `OPENAI_API_KEY` | OpenAI API key | — |
| `ANTHROPIC_API_KEY` | Anthropic API key | — |
| `N20_MCP_URL` | External MCP bridge URL | — |
| `N20_MCP_DM_TOKEN` | MCP auth shared secret | — |
| `N20_LLM_PROMPT_MAX_CHARS` | Prompt truncation limit | — |
| `TEMPLATE_DIR` | Campaign template directory | `../templates` |
| `CORS_ORIGINS` | Allowed CORS origins | — |
