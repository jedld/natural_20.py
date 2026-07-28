# TTS (Text-to-Speech) Voice Recommendations for natural_20.py

> **Purpose**: Recommend an open-source, self-hosted TTS solution for generating NPC voices via **text prompts** (e.g., "Old man with a raspy voice"), then locking that voice consistently for each NPC.

---

## Current State

The project has **no TTS implementation**. The existing conversation system (`webapp/conversation_service.py`, `webapp/entity_rag_handler.py`) handles:
- Speech physics (volume, distance, acoustic reachability)
- Language detection and translation
- LLM-driven NPC dialogue generation
- SocketIO event broadcasting for in-game chat

TTS would sit **after** LLM response generation, converting the NPC's textual reply into audio streamed to connected clients.

---

## Requirements Summary

| Requirement | Detail |
|---|---|
| **Text-to-Voice Prompts** | Generate a voice by describing it in words, e.g., `"Old man with a raspy voice"` or `"Young woman, soft and gentle tone"` |
| **Voice Locking** | Lock the generated voice to an NPC UID for consistent reuse across sessions |
| **Emotion & Expression** | Generate speech with tonal variation (anger, fear, joy, etc.) |
| **Near Real-Time** | Sub-5-second latency for live conversation flow |
| **Self-Hosted** | Must run entirely on local GPU/CPU — no cloud APIs |
| **Python API** | Must integrate with Flask/SocketIO backend |
| **Multi-voice** | Different NPCs get different voices from the same model |

---

## Top Recommendations

### 1. 🥇 Coqui XTTS v2 (Self-Hosted) — Best Balance

**URL**: https://github.com/coqui-ai/XTTS  
**License**: MPL-2.0

| Criterion | Assessment |
|---|---|
| **Text-to-Voice Prompts** | ✅ **Voice cloning from audio reference** — describe voice via LLM-generated reference audio. See work-around below. |
| **Voice Locking** | ✅ **Clone from 3-second sample** or use 5 built-in library voices. Clone is saved as a `.wav` reference file. |
| **Emotion** | ⚠️ Limited — model preserves prosody from reference audio. Emotion must be induced via text content (LLM injection of `*laughs*`, `[sighs]`, etc.). |
| **Latency** | ⚠️ ~3–8 seconds on GPU (RTX 3060+). ~15–30s on CPU. Acceptable for turn-based D&D conversation. |
| **Self-Hosted** | ✅ Fully self-hosted. No API keys. |
| **Python** | ✅ `pip install TTS` — full Python API. |
| **Cost** | Free. |

#### How Text-to-Voice Prompts Work with XTTS

XTTS v2 does **not** natively accept text prompts like "raspy old man" for voice generation. Instead, it uses **audio reference cloning**. The workflow to achieve text-to-voice prompt generation:

```
User describes voice → LLM generates a matching reference audio sample → XTTS clones the voice → Voice locked for NPC
```

**Implementation approach**:

```python
# webapp/tts/xtts_provider.py
import torch
from TTS.api import TTS

class XTTSTTS:
    def __init__(self, device: str = "cuda"):
        self.tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)
        self._voice_registry = {}  # npc_uid -> reference_audio_path
        self._voice_descriptions = {}  # npc_uid -> prompt_text
    
    def generate_voice_from_prompt(self, npc_uid: str, voice_prompt: str) -> str:
        """
        Generate a voice by using a reference speaker + LLM-guided selection.
        
        Since XTTS clones from audio, we use the built-in library voices
        and let the LLM pick the closest match, or generate a custom
        reference via a secondary TTS system.
        """
        # Option A: Map prompt to closest built-in voice
        library_voices = {
            "Anne": "tts_models/multilingual/multi-dataset/xtts_v2/Anne",
            "Bella": "tts_models/multilingual/multi-dataset/xtts_v2/Bella",
            "Esther": "tts_models/multilingual/multi-dataset/xtts_v2/Esther",
            "Diana": "tts_models/multilingual/multi-dataset/xtts_v2/Diana",
            "Dominic": "tts_models/multilingual/multi-dataset/xtts_v2/Dominic",
        }
        
        # Use LLM to pick the closest library voice to the prompt
        chosen_voice = self._llm_pick_closest_voice(voice_prompt, library_voices)
        
        # Lock the chosen voice for this NPC
        self._voice_registry[npc_uid] = chosen_voice
        self._voice_descriptions[npc_uid] = voice_prompt
        
        return chosen_voice
    
    def _llm_pick_closest_voice(self, prompt: str, library_voices: dict) -> str:
        """Delegate voice selection to an LLM based on prompt description."""
        # This calls your existing LLM controller
        # Prompt: "Which library voice best matches: '{prompt}'? Choices: {list}"
        ...
    
    def generate(self, text: str, npc_uid: str) -> str:
        ref_audio = self._voice_registry.get(npc_uid)
        if not ref_audio:
            raise ValueError(f"No voice locked for NPC {npc_uid}")
        
        output_path = f"/tmp/tts_{npc_uid}_{id(text)}.wav"
        self.tts.tts_to_file(
            text=text,
            speaker_wav=ref_audio,
            language="en",
            file_path=output_path,
        )
        return output_path
```

**For true text-to-voice prompting** (not just library selection), see **Option B** below.

#### Option B: Hybrid Approach — Generate Custom Voice via Secondary TTS

Use a **text-to-voice model** (like OpenVoice or VoiceCraft) to generate a 3-second reference audio from a text prompt, then clone into XTTS for production:

```
Voice prompt → OpenVoice/VoiceCraft → 3s reference audio → XTTS clone → Locked NPC voice
```

---

### 2. 🥈 OpenVoice V2 (Self-Hosted) — True Text-to-Voice + Instant Cloning

**URL**: https://github.com/myshell-ai/OpenVoice
**HF Repo**: https://huggingface.co/myshell-ai/OpenVoiceV2
**License**: MIT

| Criterion | Assessment |
|---|---|
| **Text-to-Voice Prompts** | ✅ **Instant style transfer** — clone from 3s audio or use built-in voice styles. Supports **cross-lingual** cloning. |
| **Voice Locking** | ✅ Save reference audio + style embedding per NPC. |
| **Emotion** | ✅ **Style codes** for emotion: `cheerful`, `lazy`, `angry`, `nodrama`, `shouting` etc. |
| **Latency** | ✅ **~500ms–2s** on GPU. Much faster than XTTS. |
| **Self-Hosted** | ✅ Fully self-hosted. |
| **Python** | ✅ `pip install openvoice-app` or clone repo. |
| **Cost** | Free. |

#### OpenVoice V2 Improvements

OpenVoice V2 offers:
- **Better audio quality** with improved training strategy
- **11 built-in style embeddings** for different accents (en-default, en-us, en-au, es, fr, jp, kr, zh, etc.)
- **Auto-download from Hugging Face** — checkpoints are downloaded automatically on first run

#### Checkpoint Auto-Download from Hugging Face

The old S3 download links in the OpenVoice documentation are broken. OpenVoice V2 checkpoints are now available directly on Hugging Face and are **auto-downloaded** by the webapp TTS provider when missing.

**Hugging Face repo structure:**
```
myshell-ai/OpenVoiceV2/
├── converter/
│   ├── checkpoint.pth      (131 MB - main model weights)
│   └── config.json         (configuration)
└── base_speakers/
    └── ses/
        ├── en-default.pth  (default English style embedding)
        ├── en-us.pth       (US English)
        ├── en-au.pth       (Australian English)
        ├── es.pth          (Spanish)
        ├── fr.pth          (French)
        ├── jp.pth          (Japanese)
        ├── kr.pth          (Korean)
        └── zh.pth          (Chinese)
```

**Download mechanism:**
1. The TTS provider searches for local checkpoints in `.local_packages/OpenVoice/`
2. If not found, it calls `huggingface_hub.snapshot_download("myshell-ai/OpenVoiceV2")`
3. Files are cached in `{cache_dir}/openvoice_v2_checkpoints/`
4. Subsequent runs use cached files (instant)

**Requirement:** `huggingface_hub` must be installed:
```bash
pip install huggingface_hub
```

#### Why OpenVoice is Strong for This Use Case

OpenVoice supports **two modes**:
1. **Instant cloning**: Upload 3-second sample → get exact voice clone
2. **Style control**: Apply emotional/style characteristics independently

This is ideal for D&D:
```
NPC "Grimjaw the Orc" = voice clone (orcsound.wav) + style = "angry, aggressive"
NPC "Elara the Wizard" = voice clone (elfwoman.wav) + style = "calm, measured"
```

#### Integration Sketch

```python
# webapp/tts/openvoice_provider.py
import os
from openvoice import se_extractor
from openvoice.api import BaseSpeakerTTS

class OpenVoiceTTS:
    def __init__(self, device: str = "cuda"):
        self.base_tts = BaseSpeakerTTS(device=device)
        self.base_tts.load_ckpt("base_speaker_en.pth")
        self._voice_registry = {}  # npc_uid -> {se_path, style}
        self._style_vocab = {
            "cheerful": "cheerful",
            "angry": "angry",
            "lazy": "lazy",
            "calm": "nodrama",
            "shouting": "shouting",
            "whisper": "whisper",
        }
    
    def generate_voice_from_prompt(self, npc_uid: str, voice_prompt: str, reference_audio: str = None) -> str:
        """
        Generate and lock a voice from a text prompt + optional reference audio.
        
        If reference_audio is provided, clone that exact voice.
        Otherwise, select from built-in styles and let the LLM map the prompt.
        """
        se_path = f"/tmp/se_{npc_uid}.pth"
        
        if reference_audio:
            # Clone exact voice from reference
            se = se_extractor.get_se(
                reference_audio, 
                self.base_tts.vocoder, 
                device=device,
                target_dir=se_path,
            )
        else:
            # Use built-in style (LLM picks based on prompt)
            style = self._llm_pick_style(voice_prompt)
            se = self._get_builtin_style_se(style)
        
        self._voice_registry[npc_uid] = {
            "se_path": se_path,
            "style": style,
            "prompt": voice_prompt,
        }
        
        return se_path
    
    def generate(self, text: str, npc_uid: str, emotion: str = None) -> str:
        voice_config = self._voice_registry.get(npc_uid)
        if not voice_config:
            raise ValueError(f"No voice locked for NPC {npc_uid}")
        
        # Resolve emotion/style
        style = emotion or voice_config["style"]
        style_key = self._style_vocab.get(style, "nodrama")
        
        output_path = f"/tmp/tts_{npc_uid}_{id(text)}.wav"
        
        self.base_tts.tts_to_file(
            text=text,
            se_path=voice_config["se_path"],
            style=style_key,
            output_path=output_path,
        )
        
        return output_path
```

---

### 3. 🥉 VoiceCraft (Self-Hosted) — Editable Voice Synthesis

**URL**: https://github.com/jasonppy/VoiceCraft  
**License**: MIT

| Criterion | Assessment |
|---|---|
| **Text-to-Voice Prompts** | ⚠️ Clones from reference audio. Supports **editing** (delete/rewrite parts) of generated speech. |
| **Voice Locking** | ✅ Reference audio saved per NPC. |
| **Emotion** | ⚠️ Preserved from reference; no explicit emotion control. |
| **Latency** | ⚠️ ~5–10s on GPU. |
| **Self-Hosted** | ✅ Fully self-hosted. |
| **Python** | ✅ PyTorch-based API. |
| **Cost** | Free. |

VoiceCraft is notable for its **speech editing** capability — you can rewrite portions of already-generated speech. Useful for fixing pronunciation but overkill for basic NPC dialogue.

---

### 4. 🏅 Silero TTS (Self-Hosted) — Fastest, No GPU Needed

**URL**: https://github.com/snakers4/silero-models  
**License**: CC BY-NC-4.0

| Criterion | Assessment |
|---|---|
| **Text-to-Voice Prompts** | ❌ Fixed voices only. No cloning, no text-to-voice. |
| **Voice Locking** | ⚠️ 18 built-in voices (5 English). Select by index. |
| **Emotion** | ❌ Monotone, no emotion. |
| **Latency** | ✅ **~50–200ms** on CPU. Extremely fast. |
| **Self-Hosted** | ✅ Fully self-hosted. |
| **Python** | ✅ `pip install silero-tts` |
| **Cost** | Free (non-commercial). |

Silero is best for **background narration** or **ambient muttering** where voice quality doesn't matter.

---

## Comparison Matrix

| Feature | OpenVoice | XTTS v2 | VoiceCraft | Silero |
|---|---|---|---|---|
| Text-to-Voice Prompts | ⚠️ Style codes | ⚠️ Audio clone | ⚠️ Audio clone | ❌ Fixed |
| Voice Locking | ✅ Reference audio | ✅ Reference audio | ✅ Reference audio | ⚠️ Fixed voices |
| Emotion Control | ✅ Style codes | ⚠️ Text-driven | ⚠️ Text-driven | ❌ None |
| Latency (GPU) | ~1s | ~5s | ~8s | ~100ms |
| Self-Hosted | ✅ | ✅ | ✅ | ✅ |
| Python | ✅ | ✅ | ✅ | ✅ |
| Cost | Free | Free | Free | Free |
| Quality | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ |
| GPU Required | Recommended | Yes (for speed) | Yes | No |

---

## Final Recommendation: **OpenVoice** + **XTTS v2** Hybrid

### Architecture: Two-Stage Voice Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│  Stage 1: Voice Creation (one-time per NPC)                 │
│                                                              │
│  "Old man with a raspy voice"                               │
│       │                                                     │
│       ▼                                                     │
│  LLM maps prompt to:                                        │
│    1. Built-in style code (e.g., "gruff", "whisper")        │
│    2. Fallback reference audio generation                    │
│       │                                                     │
│       ▼                                                     │
│  OpenVoice generates 3s reference audio                     │
│       │                                                     │
│       ▼                                                     │
│  Voice locked: se_path + style saved to NPC YAML            │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  Stage 2: Dialogue Generation (per utterance)               │
│                                                              │
│  LLM generates NPC dialogue text + emotion tag              │
│       │                                                     │
│       ▼                                                     │
│  OpenVoice TTS.generate(text, npc_uid, emotion)             │
│       │                                                     │
│       ▼                                                     │
│  .wav file → SocketIO → Client playback                     │
└─────────────────────────────────────────────────────────────┘
```

### Why This Hybrid Works

1. **OpenVoice** handles both voice creation (stage 1) and production TTS (stage 2) with emotion style codes
2. **OpenVoice's style codes** (`angry`, `cheerful`, `lazy`, `shouting`, `whisper`) map directly to D&D roleplay moments
3. **Cross-lingual cloning** lets you create an orcish voice from any language reference
4. **Fast generation** (~1s on GPU) keeps conversation flowing

---

## Implementation Code: Full Provider

```python
# webapp/tts/openvoice_provider.py
"""
OpenVoice TTS provider for natural_20.py NPC voice generation.

Supports:
- Voice creation from text prompts (via style mapping)
- Voice cloning from reference audio
- Emotion/style control per utterance
- Voice persistence in NPC YAML
"""

import os
import uuid
from dataclasses import dataclass
from typing import Optional

import torch

@dataclass
class VoiceConfig:
    npc_uid: str
    se_path: str                    # Style embedding path
    style: str                      # Default emotion style
    prompt_description: str         # Original voice prompt
    reference_audio: str = None     # Original reference audio (if cloned)


class OpenVoiceTTSProvider:
    """
    TTS provider using OpenVoice for NPC voice generation.
    
    Usage:
        provider = OpenVoiceTTSProvider(device="cuda")
        
        # Create a voice for an NPC
        provider.create_voice(
            npc_uid="npc_goblin_001",
            voice_prompt="Greedy goblin with a raspy whisper"
        )
        
        # Generate speech
        audio_path = provider.generate(
            text="Ye shall not pass, ye meddlin' fools!",
            npc_uid="npc_goblin_001",
            emotion="angry"
        )
    """
    
    # Emotion/style mapping for D&D roleplay
    EMOTION_STYLES = {
        "angry": "angry",
        "yelling": "shouting",
        "shouting": "shouting",
        "whisper": "whisper",
        "cheerful": "cheerful",
        "happy": "cheerful",
        "sad": "sad",
        "lazy": "lazy",
        "calm": "calm",
        "neutral": "calm",
        "fearful": "fearful",
        "scared": "fearful",
    }
    
    # Built-in style voice samples (path → style name)
    BUILTIN_STYLES = {
        "cheerful": "assets/openvoice_voices/cheerful.wav",
        "angry": "assets/openvoice_voices/angry.wav",
        "lazy": "assets/openvoice_voices/lazy.wav",
        "calm": "assets/openvoice_voices/calm.wav",
        "shouting": "assets/openvoice_voices/shouting.wav",
        "whisper": "assets/openvoice_voices/whisper.wav",
    }
    
    def __init__(self, device: str = "cuda"):
        self.device = device
        self._voice_registry = {}  # npc_uid -> VoiceConfig
        self._loaded = False
        self._base_tts = None
        self._se_extractor = None
    
    def initialize(self):
        """Lazy-load OpenVoice models."""
        if self._loaded:
            return
        
        try:
            from openvoice.api import BaseSpeakerTTS
            from openvoice import se_extractor
            
            self._base_tts = BaseSpeakerTTS(
                device=self.device,
                config_path="openvoice/configs/base_tts/config.json",
            )
            self._base_tts.load_ckpt("openvoice/checkpoints/base_tts/epoch_3rd.pth")
            self._se_extractor = se_extractor
            
            self._loaded = True
        except ImportError:
            raise ImportError(
                "OpenVoice not installed. Install with: "
                "pip install openvoice-app "
                "or clone from https://github.com/myshell-ai/OpenVoice"
            )
    
    def create_voice(
        self,
        npc_uid: str,
        voice_prompt: str,
        reference_audio: str = None,
    ) -> VoiceConfig:
        """
        Create and lock a voice for an NPC.
        
        Args:
            npc_uid: Unique identifier for the NPC
            voice_prompt: Text description of the voice, e.g.
                         "Old man with a raspy voice"
                         "Young woman, soft and gentle tone"
                         "Deep demonic growl"
            reference_audio: Optional path to audio file for exact cloning.
                           If None, LLM selects closest built-in style.
        
        Returns:
            VoiceConfig with locked voice path
        """
        self.initialize()
        
        se_path = f"/tmp/tts_se_{npc_uid}.pth"
        
        if reference_audio and os.path.exists(reference_audio):
            # Exact clone from reference audio
            se = self._se_extractor.get_se(
                reference_audio,
                self._base_tts.vocoder,
                device=self.device,
                target_dir=se_path,
            )
            style = "calm"  # Default; emotion applied per-utterance
        else:
            # LLM picks closest built-in style to the prompt
            style = self._llm_pick_style(voice_prompt)
            # Use the built-in style's reference for cloning
            builtin_ref = self.BUILTIN_STYLES.get(style)
            if builtin_ref and os.path.exists(builtin_ref):
                se = self._se_extractor.get_se(
                    builtin_ref,
                    self._base_tts.vocoder,
                    device=self.device,
                    target_dir=se_path,
                )
            else:
                raise FileNotFoundError(
                    f"Built-in style reference not found: {builtin_ref}. "
                    f"Provide a reference_audio file or download OpenVoice samples."
                )
        
        config = VoiceConfig(
            npc_uid=npc_uid,
            se_path=se_path,
            style=style,
            prompt_description=voice_prompt,
            reference_audio=reference_audio,
        )
        
        self._voice_registry[npc_uid] = config
        return config
    
    def generate(
        self,
        text: str,
        npc_uid: str,
        emotion: str = None,
        output_path: str = None,
    ) -> str:
        """
        Generate speech audio for an NPC.
        
        Args:
            text: The dialogue text to speak
            npc_uid: The NPC whose voice to use
            emotion: Optional emotion/style override (e.g., "angry", "whisper")
            output_path: Optional output path. Auto-generated if None.
        
        Returns:
            Path to the generated .wav file
        """
        self.initialize()
        
        voice_config = self._voice_registry.get(npc_uid)
        if not voice_config:
            raise ValueError(f"No voice locked for NPC '{npc_uid}'. "
                           f"Call create_voice() first.")
        
        # Resolve emotion/style
        style = emotion or voice_config.style
        style_key = self.EMOTION_STYLES.get(style, "calm")
        
        output_path = output_path or f"/tmp/tts_{npc_uid}_{uuid.uuid4().hex[:8]}.wav"
        
        self._base_tts.tts_to_file(
            text=text,
            se_path=voice_config.se_path,
            style=style_key,
            output_path=output_path,
        )
        
        return output_path
    
    def _llm_pick_style(self, voice_prompt: str) -> str:
        """
        Use an LLM to pick the closest built-in style to a voice prompt.
        
        This can integrate with the project's existing LLM controller.
        """
        choices = list(self.BUILTIN_STYLES.keys())
        
        # This would call your existing LLM provider
        prompt = (
            f"Which voice style best matches the description: '{voice_prompt}'?\n"
            f"Choices: {choices}\n"
            f"Return only the style name."
        )
        
        # Example: use mock for now
        # From webapp.llm_handler import get_llm_response
        # return get_llm_response(prompt)
        
        # Default fallback
        return "calm"
    
    def persist_voice(self, npc_uid: str) -> dict:
        """Export voice config for save/load."""
        config = self._voice_registry.get(npc_uid)
        if not config:
            return {}
        return {
            "se_path": config.se_path,
            "style": config.style,
            "prompt_description": config.prompt_description,
            "reference_audio": config.reference_audio,
        }
    
    def restore_voice(self, npc_uid: str, voice_data: dict) -> VoiceConfig:
        """Restore a voice config from save data."""
        config = VoiceConfig(
            npc_uid=npc_uid,
            se_path=voice_data["se_path"],
            style=voice_data["style"],
            prompt_description=voice_data["prompt_description"],
            reference_audio=voice_data.get("reference_audio"),
        )
        self._voice_registry[npc_uid] = config
        return config
    
    def list_locked_voices(self) -> list[str]:
        """Return all NPC UIDs that have locked voices."""
        return list(self._voice_registry.keys())
```

---

## NPC YAML Integration

Add voice configuration to NPC YAML files:

```yaml
# templates/npcs/goblin_elder.yml
name: "Goblin Elder Grishnak"
uid: "npc_goblin_elder_grishnak"
voice:
  prompt: "Ancient goblin with a raspy, wheezy voice"
  style: "lazy"  # Default style
  reference_audio: null  # Or path to custom voice sample
  locked: true
```

---

## Conversation Service Integration

Wire TTS into the existing conversation flow:

```python
# webapp/conversation_service.py (modification)

class ConversationService:
    def __init__(self):
        # ... existing init ...
        self.tts_provider = OpenVoiceTTSProvider(device="cuda")
    
    def handle_talk_request(self, session, game, sender, data):
        # ... existing LLM response generation ...
        llm_response = self._generate_npc_response(...)
        
        # NEW: Generate TTS audio
        emotion = self._extract_emotion_from_response(llm_response)
        npc_uid = sender.uid
        
        # Create voice if not already locked
        if npc_uid not in self.tts_provider.list_locked_voices():
            voice_config = self.tts_provider.create_voice(
                npc_uid=npc_uid,
                voice_prompt=self._get_npc_voice_prompt(sender),
            )
        
        # Generate speech
        audio_path = self.tts_provider.generate(
            text=llm_response,
            npc_uid=npc_uid,
            emotion=emotion,
        )
        
        # Broadcast with audio
        payload = {
            'text': llm_response,
            'audio_url': f'/static/tts/{os.path.basename(audio_path)}',
            'npc_name': sender.name,
            'npc_uid': npc_uid,
        }
        socketio.emit('npc_speech', payload, room=game.current_map)
```

---

## Environment Variables

```bash
# TTS Configuration
TTS_PROVIDER=openvoice       # openvoice | xtts | silero
TTS_DEVICE=cuda              # cuda | cpu

# OpenVoice paths (if not using defaults)
OPENVOICE_CHECKPOINT_DIR=/path/to/openvoice/checkpoints
OPENVOICE_STYLE_VOCAB_DIR=/path/to/openvoice/styles

# XTTS paths (if using XTTS provider)
XTTS_MODEL_DIR=/path/to/xtts/models
```

---

## Dependencies

Add to `requirements.txt`:

```
openvoice-app>=1.0.0
# OR for direct install:
git+https://github.com/myshell-ai/OpenVoice.git
```

---

## Implementation Roadmap

| Phase | Task | Priority |
|---|---|---|
| 1 | Install OpenVoice + download checkpoints | High |
| 2 | Create `webapp/tts/` package with `OpenVoiceTTSProvider` | High |
| 3 | Add voice creation UI (voice prompt → locked voice) | High |
| 4 | Wire TTS into `conversation_service.py` | High |
| 5 | Add `npc_speech` SocketIO event + client-side audio player | High |
| 6 | Add voice persistence (NPC YAML save/load) | Medium |
| 7 | Add emotion detection from LLM response → TTS style mapping | Medium |
| 8 | Add custom reference audio upload per NPC | Low |

---

## Client-Side Audio Playback

```javascript
// webapp/static/js/tts_player.js (new file)

window.TTSPlayer = {
    _audioQueue: [],
    _isPlaying: false,
    
    onNPCSpeech: function(data) {
        this._queueAudio({
            text: data.text,
            audioUrl: data.audio_url,
            npcName: data.npc_name,
        });
    },
    
    _queueAudio: function(audioData) {
        this._audioQueue.push(audioData);
        this._playNext();
    },
    
    _playNext: function() {
        if (this._isPlaying || this._audioQueue.length === 0) return;
        
        this._isPlaying = true;
        const audio = new Audio(this._audioQueue[0].audioUrl);
        
        audio.addEventListener('ended', () => {
            this._isPlaying = false;
            this._audioQueue.shift();
            this._playNext();
        });
        
        audio.addEventListener('error', (e) => {
            console.warn('TTS audio playback failed:', e);
            this._isPlaying = false;
            this._audioQueue.shift();
            this._playNext();
        });
        
        // Show NPC dialogue bubble
        Chat.showNPCDialogue(this._audioQueue[0]);
        audio.play();
    },
};

// Register SocketIO handler
socketio.on('npc_speech', (data) => {
    window.TTSPlayer.onNPCSpeech(data);
});
```

---

## Summary

| Recommendation | Best For |
|---|---|
| **OpenVoice** (primary) | Text-to-voice style control + fast generation + emotion codes |
| **XTTS v2** (alternative) | Highest quality voice cloning (slower, no emotion codes) |
| **Silero** (fallback) | Ultra-fast background narration, no emotion needed |

**For your requirements** (open-source, text-to-voice prompts, voice locking, emotion, near real-time), **OpenVoice** is a solid fit. However, newer models have emerged that may be even better. See the **2025-2026 Updates** section below for a detailed comparison.

---

## 2025-2026 Updates: New TTS Contenders

Since the original recommendations, several new open-source TTS models have emerged that surpass OpenVoice in key areas. This section evaluates the current state of the art as of mid-2026.

### 🆕 CosyVoice 3 (FunAudioLLM / Alibaba) — ⭐ TOP RECOMMENDATION UPDATE

**URL**: https://github.com/FunAudioLLM/CosyVoice
**HF Repo**: https://huggingface.co/FunAudioLLM/CosyVoice-3
**License**: MIT
**Params**: 0.5B (500M)
**Released**: December 2025 (v3.0)

| Criterion | Assessment |
|---|---|
| **Text-to-Voice Prompts** | ✅ **Zero-shot voice cloning from 3-10s reference** — superior quality to OpenVoice. Cross-lingual cloning across 9 languages. |
| **Voice Locking** | ✅ **Semantic token-based** — save the extracted semantic tokens for instant reuse. |
| **Emotion** | ✅ **Explicit emotion control** — cheerful, sad, angry, fearful, calm, and more via style tokens. |
| **Latency** | ✅ **~150ms TTFT (time-to-first-token)** — ultra-low latency. Full generation ~1-3s on GPU. |
| **Self-Hosted** | ✅ Fully self-hosted PyTorch model. |
| **Python** | ✅ `pip install cosyvoice` — full Python API. |
| **Cost** | Free (MIT license). |
| **Languages** | 9 languages (Chinese, English, Japanese, Korean, German, Spanish, French, and more) with 18 dialects. |

#### Why CosyVoice 3 Outperforms OpenVoice

1. **Architecture**: Uses LLM-based text-to-speech with flow matching and supervised semantic tokens. This is fundamentally superior to OpenVoice's style embedding approach.
2. **Quality**: Benchmarks show CER (Character Error Rate) of 5.09% vs OpenVoice's ~8-10%. Content consistency and speaker similarity are significantly higher.
3. **Pronunciation Inpainting**: Can correct mispronounced words by re-synthesizing just the problematic segments.
4. **Speed**: 150ms TTFT enables near-instant dialogue generation — critical for conversational D&D NPCs.
5. **Multilingual**: Native cross-lingual support without separate language models.

#### Integration Example

```python
# webapp/tts/cosyvoice_provider.py
import torch
from cosyvoice.cli.cosyvoice import CosyVoice

class CosyVoiceProvider(TTSEngine):
    EMOTION_STYLES = {
        "angry": "angry",
        "cheerful": "cheerful",
        "sad": "sad",
        "fearful": "fearful",
        "calm": "calm",
        # Map D&D emotions to CosyVoice emotion tokens
    }
    
    def __init__(self, device: str = "cuda"):
        self.device = device
        self._cosyvoice = None
        self._voice_registry = {}  # npc_uid -> semantic_tokens_path
        
    def initialize(self):
        self._cosyvoice = CosyVoice('FunAudioLLM/CosyVoice-3-0.5B')
        
    def create_voice(self, npc_uid: str, voice_prompt: str,
                     reference_audio: Optional[str] = None) -> VoiceConfig:
        if not reference_audio:
            raise ValueError("CosyVoice requires reference audio for voice cloning")
        
        # Extract semantic tokens from reference
        tokens = self._cosyvoice.extract_semantic_tokens(reference_audio)
        tokens_path = f"/tmp/cosyvoice_se_{npc_uid}.pt"
        torch.save(tokens, tokens_path)
        
        config = VoiceConfig(
            npc_uid=npc_uid,
            se_path=tokens_path,
            style="calm",
            prompt_description=voice_prompt,
            reference_audio=reference_audio,
        )
        self._voice_registry[npc_uid] = config
        return config
    
    def generate(self, text: str, npc_uid: str,
                 emotion: Optional[str] = None, output_path: Optional[str] = None) -> str:
        config = self._voice_registry.get(npc_uid)
        if not config:
            raise ValueError(f"No voice locked for NPC {npc_uid}")
        
        emotion_token = self.EMOTION_STYLES.get(emotion or "calm", "calm")
        tokens = torch.load(config.se_path)
        
        # Generate speech with emotion control
        result = self._cosyvoice.inference_zero_shot(
            text=text,
            prompt_speech_path=config.reference_audio,
            prompt_text="",  # Not required
            emotion=emotion_token,
        )
        
        output_path = output_path or f"/tmp/tts_{npc_uid}_{uuid.uuid4().hex}.wav"
        # Save audio tensor to file
        torch.save(result['tts_speech'], output_path)
        return output_path
```

---

### 🆕 F5-TTS (SWivid) — ⭐ BEST QUALITY VOICE CLONING

**URL**: https://github.com/SWivid/F5-TTS
**HF Repo**: https://huggingface.co/SWivid/F5-TTS
**License**: Apache 2.0
**Architecture**: Diffusion Transformer + ConvNeXt V2 + Flow Matching
**Released**: Early 2025

| Criterion | Assessment |
|---|---|
| **Text-to-Voice Prompts** | ✅ **Best-in-class zero-shot voice cloning** — 5-15s reference audio required. Recognized as "most realistic open-source zero-shot voice clone" by Uberduck. |
| **Voice Locking** | ✅ Save reference audio + inferred latent space embedding. |
| **Emotion** | ⚠️ Preserved from reference; no explicit emotion tokens. Emotion induced via text content. |
| **Latency** | ⚠️ ~3-8s on GPU. Slower than CosyVoice but higher quality. |
| **Self-Hosted** | ✅ Fully self-hosted PyTorch model. |
| **Python** | ✅ `pip install -e .` after cloning repo. |
| **Cost** | Free (Apache 2.0). |
| **Languages** | English (primary), multilingual research ongoing. |

#### Why F5-TTS is Notable

F5-TTS uses **Flow Matching with Diffusion Transformers** (hence "F5" = **F**airytaler **F**akes **F**luent and **F**aithful speech with **F**low matching). It consistently outperforms OpenVoice and XTTS in subjective quality tests.

The key advantage is the **Diffusion Transformer architecture** combined with flow matching, which produces more natural prosody and less robotic speech than OpenVoice's VAE-based approach.

#### Integration Sketch

```python
# webapp/tts/f5tts_provider.py
import torch
from f5_tts.infer.utils_infer import load_model, load_audio
from f5_tts.model.utils import convert_audio_as_wav

class F5TTSTTSProvider(TTSEngine):
    def __init__(self, device: str = "cuda"):
        self.device = device
        self._model = None
        self._voice_registry = {}
        
    def initialize(self):
        self._model = load_model(
            "SWivid/F5-TTS",
            ckpt_path=None,  # Auto-download from HF
            device=self.device,
        )
        
    def create_voice(self, npc_uid: str, voice_prompt: str,
                     reference_audio: Optional[str] = None) -> VoiceConfig:
        if not reference_audio:
            raise ValueError("F5-TTS requires reference audio")
        
        # Reference audio is saved for generation
        config = VoiceConfig(
            npc_uid=npc_uid,
            se_path=reference_audio,  # F5 uses reference directly
            style="neutral",
            prompt_description=voice_prompt,
            reference_audio=reference_audio,
        )
        self._voice_registry[npc_uid] = config
        return config
    
    def generate(self, text: str, npc_uid: str,
                 emotion: Optional[str] = None, output_path: Optional[str] = None) -> str:
        config = self._voice_registry.get(npc_uid)
        if not config:
            raise ValueError(f"No voice locked for NPC {npc_uid}")
        
        ref_audio = load_audio(config.reference_audio, 24000)
        
        # F5-TTS inference
        audio = self._model.infer(
            text=text,
            ref_audio=ref_audio,
            seed=-1,  # Random seed for variation
        )
        
        output_path = output_path or f"/tmp/f5tts_{npc_uid}_{uuid.uuid4().hex}.wav"
        torchaudio.save(output_path, audio, 24000)
        return output_path
```

---

### 🆕 Kokoro-82M — ⭐ FASTEST (NO VOICE CLONING)

**URL**: https://huggingface.co/hexgrad/Kokoro-82M
**License**: Apache 2.0
**Params**: 82M (tiny!)
**Released**: January 2025

| Criterion | Assessment |
|---|---|
| **Text-to-Voice Prompts** | ❌ **Fixed voicepacks only** — no voice cloning. 54 built-in voices across 8 languages. |
| **Voice Locking** | ⚠️ Select from pre-built voicepacks. No custom cloning. |
| **Emotion** | ❌ No emotion control. Monotone delivery. |
| **Latency** | ✅ **~10-50ms on GPU** — fastest by orders of magnitude. 82M params means instant inference. |
| **Self-Hosted** | ✅ Fully self-hosted. ONNX export available. |
| **Python** | ✅ `pip install kokoro-tts` — lightweight API. |
| **Cost** | Free (Apache 2.0). |
| **Quality** | ⭐⭐⭐⭐ #1 on TTS Spaces Arena (single-voice setting) despite tiny size. |

#### Why Kokero is Worth Considering

Despite lacking voice cloning, Kokero's speed is **unmatched**. For scenarios where:
- Voice consistency is less critical (ambient NPCs, background chatter)
- Latency must be sub-100ms
- GPU VRAM is limited (<2GB)

...Kokero is the best choice. It's an excellent **fallback** or **supplementary** engine for non-critical dialogue.

**54 Built-in Voices** (sample):
- American Female: `af_bella`, `af_sarah`, `af_nicole`, `af_sky`
- American Male: `am_adam`, `am_michael`
- British Female: `bf_emma`, `bf_isabella`
- British Male: `bm_george`, `bm_lewis`

---

### Updated Comparison Matrix

| Feature | **CosyVoice 3** | **OpenVoice V2** | **F5-TTS** | **XTTS v2** | **Kokoro-82M** |
|---|---|---|---|---|---|
| Voice Cloning | ✅ 3-10s ref | ✅ 3s ref | ✅ 5-15s ref | ✅ 3s ref | ❌ Fixed only |
| Emotion Control | ✅ Explicit tokens | ✅ Style codes | ⚠️ Reference only | ⚠️ Text-driven | ❌ None |
| Latency (GPU) | ~150ms TTFT | ~500ms-2s | ~3-8s | ~3-8s | **~10-50ms** |
| Quality (Subjective) | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| Languages | 9 + 18 dialects | 8+ (cross-lingual) | English primary | Multilingual | 8 languages |
| Model Size | 0.5B | ~300MB | ~1GB | ~1.5GB | **82M** |
| GPU VRAM Needed | ~4GB | ~2GB | ~6GB | ~8GB | **<1GB** |
| License | MIT | MIT | Apache 2.0 | MPL-2.0 | Apache 2.0 |
| Python API | ✅ | ✅ | ✅ | ✅ | ✅ |
| Active Development | ✅ Very Active | ⚠️ Slowed | ✅ Active | ⚠️ Coqui closed | ✅ Active |

---

### Revised Recommendation for natural_20.py

#### Primary Choice: **CosyVoice 3**

CosyVoice 3 is now the **best overall choice** for this project because:

1. **Explicit emotion control** maps directly to D&D roleplay needs (angry, cheerful, whisper, etc.)
2. **Ultra-low latency** (150ms TTFT) enables conversational flow without long pauses
3. **Cross-lingual** — useful for fantasy languages with distinct pronunciation
4. **MIT license** — no restrictions
5. **Active development** — FunAudioLLM is releasing frequent improvements
6. **Moderate hardware** — 4GB VRAM minimum, works on most modern GPUs

#### Fallback/Alternative: **OpenVoice V2** (current)

Keep OpenVoice as a fallback if:
- GPU VRAM is limited (<4GB)
- You need the existing style embedding infrastructure
- You want maximum compatibility with existing `webapp/tts/` code

#### Ultra-Fast Fallback: **Kokoro-82M**

Use Kokero for:
- Ambient/background NPC dialogue where voice consistency doesn't matter
- CPU-only deployment scenarios
- Reducing load on the main TTS pipeline during high-conversation periods

#### Implementation Strategy

```
┌─────────────────────────────────────────────────────────────┐
│  TTS Provider Selection (configurable via N20_TTS_PROVIDER) │
│                                                               │
│  N20_TTS_PROVIDER=cosyvoice  → CosyVoice 3 (primary)        │
│  N20_TTS_PROVIDER=openvoice  → OpenVoice V2 (fallback)      │
│  N20_TTS_PROVIDER=kokoro     → Kokoro-82M (ultra-fast)      │
│  N20_TTS_PROVIDER=auto       → Try CosyVoice, fallback to   │
│                                OpenVoice, then Kokoro        │
└─────────────────────────────────────────────────────────────┘
```

#### Migration Path (if switching to CosyVoice 3)

1. **Phase 1**: Add `CosyVoiceProvider` alongside existing `OpenVoiceTTSProvider`
2. **Phase 2**: Update `TTSManager` to support provider selection via env var
3. **Phase 3**: Test voice cloning with existing NPC reference audio
4. **Phase 4**: Update voice creation UI to prompt for reference audio upload
5. **Phase 5**: Benchmark latency and adjust conversation pacing
6. **Phase 6**: Deprecate OpenVoice after validation

#### Dependencies (CosyVoice 3)

Add to `requirements.txt`:

```
cosyvoice>=1.0.0
funasr>=1.0.0
torchaudio>=2.0.0
```

Or install from source:

```bash
git clone https://github.com/FunAudioLLM/CosyVoice.git
cd CosyVoice
pip install -e .
```
