# CosyVoice NPC Voice Installation Guide

## Quick Setup

```bash
# Create a dedicated Python 3.10+ virtual environment
python3 -m venv n20-tts
source n20-tts/bin/activate

# Run the automated installer
bash scripts/setup_cosyvoice.sh
```

## Manual Installation Steps

If you need to troubleshoot or install manually:

### 1. Install PyTorch with CUDA

**RTX 50-series (Blackwell / sm_120)** — requires CUDA 12.8 wheels (avoid 2.10+ torchaudio; it needs TorchCodec):

```bash
pip install torch==2.8.0+cu128 torchaudio==2.8.0+cu128 --index-url https://download.pytorch.org/whl/cu128
pip install soundfile
```

**Older GPUs (Ampere / Ada, sm_86 and below)** — CUDA 12.1 wheels:

```bash
pip install torch==2.3.1 torchaudio==2.3.1 --extra-index-url https://download.pytorch.org/whl/cu121
```

`scripts/setup_cosyvoice.sh` auto-detects Blackwell GPUs and picks the right wheel.

### 2. Clone CosyVoice Repository

```bash
git clone --recursive https://github.com/FunAudioLLM/CosyVoice.git third_party/CosyVoice
cd third_party/CosyVoice
git submodule update --init --recursive
```

### 3. Create pyproject.toml (required for pip install)

The FunAudioLLM repo lacks `setup.py` or `pyproject.toml`. Create one:

```toml
[build-system]
requires = ["setuptools>=61", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "cosyvoice"
version = "3.0.0"
description = "FunAudioLLM CosyVoice TTS"
requires-python = ">=3.8"

[tool.setuptools.packages.find]
include = ["cosyvoice*"]
```

### 4. Install Dependencies

```bash
pip install -r requirements.txt
pip install -e .
```

### 5. Fix Dependency Version Conflicts

| Conflict | Solution |
|----------|----------|
| onnxruntime 1.27.0 requires CUDA 13 | `pip install onnxruntime==1.18.0` |
| NumPy 2.x breaks onnxruntime 1.18 | `pip install numpy==1.26.4` |
| torchvision 0.28.0 requires torch 2.13.0 | `pip uninstall -y torchvision` |
| transformers 5.x requires torch 2.4+ | `pip install transformers==4.51.3` |
| numba 0.66+ needs coverage.types | `pip install 'coverage>=7.0'` |

### 6. Download Models

```bash
pip install huggingface-hub
python3 -c "
from huggingface_hub import snapshot_download
import os
cache_dir = '/tmp/natural20_tts'
os.makedirs(cache_dir, exist_ok=True)
snapshot_download('FunAudioLLM/Fun-CosyVoice3-0.5B-2512', local_dir=os.path.join(cache_dir, 'Fun-CosyVoice3-0.5B-2512'))
"
```

## Verification

```python
# Test CosyVoice import
from cosyvoice.cli.cosyvoice import CosyVoice
print("CosyVoice import successful!")

# Test Provider initialization
from webapp.tts.cosyvoice_provider import CosyVoiceProvider
provider = CosyVoiceProvider(device='cpu', cache_dir='/tmp/natural20_tts')
print(f"Provider status: {provider.status}")
```

## Enable in Webapp

Add to `webapp/.env`:

```
TTS_PROVIDER=cosyvoice
TTS_ENABLED=1
TTS_DEVICE=gpu
# Optional: pin TTS to a specific GPU index (e.g. 1 for a second Blackwell card)
# TTS_CUDA_DEVICE=1
TTS_DEFAULT_ACCENT=american
N20_TTS_CACHE_DIR=/tmp/natural20_tts
```

Per-NPC voice settings go under map/NPC YAML (`gender` plus `voice:`):

```yaml
gender: female
voice:
  gender: female
  prompt: "Soft ghostly child voice"
  style: calm
  accent: british          # american | british | romanian | eastern european | ...
  language: en
  locked: true
```

Set `gender` (or `voice.gender`) explicitly when the voice prompt alone might be ambiguous
(e.g. "gravelly barkeeper" without a gender cue). The TTS layer uses this to pick the
reference speaker clip and CosyVoice instruct delivery.

NPC LLM replies can also steer delivery with control tags (stripped from spoken text):

```text
[VOLUME: whisper] [EMOTION: fearful] [TTS: trembling, barely holding back tears]
Please! You have to be quiet!
```

- `[EMOTION: …]` — short mood token (`fearful`, `angry`, `whisper`, …)
- `[TTS: …]` / `[TTS_INSTRUCT: …]` — free-form CosyVoice acting notes

CosyVoice3 uses `inference_instruct2` when an accent or TTS instruct is set so the stock Chinese
reference clip does not force a Mandarin accent. Set `TTS_DEFAULT_ACCENT=none` to
keep model-native pronunciation for NPCs without an explicit `voice.accent`.

Restart the Flask/gunicorn process after changing `.env`. On startup you should see
`[TTS] Attached TTS manager` / `Initialized with provider=...`. If CosyVoice/OpenVoice
cannot load, the manager automatically falls back to `mock_cosyvoice` so the replay
speaker icon still works (placeholder audio).

In the JRPG dialog / local conversation panel, NPC lines with TTS include a speaker
button to replay the clip.

## System Requirements

- **Python**: 3.10+ (3.11 recommended)
- **GPU**: NVIDIA RTX 3090+ (24GB VRAM ideal) for GPU acceleration
- **CPU**: Will work without GPU (slower)
- **Disk**: ~15GB (models + dependencies)
- **CUDA**: 12.1 (cu121 wheels) or 12.8+ (cu128 wheels for RTX 50-series / sm_120)

## Known Issues

### Bus Error (core dumped)
- **Cause**: Corrupted torch native libraries from partial install
- **Fix**: `pip uninstall -y torch torchaudio triton && pip install torch==2.3.1 torchaudio==2.3.1 --extra-index-url https://download.pytorch.org/whl/cu121`

### ModuleNotFoundError: No module named 'matcha' / 'pyarrow' / 'pkg_resources'
- **Cause**: CosyVoice runtime deps not fully installed, or Matcha-TTS not on `PYTHONPATH`
- **Fix**:
  ```bash
  pip install 'setuptools<81' pyarrow
  export PYTHONPATH="$PWD:$PWD/third_party/CosyVoice:$PWD/third_party/CosyVoice/third_party/Matcha-TTS"
  ```
  `webapp/start_web.sh` sets this `PYTHONPATH` automatically.

### CosyVoice3 AssertionError: `<|endofprompt|>` not detected
- **Cause**: CosyVoice3 requires prompt/instruct text to include `<|endofprompt|>`
- **Fix**: Handled in `CosyVoiceProvider` (`You are a helpful assistant.<|endofprompt|>...`)

### `cv2.__spec__ is None`
- **Cause**: Repo-root `sitecustomize.py` used to stub a blank `cv2` whenever the repo was on `PYTHONPATH` (including `start_web.sh`). CosyVoice/torchvision require a real OpenCV module.
- **Fix**: Stub is pytest-only now. Install: `pip install 'opencv-python-headless==4.10.0.84' 'numpy==1.26.4'` (OpenCV 5 pulls NumPy 2.x and breaks onnxruntime). `start_web.sh` attempts this automatically.

### AttributeError: `_ARRAY_API not found`
- **Cause**: NumPy 2.x incompatibility with onnxruntime 1.18 (often after installing OpenCV)
- **Fix**: `pip install numpy==1.26.4`

### RTX 50-series / sm_120 CUDA warnings / silent failed inference
- **Cause**: PyTorch wheels built with CUDA 12.1–12.6 do not include sm_120 kernels
- **Fix**: Install PyTorch cu128: `pip install torch==2.8.0+cu128 torchaudio==2.8.0+cu128 --index-url https://download.pytorch.org/whl/cu128` and `pip install soundfile` (or re-run `bash scripts/setup_cosyvoice.sh`). On multi-GPU hosts, set `TTS_CUDA_DEVICE=1` (or the index of your Blackwell card) in `webapp/.env`.

### TTS plays a short beep instead of speech
- **Cause**: CosyVoice inference failed and fell back to the mock 440 Hz placeholder tone. Common with TorchAudio 2.9+ / 2.10, which require TorchCodec for `torchaudio.load`/`save`.
- **Fix**: Use torch/torchaudio 2.8.0+cu128 (see above) or ensure `soundfile` is installed — `CosyVoiceProvider` patches torchaudio to use soundfile automatically on startup.

### ImportError: libcudart.so.13
- **Cause**: onnxruntime compiled for CUDA 13, system has CUDA 12
- **Fix**: `pip install onnxruntime==1.18.0`

### AttributeError: module 'coverage' has no attribute 'types'
- **Cause**: `numba` 0.66+ (pulled in by `openai-whisper` for CosyVoice) imports `coverage.types`, but the `coverage` package is not installed in the TTS venv
- **Fix**: `pip install 'coverage>=7.0'`
- **Note**: `webapp/start_web.sh` and `scripts/setup_cosyvoice.sh` install this automatically

### AttributeError: _ARRAY_API not found
- **Cause**: NumPy 2.x incompatibility with onnxruntime 1.18
- **Fix**: `pip install numpy==1.26.4`

### module 'torch.library' has no attribute 'register_fake'
- **Cause**: torchvision 0.28.0 requires torch 2.13.0
- **Fix**: `pip uninstall -y torchvision`
