#!/bin/bash
# One-shot: launch the Natural20 webapp in production mode (gunicorn) with ngrok
# inside a detached tmux session, then wait for and print the public ngrok URL.
#
# Usage: ./start_production_ngrok.sh [campaign_dir]
#   campaign_dir defaults to user_levels/wild_sheep_chase (same as start_ngrok.sh)
#
# The tmux session is named "n20":
#   - pane 0: gunicorn webapp (started via start_ngrok.sh)
#   - pane 1: ngrok http 5001
#
# Attach later with: tmux attach -t n20
# Kill with:         tmux kill-session -t n20

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
CAMPAIGN="${1:-$ROOT/user_levels/wild_sheep_chase}"
SESSION_NAME="n20"
NGROK_PORT=5001
WAIT_SECONDS="${NGROK_WAIT_SECONDS:-90}"

# Abort early if a session with this name is already running.
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
  echo "tmux session '$SESSION_NAME' already exists."
  echo "  attach: tmux attach -t $SESSION_NAME"
  echo "  kill:   tmux kill-session -t $SESSION_NAME"
  exit 1
fi

# 1. Fresh detached session; pane 0 runs the production webapp (gunicorn).
tmux new-session -d -s "$SESSION_NAME" -c "$ROOT"
tmux send-keys -t "$SESSION_NAME" "$ROOT/start_ngrok.sh $CAMPAIGN" C-m

# 2. Second pane runs ngrok on the webapp port.
tmux split-window -t "$SESSION_NAME" -v -c "$ROOT"
tmux send-keys -t "$SESSION_NAME.1" "ngrok http $NGROK_PORT" C-m

echo "Started tmux session '$SESSION_NAME':"
echo "  pane 0: start_ngrok.sh $CAMPAIGN"
echo "  pane 1: ngrok http $NGROK_PORT"

# 3. Poll the ngrok pane until a forwarding URL shows up (or timeout).
url=""
for _ in $(seq 1 "$WAIT_SECONDS"); do
  pane_output="$(tmux capture-pane -t "$SESSION_NAME.1" -p 2>/dev/null || true)"
  url="$(printf '%s\n' "$pane_output" | grep -oE 'https://[a-z0-9]+\.ngrok\.(io|free\.(app|dev))' | head -1 || true)"
  if [ -n "$url" ]; then
    break
  fi
  sleep 1
done

if [ -n "$url" ]; then
  echo ""
  echo "ngrok URL: $url"
else
  echo ""
  echo "WARNING: no ngrok URL detected after ${WAIT_SECONDS}s."
  echo "Check pane 1: tmux capture-pane -t $SESSION_NAME.1 -p"
  # Show recent pane 0 output to help diagnose webapp failures.
  echo "--- webapp pane (last lines) ---"
  tmux capture-pane -t "$SESSION_NAME.0" -p -S -30 | tail -30 || true
fi

echo ""
echo "Attach to view both panes: tmux attach -t $SESSION_NAME"
