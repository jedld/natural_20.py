# vLLM-Omni TTS sidecar (natural_20.py)

Standalone **Qwen3-TTS inference server** for the natural_20 webapp. This directory is a **separate deployable unit** — it is not imported by the Flask app and does not share the webapp Python environment.

## Quick start

```bash
cd services/vllm-omni-tts
cp .env.example .env
./install.sh          # creates .venv, installs vllm + vllm-omni
./start.sh
```

`vllm-omni` alone is **not** enough — the base **`vllm`** package must also be installed (`requirements.txt` pins both).

In another terminal:

```bash
./scripts/healthcheck.sh
```

Register Wild Sheep Chase baked voices:

```bash
./scripts/register_campaign_voices.py \
  ../../user_levels/wild_sheep_chase
```

Test streaming PCM:

```bash
curl -X POST "http://127.0.0.1:${VLLM_PORT:-8091}/v1/audio/speech" \
  -H "Content-Type: application/json" \
  -d '{
    "input": "Welcome to the tavern.",
    "voice": "n20_mara_bartender",
    "language": "English",
    "response_format": "pcm",
    "stream": true,
    "stream_format": "audio"
  }' --no-buffer | play -t raw -r 24000 -e signed -b 16 -c 1 -
```

## Connect the webapp

In `webapp/.env` (planned — see `docs/TTS_VLLM_OMNI_SPIKE.md`):

```bash
TTS_PROVIDER=qwen3_vllm
VLLM_OMNI_TTS_URL=http://127.0.0.1:8091
VLLM_OMNI_TTS_MODEL=Qwen/Qwen3-TTS-12Hz-1.7B-Base
TTS_DELIVERY=stream
```

Remote GPU host:

```bash
VLLM_OMNI_TTS_URL=http://jedld-strix.local:8091
```

The webapp sends HTTP only; no GPU required on the webapp machine.

## Layout

| Path | Purpose |
|------|---------|
| `start.sh` | Launch `vllm serve` with Qwen3 Base + deploy config |
| `.env.example` | Port, model, GPU pinning |
| `requirements.txt` | `vllm-omni` pin (isolated from main repo) |
| `scripts/healthcheck.sh` | Verify `/v1/audio/voices` |
| `scripts/register_campaign_voices.py` | Upload `assets/voice_samples/*.wav` |
| `docker-compose.yml` | Optional NVIDIA GPU container |

## Model choice

| Model | Use |
|-------|-----|
| `Qwen/Qwen3-TTS-12Hz-1.7B-Base` | **Default** — matches baked NPC clone workflow |
| `Qwen/Qwen3-TTS-12Hz-0.6B-Base` | Lower latency, slightly lower quality |

VoiceDesign / CustomVoice require a **different** server model — run a separate instance on another port if needed.

## Troubleshooting

- **`vllm: not found`:** run `./install.sh` (installs matched `vllm==0.24.0` + `vllm-omni==0.24.0`).
- **`No module named vllm.entrypoints.serve.disagg`:** version mismatch — reinstall with `./install.sh` (do not use vllm 0.25.x with omni 0.24.x).
- **CUDA OOM:** lower `--gpu-memory-utilization` in `start.sh` or use 0.6B model.
- **Voices missing after restart:** re-run `register_campaign_voices.py` (vLLM stores voices in memory).
- **Streaming silent:** ensure `response_format=pcm`, `stream=true`, `stream_format=audio`, and server was started with `qwen3_tts.yaml` (`async_chunk: true`).

See `docs/TTS_VLLM_OMNI_SPIKE.md` for the full integration plan.
