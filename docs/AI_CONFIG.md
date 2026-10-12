# AI configuration (`.ai.yaml`) and the DM AI Settings panel

The DM can configure every AI subsystem from **DM Console → AI Settings** (DM only). The
panel sets up:

- **Model providers**: endpoints, models, credentials, context window, timeouts.
- **Combat**: which NPCs use deterministic AI, an LLM, or manual control.
- **NPC conversation and autonomous tasks**: goals, movement, environment ticks and long-rest simulation.
- **Sidekick defaults** and **per-NPC overrides**.

Implementation: `n20-webapp/webapp/ai_config.py`, routes in `webapp/blueprints/ai.py`,
UI in `webapp/static/ai_config.js` / `ai_config.css`, MCP tool `dm.ai_config`.

## Layers and precedence

| Priority | Source | Notes |
|---|---|---|
| 1 | `<campaign>/.ai.yaml` | Default save target of the panel |
| 2 | Legacy campaign settings | `game.yml` blocks (`npc_background_llm`, `npc_environment_ticks`, …) and `index.json` `npc_default_controller` |
| 3 | `n20-webapp/webapp/.ai.yaml` | Installation-wide defaults; path override `N20_AI_CONFIG_PATH` |
| 4 | Environment variables | `LLM_PROVIDER`, `NPC_*`, `BATTLE_*`, `TYPESAFE_*`, `N20_NPC_*` (see `AGENTS.md`) |

Provider slots (`dm`, `npc`, `battle`) fall back to the matching env setup
(`configure_*_from_environment` in `webapp/blueprints/helpers/llm_init.py`). They also fall back
when the profile is missing from both `.ai.yaml` files, or when it fails to initialize.

The env kill switch `N20_NPC_LOOPS=0` still beats `game.yml`. Only an explicit
`tasks.autonomous_loops` in an `.ai.yaml` overrides it.

Both files are git-ignored because they may contain API keys. Files are written with `0600`
permissions. To keep secrets out of YAML entirely, use `api_key_env: SOME_ENV_VAR`. The API
returns keys masked as `********`, and saving a masked value keeps the stored key.

## Schema

```yaml
version: 1
providers:                 # named profiles; dm / npc / battle map to the LLMHandler slots
  dm:     {provider: llama_cpp, base_url: http://host:8011, model: qwen3, context_window: 32768}
  npc:    {provider: ollama, base_url: http://host:11434, model: gemma3:12b, timeout: 120}
  battle: {provider: jev, base_url: http://host:8901, api_key_env: TYPESAFE_API_KEY}
  fast_chat: {provider: openai, model: gpt-4o-mini, api_key_env: OPENAI_API_KEY}   # custom
  # any profile: enabled: false  -> slot disabled (npc falls back to dm, battle to dm)
combat:
  npc_controller: ai        # ai = deterministic GenericController | llm | manual (DM)
  llm_provider: battle      # profile for llm combat controllers (default: battle -> dm)
  force_llm: false          # NPC_LLM_COMBAT_ENABLED equivalent; beats per-NPC settings
conversation:
  enabled: true             # false = no dedicated NPC provider (NPC_LLM_ENABLED=0)
  provider: npc             # profile for NPC dialogue
tasks:
  provider: npc             # profile for goals / movement / env ticks / long rest (default: conversation)
  autonomous_loops: true    # N20_NPC_LOOPS
  background_llm: true      # N20_NPC_BACKGROUND_LLM
  environment_ticks: true   # N20_NPC_ENV_TICKS
  goal_turn_seconds: 6      # NPC_GOAL_TURN_SECONDS
sidekicks:                  # applied to in-party sidekicks before the general defaults
  combat: {controller: manual, provider: battle}
  conversation: {provider: fast_chat}
  tasks: {enabled: true, provider: npc}
npcs:                       # keyed by entity_uid (individual) or NPC type
  goblin:      {combat: {controller: ai}}
  npc_boss_1:  {combat: {controller: llm, provider: battle}, conversation: {provider: fast_chat},
                tasks: {enabled: false}}
```

Provider names: `llama_cpp`, `ollama`, `openai`, `anthropic`, `jev`, `mock`. `llamacpp` and
`llama.cpp` are normalized to `llama_cpp`.

## Per-entity resolution

`AiConfig.entity_setting(entity, section, key)` checks these sources in order:

1. `npcs[<entity_uid>]`
2. `npcs[<npc_type>]`
3. `sidekicks` (in-party sidekicks only)
4. The general default: `combat.npc_controller`, `combat.llm_provider`, `conversation.provider` or `tasks.provider`

Where each setting is used:

- **Combat controller.** `GameControllerRegistry.effective_npc_combat_controller(entity)` and
  `build_combat_controller_for_entity` resolve it. Battles started automatically, the battle-setup
  dialog's default controller (`add.html`), and the controller selector all use this.
- **Sidekick ownership.** A sidekick with a player owner stays under that player unless an explicit
  NPC or sidekick controller is configured.
- **Manual control.** Manual control with no assigned user goes to the DM.
- **LLM combat provider.** `ai_config.combat_llm_provider_for(handler, entity)` resolves it, with
  fallbacks: per-NPC profile, then `combat.llm_provider`, then the `battle` slot, then the `dm` slot.
  It is used by `/battle`, `/update_controller`, MCP `dm.set_controller` and auto-battles.
- **Conversation and task providers.** `LLMConversationController.generate_response` tags each call
  with `entity_uid` and `ai_role`. A conversation id of the form `<uid>:goal|movement|environment|long_rest*`
  is a task. `LLMHandler.npc_provider_resolver`, installed by `configure_ai`, swaps in the profile's
  provider. Task calls fall back to the conversation profile.
- **`tasks.enabled: false`.** The NPC is skipped by environment ticks and the long-rest simulation,
  and new short-term goals are refused.

## HTTP / MCP

| Route | Purpose |
|---|---|
| `GET /ai/config` | Masked layers, effective config, env fallbacks, live provider status, NPC list with resolved values |
| `POST /ai/config` | `{scope: campaign\|webapp, config}`: replaces that layer and re-initializes only the changed provider slots |
| `POST /ai/config/npc` | `{scope, key, settings}`: upserts one per-NPC override (omit `settings` to clear) |
| `POST /ai/config/test` | `{name?, profile}`: initializes a provider without saving (masked key → saved key) |
| `POST /ai/config/reload` | Re-reads both files and re-applies every slot |

MCP: `dm.ai_config` with `op=get|save|set_npc|reload` and `scope=campaign|webapp`.

The older Command Console "Default NPC controller" select (`/update_npc_default_controller`) still
changes the runtime default for the current session only. Use AI Settings to persist it.
