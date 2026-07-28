# vLLM-Omni TTS spike plan

Goal: run **Qwen3-TTS with true streaming** (~100 ms first audio packet) as a **separate GPU service**, while `natural_20.py` webapp stays a thin HTTP client — no `vllm-omni` in the main Python environment.

## Why separate?

| Concern | In-process `qwen3` (today) | Sidecar `vllm-omni` |
|---------|------------------------------|---------------------|
| Dependencies | `qwen-tts`, torch, flash-attn in webapp venv | Isolated venv / container |
| GPU ownership | Competes with Flask/gunicorn on same process | Dedicated inference worker |
| Streaming | Buffered WAV → fake chunking | Real PCM stream (`stream=true`) |
| Scale | 1 GPU, 1 worker | Can run on another host (`jedld-strix:8091`) |
| Deploy | Restart webapp to reload TTS | Rolling restart of TTS only |

The webapp already has stream delivery (`tts_stream_*` Socket.IO + `TTSPlayer`). A remote provider only needs to feed **real PCM chunks** into `TTSManager.generate_stream()`.

## Architecture

```mermaid
flowchart LR
  subgraph webapp["natural_20.py webapp"]
    CS[ConversationService]
    TM[TTSManager]
    P[qwen3_vllm provider]
    CS --> TM --> P
  end

  subgraph sidecar["services/vllm-omni-tts (separate project)"]
    VLLM[vLLM-Omni serve]
    GPU[(GPU)]
    VLLM --> GPU
  end

  P -->|"POST /v1/audio/speech\nstream + pcm"| VLLM
  P -->|"POST /v1/audio/voices\n(register NPC refs)"| VLLM
  CS -->|"tts_stream_chunk"| Client[Browser TTSPlayer]
```

### Data flow (clone mode — Wild Sheep Chase)

1. **Bake** (existing): `scripts/bake_npc_voices.py` → `assets/voice_samples/<npc_uid>.wav` + `.ref.txt`
2. **Register** (new sidecar script): `services/vllm-omni-tts/scripts/register_campaign_voices.py` → `POST /v1/audio/voices` with `name=n20_<npc_uid>`
3. **Runtime**: webapp `create_voice()` stores `vllm_voice_name`; `generate_stream()` calls vLLM with `voice=n20_mara_bartender`, `stream=true`, `response_format=pcm`
4. **Replay**: concatenate streamed PCM → WAV in `N20_TTS_CACHE_DIR` (same as today)

## Sidecar project layout

Self-contained under `services/vllm-omni-tts/` (not imported by webapp):

```
services/vllm-omni-tts/
  README.md              # install, start, healthcheck
  .env.example             # port, model, GPU, allowed paths
  start.sh                 # vllm serve wrapper
  docker-compose.yml       # optional GPU container
  scripts/
    healthcheck.sh         # curl /v1/audio/voices
    register_campaign_voices.py   # upload baked NPC WAVs
```

Start independently:

```bash
cd services/vllm-omni-tts
cp .env.example .env
./start.sh
```

Webapp connects via env only (no shared code):

```bash
# webapp/.env
TTS_PROVIDER=qwen3_vllm
VLLM_OMNI_TTS_URL=http://localhost:8091
VLLM_OMNI_TTS_MODEL=Qwen/Qwen3-TTS-12Hz-1.7B-Base
TTS_DELIVERY=stream
```

Remote host example (TTS on `jedld-strix`, webapp elsewhere):

```bash
VLLM_OMNI_TTS_URL=http://jedld-strix.local:8091
```

## vLLM-Omni API surface (spike scope)

Reference: [vLLM-Omni speech API](https://docs.vllm.ai/projects/vllm-omni/en/latest/serving/speech_api/)

### Server (Base clone model)

```bash
vllm serve Qwen/Qwen3-TTS-12Hz-1.7B-Base \
  --deploy-config vllm_omni/deploy/qwen3_tts.yaml \
  --omni --port 8091 --trust-remote-code --enforce-eager
```

`qwen3_tts.yaml` enables `async_chunk: true` (required for streaming TTFA).

### Register NPC voice (once per NPC)

```bash
curl -X POST http://localhost:8091/v1/audio/voices \
  -F "audio_sample=@mara_bartender.wav" \
  -F "consent=campaign_baked" \
  -F "name=n20_mara_bartender" \
  -F "ref_text=@mara_bartender.ref.txt"
```

Then synthesis uses `voice=n20_mara_bartender` without sending `ref_audio` each request.

**Alternative (no pre-register):** pass `ref_audio` as base64 data URL + `ref_text` per request — simpler spike, higher per-line overhead.

### Buffered synthesis

```json
POST /v1/audio/speech
{
  "model": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
  "task_type": "Base",
  "input": "Welcome to the tavern.",
  "voice": "n20_mara_bartender",
  "language": "English",
  "response_format": "wav"
}
```

### True streaming (spike success metric)

```json
POST /v1/audio/speech
{
  "input": "Welcome to the tavern.",
  "voice": "n20_mara_bartender",
  "language": "English",
  "response_format": "pcm",
  "stream": true,
  "stream_format": "audio"
}
```

Returns **raw 16-bit PCM, 24 kHz mono** chunks as they're decoded. Wire these into existing `tts_stream_chunk` events (`sample_rate=24000`).

Constraints from upstream:

- `speed` not supported when streaming
- `stream=true` requires `response_format=pcm`
- Model variant must match `task_type` (Base server for clone voices)

## Webapp integration

Provider: `webapp/tts/qwen3_vllm_provider.py` (`TTS_PROVIDER=qwen3_vllm`).

| Method | Behavior |
|--------|----------|
| `initialize()` | `GET /v1/audio/voices` healthcheck; no local GPU |
| `create_voice()` | Ensure voice registered (`POST /v1/audio/voices` if missing); store `vllm_voice_name` in `VoiceConfig.extra_metadata` |
| `generate()` | `POST /v1/audio/speech` → save WAV to cache |
| `generate_stream()` | `POST` with `stream=true` → yield `(24000, pcm_bytes)` |
| `persist_voice()` | Serialize `vllm_voice_name`, `ref_audio`, `ref_text` |
| `restore_voice()` | Re-register on load if server lost state |

Register in `TTSManager.PROVIDERS`:

```python
"qwen3_vllm": Qwen3VLLMProvider,
"mock_qwen3_vllm": MockQwen3VLLMProvider,  # tests
```

### Env vars

| Variable | Default | Purpose |
|----------|---------|---------|
| `VLLM_OMNI_TTS_URL` | `http://127.0.0.1:8091` | Sidecar base URL |
| `VLLM_OMNI_TTS_API_KEY` | `none` | `Authorization: Bearer` (if enabled) |
| `VLLM_OMNI_TTS_MODEL` | `Qwen/Qwen3-TTS-12Hz-1.7B-Base` | Must match server model |
| `VLLM_OMNI_TTS_VOICE_PREFIX` | `n20_` | Namespace uploaded NPC voices |
| `VLLM_OMNI_TTS_TIMEOUT` | `120` | HTTP timeout seconds |
| `VLLM_OMNI_TTS_REGISTER_ON_CREATE` | `1` | Auto-upload ref WAV on `create_voice` |

### HTTP client

Use `httpx` (already a transitive dep in many setups; add to `requirements.txt` if missing). Stream with `client.stream("POST", url, json=payload)` and read raw bytes.

No `qwen-tts` / `torch` / `flash-attn` in webapp when `TTS_PROVIDER=qwen3_vllm`.

### Sample rate note

vLLM-Omni Qwen3 outputs **24 kHz** PCM; in-process Qwen3 is often **12 Hz tokenizer → different rate**. `TTSPlayer` already accepts per-chunk `sample_rate` — verify replay WAV header uses 24000.

## Spike phases

### Phase 0 — Sidecar smoke test (no webapp changes)

**Owner:** ops / local GPU machine  
**Deliverables:**

- [ ] `services/vllm-omni-tts` starts and `scripts/healthcheck.sh` passes
- [ ] Manual `curl` WAV clone with Mara ref audio
- [ ] Manual `curl` PCM stream plays via `play -t raw -r 24000 -e signed -b 16 -c 1 -`
- [ ] Record TTFA (time to first byte) and full-line latency in `docs/TTS_VLLM_OMNI_SPIKE.md` results section

**Success:** first PCM byte &lt; 500 ms after request (target ~100–300 ms per Qwen benchmarks).

### Phase 1 — Voice registration bridge

**Deliverables:**

- [ ] `register_campaign_voices.py` uploads all `assets/voice_samples/*.wav` for a campaign
- [ ] Idempotent: skip if `GET /v1/audio/voices` already lists `n20_<uid>`
- [ ] Document re-run after campaign voice rebakes

### Phase 2 — Webapp HTTP provider (buffered)

**Deliverables:**

- [x] `Qwen3VLLMProvider.generate()` working with `TTS_PROVIDER=qwen3_vllm`
- [x] `scripts/benchmark_qwen3_tts.py --provider qwen3_vllm` parity
- [x] Unit tests with `mock_qwen3_vllm` (httpx mock)
- [x] Fallback: if sidecar down, log error + skip TTS (don't block conversation)

### Phase 3 — True streaming path

**Deliverables:**

- [x] `generate_stream()` forwards PCM to `ConversationService._stream_tts_audio`
- [x] `TTS_DELIVERY=stream` auto-plays chunks (`stream=true`, `response_format=pcm`)
- [x] Final WAV saved for replay (`_last_stream_output_path` + `tts_stream_end`)
- [x] Line cache still works (lookup before stream; WAV path after stream completes)

### Phase 4 — Production hardening (optional)

- [ ] Docker Compose with GPU reservation
- [ ] Voice pre-registration at campaign load (DM save/load hook)
- [ ] Separate TTS GPU host in ngrok/tmux docs
- [ ] Compare 0.6B vs 1.7B on same hardware

## Coexistence with in-process Qwen3

| Use case | Provider |
|----------|----------|
| Dev laptop, no vLLM setup | `qwen3` (in-process) |
| Production / low latency | `qwen3_vllm` (sidecar) |
| CI tests | `mock_qwen3_vllm` |

Campaign assets (`voice_samples/`, `voice_profiles/`) are **shared**; only the synthesis backend changes.

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| vLLM-Omni API drift | Pin version in sidecar `requirements.txt`; integration tests against `/v1/audio/voices` |
| Server restart drops uploaded voices | Re-run `register_campaign_voices.py` on sidecar start (systemd `ExecStartPost`) |
| 24 kHz vs 22.05 kHz client assumptions | Pass `sample_rate` on every stream chunk |
| GPU memory with LLM + TTS on same box | Run sidecar on dedicated GPU (`CUDA_VISIBLE_DEVICES`) |
| Network latency remote TTS | Prefer LAN; benchmark `jedld-strix.local:8091` RTT |

## Benchmark checklist (fill in during spike)

| Metric | In-process `qwen3` clone | vLLM-Omni stream |
|--------|------------------------|------------------|
| Process init | ~20 s | N/A (separate process) |
| TTFA (first PCM byte) | ~5 s (full line first) | _TBD_ |
| Full line (~4 s audio) | ~5.5 s | _TBD_ |
| RTF | ~1.3 | _TBD_ (&lt;1.0 target) |
| Line cache hit | &lt;10 ms | &lt;10 ms (webapp-side) |

Use:

```bash
# in-process baseline
cd webapp && python ../scripts/benchmark_qwen3_tts.py ../user_levels/wild_sheep_chase

# sidecar (after Phase 2)
cd webapp && python ../scripts/benchmark_qwen3_tts.py ../user_levels/wild_sheep_chase --provider qwen3_vllm
```

## References

- [vLLM-Omni speech API](https://docs.vllm.ai/projects/vllm-omni/en/latest/serving/speech_api/)
- [Qwen3-TTS online serving example](https://docs.vllm.ai/projects/vllm-omni/en/stable/user_guide/examples/online_serving/qwen3_tts/)
- [Qwen3-TTS performance guide](https://qwenlm-qwen3-tts.mintlify.app/advanced/performance)
- Repo: `services/vllm-omni-tts/README.md`
- Repo: `docs/TTS_PROVIDERS.md`, `docs/TTS_DELIVERY.md`
