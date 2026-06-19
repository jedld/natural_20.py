import os
import sys

WEBAPP_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'webapp')
if WEBAPP_DIR not in sys.path:
    sys.path.insert(0, WEBAPP_DIR)

template_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'templates'))
os.environ.setdefault('TEMPLATE_DIR', template_root)

from webapp import app as app_module
from webapp.conversation_service import ConversationService


class FakeBattle:
    def __init__(self, hostile_pairs=None, allied_pairs=None):
        self.hostile_pairs = hostile_pairs or set()
        self.allied_pairs = allied_pairs or set()

    def _pair(self, left, right):
        return tuple(sorted([left.entity_uid, right.entity_uid]))

    def opposing(self, left, right):
        return self._pair(left, right) in self.hostile_pairs

    def allies(self, left, right):
        return self._pair(left, right) in self.allied_pairs

    def entity_state_for(self, entity):
        return {'group': getattr(entity, 'group', 'a')}


class FakeCurrentGame:
    def __init__(self, battle=None, goal_state=None):
        self._battle = battle
        self._goal_state = goal_state

    def get_current_battle(self):
        return self._battle

    def get_short_term_goal(self, entity):
        return self._goal_state


class FakeEntityRagHandler:
    def get_conversation_targets(self, receiver, speaker=None):
        return [speaker] if speaker is not None else []

    def witnessed_events_summary(self, entity):
        return ""

    def offer_item_guidance_for_conversation(self, receiver, speaker):
        return ""

    def parse_response_controls(self, response):
        return {'no_response': '[NO_RESPONSE]' in response}

    def apply_response_plan_directives(self, plan, actor, speaker=None, advance_time=False):
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


class FakeSpeaker:
    def __init__(self, entity_uid='rumblebelly', group='a'):
        self.entity_uid = entity_uid
        self.group = group

    def label(self):
        return 'Rumblebelly'


class FakeReceiver:
    def __init__(self):
        self.entity_uid = 'rose_durst'
        self.group = 'b'
        self.statuses = ['frightened']
        self.hp = 3
        self.max_hp = 12

    def label(self):
        return 'Rose Durst'

    def alignment(self):
        return 'neutral_good'

    def current_effects(self):
        return [{'effect': 'sanctuary'}]


def test_conversation_prompt_explicitly_allows_in_character_refusals(monkeypatch):
    monkeypatch.setattr(app_module, 'entity_rag_handler', FakeEntityRagHandler())
    monkeypatch.setattr(app_module, 'current_game', FakeCurrentGame())
    monkeypatch.setattr(app_module, 'entity_owners', lambda entity: [])

    prompt = app_module.conversation_response_prompt(FakeReceiver(), FakeSpeaker())

    assert 'explicitly refuse to answer' in prompt
    assert 'use [NO_RESPONSE] only when you stay completely silent' in prompt
    assert 'Do not use [NO_RESPONSE] for hello' in prompt


def test_message_expects_direct_reply_detects_greetings_and_questions():
    assert ConversationService.message_expects_direct_reply('hello!')
    assert ConversationService.message_expects_direct_reply('really? where is it?')
    assert not ConversationService.message_expects_direct_reply('ok')
    assert not ConversationService.message_expects_direct_reply('thanks')


def test_conversation_prompt_includes_attitude_and_pressure_context(monkeypatch):
    hostile_pair = tuple(sorted(['rose_durst', 'rumblebelly']))
    battle = FakeBattle(hostile_pairs={hostile_pair})
    goal_state = {
        'status': 'active',
        'goal': 'Protect the children',
    }

    monkeypatch.setattr(app_module, 'entity_rag_handler', FakeEntityRagHandler())
    monkeypatch.setattr(app_module, 'current_game', FakeCurrentGame(battle=battle, goal_state=goal_state))
    monkeypatch.setattr(app_module, 'entity_owners', lambda entity: [])

    prompt = app_module.conversation_response_prompt(FakeReceiver(), FakeSpeaker())

    assert 'Current stance toward the speaker: hostile.' in prompt
    assert 'badly hurt' in prompt
    assert 'statuses: frightened' in prompt
    assert 'active effects: sanctuary' in prompt
    assert 'active goal: Protect the children' in prompt
    assert 'currently in combat' in prompt


def test_conversation_prompt_includes_gear_and_inventory_rule(monkeypatch):
    monkeypatch.setattr(app_module, 'entity_rag_handler', FakeEntityRagHandler())
    monkeypatch.setattr(app_module, 'current_game', FakeCurrentGame())
    monkeypatch.setattr(app_module, 'entity_owners', lambda entity: [])

    prompt = app_module.conversation_response_prompt(FakeReceiver(), FakeSpeaker())

    assert 'Your gear and inventory (authoritative; do not contradict):' in prompt
    assert 'Do not invent equipment.' in prompt