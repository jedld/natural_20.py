# LLM and voice setup for the web UI

One page to wire up every AI the VTT can use: the **conversation LLMs**
(DM assistant + NPC dialogue), the **System One decision model** (JEV —
battle tactics, player instructions, System One Ready parsing), and
**NPC voice design + TTS**. Deep dives live in
[`AI_CONFIG.md`](AI_CONFIG.md), [`JEV_NPC_BATTLE_AI.md`](JEV_NPC_BATTLE_AI.md),
[`S1_LOCAL.md`](S1_LOCAL.md), [`TTS_PROVIDERS.md`](TTS_PROVIDERS.md) and
[`COSYVOICE_INSTALL.md`](COSYVOICE_INSTALL.md); this guide gives the
recipes and which switches to touch.

## Where settings live

| Layer | What | Notes |
|---|---|---|
| **DM Console → AI Settings** | Providers (dm/npc/battle + custom), combat controllers, NPC conversation/task AI, per-NPC overrides | Saves to `<campaign>/.ai.yaml`; the easiest way in |
| `<campaign>/.ai.yaml` | Same schema as the panel | Highest-precedence config file (see precedence table in `AI_CONFIG.md`) |
| `n20-webapp/webapp/.env` | Env-var fallbacks (`LLM_PROVIDER`, `NPC_*`, `BATTLE_*`, `TYPESAFE_*`, `TTS_*`) | Copy from `webapp/env.example` |
| `game.yml` | Campaign extras (`tts_delivery`, controller defaults) | Campaign-scoped |

Precedence: campaign `.ai.yaml` → legacy `game.yml`/`index.json` → webapp
`.ai.yaml` → environment variables. Both `.ai.yaml` files are git-ignored
(they may hold keys; prefer `api_key_env: NAME` over inline keys).

Supported LLM providers everywhere: `llamacpp` (`llama_cpp` in YAML),
`ollama`, `openai`, `anthropic`, `jev` (decision model only), `mock`.

Three provider slots:

- **dm** — DM assistant/narration, sidebar chat.
- **npc** — NPC conversation (`/talk`, JRPG dialog) and autonomous tasks.
  Falls back to **dm** when unset.
- **battle** — the System One decision model for combat
  (`llm`/`hybrid` controllers, player Instruct, JEV callouts).
  Falls back to **dm** when unset (generative providers still work for
  the battle "llm" controller, but lose the System One features below).

---

## Recommended: the full local stack (Gemma 4 conversation)

For a fully self-hosted game, use a **Gemma 4** build for everything
generative. It is the recommended local conversation LLM for both the DM
assistant and NPC `/talk` (chat-tuned, fast enough on one 16–24 GB GPU,
and the same family used for callout phrasing).

Serving options:

```bash
# llama.cpp server (recommended; env.example defaults to this)
llama-server -m gemma4-26b-a4b-Q4_K_M.gguf --port 8000 --host 127.0.0.1

# or Ollama
ollama pull gemma4
```

`n20-webapp/webapp/.env`:

```bash
# DM assistant / narration
LLM_PROVIDER=llamacpp
LLAMA_CPP_BASE_URL=http://localhost:8000
LLAMA_CPP_MODEL=gemma4

# NPC conversation on its own (slower/cheaper) slot — recommended so
# battle narration stays responsive even while NPCs chat
NPC_LLM_ENABLED=1
NPC_LLM_PROVIDER=llamacpp
NPC_BASE_URL=http://localhost:8001          # second server, or reuse 8000
NPC_MODEL=gemma4                            # a smaller gemma4 tag works too
# NPC_LLM_CONTEXT_SIZE=32768                # or let N20_LLM_CONTEXT_AUTO_DETECT=1 probe it
```

`.ai.yaml` equivalent (what the AI Settings panel writes):

```yaml
version: 1
providers:
  dm:  {provider: llama_cpp, base_url: "http://localhost:8000", model: gemma4, context_window: 32768}
  npc: {provider: llama_cpp, base_url: "http://localhost:8001", model: gemma4}
```

Notes:

- The NPC slot has its own **context budget** (`webapp/llm_context_budget.py`):
  it auto-detects the server's window (llama.cpp `/props`, Ollama
  `/api/show`) and compacts old turns before overflows. Override with
  `NPC_LLM_CONTEXT_SIZE` or `POST /ai/set-context-window`.
- With `NPC_LLM_ENABLED=0`, NPC chat simply uses the dm provider.
- NPC background work (environment ticks, long-rest simulation) can run
  without an LLM at all: `N20_NPC_BACKGROUND_LLM=0`.

## Recommended: System One battle brain (TypeSafe JEV)

JEV is a **decision model**, not a prose generator: it answers
`decide_action(state, options) -> {index, ...}` over the engine's
flattened legal-action menu. It powers:

- battle controllers of kind **`llm`** (JEV picks the whole turn) and
  **`hybrid`** (a generative strategist plans, JEV executes);
- the **Instruct** button (step-by-step fulfilment of a player's
  free-text instruction — see `docs/PLAYER_INSTRUCTIONS.md`);
- **System One Ready** parsing (the Ready/Hold dialog is classified with
  two Choice questions instead of prose generation);
- tactical NPC callouts and decision quality tiers.

None of these exist without a live decision provider — there is no
generative fallback for them.

### Hosted TypeSafe JEV (recommended)

```bash
pip install typesafe-sdk          # optional dep; JevProvider lazy-imports it
```

`n20-webapp/webapp/.env`:

```bash
BATTLE_LLM_PROVIDER=jev
TYPESAFE_API_KEY=***
# optional: TYPESAFE_BASE_URL (default https://api.typesafe.ai),
#           TYPESAFE_MODEL (default jev-latest), JEV_TIMEOUT=8
# per-battle overrides fall back to the shared TYPESAFE_* vars:
# BATTLE_TYPESAFE_API_KEY / BATTLE_TYPESAFE_BASE_URL / BATTLE_TYPESAFE_MODEL

# conversation stays generative (Gemma 4 from the recipe above)
LLM_PROVIDER=llamacpp
NPC_LLM_PROVIDER=llamacpp
```

Then pick which NPCs use it — in the AI Settings panel set the campaign
combat default to **AI** (deterministic heuristics — no LLM),
**LLM** (pure System One), or **LLM + strategist ("hybrid")**, or via
`.ai.yaml`:

```yaml
combat:
  npc_controller: llm          # ai | llm | hybrid | manual | agent:<name>
  llm_provider: battle         # -> providers.battle (the jev profile)
  strategist_provider: dm      # hybrid planner; must be generative (never jev)
  # force_llm: true            # every NPC, ignoring per-NPC settings
providers:
  battle: {provider: jev, api_key_env: TYPESAFE_API_KEY}
```

Named **agents** bundle a controller + provider + standing orders
("Focus archers first...") per NPC — see `AI_CONFIG.md`. Per-NPC
overrides live under `npcs.<uid>.combat`.

Verify: `GET /ai/provider-info` shows a `battle_provider` block; the DM
battle tab shows each combatant's controller.

### Fully-local System One

`s1_local/` trains and serves a small local model with the *same wire
protocol* as the TypeSafe API — point `TYPESAFE_BASE_URL` (or
`BATTLE_TYPESAFE_BASE_URL`) at `scripts/s1_local_api_server.py` and no
other change is needed. See [`S1_LOCAL.md`](S1_LOCAL.md).

---

## NPC voice: TTS providers and voice design

Speech is generated for NPC `/talk` replies and streamed to the browser
(`tts_player.js` + `/tts/*`). Voices are described in **words**, locked
per NPC, and materialized differently per backend.

### Enable TTS

`n20-webapp/webapp/.env`:

```bash
TTS_ENABLED=1
TTS_PROVIDER=cosyvoice          # or qwen3 | qwen3_vllm | openvoice | mock_*
TTS_DEVICE=cuda                 # cpu is the default
# TTS_CUDA_DEVICE=1
# TTS_DELIVERY=async            # async | stream | manual (campaign override: game.yml tts_delivery)
```

Backend installation guides: CosyVoice 3 —
[`COSYVOICE_INSTALL.md`](COSYVOICE_INSTALL.md) (`bash scripts/setup_cosyvoice.sh`);
Qwen3-TTS — local model or the **vLLM-Omni sidecar** (`TTS_PROVIDER=qwen3_vllm`
+ `VLLM_OMNI_TTS_URL`, lowest latency, see `env.example` and
`TTS_VLLM_OMNI_SPIKE.md`); OpenVoice — `bash scripts/install_openvoice.sh`.

### Per-NPC voice block (YAML)

Give each NPC an identity in `<campaign>/npcs/<name>.yml`:

```yaml
gender: female            # top-level gender helps TTS + profile generation
voice:
  prompt: "Cool tavern owner, low alto, unimpressed"
  age: adult              # young | mature | adult | elderly
  style: calm
  accent: eastern european
  language: en
  traits: [low, warm]     # folded into the voice-design prompt
  strategy: auto          # auto | clone | design | preset | instruct
  reference_audio: voices/mara.wav   # optional; enables clone
  locked: true            # keep the same voice across sessions
```

The provider-neutral resolver (`webapp/tts/voice_resolver.py`) picks the
strategy per backend:

| Strategy | Meaning | Backends that support it |
|---|---|---|
| `clone` | timbre lock from a reference WAV | CosyVoice, Qwen3 Base, OpenVoice, qwen3_vllm |
| `design` | voice from a text description (**voice design**) | Qwen3 VoiceDesign, ElevenLabs (bake) |
| `preset` | built-in speaker pool | Qwen3 CustomVoice |
| `instruct` | zero-shot + delivery control | CosyVoice Instruct2 |
| `auto` | resolver picks from the above | all |

### Voice design workflow (recommended for English campaigns)

CosyVoice's stock clips are Chinese; for English voices the proven path
is **bake with Qwen3 VoiceDesign, run with `qwen3_vllm` clone**:

```bash
# 1. (optional) auto-draft voice blocks from each NPC's personality
python scripts/generate_voice_profiles.py user_levels/<campaign>

# 2. bake a stable reference clip per NPC -> user_levels/<campaign>/assets/voice_samples/
python scripts/bake_npc_voices.py user_levels/<campaign>            # Qwen3 VoiceDesign default
python scripts/bake_npc_voices.py user_levels/<campaign> --bake-provider elevenlabs  # cloud alternative
python scripts/bake_single_voice.py ...                             # one NPC

# 3. runtime: clone the baked clips (no design at play time)
TTS_ENABLED=1 TTS_PROVIDER=qwen3_vllm VLLM_OMNI_TTS_URL=http://127.0.0.1:8091
```

- **ElevenLabs voice design bake**: `--bake-provider elevenlabs` +
  `ELEVENLABS_API_KEY` (env knobs: `ELEVENLABS_VOICE_DESIGN_MODEL`,
  `ELEVENLABS_VOICE_SEED`, ...). Runtime TTS stays Qwen3/qwen3_vllm.
- **CosyVoice** is great when you already have an *English* reference
  WAV (`reference_audio:`); it then clones + applies accents via
  Instruct2 (`TTS_PROVIDER=cosyvoice`).
- `scripts/backfill_voice_ref_text.py` repairs baked-clip transcripts so
  clones keep their accent.
- Delivery mode per campaign: `game.yml` `tts_delivery: async|stream|manual`
  (see `TTS_DELIVERY.md`).

---

## Cheat sheet — recommended combos

| Setup | DM/narration | NPC conversation | Battle (System One) | NPC voice |
|---|---|---|---|---|
| **Local-first** | `llamacpp` + gemma4 | `NPC_*` gemma4 (smaller ok) | `BATTLE_LLM_PROVIDER=jev` + `s1_local` server | Qwen3 bake + `qwen3_vllm` |
| **Recommended mix** | `llamacpp`/`ollama` gemma4 | `NPC_*` gemma4 | `BATTLE_LLM_PROVIDER=jev` (TypeSafe, `llm` or `hybrid` controllers) | Qwen3 bake + `qwen3_vllm`, or CosyVoice clone |
| **Cloud** | `openai`/`anthropic` | same or `gpt-4o-mini`-class | `BATTLE_LLM_PROVIDER=jev` | ElevenLabs bake + `qwen3_vllm` |

## Verifying

- `GET /ai/provider-info` — dm / npc / battle provider blocks, resolved
  context limits, `battle_provider` presence.
- DM battle tab — per-combatant controller (AI / LLM / Hybrid / Manual).
- Action bar shows the **Instruct** button only when a decision model
  (System One) is live for the character.
- NPC speaking: `/tts/status`, and `/tts/preferences` for the campaign
  delivery mode.
