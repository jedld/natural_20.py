import os
import sys

WEBAPP_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'webapp')
if WEBAPP_DIR not in sys.path:
    sys.path.insert(0, WEBAPP_DIR)

template_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'templates'))
os.environ.setdefault('TEMPLATE_DIR', template_root)

from webapp import app as app_module


class FakeSpeaker:
    def __init__(self):
        self.entity_uid = 'rumblebelly'

    def send_conversation(self, message, distance_ft=30, targets=None, language=None):
        receiver = FakeReceiver()
        listener = FakeListener()
        return [(receiver, message, [receiver]), (listener, message, [])]


class FakeReceiver:
    def __init__(self):
        self.entity_uid = 'thorn_durst'
        self.dialog = True
        self.ability_scores = {'str': 10}
        self.conversation_buffer = []

    def is_npc(self):
        return True

    def backstory(self):
        return 'npc backstory'

    def label(self):
        return 'Thorn Durst'

    def alignment(self):
        return 'neutral_good'

    def languages(self):
        return ['common']

    def send_conversation(self, message, targets=None, language=None):
        return []


class FakeListener:
    def __init__(self):
        self.entity_uid = 'rose_listener'
        self.dialog = False

    def label(self):
        return 'Rose Listener'

    def is_npc(self):
        return False


class FakeCurrentGame:
    def __init__(self, speaker):
        self._speaker = speaker
        self.username_to_sid = {
            'dm': ['sid-dm'],
            'player1': ['sid-player1'],
            'player2': ['sid-player2'],
        }

    def get_entity_by_uid(self, entity_uid):
        if entity_uid == self._speaker.entity_uid:
            return self._speaker
        return None

    def increment_game_time(self, entity):
        return None


class FakeConversationHandler:
    def create_conversation(self, conversation_id, system_prompt):
        return None

    def update_conversation_history(self, conversation_id, conversation_buffer):
        return None

    def generate_response(self, conversation_id):
        return 'Hello there.'


class FakeEntityRagHandler:
    def process_entity_response(self, response, receiver, speaker, llm_conversation_handler):
        return 'common', response


class FakeGameSession:
    def entity_by_uid(self, entity_uid):
        return None


class EmitRecorder:
    def __init__(self):
        self.calls = []

    def __call__(self, event_name, payload, to=None, **kwargs):
        self.calls.append({'event_name': event_name, 'payload': payload, 'to': to})


def test_talk_replies_are_sent_to_requesting_dm(monkeypatch):
    speaker = FakeSpeaker()
    emit_recorder = EmitRecorder()

    monkeypatch.setattr(app_module, 'current_game', FakeCurrentGame(speaker))
    monkeypatch.setattr(app_module, 'llm_conversation_handler', FakeConversationHandler())
    monkeypatch.setattr(app_module, 'entity_rag_handler', FakeEntityRagHandler())
    monkeypatch.setattr(app_module, 'game_session', FakeGameSession())
    monkeypatch.setattr(app_module, 'entity_owners', lambda entity: ['player1'])
    monkeypatch.setattr(app_module.socketio, 'emit', emit_recorder)
    monkeypatch.setattr(app_module, 'LOGINS', [
        {'name': 'dm', 'role': ['dm']},
        {'name': 'player1', 'role': ['player']},
    ])

    app_module.app.config['TESTING'] = True
    client = app_module.app.test_client()
    with client.session_transaction() as sess:
        sess['username'] = 'dm'

    response = client.post('/talk', json={
        'entity_id': 'rumblebelly',
        'message': 'hello',
        'language': 'common',
        'targets': ['thorn_durst'],
    })

    assert response.status_code == 200

    conversation_calls = [
        call for call in emit_recorder.calls
        if call['event_name'] == 'message' and call['payload'].get('type') == 'conversation'
    ]

    assert any(
        call['payload']['message']['entity_id'] == 'thorn_durst' and call['to'] == 'sid-dm'
        for call in conversation_calls
    )
    assert any(
        call['payload']['message']['entity_id'] == 'thorn_durst' and call['to'] == 'sid-player1'
        for call in conversation_calls
    )


def test_talk_is_also_sent_to_overhearers(monkeypatch):
    speaker = FakeSpeaker()
    emit_recorder = EmitRecorder()

    monkeypatch.setattr(app_module, 'current_game', FakeCurrentGame(speaker))
    monkeypatch.setattr(app_module, 'llm_conversation_handler', FakeConversationHandler())
    monkeypatch.setattr(app_module, 'entity_rag_handler', FakeEntityRagHandler())
    monkeypatch.setattr(app_module, 'game_session', FakeGameSession())
    monkeypatch.setattr(
        app_module,
        'entity_owners',
        lambda entity: {
            'rumblebelly': ['player1'],
            'thorn_durst': ['player1'],
            'rose_listener': ['player2'],
        }.get(entity.entity_uid, []),
    )
    monkeypatch.setattr(app_module.socketio, 'emit', emit_recorder)
    monkeypatch.setattr(app_module, 'LOGINS', [
        {'name': 'dm', 'role': ['dm']},
        {'name': 'player1', 'role': ['player']},
        {'name': 'player2', 'role': ['player']},
    ])

    app_module.app.config['TESTING'] = True
    client = app_module.app.test_client()
    with client.session_transaction() as sess:
        sess['username'] = 'player1'

    response = client.post('/talk', json={
        'entity_id': 'rumblebelly',
        'message': 'keep quiet',
        'language': 'common',
        'targets': ['thorn_durst'],
    })

    assert response.status_code == 200

    conversation_calls = [
        call for call in emit_recorder.calls
        if call['event_name'] == 'message' and call['payload'].get('type') == 'conversation'
    ]

    assert any(
        call['payload']['message']['entity_id'] == 'rumblebelly' and call['to'] == 'sid-player2'
        for call in conversation_calls
    )
