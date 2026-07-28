#!/usr/bin/env bash
# Create .venv and install vLLM + vLLM-Omni for the TTS sidecar.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

python -m pip install -U pip wheel
python -m pip install -r requirements.txt

if ! command -v vllm >/dev/null 2>&1; then
  echo "Install finished but 'vllm' CLI is missing from .venv/bin." >&2
  exit 1
fi

echo "[install] OK: $(vllm --version 2>/dev/null || echo vllm)"
echo "[install] Start with: ./start.sh"
