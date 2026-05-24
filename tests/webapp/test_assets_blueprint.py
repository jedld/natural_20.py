"""Smoke tests for the assets blueprint routes."""
import os
import sys

WEBAPP_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'webapp')
if WEBAPP_DIR not in sys.path:
    sys.path.insert(0, WEBAPP_DIR)

template_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'templates'))
os.environ.setdefault('TEMPLATE_DIR', template_root)

from webapp.app import app  # noqa: E402


class TestAssetsBlueprint:
    def test_create_map_requires_auth(self):
        client = app.test_client()
        response = client.post('/create_map', json={})
        assert response.status_code in (400, 401, 403, 302)

    def test_delete_map_requires_auth(self):
        client = app.test_client()
        response = client.post('/delete_map', json={'map_name': 'missing'})
        assert response.status_code in (401, 403, 302)

    def test_serve_map_image_not_found(self):
        client = app.test_client()
        response = client.get('/assets/maps/does-not-exist.png')
        assert response.status_code == 404
