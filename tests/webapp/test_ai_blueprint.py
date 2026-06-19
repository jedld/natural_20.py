"""Smoke tests for the AI blueprint routes."""
import os
import sys

WEBAPP_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'webapp')
if WEBAPP_DIR not in sys.path:
    sys.path.insert(0, WEBAPP_DIR)

template_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'templates'))
os.environ.setdefault('TEMPLATE_DIR', template_root)

from webapp.app import app  # noqa: E402


class TestAiBlueprint:
    def test_ai_context_requires_dm(self):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['username'] = 'player'
        response = client.get('/ai/context')
        assert response.status_code == 403

    def test_ai_history_requires_dm(self):
        client = app.test_client()
        response = client.get('/ai/history', follow_redirects=False)
        assert response.status_code in (302, 401, 403)

    def test_ai_provider_info_when_dm(self):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['username'] = 'dm'
        response = client.get('/ai/provider-info')
        assert response.status_code == 200
        data = response.get_json()
        assert data.get('success') is True
        assert 'info' in data

    def test_ai_clear_history_requires_dm(self):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['username'] = 'player'
        response = client.post('/ai/clear-history')
        assert response.status_code == 403
