#!/bin/sh
# Launch ngrok + gunicorn using submodule layout.
ROOT="$(cd "$(dirname "$0")" && pwd)"
export N20_CAMPAIGNS_DIR="${N20_CAMPAIGNS_DIR:-$ROOT/user_levels}"
CAMPAIGN="${1:-$ROOT/user_levels/wild_sheep_chase}"
if [ -f "$ROOT/n20-webapp/webapp/start_ngrok.sh" ]; then
  exec "$ROOT/n20-webapp/webapp/start_ngrok.sh" "$CAMPAIGN"
fi
echo "start_ngrok.sh not found under n20-webapp/webapp/" >&2
exit 1
