# TTS delivery modes

NPC speech audio is synthesized by `webapp/tts/` and attached to conversation payloads in `ConversationService`. **Text is always delivered immediately**; audio follows based on the selected delivery mode.

## Modes

| Mode | Campaign `game.yml` / env | Behavior |
|------|-----------------------------|----------|
| **`async`** (default) | `tts_delivery: async` or `TTS_DELIVERY=async` | Background synthesis after the message is shown. Speak button shows a spinner, then becomes playable when `tts_ready` arrives. Click to play. |
| **`stream`** | `tts_delivery: stream` or `TTS_DELIVERY=stream` | Background task streams PCM chunks via Socket.IO (`tts_stream_start` / `tts_stream_chunk` / `tts_stream_end`). Audio plays as chunks arrive (stream mode auto-plays). Final `audio_url` enables replay. |
| **`manual`** | `tts_delivery: manual` or `TTS_DELIVERY=manual` | No server synthesis during emit. Speak button calls `POST /tts/generate` on click. |
| **`sync`** (legacy) | `tts_delivery: sync` or `TTS_DELIVERY=sync` | Blocks emit until audio is generated (not recommended for live play). |

### Campaign configuration

Set delivery mode once per campaign in **`game.yml`**:

```yaml
tts_delivery: async   # async | stream | manual | sync
```

Or nest under a `tts` block:

```yaml
tts:
  delivery: stream
```

All players use the same mode. The server reads this at bootstrap and after DM save/load. If omitted, the server falls back to the `TTS_DELIVERY` environment variable (default `async`).

`GET /tts/preferences` returns the active campaign mode (read-only). The client receives `window.N20_TTS_DELIVERY` on page load.

## Client UX

- **JRPG dialog** and **local chat** show a speak button on NPC lines.
- **`async`**: spinner → volume icon on `tts_ready` (matched by `reply_id`).
- **`stream`**: pulsing volume icon while streaming; upgrades to replay on `tts_stream_end`.
- **`manual`**: volume icon immediately; click runs `/tts/generate`.
- **Playback**: click-to-play in async/manual. Stream mode plays automatically while chunks arrive.
- Optional auto-play for async: `TTSPlayer.setAutoplay(true)` or `localStorage n20.tts.autoplay=true`.

## Socket events

| Event | Direction | Payload |
|-------|-----------|---------|
| `message` (`type: conversation`) | server → client | Text + `tts_status` (`pending` / `streaming` / `manual`) |
| `tts_ready` | server → client | `{ reply_id, audio_url, tts_emotion, tts_gain, … }` |
| `tts_stream_start` | server → client | `{ reply_id, sample_rate, tts_gain, … }` |
| `tts_stream_chunk` | server → client | `{ reply_id, seq, sample_rate, pcm_b64 }` |
| `tts_stream_end` | server → client | `{ reply_id, audio_url, … }` |
| `npc_speech` | server → client | Legacy standalone audio event |

## Implementation notes

- Streaming uses `TTSManager.generate_stream()` → provider `generate_stream()` when available, else buffered WAV chunking.
- CosyVoice uses `stream=True` on inference when supported; mock provider chunks placeholder WAV for tests.
- **Multi-segment pipeline** (default on): while segment *N* audio is emitted, segment *N+1* can synthesize on a worker thread (`N20_TTS_PIPELINE_SEGMENTS=1`). Set `N20_TTS_PIPELINE_CONCURRENT=0` to disable overlapping GPU inference (safer on a single CosyVoice model); segment prefetch still runs after each segment completes.
- Per-listener reachability still skips TTS (`tts_skipped`) for deaf/unconscious listeners or when too far away.

## Long dialogue chunking

Providers such as CosyVoice enforce a ~200-token synthesis cap. `TTSManager` resolves a **model profile** (`webapp/tts/model_config.py`) and chunks text accordingly:

| Profile | Default max chars | Streaming | Notes |
|---------|-------------------|-----------|-------|
| `cosyvoice_v2` / `cosyvoice_v3` | 220 | yes | CosyVoice `token_max_length` ~200 |
| `cosyvoice_openvoice_fallback` | 350 | no | CosyVoice runtime OpenVoice fallback |
| `openvoice` | 400 | no | OpenVoice cloning |
| `openvoice_gtts` | 500 | no | gTTS fallback |
| `mock_cosyvoice` | 220 | yes | Test/dev mock |

Chunking strategy: sentences → clauses → words. Segments are synthesized and concatenated with a profile-specific pause.

### Env overrides

- `N20_TTS_MAX_CHARS` — global override for all profiles
- `N20_TTS_CHUNK_PAUSE_MS` — global pause between stitched chunks
- `N20_TTS_MAX_CHARS_<PROFILE>` — per-profile override (e.g. `N20_TTS_MAX_CHARS_COSYVOICE_V3`)
- `N20_TTS_CHUNK_PAUSE_MS_<PROFILE>` — per-profile pause override

`GET /tts/status` returns the active `model_profile` and resolved `model_config`.

## Related env vars

- `TTS_ENABLED`, `TTS_PROVIDER`, `TTS_DEVICE`, `N20_TTS_CACHE_DIR` — provider setup (see `AGENTS.md`).
- `N20_TTS_MAX_CHARS`, `N20_TTS_MAX_CHARS_<PROFILE>`, `N20_TTS_CHUNK_PAUSE_MS` — see chunking table above.
- `N20_TTS_PIPELINE_SEGMENTS` — `1` (default) prefetch next text segment during stream delivery; `0` for legacy sequential segments.
- `N20_TTS_PIPELINE_CONCURRENT` — `1` (default) allow next-segment synthesis to overlap the current segment's live CosyVoice stream; set `0` if a single GPU model shows thread-safety issues.
- `VLLM_OMNI_TTS_SOCKET_PCM` — `1`/`0` to force live Socket.IO PCM during stream delivery. When unset, **`qwen3_vllm` auto-enables live PCM when `TTS_DELIVERY=stream`** (other providers default on).
- `VLLM_OMNI_TTS_REGISTER_ON_START` — `1` (default) upload missing campaign `voice_samples/` to the sidecar on webapp bootstrap when `TTS_PROVIDER=qwen3_vllm`.
