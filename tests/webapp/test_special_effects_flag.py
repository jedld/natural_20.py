import os
import sys


WEBAPP_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'webapp')
if WEBAPP_DIR not in sys.path:
    sys.path.insert(0, WEBAPP_DIR)

template_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'templates'))
os.environ.setdefault('TEMPLATE_DIR', template_root)

from webapp.app import app, filter_effect_payload, has_enabled_effect_payloads, map_default_effect_payloads, origin_allowed, socketio


class DummyMap:
    def __init__(self, properties):
        self.properties = properties


def test_heavy_effects_are_filtered_when_globally_disabled():
    original = app.config.get('SPECIAL_EFFECTS_ENABLED', True)
    try:
        app.config['SPECIAL_EFFECTS_ENABLED'] = False

        assert filter_effect_payload({'effect': 'fog', 'action': 'start', 'config': {}}) is None
        assert filter_effect_payload({'effect': 'rain', 'action': 'start', 'config': {}}) is None
        assert not has_enabled_effect_payloads([{'effect': 'snow', 'action': 'start', 'config': {}}])

        allowed = filter_effect_payload({'effect': 'custom_overlay', 'action': 'start', 'config': {'foo': 'bar'}})
        assert allowed == {'effect': 'custom_overlay', 'action': 'start', 'config': {'foo': 'bar'}}

        payloads = map_default_effect_payloads(DummyMap({
            'default_effects': [
                {'effect': 'fog', 'action': 'start', 'config': {'density': 0.5}},
                {'effect': 'snow', 'action': 'start', 'config': {'intensity': 0.2}},
            ]
        }))
        assert payloads == []
    finally:
        app.config['SPECIAL_EFFECTS_ENABLED'] = original


def test_admin_effect_route_rejects_heavy_effect_start_when_disabled():
    original = app.config.get('SPECIAL_EFFECTS_ENABLED', True)
    try:
        app.config['SPECIAL_EFFECTS_ENABLED'] = False
        app.config['TESTING'] = True

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['username'] = 'dm'

        response = client.post('/admin/effect', json={
            'effect': 'fog',
            'action': 'start',
            'config': {'density': 0.5},
        })

        assert response.status_code == 409
        data = response.get_json()
        assert data is not None
        assert 'disabled' in data['error'].lower()
    finally:
        app.config['SPECIAL_EFFECTS_ENABLED'] = original


def test_origin_allowed_accepts_ngrok_free_dev_subdomains():
    allowed_origins = [
        'https://*.ngrok-free.dev',
        'https://*.ngrok-free.app',
    ]

    assert origin_allowed('https://yahaira-experienceless-kirk.ngrok-free.dev', allowed_origins)
    assert not origin_allowed('https://example.com', allowed_origins)


def test_socketio_uses_named_cookie_for_engineio_handshake():
    assert socketio.server.eio.cookie == 'io'