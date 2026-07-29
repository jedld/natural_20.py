#!/usr/bin/env bash
# Start vLLM-Omni, wait for health, register campaign voices, keep server in foreground.
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
BASE="${VLLM_OMNI_TTS_URL:-http://127.0.0.1:${PORT}}"
CAMPAIGN="${VLLM_REGISTER_CAMPAIGN:-../../user_levels/wild_sheep_chase}"
WAIT_SECS="${VLLM_REGISTER_WAIT_SECS:-180}"

echo "[vllm-omni-tts] starting sidecar (background)..."
./start.sh &
VLLM_PID=$!

cleanup() {
  if kill -0 "${VLLM_PID}" 2>/dev/null; then
    kill "${VLLM_PID}" 2>/dev/null || true
    wait "${VLLM_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

echo "[vllm-omni-tts] waiting for ${BASE}/v1/audio/voices (up to ${WAIT_SECS}s)..."
deadline=$((SECONDS + WAIT_SECS))
until curl -fsS "${BASE}/v1/audio/voices" >/dev/null 2>&1; do
  if ! kill -0 "${VLLM_PID}" 2>/dev/null; then
    echo "[vllm-omni-tts] server exited before healthcheck passed" >&2
    wait "${VLLM_PID}" || true
    exit 1
  fi
  if (( SECONDS >= deadline )); then
    echo "[vllm-omni-tts] timed out waiting for sidecar health" >&2
    exit 1
  fi
  sleep 2
done
echo "[vllm-omni-tts] sidecar healthy"

if [[ -n "${VLLM_REGISTER_CAMPAIGN:-}" ]]; then
  echo "[vllm-omni-tts] registering voices from ${CAMPAIGN}"
  "${ROOT}/scripts/register_campaign_voices.py" "${CAMPAIGN}"
else
  echo "[vllm-omni-tts] VLLM_REGISTER_CAMPAIGN unset; skipping voice registration"
fi

echo "[vllm-omni-tts] serving (pid=${VLLM_PID})"
wait "${VLLM_PID}"
