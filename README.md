# natural_20.py — D&D 5e Game Engine for AI Research

A Dungeons and Dragons 5th edition game engine that can be used for AI-related research.

This project provides a complete [Gymnasium](https://gymnasium.farama.org/) compatible environment for performing AI research on the Dungeons and Dragons 5th edition RPGs. It includes a full virtual tabletop (VTT) with LLM-powered NPC and DM interactions.

## Table of Contents

- [Project Overview](#project-overview)
- [Repository Structure](#repository-structure)
- [Disclaimer](#disclaimer)
- [Features](#features)
- [Character Classes](#character-classes)
- [Installation](#installation)
- [Quickstart](#quickstart)
- [Samples](#samples)
- [Visual Effects](#visual-effects)
- [Dice Rolls](#dice-rolls)
- [Running the Webapp](#running-the-webapp)
- [LLM Configuration](#llm-configuration)
- [LLM NPC Controller (MCP)](#llm-npc-controller-mcp)
- [Running Tests](#running-tests)
- [Observation and Action Spaces](#observation-and-action-spaces)
- [Environment Initialization Options](#environment-initialization-options)
- [Documentation](#documentation)

---

## Project Overview

natural_20.py is a complete D&D 5e simulation engine with:

- **Core simulation**: Map rendering, line of sight, cover computation, turn-based battle system
- **AI research**: Gymnasium-compatible environments for reinforcement learning and LLM agents
- **Web VTT**: Full-featured virtual tabletop with real-time multiplayer support
- **LLM Integration**: Multi-provider LLM support (OpenAI, Anthropic, Ollama, llama.cpp) for DM conversations, NPC interactions, and combat decisions

## Repository Structure

This repository uses **git submodules** to separate the engine from the VTT and campaign content:

| Path | Remote | Role |
|------|--------|------|
| `natural20/` | — | Core engine (Python package) |
| `templates/` | — | SRD templates (spells, items, classes, maps) |
| `n20-webapp/` | `n20-webapp.git` | Flask VTT, static assets, web tests |
| `user_levels/` | `n20-campaigns.git` | Campaign YAML, maps, assets (audio via Git LFS) |

Clone with submodules:

```bash
git clone --recurse-submodules git@github.com:jedld/natural_20.py.git
cd natural_20.py
git lfs install
git -C user_levels lfs pull
pip install -e .
pip install -e "./n20-webapp[dev]"
cd n20-webapp && npm install && cd ..
```

Existing clone:

```bash
git submodule update --init --recursive
git -C user_levels lfs pull
```

For the full repository layout guide, see [docs/REPOSITORY_SPLIT.md](docs/REPOSITORY_SPLIT.md).

## Disclaimer

This library is an independent research project for AI research. The developers and researchers in this project are in no way affiliated with Wizards of the Coast or Hasbro. D&D is a registered trademark of Wizards of the Coast. This project only includes content from the System Reference Document (SRD). Abilities outside the SRD from official published sources may be included for research purposes but are clearly marked.

## Features

- **D&D 5e Simulation**: Complete map system with line of sight, cover computation, and terrain effects
- **Character Classes**: Fighter, Rogue, Cleric, Mage (Wizard), Paladin, Barbarian, Bard, Druid, Sorcerer, Warlock, Ranger, Monk
- **Race System**: Dragonborn and other races with racial abilities
- **Weapons & Spells**: Full SRD weapon and spell systems with customizable AoE effects
- **Battle System**: Turn-based combat with initiative, legendary actions, opportunity attacks, and rest mechanics
- **LLM-Powered NPCs**: Multi-provider LLM integration for NPC conversations and combat decisions
- **Web VTT**: Full-featured virtual tabletop with real-time multiplayer, character builder, and inventory management
- **Gymnasium Integration**: Ready-to-use reinforcement learning environments
- **Entity Registry**: Centralized UID-based entity lookup and serialization
- **Map Stacking**: Multi-level maps with vertical movement and line of sight
- **Time of Day**: Day/night cycle affecting gameplay
- **TTS Integration**: Text-to-speech for NPC voices with campaign-specific voice profiles

## Character Classes

| Class | Module | Key Features |
|-------|--------|-------------|
| Fighter | `natural20/entity_class/fighter.py` | Action Surge, Second Wind, fighting styles |
| Rogue | `natural20/entity_class/rogue.py` | Sneak Attack, Cunning Action, Evasion |
| Cleric | `natural20/entity_class/cleric.py` | Spellcasting, Turn Undead, domain abilities |
| Wizard | `natural20/entity_class/wizard.py` | Spellbook, Arcane Recovery, ritual casting |
| Paladin | `natural20/entity_class/paladin.py` | Divine Smite, Lay on Hands, aura abilities |
| Barbarian | `natural20/entity_class/barbarian.py` | Rage, Reckless Attack, Unarmored Defense |
| Bard | `natural20/entity_class/bard.py` | Bardic Inspiration, Magical Secrets, spellcasting |
| Druid | `natural20/entity_class/druid.py` | Wild Shape, spellcasting, druidic lore |
| Sorcerer | `natural20/entity_class/sorcerer.py` | Sorcery Points, Metamagic, spellcasting |
| Warlock | `natural20/entity_class/warlock.py` | Eldritch Blast, Pact Magic, Invocations |
| Ranger | `natural20/entity_class/ranger.py` | Favored Enemy, Spellcasting, Natural Explorer |
| Monk | `natural20/entity_class/monk.py` | Martial Arts, Flurry of Blows, Step of the Wind |

## Installation

### Prerequisites

- Python 3.10+
- Node.js 18+ (for webapp JS assets)
- Git LFS (for campaign audio assets)

### Install Dependencies

```bash
# Engine only
pip install -r requirements.txt

# Engine + Webapp (development)
pip install -e .
pip install -e "./n20-webapp[dev]"
cd n20-webapp && npm install && cd ..
```

## Quickstart

Here is a simple example to get started with the gym environment:

```python
from gymnasium import make
from samples.llm_interface import GPT4Interfacer

MAX_EPISODES = 20

# Initialize the environment
env = make("dndenv-v0", root_path="templates", render_mode="ansi")
observation, info = env.reset(seed=42)

# Initialize your language model interfacer
prompt = GPT4Interfacer(debug=True)

# Select an action based on the initial state
action = prompt.select_action_for_state(observation, info)
print(f"Selected action: {action}")

terminal = False
episode = 0
while not terminal and episode < MAX_EPISODES:
    episode += 1
    observation, reward, terminal, truncated, info = env.step(action)
    if not terminal and not truncated:
        print(env.render())
        action = prompt.select_action_for_state(observation, info)
        print(f"Selected action: {action}")

    if terminal or truncated:
        print(f"Reward: {reward}")
        break
```

## Samples

Please see the `samples/` directory for more examples:

| Script | Purpose |
|--------|---------|
| `samples/dnd_dqn.ipynb` | Train an RL agent against rules-based AI |
| `samples/agent_vs_ai.py` | Rules-based AI vs rules-based AI |
| `samples/llm_vs_ai.py` | LLM vs rules-based AI |
| `samples/llm_vs_llm.py` | LLM vs LLM battle |
| `samples/agent_vs_llm.py` | Rules-based AI vs LLM |

DQN training scripts using LLMs:

- `DQN_tests_gpt4o.py` — GPT-4o agent training
- `DQN_tests_llama.py` — Local Llama agent training
- `DQN_tests_mistral.py` — Mistral agent training

For local LLM hosting, [VLLM](https://github.com/vllm-project/vllm) is recommended:

```bash
docker run --runtime=nvidia --gpus all -p 8000:8000 -v ~/.cache/huggingface:/root/.cache/huggingface \
       -it vllm --model NousResearch/Meta-Llama-3-8B-Instruct --dtype=auto --api-key token1234
```

## Visual Effects

The web client supports map-wide effects (fog, rain, snow, water) and per-tile fire emitters defined in your map YAML.

### Point Fire Emitters

Point fires are for candles, bonfires, fireplaces, etc. Define them in your map YAML:

```yaml
point_fires:
  - pos: [x, y]            # required tile coordinates
    intensity: 0.0..1.0    # optional, default 0.7
    color: "#ffb347"       # optional hex color, default warm amber
    size_px: 18..48        # optional pixel size; auto-scales if omitted
    speed: 0.5..2.0        # optional flicker speed, default 1.0
    turbulence: 0.0..1.0   # optional randomness, default 0.6
    offset_px: [dx, dy]    # optional pixel offset from tile center
```

### Flame Shapes

Use `shape` to control flame characteristics:

- `bonfire` — larger, hotter core and glow
- `campfire` or `circular` — round campfire glow
- `candle` — tall, thin flame
- `fireflies` — cluster of flickering fireflies around the point

```yaml
point_fires:
  - pos: [9, 8]
    shape: bonfire
    intensity: 1.0
    color: "#ff7a2b"
  - pos: [2, 3]
    shape: candle
    intensity: 0.3
  - pos: [6, 4]
    shape: fireflies
    intensity: 0.6
    color: "#ffe99a"
    spread_px: 28
    fly_count: 8
```

Notes:
- Point fires are automatically sent to clients on map load/switch
- They render relative to tile centers and respect Fog of War
- They appear under tokens/objects and above the background image

### Performance and Disabling Effects

- Toggle with the "Effects: On/Off" button in the web client
- Preference saved in `localStorage` under key `vtt.effects.enabled`
- When disabled, running effects stop and future effects are ignored

## Environment and Setup

Map building and customization is done through `.yml` files. The `templates/` directory contains a complete game setup including NPCs, races, character sheets, maps, and more.

Campaign-specific configurations go in `user_levels/<campaign>/`. See [docs/CAMPAIGN_BUILDING.md](docs/CAMPAIGN_BUILDING.md).

## Dice Rolls

natural_20.py includes a complete D&D dice roll simulator that can be used standalone.

### DieRoll Class Usage

The `DieRoll` class handles dice rolls with advantage/disadvantage, critical hits, and language-aware output.

```python
from natural20.die_roll import DieRoll

# Single d20
result = DieRoll.roll('1d20').result()

# Multiple dice with modifier
result = DieRoll.roll('2d6+2').result()

# Advantage / Disadvantage
adv_roll = DieRoll.roll('1d20', advantage=True)
dis_roll = DieRoll.roll('1d20', disadvantage=True)

# Critical hit (double dice)
critical_roll = DieRoll.roll('1d6', crit=True)

# Expected value
expected = DieRoll.roll('1d6+2').expected()

# Probability
probability = DieRoll.roll('1d20+5').prob(10)

# Complex roll with advantage
complex_roll = DieRoll.roll('2d20', advantage=True)
for roll_pair in complex_roll.rolls:
    print(f"Roll pair: {roll_pair} -> Chosen: {max(roll_pair)}")

# Check for specific conditions
contains_max = any(roll == complex_roll.die_sides for roll in complex_roll.rolls)
```

## Running the Webapp

### Development Mode

The simplest way to run the webapp is from the repository root:

```bash
# Defaults to wild_sheep_chase campaign
./start_web.sh

# Specify a campaign
./start_web.sh death_house
./start_web.sh wild_sheep_chase
./start_web.sh pvp

# Or use the submodule launcher directly
./n20-webapp/start_web.sh wild_sheep_chase
```

The dev server runs on port 5001 by default (`http://localhost:5001`).

### Production Mode (Gunicorn)

```bash
N20_USE_GUNICORN=1 ./start_web.sh user_levels/death_house
```

Or standalone:

```bash
N20_USE_GUNICORN=1 ./n20-webapp/start_web.sh ../user_levels/death_house
```

### Remote Access via ngrok (in tmux)

1. Create tmux session:
   ```bash
   tmux new-session -d -s n20
   ```

2. Start the webapp in the session:
   ```bash
   tmux send-keys -t n20 './start_web.sh death_house' Enter
   ```

3. Split and start ngrok:
   ```bash
   tmux split-window -t n20 -v
   tmux send-keys -t n20.1 'ngrok http 5001' Enter
   ```

4. Get the ngrok URL:
   ```bash
   tmux capture-pane -t n20.1 -p
   ```

5. Attach to view:
   ```bash
   tmux attach -t n20
   ```

### Docker

```bash
cd n20-webapp
docker build -t n20-webapp .
docker run --env-file webapp/.env \
  -e TEMPLATE_DIR=/campaigns/wild_sheep_chase \
  -v /path/to/user_levels:/campaigns:ro \
  -p 5001:5001 n20-webapp
```

### Login Credentials

Login details are defined in each campaign's `index.json`. For the bundled templates, the DM login is `dm/admin`. Character logins are listed in `user_levels/<campaign>/index.json`.

### Webapp Architecture

The webapp uses a Flask Blueprint architecture for modular route organization. See [docs/WEBAPP_BLUEPRINTS.md](docs/WEBAPP_BLUEPRINTS.md) for the full blueprint map and conventions.

## LLM Configuration

The webapp supports multiple LLM providers for the DM chatbot and NPC conversations.

### Supported Providers

| Provider | Models | Requirements |
|----------|--------|-------------|
| **OpenAI** | GPT-4o, GPT-4, GPT-3.5 | API key |
| **Anthropic** | Claude 3/3.5 Sonnet | API key |
| **llama.cpp** | Any GGUF model | Local server (OpenAI-compatible) |
| **Ollama** | Gemma, Llama, Mistral, etc. | Local Ollama instance |
| **Mock** | N/A | None (testing only) |

### Quick Configuration

1. Copy the example environment file:
   ```bash
   cp n20-webapp/webapp/env.example n20-webapp/webapp/.env
   ```

2. Edit `.env` with your preferred configuration:
   ```bash
   # OpenAI
   LLM_PROVIDER=openai
   OPENAI_API_KEY=your_api_key_here
   OPENAI_MODEL=gpt-4o-mini

   # llama.cpp (local)
   LLM_PROVIDER=llama_cpp
   LLAMA_CPP_BASE_URL=http://localhost:8011
   LLAMA_CPP_API_KEY=llama-cpp

   # Ollama (local, default)
   LLM_PROVIDER=ollama
   OLLAMA_BASE_URL=http://localhost:11434
   OLLAMA_MODEL=gemma3:27b
   ```

3. Start the application:
   ```bash
   ./start_web.sh wild_sheep_chase
   ```

### Environment Variables

#### CORS Configuration

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `CORS_ORIGINS` | Comma-separated allowed origins | Development-based | No |

**CORS Defaults:**
- **Development**: `http://localhost:5000`, `http://127.0.0.1:5000`, `http://localhost:5001`, `http://127.0.0.1:5001`
- **Production**: AWS ALB domain + wildcard (`*`)

#### LLM Configuration

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `LLM_PROVIDER` | Provider (`ollama`, `openai`, `anthropic`, `llama_cpp`, `mock`) | `ollama` | No |
| `OPENAI_API_KEY` | OpenAI API key | — | Yes (for OpenAI) |
| `OPENAI_MODEL` | OpenAI model name | `gpt-4o-mini` | No |
| `OPENAI_BASE_URL` | Custom OpenAI endpoint | `https://api.openai.com/v1` | No |
| `ANTHROPIC_API_KEY` | Anthropic API key | — | Yes (for Anthropic) |
| `ANTHROPIC_MODEL` | Anthropic model name | `claude-3-5-sonnet-20241022` | No |
| `LLAMA_CPP_BASE_URL` | llama.cpp server URL | `http://localhost:8011` | No |
| `LLAMA_CPP_MODEL` | llama.cpp model name | first available | No |
| `LLAMA_CPP_API_KEY` | llama.cpp API key | `llama-cpp` | No |
| `OLLAMA_BASE_URL` | Ollama server URL | `http://localhost:11434` | No |
| `OLLAMA_MODEL` | Ollama model name | `gemma3:27b` | No |

#### NPC LLM (Separate Provider for Conversations)

Optional: run a dedicated fast/cheap model for NPC conversations while keeping the DM on a larger model.

| Variable | Description | Default |
|----------|-------------|---------|
| `NPC_LLM_ENABLED` | Enable dedicated NPC LLM | `1` (enabled) |
| `NPC_LLM_PROVIDER` | Provider (`ollama`, `openai`, `anthropic`, `llama_cpp`, `mock`) | Inherits DM provider |
| `NPC_MODEL` / `NPC_OLLAMA_MODEL` | NPC model name | Inherits DM model |
| `NPC_BASE_URL` / `NPC_OLLAMA_BASE_URL` | NPC server URL | Inherits DM URL |
| `NPC_API_KEY` / `NPC_OLLAMA_API_KEY` | NPC API key | Inherits DM key |
| `N20_NPC_BACKGROUND_LLM` | Skip NPC LLM for background ticks | `1` (enabled) |

**NPC Context Budget** (auto-compacts conversation history):
- `N20_NPC_CONTEXT_SIZE` / `N20_LLM_CONTEXT_SIZE` — context window size
- `N20_LLM_CONTEXT_AUTO_DETECT=1` — auto-detect from provider API
- `N20_LLM_CONTEXT_SAFETY_MARGIN` — reserved tokens (default: 512)
- `N20_LLM_CONTEXT_COMPACT_PCT` — compact threshold (default: 85%)
- `N20_NPC_CONTEXT_KEEP_RECENT_TURNS` — keep recent turns (default: 6)

DM override at runtime: `POST /ai/set-context-window` with `{"context_window": 32768, "target": "npc"}`.

#### MCP Bridge

| Variable | Description | Default |
|----------|-------------|---------|
| `N20_MCP_URL` | External MCP server URL for action selection | — |
| `N20_MCP_DM_TOKEN` | Shared secret for unauthenticated MCP tool access | — |
| `N20_LLM_PROMPT_MAX_CHARS` | Max prompt length before truncation | — |

## LLM NPC Controller (MCP)

Drive NPCs with a language model via the built-in LLM controller. Works in both auto battles and manual initiative mode.

### Controller Selection

In the initiative window, each entity has a Controller dropdown: **Manual**, **AI** (heuristic), and **LLM**.

To set LLM as the default for NPCs in a level config (`user_levels/<campaign>/index.json`):

```json
{
  "npc_default_controller": "llm"
}
```

### Force LLM for All Combat NPCs

```bash
export NPC_LLM_COMBAT_ENABLED=true
./start_web.sh death_house
```

This override takes precedence over `npc_default_controller` from the campaign config.

### MCP Action Bridge

The LLM controller supports an optional MCP-style HTTP tool for action selection:

```bash
export N20_MCP_URL="http://localhost:3000/mcp/choose_action"
```

Request:
```json
{ "prompt": "...state and actions...", "n_actions": 7 }
```

Response:
```json
{ "index": 2 }
```

### MCP Tool Surface

When `N20_MCP_DM_TOKEN` is set, callers can hit the in-process MCP tool surface at `/mcp/*` with header `X-MCP-Token: <value>`.

**Tool Catalogue:**

| Category | Tools |
|----------|-------|
| `tools_world` | `world.list_maps`, `world.get_map`, `world.list_entities`, `world.get_entity`, `world.get_battle`, `world.list_npc_types` |
| `tools_dm` | `dm.set_hp`, `dm.heal`, `dm.damage`, `dm.add_status`, `dm.remove_status`, `dm.set_property`, `dm.add_item`, `dm.remove_item`, `dm.equipment`, `dm.set_resource`, `dm.award_xp`, `dm.grant_level_up`, `dm.spawn_npc`, `dm.spawn_object`, `dm.remove_entity`, `dm.teleport`, `dm.battle_admin`, `dm.set_controller`, `dm.rest`, `dm.save_load`, `dm.effect`, `dm.sound`, `dm.advance_time`, `dm.map_landmark`, `dm.user_admin` |
| `tools_actions` | `actions.list_available`, `actions.execute`, `actions.move`, `actions.end_turn`, `actions.start_battle`, `actions.end_battle` |

For the complete tool catalogue, see [AGENTS.md](AGENTS.md).

## Running Tests

### Python Tests

```bash
# Run all tests
pytest

# Run specific test
pytest tests/test_gym.py::TestGym::test_reset

# Parallel runs
pytest -n auto
```

### JavaScript Tests (webapp/engine.js)

```bash
cd n20-webapp
npm install --no-audit --no-fund
npx jest --runInBand --colors
npm run test:coverage
```

### Webapp Endpoint Parity Tests

After any webapp route changes, run:

```bash
python scripts/generate_baseline_artifacts.py
pytest tests/webapp/test_*_parity.py
```

### CI

GitHub Actions runs both JS and Python tests on pushes and PRs. JS tests include coverage reporting.

## Observation and Action Spaces

### Observation Space

The observation is a dictionary with:

| Key | Shape | Description |
|-----|-------|-------------|
| `map` | `(viewport_size, viewport_size, 5)` | Game map array |
| `turn_info` | `(3,)` | Turn information |
| `conditions` | `(8,)` | Player conditions |
| `player_ac` | `(1,)` | Player armor class |
| `player_equipped` | `(5,)` | Equipped items |
| `enemy_ac` | `(1,)` | Enemy armor class |
| `health_pct` | `(1,)` | Player health percentage |
| `health_enemy` | `(1,)` | Enemy health percentage |
| `enemy_reactions` | `(1,)` | Enemy reactions |
| `enemy_conditions` | `(8,)` | Enemy conditions |
| `player_type` | `(1,)` | Player type |
| `enemy_type` | `(1,)` | Enemy type |
| `ability_info` | `(8,)` | Player abilities |
| `movement` | `(1,)` | Movement remaining |
| `spell_slots` | `(9,)` | Spell slots by level |
| `is_reaction` | `(1,)` | Whether current action is a reaction |

### Action Space

Tuple containing:

| Element | Shape | Description |
|---------|-------|-------------|
| `action_type` | `(1,)` | Action type identifier |
| `target_position` | `(2,)` | Target coordinates |
| `movement_vector` | `(2,)` | Movement direction |
| `spell_index` | `int` | Spell to cast |
| `item_index` | `int` | Item to use |

## Environment Initialization Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `view_port_size` | int | 12 | Viewport size (12x12) |
| `max_rounds` | int | — | Max rounds before auto-end |
| `render_mode` | str | — | Render mode (`ansi`, etc.) |
| `root_path` | str | — | Campaign root path |
| `map_file` | str | — | Specific map file |
| `profiles` | list | — | Hero profiles |
| `enemies` | list | — | Enemy profiles |
| `hero_names` | list/lambda | — | Hero name generator |
| `enemy_names` | list | — | Enemy names |
| `show_logs` | bool | — | Show battle logs |
| `custom_controller` | obj | — | Custom AI controller |
| `custom_agent` | lambda | — | Custom agent function |
| `custom_initializer` | obj | — | Custom initializer |
| `control_groups` | list | — | Agent control groups |
| `damage_based_reward` | bool | — | Damage-based reward function |
| `event_manager` | obj | — | Custom event manager |
| `custom_session` | obj | — | Custom session object |
| `reactions_callback` | func | — | Reaction callback |

## Documentation

| Document | Description |
|----------|-------------|
| [AGENTS.md](AGENTS.md) | AI agent quick reference and patterns |
| [docs/CAMPAIGN_BUILDING.md](docs/CAMPAIGN_BUILDING.md) | Campaign creation guide |
| [docs/CAMPAIGN_ASSET_GENERATOR.md](docs/CAMPAIGN_ASSET_GENERATOR.md) | AI asset generation |
| [docs/CONVERSATION_RAG.md](docs/CONVERSATION_RAG.md) | NPC RAG conversation system |
| [docs/DUNGEON_GENERATOR.md](docs/DUNGEON_GENERATOR.md) | Dungeon generation |
| [docs/MAP_ANNOTATIONS.md](docs/MAP_ANNOTATIONS.md) | Map landmarks and annotations |
| [docs/MAP_IMAGE_GENERATOR.md](docs/MAP_IMAGE_GENERATOR.md) | Map image generation |
| [docs/MERCHANT_TRADING.md](docs/MERCHANT_TRADING.md) | Merchant trading system |
| [docs/PICKPOCKET.md](docs/PICKPOCKET.md) | Pickpocket mechanics |
| [docs/REPOSITORY_SPLIT.md](docs/REPOSITORY_SPLIT.md) | Repository structure |
| [docs/WEBAPP_BLUEPRINTS.md](docs/WEBAPP_BLUEPRINTS.md) | Webapp architecture |
| [docs/CHANGELOG_llm_support_merge.md](docs/CHANGELOG_llm_support_merge.md) | Major merge changelog |
| [docs/TTS_PROVIDERS.md](docs/TTS_PROVIDERS.md) | Text-to-speech providers |
