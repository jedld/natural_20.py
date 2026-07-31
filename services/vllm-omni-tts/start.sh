#!/usr/bin/env bash
# Start vLLM-Omni with Qwen3-TTS Base (voice clone + streaming).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

PORT="${VLLM_PORT:-8091}"
MODEL="${VLLM_MODEL:-Qwen/Qwen3-TTS-12Hz-1.7B-Base}"
GPU_UTIL="${VLLM_GPU_MEMORY_UTILIZATION:-0.35}"

VLLM_BIN=""
PYTHON_BIN=""
if [[ -x "${ROOT}/.venv/bin/vllm" ]]; then
  VLLM_BIN="${ROOT}/.venv/bin/vllm"
  PYTHON_BIN="${ROOT}/.venv/bin/python"
elif command -v vllm >/dev/null 2>&1; then
  VLLM_BIN="vllm"
  PYTHON_BIN="python3"
else
  echo "[vllm-omni-tts] 'vllm' not found." >&2
  echo "Run: ./install.sh   (or: pip install -r requirements.txt in an active venv)" >&2
  exit 127
fi

DEPLOY_CONFIG="${VLLM_DEPLOY_CONFIG:-}"
if [[ -z "${DEPLOY_CONFIG}" ]]; then
  # find_spec avoids importing vllm_omni (its import logs to stdout and breaks capture).
  DEPLOY_CONFIG="$("${PYTHON_BIN}" -c "
import importlib.util
import pathlib
import sys

spec = importlib.util.find_spec('vllm_omni')
if spec and spec.origin:
    path = pathlib.Path(spec.origin).resolve().parent / 'deploy' / 'qwen3_tts.yaml'
    if path.is_file():
        print(path)
        sys.exit(0)
sys.exit(1)
" 2>/dev/null || true)"
fi
if [[ -z "${DEPLOY_CONFIG}" || ! -f "${DEPLOY_CONFIG}" ]]; then
  echo "[vllm-omni-tts] deploy config not found (set VLLM_DEPLOY_CONFIG in .env)" >&2
  exit 1
fi

EXTRA_ARGS=()
if [[ "${VLLM_ENFORCE_EAGER:-1}" == "1" ]]; then
  EXTRA_ARGS+=(--enforce-eager)
fi

if [[ -n "${CUDA_VISIBLE_DEVICES:-}" ]]; then
  export CUDA_VISIBLE_DEVICES
fi
# Avoid wrong GPU pick when multiple NVIDIA cards are present.
export CUDA_DEVICE_ORDER="${CUDA_DEVICE_ORDER:-PCI_BUS_ID}"

echo "[vllm-omni-tts] model=${MODEL} port=${PORT} cuda=${CUDA_VISIBLE_DEVICES:-default}"
echo "[vllm-omni-tts] deploy_config=${DEPLOY_CONFIG}"

exec "${VLLM_BIN}" serve "${MODEL}" \
  --deploy-config "${DEPLOY_CONFIG}" \
  --omni \
  --port "${PORT}" \
  --trust-remote-code \
  --gpu-memory-utilization "${GPU_UTIL}" \
  "${EXTRA_ARGS[@]}"
