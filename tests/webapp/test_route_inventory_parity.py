"""
Route inventory parity test.

Compares the current Flask URL map against the baseline artifact captured
before the refactor began.  Any added, removed, or changed route will
cause this test to fail, ensuring the refactor does not alter the public
API surface.
"""
import json
import os
import sys

# Ensure webapp and project root are importable (app.py imports `utils` from webapp/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WEBAPP_DIR = os.path.join(PROJECT_ROOT, 'webapp')
for _dir in (WEBAPP_DIR, PROJECT_ROOT):
    if _dir not in sys.path:
        sys.path.insert(0, _dir)

template_root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'templates'))
os.environ.setdefault('TEMPLATE_DIR', template_root)

# Import app module — must happen after path setup
from webapp.app import app  # noqa: E402

# Baseline artifact location (relative to project root).
_ARTIFACTS_DIR = os.path.join(
    PROJECT_ROOT,
    'plans',
    'artifacts',
)
_ROUTES_BASELINE = os.path.join(_ARTIFACTS_DIR, 'routes_baseline.json')


def _load_baseline():
    with open(_ROUTES_BASELINE) as f:
        return json.load(f)


def _capture_current_routes():
    """Return a sorted list of route dicts from the live app."""
    routes = []
    for rule in sorted(app.url_map.iter_rules(), key=lambda r: (r.rule, r.endpoint)):
        routes.append({
            "rule": rule.rule,
            "endpoint": rule.endpoint,
            "methods": sorted(rule.methods),
        })
    return routes


class TestRouteInventoryParity:
    """Assert the live route inventory matches the baseline."""

    baseline = _load_baseline()
    current = _capture_current_routes()

    def test_route_count_matches(self):
        assert len(self.current) == len(self.baseline), (
            f"Route count mismatch: expected {len(self.baseline)}, got {len(self.current)}"
        )

    def test_no_missing_routes(self):
        current_keys = {(r["rule"], r["endpoint"]) for r in self.current}
        baseline_keys = {(r["rule"], r["endpoint"]) for r in self.baseline}
        missing = baseline_keys - current_keys
        assert not missing, f"Routes present in baseline but missing now: {sorted(missing)}"

    def test_no_extra_routes(self):
        current_keys = {(r["rule"], r["endpoint"]) for r in self.current}
        baseline_keys = {(r["rule"], r["endpoint"]) for r in self.baseline}
        extra = current_keys - baseline_keys
        assert not extra, f"Routes present now but not in baseline: {sorted(extra)}"

    def test_methods_match(self):
        baseline_map = {(r["rule"], r["endpoint"]): r["methods"] for r in self.baseline}
        current_map = {(r["rule"], r["endpoint"]): r["methods"] for r in self.current}
        mismatches = []
        for key in baseline_map:
            if baseline_map[key] != current_map.get(key):
                mismatches.append({
                    "key": key,
                    "baseline": baseline_map[key],
                    "current": current_map.get(key),
                })
        assert not mismatches, f"Method mismatches: {mismatches}"
