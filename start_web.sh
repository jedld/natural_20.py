#!/bin/sh
# Launch the VTT from the engine monorepo (n20-webapp + user_levels submodules).
ROOT="$(cd "$(dirname "$0")" && pwd)"
export N20_CAMPAIGNS_DIR="${N20_CAMPAIGNS_DIR:-$ROOT/user_levels}"
if [ $# -eq 0 ]; then
  set -- wild_sheep_chase
fi
exec "$ROOT/n20-webapp/start_web.sh" "$@"
