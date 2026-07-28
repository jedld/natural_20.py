#!/bin/sh
# Standalone webapp launcher (n20-webapp repository).
WEBAPP_DIR="$(cd "$(dirname "$0")/webapp" && pwd)"
REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"

if [ -f "$WEBAPP_DIR/.env" ]; then
    set -a
    . "$WEBAPP_DIR/.env"
    set +a
fi

EDIT_MODE=0
if [ -n "$1" ] && [ "$1" = "--edit" ]; then
    EDIT_MODE=1
    shift
fi
if [ -n "$1" ]; then
    TEMPLATE_DIR="$1"
else
    TEMPLATE_DIR="${TEMPLATE_DIR:-../natural_20.py/templates}"
fi
export N20_EDIT_MODE="$EDIT_MODE"

PORT="${FLASK_RUN_PORT:-${PORT:-5001}}"
export FLASK_RUN_PORT="$PORT"
export FLASK_RUN_HOST="${FLASK_RUN_HOST:-0.0.0.0}"
export FLASK_DEBUG=0
export N20_BOOT_ID="${N20_BOOT_ID:-boot-$(date +%s)-$$}"

N20_PYTHON="${N20_PYTHON:-python}"
export PYTHONPATH="$REPO_ROOT:$WEBAPP_DIR${PYTHONPATH:+:$PYTHONPATH}"

# Resolve TEMPLATE_DIR relative to repo root, webapp/, or N20_CAMPAIGNS_DIR slug.
case "$TEMPLATE_DIR" in
  /*) ;;
  *)
    if [ -n "${N20_CAMPAIGNS_DIR:-}" ] && [ -f "$N20_CAMPAIGNS_DIR/$TEMPLATE_DIR/index.json" ]; then
      TEMPLATE_DIR="$(cd "$N20_CAMPAIGNS_DIR/$TEMPLATE_DIR" && pwd)"
    elif [ -d "$REPO_ROOT/$TEMPLATE_DIR" ]; then
      TEMPLATE_DIR="$(cd "$REPO_ROOT/$TEMPLATE_DIR" && pwd)"
    elif [ -d "$WEBAPP_DIR/$TEMPLATE_DIR" ]; then
      TEMPLATE_DIR="$(cd "$WEBAPP_DIR/$TEMPLATE_DIR" && pwd)"
    fi
    ;;
esac
export TEMPLATE_DIR="$TEMPLATE_DIR"

cd "$REPO_ROOT" || exit 1

if [ "${N20_USE_GUNICORN:-}" = "1" ]; then
  exec "$N20_PYTHON" -m gunicorn \
    --chdir "$WEBAPP_DIR" \
    --worker-class eventlet \
    --workers 1 \
    --bind "$FLASK_RUN_HOST:$PORT" \
    --timeout 120 \
    app:app
fi

exec "$N20_PYTHON" -m webapp.app
