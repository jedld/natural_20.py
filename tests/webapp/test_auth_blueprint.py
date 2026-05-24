"""Smoke tests for the auth blueprint routes."""
import os
import sys

WEBAPP_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'webapp')
if WEBAPP_DIR not in sys.path:
    sys.path.insert(0, WEBAPP_DIR)

template_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'templates'))
os.environ.setdefault('TEMPLATE_DIR', template_root)

from webapp.app import app  # noqa: E402


class TestAuthBlueprint:
    def test_login_page_renders(self):
        client = app.test_client()
        response = client.get('/login')
        assert response.status_code == 200

    def test_logout_clears_session(self):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['username'] = 'dm'
        response = client.post('/logout')
        assert response.status_code in (200, 302)

    def test_character_selection_requires_login(self):
        client = app.test_client()
        response = client.get('/character_selection')
        assert response.status_code == 302
        assert '/login' in response.headers.get('Location', '')

    def test_select_character_requires_login(self):
        client = app.test_client()
        response = client.post('/select_character', json={'character': 'test'})
        assert response.status_code in (401, 302, 400)
