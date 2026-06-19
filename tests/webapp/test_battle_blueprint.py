"""Smoke tests for the battle blueprint routes."""
import os
import sys

WEBAPP_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'webapp')
if WEBAPP_DIR not in sys.path:
    sys.path.insert(0, WEBAPP_DIR)

template_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'templates'))
os.environ.setdefault('TEMPLATE_DIR', template_root)

from webapp.app import app  # noqa: E402


class TestBattleBlueprint:
    def test_combat_log_api_when_logged_in(self):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['username'] = 'dm'
        response = client.get('/api/combat-log')
        assert response.status_code == 200
        assert 'combat_log' in response.get_json()

    def test_stop_battle_when_logged_in(self):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['username'] = 'dm'
        response = client.post('/stop')
        assert response.status_code == 200
        assert response.get_json()['status'] == 'ok'

    def test_game_time_returns_json(self):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['username'] = 'dm'
        response = client.get('/game_time')
        assert response.status_code == 200
        assert 'game_time' in response.get_json()

    def test_reset_narrations_requires_login(self):
        client = app.test_client()
        response = client.post('/reset_narrations', follow_redirects=False)
        assert response.status_code in (302, 401, 403)
