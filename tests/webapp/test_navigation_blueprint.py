"""Smoke tests for the navigation blueprint routes."""
import os
import sys

WEBAPP_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'webapp')
if WEBAPP_DIR not in sys.path:
    sys.path.insert(0, WEBAPP_DIR)

template_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'templates'))
os.environ.setdefault('TEMPLATE_DIR', template_root)

from webapp.app import app  # noqa: E402


class TestNavigationBlueprint:
    def test_unauthenticated_index_redirects_to_login(self):
        client = app.test_client()
        response = client.get('/')
        assert response.status_code == 302
        assert '/login' in response.headers.get('Location', '')

    def test_jump_info_requires_entity_id(self):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['username'] = 'dm'
        response = client.get('/jump_info')
        assert response.status_code == 400
        assert response.get_json()['error'] == 'Missing entity id'

    def test_mark_note_read_requires_note_id(self):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['username'] = 'dm'
        response = client.post('/mark_note_read', json={})
        assert response.status_code == 400
        assert 'note_id' in response.get_json()['error']

    def test_focus_emits_ok(self):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['username'] = 'dm'
        response = client.post('/focus', data={'x': '1', 'y': '2'})
        assert response.status_code == 200
        assert response.get_json()['status'] == 'ok'
