import os
import sys

WEBAPP_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'webapp')
if WEBAPP_DIR not in sys.path:
    sys.path.insert(0, WEBAPP_DIR)

from webapp.llm_conversation_controller import LLMConversationController


class DummyHandler:
    def send_message(self, messages):
        return 'ok'


class RouterHandler:
    def __init__(self, response_text):
        self.response_text = response_text
        self.messages = []

    def send_message(self, messages):
        self.messages.append(messages)
        return self.response_text


class DummyEntity:
    def __init__(self, entity_uid, name):
        self.entity_uid = entity_uid
        self._name = name

    def label(self):
        return self._name

    def __str__(self):
        return self._name


def test_update_conversation_history_treats_received_untargeted_message_as_user_prompt():
    controller = LLMConversationController(DummyHandler())
    rose = DummyEntity('rose_durst', 'Rose Durst')
    rumble = DummyEntity('rumblebelly', 'RumbleBelly')

    controller.create_conversation('rose_durst', 'system')
    controller.update_conversation_history('rose_durst', [
        {
            'source': rumble,
            'directed_to': [],
            'target': rose,
            'message': "What's your name?",
            'language': 'common',
        }
    ])

    messages = controller.conversations['rose_durst']['messages']
    assert messages == [{
        'role': 'user',
        'content': "RumbleBelly says to you (in common): What's your name?",
    }]


def test_update_conversation_history_keeps_overheard_directed_message_as_context():
    controller = LLMConversationController(DummyHandler())
    rose = DummyEntity('rose_durst', 'Rose Durst')
    thorn = DummyEntity('thorn_durst', 'Thorn Durst')
    rumble = DummyEntity('rumblebelly', 'RumbleBelly')

    controller.create_conversation('rose_durst', 'system')
    controller.update_conversation_history('rose_durst', [
        {
            'source': rumble,
            'directed_to': [thorn],
            'target': rose,
            'message': 'Thorn, who are you?',
            'language': 'common',
        }
    ])

    messages = controller.conversations['rose_durst']['messages']
    assert messages == [{
        'role': 'system',
        'content': 'you overhear RumbleBelly talk to Thorn Durst (in common): Thorn, who are you?',
    }]


def test_update_conversation_history_treats_explicit_direct_target_as_user_prompt():
    controller = LLMConversationController(DummyHandler())
    rose = DummyEntity('rose_durst', 'Rose Durst')
    rumble = DummyEntity('rumblebelly', 'RumbleBelly')

    controller.create_conversation('rose_durst', 'system')
    controller.update_conversation_history('rose_durst', [
        {
            'source': rumble,
            'directed_to': [rose],
            'target': rose,
            'message': 'Rose, answer me.',
            'language': 'common',
        }
    ])

    messages = controller.conversations['rose_durst']['messages']
    assert messages == [{
        'role': 'user',
        'content': 'RumbleBelly says to you (in common): Rose, answer me.',
    }]


def test_route_conversation_responders_returns_llm_selected_candidate():
    speaker = DummyEntity('rumblebelly', 'RumbleBelly')
    thorn = DummyEntity('thorn_durst', 'Thorn Durst')
    rose = DummyEntity('rose_durst', 'Rose Durst')
    rose.conversation_buffer = [{'source': speaker, 'target': rose, 'directed_to': [], 'message': "What's your name?", 'language': 'common'}]
    thorn.conversation_buffer = [{'source': speaker, 'target': thorn, 'directed_to': [], 'message': 'Anyone there?', 'language': 'common'}]

    handler = RouterHandler('{"responders": ["rose_durst"], "reason": "Rose was addressed most recently."}')
    controller = LLMConversationController(handler)

    result = controller.route_conversation_responders(
        speaker,
        [thorn, rose],
        latest_message="What's your name?",
        targeted_entities=[],
        language='common',
        volume='normal',
    )

    assert result == [rose]
    assert handler.messages


def test_route_conversation_responders_returns_none_on_unparseable_router_output():
    speaker = DummyEntity('rumblebelly', 'RumbleBelly')
    thorn = DummyEntity('thorn_durst', 'Thorn Durst')
    rose = DummyEntity('rose_durst', 'Rose Durst')

    controller = LLMConversationController(RouterHandler('not json'))

    result = controller.route_conversation_responders(
        speaker,
        [thorn, rose],
        latest_message='Anyone there?',
    )

    assert result is None