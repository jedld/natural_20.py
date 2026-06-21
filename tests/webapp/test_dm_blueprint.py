"""Smoke tests for the DM blueprint routes."""
import os
import sys

WEBAPP_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'webapp')
if WEBAPP_DIR not in sys.path:
    sys.path.insert(0, WEBAPP_DIR)

template_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'templates'))
os.environ.setdefault('TEMPLATE_DIR', template_root)

from webapp.app import app  # noqa: E402


class TestDmBlueprint:
    def test_admin_saves_requires_login(self):
        client = app.test_client()
        response = client.get('/admin/saves', follow_redirects=False)
        assert response.status_code in (302, 401, 403)

    def test_available_npcs_requires_dm(self):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['username'] = 'player'
        response = client.get('/available_npcs')
        assert response.status_code == 403

    def test_get_users_empty_query(self):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['username'] = 'dm'
        response = client.get('/get_users')
        assert response.status_code == 200
        assert response.get_json() == []

    def test_admin_campaign_logs_status_requires_dm(self):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['username'] = 'player'
        response = client.get('/admin/campaign-logs/status')
        assert response.status_code == 403

    def test_xp_summary_requires_dm(self):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['username'] = 'player'
        response = client.get('/xp_summary')
        assert response.status_code == 403

    def test_award_xp_rejects_negative_amount_for_dm(self):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['username'] = 'dm'
        response = client.post('/award_xp', json={'amount': -1})
        assert response.status_code == 400

    def test_grant_level_up_requires_dm(self):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['username'] = 'player'
        response = client.post('/grant_level_up', json={'levels': 1})
        assert response.status_code == 403

    def test_grant_event_level_up_requires_event(self):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['username'] = 'dm'
        response = client.post('/grant_event_level_up', json={})
        assert response.status_code == 400
