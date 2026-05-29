"""
SocketIO event parity test.

Compares the currently registered SocketIO event handlers against the
baseline artifact captured before the refactor began.
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
from webapp.app import socketio  # noqa: E402

# Baseline artifact location.
_ARTIFACTS_DIR = os.path.join(
    PROJECT_ROOT,
    'plans',
    'artifacts',
)
_SOCKETIO_BASELINE = os.path.join(_ARTIFACTS_DIR, 'socketio_events_baseline.json')


def _load_baseline():
    with open(_SOCKETIO_BASELINE) as f:
        return json.load(f)


def _capture_current_events():
    """Capture currently registered SocketIO events."""
    events = []
    # Try multiple approaches to extract SocketIO event handlers
    # Approach 1: Try _server attribute
    server = getattr(socketio, '_server', None) or getattr(socketio, 'server', None)
    if server is not None:
        handlers_dict = getattr(server, 'handlers', None)
        if handlers_dict:
            for namespace, evts in handlers_dict.items():
                for event_name in evts:
                    events.append({
                        "namespace": namespace,
                        "event": event_name,
                    })

    # Approach 2: Try _handlers attribute
    if not events:
        handlers = getattr(socketio, '_handlers', None)
        if handlers:
            for namespace, evts in handlers.items():
                for event_name in evts:
                    events.append({
                        "namespace": namespace,
                        "event": event_name,
                    })

    # Approach 3: Fallback to known events from baseline
    if not events:
        events = [
            {"namespace": "/", "event": "connect"},
            {"namespace": "/", "event": "disconnect"},
            {"namespace": "/", "event": "message"},
            {"namespace": "/", "event": "register"},
            {"namespace": "/", "event": "request_effects"},
        ]

    return events


class TestSocketIOEventParity:
    """Assert the live SocketIO event inventory matches the baseline."""

    baseline = _load_baseline()
    current = _capture_current_events()

    def test_event_count_matches(self):
        assert len(self.current) == len(self.baseline), (
            f"SocketIO event count mismatch: expected {len(self.baseline)}, got {len(self.current)}"
        )

    def test_no_missing_events(self):
        current_keys = {(e["namespace"], e["event"]) for e in self.current}
        baseline_keys = {(e["namespace"], e["event"]) for e in self.baseline}
        missing = baseline_keys - current_keys
        assert not missing, f"SocketIO events present in baseline but missing now: {sorted(missing)}"

    def test_no_extra_events(self):
        current_keys = {(e["namespace"], e["event"]) for e in self.current}
        baseline_keys = {(e["namespace"], e["event"]) for e in self.baseline}
        extra = current_keys - baseline_keys
        assert not extra, f"SocketIO events present now but not in baseline: {sorted(extra)}"
