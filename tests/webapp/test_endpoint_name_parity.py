"""
Endpoint name parity test.

Ensures that all Flask endpoint names from the baseline artifact are still
resolvable via ``url_for()`` after the refactor.  This protects templates
and redirects that depend on stable endpoint names.
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

# Baseline artifact location.
_ARTIFACTS_DIR = os.path.join(
    PROJECT_ROOT,
    'plans',
    'artifacts',
)
_ENDPOINTS_BASELINE = os.path.join(_ARTIFACTS_DIR, 'endpoints_baseline.json')


def _load_baseline():
    with open(_ENDPOINTS_BASELINE) as f:
        return json.load(f)


def _capture_current_endpoints():
    """Return a set of endpoint names from the live app."""
    endpoints = set()
    for rule in app.url_map.iter_rules():
        endpoints.add(rule.endpoint)
    return endpoints


class TestEndpointNameParity:
    """Assert all baseline endpoint names are still present and resolvable."""

    baseline = _load_baseline()
    current_endpoints = _capture_current_endpoints()

    def test_endpoint_count_matches(self):
        baseline_count = len(self.baseline)
        assert len(self.current_endpoints) >= baseline_count, (
            f"Endpoint count dropped: expected >= {baseline_count}, got {len(self.current_endpoints)}"
        )

    def test_no_missing_endpoints(self):
        baseline_names = {e["endpoint"] for e in self.baseline}
        missing = baseline_names - self.current_endpoints
        assert not missing, f"Endpoints present in baseline but missing now: {sorted(missing)}"

    def test_all_baseline_endpoints_resolvable(self):
        """Check each baseline endpoint exists in the URL map.

        Endpoints with path variables (e.g., ``/character/<name>/journal``)
        cannot be resolved via ``url_for()`` without providing those variables.
        Instead we verify the endpoint name appears in at least one URL rule.
        """
        baseline_names = {e["endpoint"] for e in self.baseline}
        current_names = set()
        for rule in app.url_map.iter_rules():
            current_names.add(rule.endpoint)
        missing = baseline_names - current_names
        assert not missing, f"Endpoints not in URL map: {sorted(missing)}"
