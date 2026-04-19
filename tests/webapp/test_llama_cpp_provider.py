import os
import sys


WEBAPP_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'webapp')
if WEBAPP_DIR not in sys.path:
    sys.path.insert(0, WEBAPP_DIR)

template_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'templates'))
os.environ.setdefault('TEMPLATE_DIR', template_root)

from webapp.app import app
from webapp.llm_handler import LlamaCppProvider


class MockResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_llama_cpp_provider_uses_local_default_and_first_model(monkeypatch):
    seen_urls = []
    seen_payloads = []

    def fake_get(url, headers=None, timeout=None):
        seen_urls.append(url)
        return MockResponse({'models': [{'name': 'qwen-local'}]})

    def fake_post(url, headers=None, json=None, timeout=None):
        seen_urls.append(url)
        seen_payloads.append(json)
        assert json['model'] == 'qwen-local'
        return MockResponse({'choices': [{'message': {'content': '[FUNCTION_CALL: get_map_info()]'}}]})

    monkeypatch.setattr('requests.get', fake_get)
    monkeypatch.setattr('requests.post', fake_post)

    provider = LlamaCppProvider()
    assert provider.initialize({}) is True
    assert provider.base_url == 'http://localhost:8011'
    assert provider.current_model == 'qwen-local'
    assert provider.get_available_models() == ['qwen-local']
    assert provider.send_message([{'role': 'user', 'content': 'hello'}]) == '[FUNCTION_CALL: get_map_info()]'
    assert seen_payloads[0]['chat_template_kwargs'] == {'enable_thinking': False}
    assert 'http://localhost:8011/v1/models' in seen_urls
    assert 'http://localhost:8011/v1/chat/completions' in seen_urls


def test_llama_cpp_provider_parses_openai_content_parts(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        return MockResponse({'data': [{'id': 'qwen-local'}]})

    def fake_post(url, headers=None, json=None, timeout=None):
        return MockResponse({
            'choices': [{
                'message': {
                    'content': [
                        {'type': 'text', 'text': 'hello '},
                        {'type': 'output_text', 'text': 'there'}
                    ]
                }
            }]
        })

    monkeypatch.setattr('requests.get', fake_get)
    monkeypatch.setattr('requests.post', fake_post)

    provider = LlamaCppProvider()
    assert provider.initialize({}) is True
    assert provider.send_message([{'role': 'user', 'content': 'hello'}]) == 'hello there'


def test_ai_initialize_supports_llama_cpp(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        return MockResponse({'models': [{'model': 'qwen-local'}]})

    monkeypatch.setattr('requests.get', fake_get)

    app.config['TESTING'] = True
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['username'] = 'dm'

    response = client.post('/ai/initialize', data={'provider': 'llama_cpp'})

    assert response.status_code == 200
    data = response.get_json()
    assert data is not None
    assert data['success'] is True
    assert data['model'] == 'qwen-local'