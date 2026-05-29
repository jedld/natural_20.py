"""Smoke tests for SocketIO handler registration."""
import os
import sys

WEBAPP_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'webapp')
if WEBAPP_DIR not in sys.path:
    sys.path.insert(0, WEBAPP_DIR)

template_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'templates'))
os.environ.setdefault('TEMPLATE_DIR', template_root)

from webapp.app import socketio  # noqa: E402


class TestSocketIOHandlers:
    def test_expected_events_registered(self):
        server = getattr(socketio, '_server', None) or getattr(socketio, 'server', None)
        handlers = getattr(server, 'handlers', None) if server is not None else None
        if not handlers:
            handlers = getattr(socketio, '_handlers', None)
        assert handlers, 'Could not introspect SocketIO handlers'
        events = set(handlers.get('/', {}).keys())
        expected = {'connect', 'disconnect', 'message', 'register', 'request_effects'}
        assert expected.issubset(events), f'Missing events: {expected - events}'
