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

    def send_conversation(self, message, distance_ft=30, targets=None, language=None, volume=None):
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

    def send_conversation(self, message, targets=None, language=None, distance_ft=30, volume=None):
        return []


class FakeListener:
    def __init__(self):
        self.entity_uid = 'rose_listener'
        self.dialog = False

    def label(self):
        return 'Rose Listener'

    def is_npc(self):
        return False

    def languages(self):
        return []


class FakeDialogListener(FakeListener):
    def __init__(self, entity_uid='rose_durst', name='Rose Durst'):
        super().__init__()
        self.entity_uid = entity_uid
        self.dialog = True
        self.ability_scores = {'str': 10}
        self.conversation_buffer = []
        self._name = name

    def label(self):
        return self._name

    def is_npc(self):
        return True

    def backstory(self):
        return 'npc backstory'

    def alignment(self):
        return 'neutral_good'

    def send_conversation(self, message, targets=None, language=None, distance_ft=30, volume=None):
        return []


class FakeCurrentGame:
    def __init__(self, speaker):
        self._speaker = speaker
        self.username_to_sid = {
            'dm': ['sid-dm'],
            'player1': ['sid-player1'],
            'player2': ['sid-player2'],
        }
        self.scheduled_goals = []

    def get_entity_by_uid(self, entity_uid):
        if entity_uid == self._speaker.entity_uid:
            return self._speaker
        return None

    def increment_game_time(self, entity):
        return None

    def schedule_short_term_goal(self, entity, goal_text, speaker=None):
        self.scheduled_goals.append({
            'entity_uid': entity.entity_uid,
            'goal': goal_text,
            'speaker_uid': getattr(speaker, 'entity_uid', None),
        })
        return self.scheduled_goals[-1]


class FakeConversationHandler:
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.conversations = {}

    def create_conversation(self, conversation_id, system_prompt):
        self.conversations.setdefault(conversation_id, {'system_prompt': system_prompt})
        return self.conversations[conversation_id]

    def update_conversation_history(self, conversation_id, conversation_buffer):
        return None

    def generate_response(self, conversation_id):
        return self.responses.get(conversation_id, 'Hello there.')


class RecordingConversationHandler(FakeConversationHandler):
    def __init__(self, responses=None):
        super().__init__(responses=responses)
        self.generated_ids = []

    def generate_response(self, conversation_id):
        self.generated_ids.append(conversation_id)
        return super().generate_response(conversation_id)


class RoutingConversationHandler(RecordingConversationHandler):
    def __init__(self, responses=None, routed_receivers=None):
        super().__init__(responses=responses)
        self.routed_receivers = routed_receivers
        self.route_calls = []

    def route_conversation_responders(self, speaker, candidates, latest_message, targeted_entities=None, language='common', volume='normal'):
        self.route_calls.append({
            'speaker': speaker.entity_uid,
            'candidate_ids': [candidate.entity_uid for candidate in candidates],
            'latest_message': latest_message,
            'targeted_ids': [entity.entity_uid for entity in (targeted_entities or [])],
            'language': language,
            'volume': volume,
        })
        if self.routed_receivers is None:
            return None
        routed_ids = set(self.routed_receivers)
        return [candidate for candidate in candidates if candidate.entity_uid in routed_ids]


class FakeEntityRagHandler:
    def process_entity_response(self, response, receiver, speaker, llm_conversation_handler):
        return 'common', response

    def build_conversation_response_plan(self, response, receiver, speaker, llm_conversation_handler):
        if '[SET_GOAL:' in response:
            goal_text = response.split('[SET_GOAL:', 1)[1].split(']', 1)[0].strip()
            return {
                'skip': '[NO_RESPONSE]' in response,
                'language': 'common',
                'message': '',
                'targets': [],
                'volume': None,
                'set_goal': goal_text,
            }
        if response == '[NO_RESPONSE]':
            return {
                'skip': True,
                'language': 'common',
                'message': '',
                'targets': [],
                'volume': None,
            }
        return {
            'skip': False,
            'language': 'common',
            'message': response,
            'targets': [speaker],
            'volume': 'normal',
            'set_goal': None,
        }

    def get_conversation_targets(self, receiver, speaker=None):
        return [speaker] if speaker is not None else []

    def witnessed_events_summary(self, entity):
        return ""

    def offer_item_guidance_for_conversation(self, receiver, speaker):
        return ""

    def parse_response_controls(self, response):
        return {'no_response': '[NO_RESPONSE]' in response}

    def apply_response_plan_directives(self, plan, actor, speaker=None, advance_time=False):
        if plan.get('set_goal'):
            pass

    def apply_conversation_keywords(self, response, receiver, speaker, llm_handler):
        pass

    def get_nearby_entities(self, entity, distance_ft, volume=None, include_extended=False):
        return []

    def build_conversation_response_plan(self, response, receiver, speaker, llm_handler):
        if '[NO_RESPONSE]' in response:
            return {'skip': True, 'language': 'common', 'message': '', 'targets': [], 'volume': None}
        return {'skip': False, 'language': 'common', 'message': response, 'targets': [speaker], 'volume': 'normal'}

    def process_entity_response(self, response, receiver, speaker, llm_handler):
        return 'common', response
        if plan.get('set_goal'):
            app_module.current_game.schedule_short_term_goal(actor, plan['set_goal'], speaker=speaker)
        return {}


class FakeGameSession:
    def entity_by_uid(self, entity_uid):
        return None


class EmitRecorder:
    def __init__(self):
        self.calls = []

    def __call__(self, event_name, payload, to=None, **kwargs):
        self.calls.append({'event_name': event_name, 'payload': payload, 'to': to})


class FakeMentionMap:
    def __init__(self, entities):
        self.entities = entities

    def can_see(self, observer, target):
        return True


class FakeMentionTarget(FakeReceiver):
    def __init__(self):
        super().__init__()
        self.entity_uid = 'thorn_durst'


class FakeMentionSpeaker(FakeSpeaker):
    def __init__(self, receiver, listener):
        super().__init__()
        self.receiver = receiver
        self.listener = listener

    def label(self):
        return 'Rumblebelly'

    def send_conversation(self, message, distance_ft=30, targets=None, language=None, volume=None):
        return [(self.receiver, message, targets or []), (self.listener, message, [])]


class FakeCurrentGameWithMap(FakeCurrentGame):
    def __init__(self, speaker, receiver, listener):
        super().__init__(speaker)
        self._entities = {
            speaker.entity_uid: speaker,
            receiver.entity_uid: receiver,
            listener.entity_uid: listener,
        }
        self._map = FakeMentionMap([speaker, receiver, listener])

    def get_entity_by_uid(self, entity_uid):
        return self._entities.get(entity_uid)

    def get_map_for_entity(self, entity):
        return self._map

    def get_pov_entity_for_user(self, username):
        if username == 'player2':
            return self._entities.get('rose_listener')
        if username == 'player1':
            return self._entities.get('rumblebelly')
        return None


class FakeAmbientSpeaker(FakeSpeaker):
    def __init__(self, receiver):
        super().__init__()
        self.receiver = receiver

    def label(self):
        return 'Rumblebelly'

    def send_conversation(self, message, distance_ft=30, targets=None, language=None, volume=None):
        return [(self.receiver, message, targets or [])]


class FakeWhisperSpeaker(FakeSpeaker):
    def __init__(self, receiver):
        super().__init__()
        self.receiver = receiver

    def label(self):
        return 'Rumblebelly'

    def send_conversation(self, message, distance_ft=30, targets=None, language=None, volume=None):
        return [(self.receiver, message, targets or [self.receiver])]


class FakeAmbientReceiver(FakeReceiver):
    def __init__(self):
        super().__init__()
        self.sent_messages = []

    def send_conversation(self, message, targets=None, language=None, distance_ft=30, volume=None):
        self.sent_messages.append({
            'message': message,
            'targets': list(targets or []),
            'language': language,
            'distance_ft': distance_ft,
            'volume': volume,
        })
        return []


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


def test_talk_route_resolves_mentions_to_directed_targets(monkeypatch):
    receiver = FakeMentionTarget()
    listener = FakeListener()
    speaker = FakeMentionSpeaker(receiver, listener)
    emit_recorder = EmitRecorder()

    monkeypatch.setattr(app_module, 'current_game', FakeCurrentGameWithMap(speaker, receiver, listener))
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
        'message': '@thorn hello there',
        'language': 'common',
        'volume': 'normal',
    })

    assert response.status_code == 200
    assert response.get_json()['mentioned_target_ids'] == ['thorn_durst']


def test_talk_route_infers_plain_name_targets(monkeypatch):
    receiver = FakeDialogListener(entity_uid='rose_durst', name='Rose Durst')
    listener = FakeDialogListener(entity_uid='watcher', name='Silent Watcher')
    speaker = FakeMentionSpeaker(receiver, listener)
    emit_recorder = EmitRecorder()

    monkeypatch.setattr(app_module, 'current_game', FakeCurrentGameWithMap(speaker, receiver, listener))
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
        sess['username'] = 'player1'

    response = client.post('/talk', json={
        'entity_id': 'rumblebelly',
        'message': 'rose, who are your parents?',
        'language': 'common',
        'volume': 'normal',
    })

    assert response.status_code == 200
    assert response.get_json()['resolved_target_ids'] == ['rose_durst']


def test_talk_route_schedules_short_term_goal_from_npc_reply(monkeypatch):
    speaker = FakeSpeaker()
    current_game = FakeCurrentGame(speaker)
    emit_recorder = EmitRecorder()

    class GoalConversationHandler(FakeConversationHandler):
        def generate_response(self, conversation_id):
            return '[SET_GOAL: Check the front door for intruders] [NO_RESPONSE]'

    monkeypatch.setattr(app_module, 'current_game', current_game)
    monkeypatch.setattr(app_module, 'llm_conversation_handler', GoalConversationHandler())
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
        sess['username'] = 'player1'

    response = client.post('/talk', json={
        'entity_id': 'rumblebelly',
        'message': 'hello',
        'language': 'common',
        'targets': ['thorn_durst'],
    })

    assert response.status_code == 200
    assert current_game.scheduled_goals == [{
        'entity_uid': 'thorn_durst',
        'goal': 'Check the front door for intruders',
        'speaker_uid': 'rumblebelly',
    }]

    speaker_events = [
        call for call in emit_recorder.calls
        if call['event_name'] == 'message'
        and call['payload'].get('type') == 'conversation'
        and call['payload']['message']['entity_id'] == 'rumblebelly'
    ]

    assert any(call['payload']['message']['targets'] == ['thorn_durst'] for call in speaker_events)


def test_talk_route_lets_audible_npc_reply_without_direct_targeting(monkeypatch):
    receiver = FakeAmbientReceiver()
    listener = FakeListener()
    speaker = FakeAmbientSpeaker(receiver)
    emit_recorder = EmitRecorder()

    monkeypatch.setattr(app_module, 'current_game', FakeCurrentGameWithMap(speaker, receiver, listener))
    monkeypatch.setattr(app_module, 'llm_conversation_handler', FakeConversationHandler({'thorn_durst': 'Who goes there?'}))
    monkeypatch.setattr(app_module, 'entity_rag_handler', FakeEntityRagHandler())
    monkeypatch.setattr(app_module, 'game_session', FakeGameSession())
    monkeypatch.setattr(
        app_module,
        'entity_owners',
        lambda entity: {
            'rumblebelly': ['player1'],
            'thorn_durst': ['player2'],
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
        'message': 'Anyone there?',
        'language': 'common',
        'volume': 'shout',
    })

    assert response.status_code == 200
    assert response.get_json()['distance_ft'] == 60
    assert response.get_json()['volume'] == 'shout'

    speaker_payloads = [
        call['payload']['message'] for call in emit_recorder.calls
        if call['event_name'] == 'message'
        and call['payload'].get('type') == 'conversation'
        and call['payload']['message']['entity_id'] == 'rumblebelly'
    ]

    assert any(payload['distance_ft'] == 60 for payload in speaker_payloads)
    assert any(payload['volume'] == 'shout' for payload in speaker_payloads)

    assert receiver.sent_messages
    assert receiver.sent_messages[0]['message'] == 'Who goes there?'
    assert receiver.sent_messages[0]['targets'][0].entity_uid == 'rumblebelly'
    assert receiver.sent_messages[0]['distance_ft'] == 30
    assert receiver.sent_messages[0]['volume'] == 'normal'


def test_talk_route_only_allows_one_ambient_npc_to_reply(monkeypatch):
    first_receiver = FakeAmbientReceiver()
    second_receiver = FakeDialogListener(entity_uid='rose_durst', name='Rose Durst')
    speaker = FakeAmbientSpeaker(first_receiver)
    emit_recorder = EmitRecorder()
    conversation_handler = RecordingConversationHandler({
        'thorn_durst': 'Who goes there?',
        'rose_durst': 'Who is speaking?',
    })

    def send_conversation(message, distance_ft=30, targets=None, language=None, volume=None):
        return [
            (first_receiver, message, targets or []),
            (second_receiver, message, targets or []),
        ]

    speaker.send_conversation = send_conversation
    current_game = FakeCurrentGame(speaker)
    current_game._entities = {
        'rumblebelly': speaker,
        'thorn_durst': first_receiver,
        'rose_durst': second_receiver,
    }
    current_game.get_entity_by_uid = lambda entity_uid: current_game._entities.get(entity_uid)

    monkeypatch.setattr(app_module, 'current_game', current_game)
    monkeypatch.setattr(app_module, 'llm_conversation_handler', conversation_handler)
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
        sess['username'] = 'player1'

    response = client.post('/talk', json={
        'entity_id': 'rumblebelly',
        'message': 'Anyone there?',
        'language': 'common',
        'volume': 'normal',
    })

    assert response.status_code == 200
    assert conversation_handler.generated_ids == ['thorn_durst']
    assert first_receiver.sent_messages[0]['message'] == 'Who goes there?'


def test_talk_route_uses_llm_router_for_ambient_multi_npc_choice(monkeypatch):
    first_receiver = FakeAmbientReceiver()
    second_receiver = FakeDialogListener(entity_uid='rose_durst', name='Rose Durst')
    speaker = FakeAmbientSpeaker(first_receiver)
    emit_recorder = EmitRecorder()
    conversation_handler = RoutingConversationHandler(
        responses={
            'thorn_durst': 'Who goes there?',
            'rose_durst': 'My name is Rose Durst.',
        },
        routed_receivers=['rose_durst'],
    )

    def send_conversation(message, distance_ft=30, targets=None, language=None, volume=None):
        return [
            (first_receiver, message, targets or []),
            (second_receiver, message, targets or []),
        ]

    speaker.send_conversation = send_conversation
    current_game = FakeCurrentGame(speaker)
    current_game._entities = {
        'rumblebelly': speaker,
        'thorn_durst': first_receiver,
        'rose_durst': second_receiver,
    }
    current_game.get_entity_by_uid = lambda entity_uid: current_game._entities.get(entity_uid)

    monkeypatch.setattr(app_module, 'current_game', current_game)
    monkeypatch.setattr(app_module, 'llm_conversation_handler', conversation_handler)
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
        sess['username'] = 'player1'

    response = client.post('/talk', json={
        'entity_id': 'rumblebelly',
        'message': "What's your name?",
        'language': 'common',
        'volume': 'normal',
    })

    assert response.status_code == 200
    assert conversation_handler.generated_ids == ['rose_durst']
    assert conversation_handler.route_calls[0]['latest_message'] == "What's your name?"


def test_talk_route_auto_shouts_on_exclamation(monkeypatch):
    receiver = FakeAmbientReceiver()
    listener = FakeListener()
    speaker = FakeAmbientSpeaker(receiver)
    emit_recorder = EmitRecorder()

    monkeypatch.setattr(app_module, 'current_game', FakeCurrentGameWithMap(speaker, receiver, listener))
    monkeypatch.setattr(app_module, 'llm_conversation_handler', FakeConversationHandler({'thorn_durst': '[NO_RESPONSE]'}))
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
        sess['username'] = 'player1'

    response = client.post('/talk', json={
        'entity_id': 'rumblebelly',
        'message': 'Watch out!',
        'language': 'common',
        'volume': 'normal',
    })

    assert response.status_code == 200
    assert response.get_json()['distance_ft'] == 60
    assert response.get_json()['volume'] == 'shout'

    speaker_payloads = [
        call['payload']['message'] for call in emit_recorder.calls
        if call['event_name'] == 'message'
        and call['payload'].get('type') == 'conversation'
        and call['payload']['message']['entity_id'] == 'rumblebelly'
    ]

    assert any(payload['distance_ft'] == 60 for payload in speaker_payloads)
    assert any(payload['volume'] == 'shout' for payload in speaker_payloads)


def test_talk_route_respects_llm_no_response(monkeypatch):
    receiver = FakeAmbientReceiver()
    listener = FakeListener()
    speaker = FakeAmbientSpeaker(receiver)

    monkeypatch.setattr(app_module, 'current_game', FakeCurrentGameWithMap(speaker, receiver, listener))
    monkeypatch.setattr(app_module, 'llm_conversation_handler', FakeConversationHandler({'thorn_durst': '[NO_RESPONSE]'}))
    monkeypatch.setattr(app_module, 'entity_rag_handler', FakeEntityRagHandler())
    monkeypatch.setattr(app_module, 'game_session', FakeGameSession())
    monkeypatch.setattr(app_module, 'entity_owners', lambda entity: ['player1'])
    monkeypatch.setattr(app_module.socketio, 'emit', EmitRecorder())
    monkeypatch.setattr(app_module, 'LOGINS', [
        {'name': 'dm', 'role': ['dm']},
        {'name': 'player1', 'role': ['player']},
    ])

    app_module.app.config['TESTING'] = True
    client = app_module.app.test_client()
    with client.session_transaction() as sess:
        sess['username'] = 'player1'

    response = client.post('/talk', json={
        'entity_id': 'rumblebelly',
        'message': 'Anyone there?',
        'language': 'common',
        'volume': 'shout',
    })

    assert response.status_code == 200
    assert receiver.sent_messages == []


def test_talk_route_emits_gibberish_to_listeners_without_language(monkeypatch):
    receiver = FakeMentionTarget()
    listener = FakeListener()
    speaker = FakeMentionSpeaker(receiver, listener)
    emit_recorder = EmitRecorder()

    monkeypatch.setattr(app_module, 'current_game', FakeCurrentGameWithMap(speaker, receiver, listener))
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
        'message': 'Secret words',
        'language': 'elvish',
        'volume': 'normal',
    })

    assert response.status_code == 200

    player1_payloads = [
        call['payload']['message'] for call in emit_recorder.calls
        if call['event_name'] == 'message' and call['to'] == 'sid-player1' and call['payload'].get('type') == 'conversation'
    ]
    player2_payloads = [
        call['payload']['message'] for call in emit_recorder.calls
        if call['event_name'] == 'message' and call['to'] == 'sid-player2' and call['payload'].get('type') == 'conversation'
    ]

    assert any(payload['message'] == 'Secret words' for payload in player1_payloads)
    assert any(payload['language'] == 'elvish' for payload in player2_payloads)
    assert any(payload['message'] != 'Secret words' for payload in player2_payloads)


def test_talk_route_shows_visual_whisper_placeholder_to_visible_non_listeners(monkeypatch):
    receiver = FakeMentionTarget()
    listener = FakeListener()
    speaker = FakeWhisperSpeaker(receiver)
    emit_recorder = EmitRecorder()

    monkeypatch.setattr(app_module, 'current_game', FakeCurrentGameWithMap(speaker, receiver, listener))
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
        'message': 'quiet now',
        'language': 'common',
        'volume': 'whisper',
        'targets': ['thorn_durst'],
    })

    assert response.status_code == 200

    player2_payloads = [
        call['payload']['message'] for call in emit_recorder.calls
        if call['event_name'] == 'message' and call['to'] == 'sid-player2' and call['payload'].get('type') == 'conversation'
    ]

    assert any(payload.get('visual_only') is True for payload in player2_payloads)
    assert any(payload['message'] == 'You can see them whispering, but cannot hear the words.' for payload in player2_payloads)
    assert all(payload['message'] != 'quiet now' for payload in player2_payloads)
