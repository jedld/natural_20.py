#!/usr/bin/env bash
# Bootstrap standalone n20-webapp and n20-campaigns repositories from the engine monorepo.
#
# Usage:
#   ./scripts/split_repositories/bootstrap.sh [TARGET_PARENT_DIR]
#
# Creates:
#   $TARGET_PARENT_DIR/n20-webapp/     — Flask VTT (depends on natural20 pip package)
#   $TARGET_PARENT_DIR/n20-campaigns/  — Campaign content (user_levels)
#
# The engine repo (this checkout) remains at natural_20.py and is installed editable:
#   pip install -e /path/to/natural_20.py
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TARGET_PARENT="${1:-$(cd "$ENGINE_ROOT/.." && pwd)}"
WEBAPP_REPO="$TARGET_PARENT/n20-webapp"
CAMPAIGNS_REPO="$TARGET_PARENT/n20-campaigns"
TEMPLATES_DIR="$SCRIPT_DIR/templates"

echo "Engine repo:  $ENGINE_ROOT"
echo "Target dir:   $TARGET_PARENT"
echo "Webapp repo:  $WEBAPP_REPO"
echo "Campaigns:    $CAMPAIGNS_REPO"
echo

if [[ -e "$WEBAPP_REPO" ]] || [[ -e "$CAMPAIGNS_REPO" ]]; then
  echo "Refusing to overwrite existing directories. Remove them first or pick another TARGET_PARENT_DIR." >&2
  exit 1
fi

rsync_common=( -a --exclude '__pycache__' --exclude '*.pyc' --exclude '.pytest_cache' )

echo "==> Creating n20-webapp"
mkdir -p "$WEBAPP_REPO/tests"
rsync "${rsync_common[@]}" "$ENGINE_ROOT/webapp/" "$WEBAPP_REPO/webapp/"
rsync "${rsync_common[@]}" "$ENGINE_ROOT/tests/webapp/" "$WEBAPP_REPO/tests/webapp/"
rsync "${rsync_common[@]}" "$ENGINE_ROOT/scripts/minify.mjs" "$WEBAPP_REPO/scripts/"
rsync "${rsync_common[@]}" "$ENGINE_ROOT/webapp/scripts/" "$WEBAPP_REPO/webapp/scripts/"
cp "$ENGINE_ROOT/package.json" "$WEBAPP_REPO/package.json"
cp "$ENGINE_ROOT/jest.setup.js" "$WEBAPP_REPO/jest.setup.js" 2>/dev/null || true
cp "$TEMPLATES_DIR/webapp/README.md" "$WEBAPP_REPO/README.md"
cp "$TEMPLATES_DIR/webapp/pyproject.toml" "$WEBAPP_REPO/pyproject.toml"
cp "$TEMPLATES_DIR/webapp/requirements.txt" "$WEBAPP_REPO/requirements.txt"
cp "$TEMPLATES_DIR/webapp/Dockerfile" "$WEBAPP_REPO/Dockerfile"
cp "$TEMPLATES_DIR/webapp/.gitignore" "$WEBAPP_REPO/.gitignore"
cp "$TEMPLATES_DIR/webapp/start_web.sh" "$WEBAPP_REPO/start_web.sh"
cp "$TEMPLATES_DIR/webapp/env.example" "$WEBAPP_REPO/webapp/env.example"
mkdir -p "$WEBAPP_REPO/.github/workflows"
cp "$TEMPLATES_DIR/webapp/python-tests.yml" "$WEBAPP_REPO/.github/workflows/python-tests.yml"
cp "$TEMPLATES_DIR/webapp/js-tests.yml" "$WEBAPP_REPO/.github/workflows/js-tests.yml"
chmod +x "$WEBAPP_REPO/start_web.sh"

# Patch package.json paths for standalone layout (webapp/ stays under repo root).
python3 - <<'PY' "$WEBAPP_REPO/package.json"
import json, sys
path = sys.argv[1]
with open(path) as f:
    data = json.load(f)
data["name"] = "n20-webapp"
with open(path, "w") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
PY

echo "==> Creating n20-campaigns"
mkdir -p "$CAMPAIGNS_REPO"
if [[ -d "$ENGINE_ROOT/user_levels" ]]; then
  rsync "${rsync_common[@]}" --exclude '.git' "$ENGINE_ROOT/user_levels/" "$CAMPAIGNS_REPO/"
fi
cp "$TEMPLATES_DIR/campaigns/README.md" "$CAMPAIGNS_REPO/README.md"
cp "$TEMPLATES_DIR/campaigns/.gitignore" "$CAMPAIGNS_REPO/.gitignore"
cp "$TEMPLATES_DIR/campaigns/.gitattributes" "$CAMPAIGNS_REPO/.gitattributes"

echo "==> Initializing git repositories"
for repo in "$WEBAPP_REPO" "$CAMPAIGNS_REPO"; do
  (cd "$repo" && git init -q && git add -A && git commit -q -m "Initial import from natural_20.py monorepo split.")
done

cat <<EOF

Done.

Next steps:
  1. Install the engine (editable) from this repo:
       pip install -e "$ENGINE_ROOT"

  2. Install the webapp:
       cd "$WEBAPP_REPO"
       pip install -e ".[dev]"
       npm install

  3. Point the webapp at campaigns:
       export N20_CAMPAIGNS_DIR="$CAMPAIGNS_REPO"
       ./start_web.sh wild_sheep_chase
     Or use an absolute path:
       ./start_web.sh "$CAMPAIGNS_REPO/wild_sheep_chase"

  4. Create remote repos and push:
       cd "$WEBAPP_REPO" && git remote add origin <webapp-remote-url> && git push -u origin HEAD
       cd "$CAMPAIGNS_REPO" && git remote add origin <campaigns-remote-url> && git push -u origin HEAD

  5. After verifying the split, remove webapp/ and user_levels/ from the engine repo
     (see docs/REPOSITORY_SPLIT.md).

EOF
