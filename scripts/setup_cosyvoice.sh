#!/bin/bash
# Install the official FunAudioLLM/CosyVoice for NPC voice synthesis.
# Usage: bash scripts/setup_cosyvoice.sh
#
# Requirements:
#   - CUDA GPU strongly recommended (RTX 3090+ ideal)
#   - Python 3.10 virtual environment
#   - ~15GB disk space (models + dependencies)
#
# IMPORTANT: This installs from the FunAudioLLM GitHub repo, NOT PyPI.
# The PyPI "cosyvoice" package is a completely different project.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
COSYVOICE_DIR="${SCRIPT_DIR}/third_party/CosyVoice"
CACHE_DIR="${N20_TTS_CACHE_DIR:-/tmp/natural20_tts}"

# Detect pip command
if command -v pip &>/dev/null; then
  PIP_CMD="pip"
else
  PIP_CMD="pip3"
fi

echo "================================================"
echo "  CosyVoice Installer (FunAudioLLM version)"
echo "================================================"
echo ""
echo "Target environment:"
echo "  Python: $(python3 --version 2>&1 || echo 'unknown')"
echo "  pip: ${PIP_CMD}"
echo "  Install dir: ${COSYVOICE_DIR}"
echo "  Model cache: ${CACHE_DIR}"
echo ""

# ── Step 1: Remove wrong PyPI package if present ───────────────────────────
echo "[Step 1] Checking for wrong cosyvoice package..."
if ${PIP_CMD} show cosyvoice 2>/dev/null | grep -q "Home-page: https://github.com/lucasjinreal"; then
  echo "[Step 1] Found WRONG cosyvoice package (PyPI/lucasjinreal). Removing..."
  ${PIP_CMD} uninstall -y cosyvoice
else
  echo "[Step 1] No wrong cosyvoice package found."
fi
echo ""

# ── Step 2: Clone (if not already present) ─────────────────────────────────
echo "[Step 2] Setting up CosyVoice repository..."
if [ -d "${COSYVOICE_DIR}/.git" ]; then
  echo "[Step 2] Repository already exists at ${COSYVOICE_DIR}"
  echo "[Step 2] Pulling latest changes..."
  cd "${COSYVOICE_DIR}"
  git pull || true
else
  mkdir -p "$(dirname "${COSYVOICE_DIR}")"
  echo "[Step 2] Cloning FunAudioLLM/CosyVoice..."
  cd "$(dirname "${COSYVOICE_DIR}")"
  git clone --recursive https://github.com/FunAudioLLM/CosyVoice.git
fi

# Ensure submodules are initialized
cd "${COSYVOICE_DIR}"
git submodule update --init --recursive || true
echo ""

# ── Step 3: Install PyTorch (CUDA) ─────────────────────────────────────────
echo "[Step 3] Installing PyTorch with CUDA support..."
TORCH_CUDA_INDEX="https://download.pytorch.org/whl/cu121"
TORCH_VERSION="2.3.1"
TORCHAUDIO_VERSION="2.3.1"
if command -v nvidia-smi &>/dev/null; then
  if nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null | grep -qE '^12\.'; then
    echo "[Step 3] Blackwell GPU (sm_120) detected — using PyTorch cu128."
    TORCH_CUDA_INDEX="https://download.pytorch.org/whl/cu128"
    TORCH_VERSION="2.8.0"
    TORCHAUDIO_VERSION="2.8.0"
  fi
fi
${PIP_CMD} install "torch==${TORCH_VERSION}" "torchaudio==${TORCHAUDIO_VERSION}" \
  --index-url "${TORCH_CUDA_INDEX}" 2>&1 | tail -5
echo ""

# ── Step 4: Install system dependencies (Ubuntu/Debian) ────────────────────
echo "[Step 4] Installing system dependencies..."
if command -v apt-get &>/dev/null; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq sox libsox-dev 2>/dev/null || true
elif command -v yum &>/dev/null; then
  sudo yum install -y sox sox-devel 2>/dev/null || true
fi
echo ""

# ── Step 5: Install from the CosyVoice source tree ─────────────────────────
echo "[Step 5] Installing CosyVoice dependencies..."
cd "${COSYVOICE_DIR}"

# Create pyproject.toml if missing (FunAudioLLM repo lacks setup files)
if [ ! -f pyproject.toml ]; then
  cat > pyproject.toml << 'TOMLEOF'
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

[project.scripts]
cosyvoice = "cosyvoice.cli.cosyvoice:main"
TOMLEOF
  echo "[Step 5] Created pyproject.toml for editable install."
fi

# Install requirements first
if [ -f requirements.txt ]; then
  echo "[Step 5] Installing from requirements.txt..."
  ${PIP_CMD} install -r requirements.txt 2>&1 | tail -5 || true
fi

# Install CosyVoice in editable mode
echo "[Step 5] Installing CosyVoice package..."
if [ -f setup.py ]; then
  ${PIP_CMD} install -e . 2>&1 | tail -5
elif [ -f pyproject.toml ]; then
  ${PIP_CMD} install -e . 2>&1 | tail -5 || ${PIP_CMD} install -e . 2>&1 | tail -5
else
  echo "[Step 5] WARNING: No setup.py or pyproject.toml found."
  echo "         CosyVoice may not be importable as a package."
fi
echo ""

# ── Step 6: Fix dependency version conflicts ──────────────────────────────
echo "[Step 6] Fixing dependency version conflicts..."
# onnxruntime 1.27.0 requires CUDA 13; downgrade to 1.18.0 for CUDA 12
${PIP_CMD} install onnxruntime==1.18.0 2>&1 | tail -3 || true
# NumPy 2.x breaks onnxruntime 1.18; downgrade to 1.26.4
${PIP_CMD} install numpy==1.26.4 2>&1 | tail -3 || true
# torchvision 0.28.0 requires torch 2.13.0; uninstall (not needed by CosyVoice)
${PIP_CMD} uninstall -y torchvision 2>&1 | tail -3 || true
# transformers 5.x requires torch 2.4+; downgrade to 4.51.3 for torch 2.3.1
${PIP_CMD} install transformers==4.51.3 2>&1 | tail -3 || true
# numba 0.66+ (via openai-whisper) imports coverage.types at import time
${PIP_CMD} install 'coverage>=7.0' 2>&1 | tail -3 || true
${PIP_CMD} install soundfile 2>&1 | tail -3 || true
${PIP_CMD} install hyperpyyaml 2>&1 | tail -3 || true
echo "[Step 6] Dependency conflicts resolved."
echo ""

# ── Step 7: Download pretrained models ─────────────────────────────────────
echo "[Step 7] Downloading pretrained models (this may take several minutes)..."
mkdir -p "${CACHE_DIR}"

python3 - <<'PYEOF'
import os
import sys

cache_dir = os.environ.get("N20_TTS_CACHE_DIR", "/tmp/natural20_tts")
os.makedirs(cache_dir, exist_ok=True)

print("[Model Download] This will download ~10GB of models from HuggingFace...")

try:
    from huggingface_hub import snapshot_download

    # Download CosyVoice text processing models
    print("[Model Download] Downloading CosyVoice-ttsfrd...")
    snapshot_download(
        "FunAudioLLM/CosyVoice-ttsfrd",
        local_dir=os.path.join(cache_dir, "CosyVoice-ttsfrd"),
        ignore_patterns=["*.bin", "*.pt"],  # Skip large checkpoint files if possible
    )

    # Download the main model
    print("[Model Download] Downloading CosyVoice-3-0.5B...")
    snapshot_download(
        "FunAudioLLM/Fun-CosyVoice3-0.5B-2512",
        local_dir=os.path.join(cache_dir, "Fun-CosyVoice3-0.5B-2512"),
    )

    print("[Model Download] Models downloaded successfully!")

except Exception as e:
    print(f"[Model Download] Partial failure: {e}")
    print("[Model Download] Models will be downloaded lazily on first use.")
PYEOF

echo ""

# ── Step 8: Verify installation ────────────────────────────────────────────
echo "[Step 8] Verifying installation..."
echo ""

# Try the import path expected by webapp/tts/cosyvoice_provider.py
python3 -c "from cosyvoice.cli.cosyvoice import CosyVoice; print('[Success] cosyvoice.cli.cosyvoice imports correctly!')" 2>&1 || {
  echo "[Warning] Import failed. This may be normal if some dependencies are missing."
  echo "          The provider will fall back to OpenVoice or mock_cosyvoice."
  echo ""
  echo "Common issues:"
  echo "  - torch not installed (Ampere/Ada): pip install torch==2.3.1 torchaudio==2.3.1 --extra-index-url https://download.pytorch.org/whl/cu121"
  echo "  - torch not installed (Blackwell/sm_120): pip install torch==2.8.0+cu128 torchaudio==2.8.0+cu128 --index-url https://download.pytorch.org/whl/cu128"
  echo "  - Missing submodules: cd ${COSYVOICE_DIR} && git submodule update --init --recursive"
  echo "  - NumPy version conflict: pip install numpy==1.26.4"
  echo "  - onnxruntime CUDA mismatch: pip install onnxruntime==1.18.0"
  echo "  - transformers version: pip install transformers==4.51.3"
}

echo ""
echo "================================================"
echo "  CosyVoice Installation Complete"
echo "================================================"
echo ""
echo "To enable CosyVoice, set in webapp/.env:"
echo "  TTS_PROVIDER=cosyvoice"
echo ""
echo "Model cache directory: ${CACHE_DIR}"
echo ""
echo "If import fails, try:"
echo "  cd ${COSYVOICE_DIR}"
echo "  git submodule update --init --recursive"
echo "  ${PIP_CMD} install -e ."
echo ""
echo "================================================"
