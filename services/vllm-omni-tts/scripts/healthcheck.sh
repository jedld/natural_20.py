#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

PORT="${VLLM_PORT:-8091}"
BASE="${VLLM_OMNI_TTS_URL:-http://127.0.0.1:${PORT}}"

echo "[healthcheck] GET ${BASE}/v1/audio/voices"
curl -fsS "${BASE}/v1/audio/voices" | head -c 500
echo
echo "[healthcheck] OK"
