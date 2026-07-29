# TTS providers (2026)

natural_20.py supports multiple self-hosted TTS backends via `TTS_PROVIDER` in `webapp/.env`.

## Voice profile framework

NPC voices are described with a **provider-neutral `VoiceProfile`** (`webapp/tts/voice_profile.py`) built from entity YAML. A **resolver** (`webapp/tts/voice_resolver.py`) picks the best materialization strategy for the active backend:

| Strategy | When used | Best backends |
|----------|-----------|---------------|
| `clone` | `reference_audio` WAV present | CosyVoice 3, Qwen3 Base, OpenVoice |
| `design` | Rich text timbre, no reference clip | **Qwen3 VoiceDesign** |
| `preset` | Stable speaker from gender pool | Qwen3 CustomVoice |
| `instruct` | Text prompt + delivery control | CosyVoice Instruct2 |
| `auto` | Default — resolver picks from above | All |

### NPC YAML fields

```yaml
voice:
  prompt: "Gravelly dockside barkeeper, dry humor"
  gender: male
  age: mature
  traits: [gravelly, low, warm]
  accent: irish          # CosyVoice instruct
  language: en
  strategy: auto         # auto|clone|design|preset|instruct
  provider: qwen3        # optional per-NPC backend override
  reference_audio: voices/mara.wav
```

`traits` and demographics are merged into `VoiceProfile.design_prompt()` — the string used by **VoiceDesign** and instruct backends.

### Does VoiceDesign help personalization?

**Yes, when you want unique timbres from text rather than 9 preset speakers.**

| Approach | Personalization | Consistency | GPU / setup |
|----------|-----------------|-------------|-------------|
| Qwen3 **CustomVoice** (`preset`) | Low — gender → one of 9 speakers | High | `CustomVoice` model |
| Qwen3 **VoiceDesign** (`design`) | **High** — full prompt + traits → timbre | Good* | `VoiceDesign` model |
| CosyVoice **instruct** | Medium — delivery + accent from text | Good with same ref | CosyVoice 3 |
| **Clone** from WAV | Highest fidelity to sample | Highest | Reference audio required |

\*VoiceDesign applies the locked `design_prompt` on every utterance; delivery emotion still varies per line via instruct. For maximum lock-in, use `strategy: clone` with a reference WAV (record or generate a calibration line once).

**Automatic voice baking (recommended for Qwen3 VoiceDesign):** On first speech, the server can generate a neutral calibration clip per NPC and save it under `assets/voice_samples/<npc_uid>.wav`, then switch to **Qwen3 Base clone** mode for all later lines (`N20_TTS_BAKE_VOICES=1`, default). Pre-bake an entire campaign:

```bash
cd webapp && python ../scripts/bake_npc_voices.py ../user_levels/wild_sheep_chase
```

Optional env: `QWEN3_TTS_CLONE_MODEL=Qwen/Qwen3-TTS-12Hz-1.7B-Base`, `N20_TTS_BAKE_SAMPLE_TEXT="..."`.

**Recommended setups:**

- **Campaign cast with distinct silhouettes, no reference clips:** `TTS_PROVIDER=qwen3`, `QWEN3_TTS_MODEL=...-VoiceDesign`, `voice.strategy: design` (or `auto`).
- **Maximum clone fidelity:** `TTS_PROVIDER=cosyvoice`, `reference_audio` per NPC, `strategy: clone`.
- **Fast + consistent presets:** `QWEN3_TTS_MODEL=...-CustomVoice`, `strategy: preset` (current default).

Env overrides: `N20_TTS_VOICE_STRATEGY`, `N20_TTS_PREFER_VOICE_DESIGN=1` (Qwen3 auto → design when model supports it).

### Campaign voice profile generator

Generate voice YAML assets from NPC backstories and map overrides:

```bash
# Heuristic profiles (default) — keyword extraction from backstory/description
python scripts/generate_voice_profiles.py --campaign user_levels/my_campaign

# LLM-guided profiles (recommended for distinct NPC casts)
python scripts/generate_voice_profiles.py --campaign templates --maps-only --mode llm --force

# Same as --mode llm
python scripts/generate_voice_profiles.py --campaign templates --maps-only --llm --force

# Strict LLM only — skip NPCs if the model returns bad JSON
python scripts/generate_voice_profiles.py --campaign templates --maps-only --mode llm --no-fallback

# Use DM LLM env vars instead of NPC_LLM_*
python scripts/generate_voice_profiles.py --campaign templates --mode llm --llm-provider dm
```

**Mode resolution order:** `--mode` / `--llm` → `N20_VOICE_PROFILE_MODE` → `game.yml` `tts.voice_profile_mode` → `heuristic`.

In LLM mode the generator uses `webapp/prompts/voice_profile_generation_system.txt` and prefers **NPC LLM** env vars (`NPC_LLM_PROVIDER`, `NPC_MODEL`, …) unless `N20_VOICE_PROFILE_LLM=dm`.

**Output layout:**

```
<campaign>/assets/voice_profiles/
  index.json          # entity_uid / type → file mapping
  gabba.yml           # per-NPC voice block + meta
  type_goblin.yml     # optional type-level fallback
```

Runtime TTS loads these via `build_voice_profile_from_entity()` (merged over inline NPC `voice:` YAML).

| Provider | Env value | Best for |
|----------|-----------|----------|
| CosyVoice 3 | `cosyvoice` | Zero-shot clone + instruct control (current default) |
| Qwen3-TTS | `qwen3` | Low-latency streaming, preset speakers, voice design |
| OpenVoice | `openvoice` | Lightweight clone fallback |
| Mocks | `mock_cosyvoice`, `mock_qwen3` | CI/dev without GPU weights |

## Qwen3-TTS

**Repo:** https://github.com/QwenLM/Qwen3-TTS  
**License:** Apache 2.0

Qwen3-TTS (Jan 2026) is Alibaba’s latest open TTS family. Highlights:

- **~97 ms first-packet latency** with dual-track streaming (12 Hz tokenizer)
- **10 languages** + dialect profiles
- **Three model types:**
  - `CustomVoice` — 9 premium speakers + natural-language style instruct
  - `VoiceDesign` — describe a voice in text, synthesize a reference timbre
  - `Base` — 3-second voice clone from reference audio (+ optional transcript)
- **Apache 2.0** — commercial-friendly

### Setup

```bash
pip install qwen-tts
```

**You do not need `flash-attn`.** Qwen3-TTS runs fine with PyTorch’s default attention. Building `flash-attn` from source often uses 16–32+ GB RAM during compile and is optional speed tuning only.

To enable flash attention **only if you already have a pre-built wheel** (do not compile on a memory-constrained machine):

```bash
# optional — only when flash-attn is already installed
QWEN3_USE_FLASH_ATTN=1
```

```bash
# webapp/.env
TTS_PROVIDER=qwen3
TTS_DEVICE=cuda   # or gpu — both use the GPU
QWEN3_TTS_MODEL=Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice
N20_TTS_WARMUP=1  # one short synthesis at startup (avoids a 60–90s first NPC line)
```

On startup you should see a log like:

```text
[TTS] Qwen3-TTS initialized (..., mode=voice_design, device=cuda:0, NVIDIA GeForce RTX 3090)
[TTS] Qwen3 GPU warmup complete (8.2s)
```

If `device=cpu` appears instead, check `TTS_DEVICE` and that PyTorch sees CUDA (`python -c "import torch; print(torch.cuda.is_available())"`).

### Performance notes

| Setting | Effect |
|---------|--------|
| `TTS_DEVICE=gpu` / `cuda` | Required for reasonable speed (~8–20s per line on a 3090) |
| `N20_TTS_WARMUP=1` | Pays CUDA compile cost at boot, not on first NPC reply |
| SDPA attention (default on CUDA) | Faster than eager PyTorch; no `flash-attn` build needed |
| `QWEN3_USE_FLASH_ATTN=1` | Optional extra speed if a pre-built `flash-attn` wheel is installed |
| `Qwen3-TTS-12Hz-0.6B-*` | ~2× faster, slightly lower quality |
| `CustomVoice` vs `VoiceDesign` | CustomVoice is faster; VoiceDesign re-synthesizes timbre from text each time |
| Long NPC lines | Chunked above ~380 chars (two `pad_token_id` log lines = two GPU passes) |

The `flash-attn is not installed` warning from `qwen-tts` is harmless when SDPA is enabled.

Model weights download from Hugging Face on first use (~2.5–4.5 GB depending on variant).

### Variants

| Model | Use case |
|-------|----------|
| `Qwen3-TTS-12Hz-1.7B-CustomVoice` | Default — maps NPC gender to built-in speakers (Ryan, Vivian, …) |
| `Qwen3-TTS-12Hz-1.7B-VoiceDesign` | NPC voice from YAML/text description |
| `Qwen3-TTS-12Hz-1.7B-Base` | Clone from reference WAV (pass `reference_audio` on voice create) |
| `Qwen3-TTS-12Hz-0.6B-*` | Lower VRAM, slightly lower quality |

Cloud API (DashScope) is also available for production without local GPU; not wired in yet.

### vLLM-Omni sidecar (production low-latency)

For **true streaming** (~0.76 s TTFA measured on RTX 3090), run Qwen3-TTS as a **separate service** and point the webapp at it over HTTP. No `vllm-omni` in the main webapp venv.

| Piece | Location |
|-------|----------|
| Spike plan + phases | `docs/TTS_VLLM_OMNI_SPIKE.md` |
| Sidecar deploy (start scripts, voice upload) | `services/vllm-omni-tts/` |
| Webapp provider | `TTS_PROVIDER=qwen3_vllm`, `VLLM_OMNI_TTS_URL=...` |

```bash
# webapp/.env
TTS_PROVIDER=qwen3_vllm
VLLM_OMNI_TTS_URL=http://127.0.0.1:8091
VLLM_OMNI_TTS_MODEL=Qwen/Qwen3-TTS-12Hz-1.7B-Base
TTS_DELIVERY=stream
VLLM_OMNI_TTS_REGISTER_ON_START=1
# Live PCM auto-enabled when TTS_DELIVERY=stream; override with VLLM_OMNI_TTS_SOCKET_PCM=0
```

Start sidecar + register campaign voices:

```bash
cd services/vllm-omni-tts && cp .env.example .env && ./install.sh
./start_with_voices.sh
# or: ./start.sh && ./scripts/register_campaign_voices.py ../../user_levels/wild_sheep_chase
```

Benchmark:

```bash
cd webapp && python ../scripts/benchmark_qwen3_tts.py ../user_levels/wild_sheep_chase --provider qwen3_vllm
```


## CosyVoice 3 (Fun-CosyVoice 3.0)

**Repo:** https://github.com/FunAudioLLM/CosyVoice  
**Paper:** [arXiv:2505.17589](https://arxiv.org/abs/2505.17589)

CosyVoice 3 is the backend already integrated as `TTS_PROVIDER=cosyvoice`. It remains excellent for:

- **In-the-wild zero-shot** cloning (messy real-world reference audio)
- **Instruct2** delivery control (accent, emotion, speaking style)
- **Mature stack** in this repo (streaming, chunking, OpenVoice fallback)

Released Dec 2025 (`Fun-CosyVoice3-0.5B-2512` on Hugging Face). Trained on ~1M hours (9 languages, 18 Chinese dialects). Uses a supervised multi-task speech tokenizer and DiffRO post-training.

### CosyVoice 3 vs Qwen3-TTS

| | CosyVoice 3 | Qwen3-TTS |
|---|-------------|-----------|
| **Strength** | Wild clone quality, instruct accents | Streaming latency, voice design API |
| **Clone** | Zero-shot from prompt WAV | 3s clone (Base) or design-then-clone |
| **Latency** | Good; streaming via chunk flow | **~97 ms** first packet (claimed) |
| **Languages** | 9 + dialects | 10 |
| **VRAM** | ~0.5B–1.5B options | 0.6B / 1.7B |
| **This repo** | Full integration + fallback | New `qwen3` provider |

**Recommendation:** Keep **CosyVoice** as default for maximum clone fidelity and existing campaign tuning. Try **Qwen3** when you need faster time-to-first-audio, preset speaker consistency, or VoiceDesign-from-YAML workflows.

## Other advanced systems (not integrated)

| System | Notes |
|--------|-------|
| **Fish Speech / OpenAudio** | Strong open clone; popular in gaming |
| **GPT-SoVITS** | Few-shot clone; heavier fine-tune workflow |
| **StyleTTS2 / F5-TTS** | Research-grade quality; less instruct control |
| **ElevenLabs / OpenAI** | Cloud-only; not self-hosted |

See also `docs/tts_voice_recommendations.md` for historical evaluation notes.
