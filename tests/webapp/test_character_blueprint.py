"""Smoke tests for the character blueprint routes."""
import os
import sys

WEBAPP_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'webapp')
if WEBAPP_DIR not in sys.path:
    sys.path.insert(0, WEBAPP_DIR)

template_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'templates'))
os.environ.setdefault('TEMPLATE_DIR', template_root)

from webapp.app import app  # noqa: E402


class TestCharacterBlueprint:
    def test_prebuilt_images_requires_login(self):
        client = app.test_client()
        response = client.get('/character_builder/prebuilt_images')
        assert response.status_code == 401

    def test_character_builder_redirects_when_not_logged_in(self):
        client = app.test_client()
        response = client.get('/character_builder')
        assert response.status_code == 302
        assert '/login' in response.headers.get('Location', '')

    def test_character_builder_items_requires_login(self):
        client = app.test_client()
        response = client.get('/character_builder/items')
        assert response.status_code == 401

    def test_journal_add_requires_text(self):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['username'] = 'dm'
        response = client.post('/character/missing/journal', json={'text': ''})
        assert response.status_code in (400, 404)
