"""Unit tests for the player-side Insight check entry point in
``webapp.conversation_service``.

These tests focus on the message detection / parsing helpers and the
high-level dispatch in ``handle_player_insight_request`` driven by a
lightweight stub of the surrounding game state.
"""

import os
import sys
import types
import logging

WEBAPP_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'webapp')
if WEBAPP_DIR not in sys.path:
    sys.path.insert(0, WEBAPP_DIR)

import importlib

conversation_service = importlib.import_module('webapp.conversation_service')

from webapp.conversation_service import (
    ConversationService,
    is_player_insight_request,
    parse_player_insight_request,
)


# ---------------------------------------------------------------------------
# Detection / parsing
# ---------------------------------------------------------------------------

def test_recognises_basic_insight_phrasings():
    assert is_player_insight_request('Insight check')
    assert is_player_insight_request('insight check on @Garrick')
    assert is_player_insight_request('I want to make an insight check')
    assert is_player_insight_request('roll insight on the merchant')
    assert is_player_insight_request('/insight')
    assert is_player_insight_request('[Insight Check on @Garrick]')


def test_does_not_match_unrelated_messages():
    assert not is_player_insight_request('That gives me real insight.')
    assert not is_player_insight_request('I check the room for traps.')
    assert not is_player_insight_request('')


def test_parse_extracts_target_and_purpose():
    target, purpose = parse_player_insight_request(
        'Insight check on @Garrick about the missing caravan'
    )
    assert target == '@Garrick'
    assert purpose == 'the missing caravan'


def test_parse_extracts_about_clause_only():
    target, purpose = parse_player_insight_request(
        'Insight check about whether he is lying'
    )
    assert target is None
    assert purpose == 'whether he is lying'


def test_parse_returns_none_when_only_keyword():
    target, purpose = parse_player_insight_request('insight check')
    assert target is None
    assert purpose is None


# ---------------------------------------------------------------------------
# handle_player_insight_request
# ---------------------------------------------------------------------------

class _StubRoll:
    def __init__(self, total):
        self._total = total

    def result(self):
        return self._total


class _StubEntity:
    def __init__(self, uid, label, npc=False, memory=None):
        self.entity_uid = uid
        self._label = label
        self._npc = npc
        self.memory_buffer = memory or []
        self.insight_calls = []

    def label(self):
        return self._label

    def is_npc(self):
        return self._npc

    def insight_check(self, description=None):
        self.insight_calls.append(description)
        return _StubRoll(17)


class _StubRagHandler:
    def __init__(self, verdict=None):
        self.verdict = verdict or {
            'assessment': 'lie',
            'reason': 'Their hands are trembling.',
        }
        self.eval_calls = []
        self.log_calls = []

    def resolve_named_target(self, actor, target_spec, speaker=None, include_objects=False):
        return None

    def _evaluate_insight_assessment(self, observer, target, statement, roll, llm_conversation_handler):
        self.eval_calls.append({
            'observer': observer,
            'target': target,
            'statement': statement,
            'roll_total': roll.result(),
        })
        return self.verdict

    def _log_social_check(self, message, entities=None):
        self.log_calls.append((message, entities))


def _make_service(speaker, target, rag_handler=None,
                  llm_conversation_handler=None):
    """Build a minimally-wired ConversationService for unit testing."""
    emitted = []

    class _StubGame:
        username_to_sid = {'alice': ['sid-alice'], 'dm': ['sid-dm']}

        def get_entity_by_uid(self, uid):
            for entity in (speaker, target):
                if entity is not None and entity.entity_uid == uid:
                    return entity
            return None

        def get_map_for_entity(self, entity):
            return None

    class _StubSocketio:
        def emit(self, event, payload, to=None):
            emitted.append({'event': event, 'payload': payload, 'to': to})

    class _StubGameSession:
        def entity_by_uid(self, uid):
            return None

    rag_handler = rag_handler if rag_handler is not None else _StubRagHandler()
    llm_handler = llm_conversation_handler if llm_conversation_handler is not None else object()

    service = ConversationService(
        current_game_getter=lambda: _StubGame(),
        game_session=_StubGameSession(),
        socketio=_StubSocketio(),
        entity_rag_handler_getter=lambda: rag_handler,
        llm_conversation_handler_getter=lambda: llm_handler,
        roles_for_username_getter=lambda: (lambda username: ['dm'] if username == 'dm' else ['player']),
        entity_owners_getter=lambda: (lambda entity: ['alice'] if entity is speaker else []),
        entities_controlled_by_getter=lambda: (lambda username: [speaker] if username == 'alice' else []),
        logins_getter=lambda: [
            {'name': 'alice', 'role': ['player']},
            {'name': 'dm', 'role': ['dm']},
        ],
        logger=logging.getLogger('test_player_insight'),
    )
    return service, emitted, rag_handler


def test_handle_request_with_no_target_emits_clarification():
    speaker = _StubEntity('pc1', 'Player', npc=False)
    service, emitted, _ = _make_service(speaker, target=None)

    response, status = service.handle_player_insight_request(
        speaker, 'Insight check'
    )

    assert status == 200
    assert response['insight'] == 'needs_target'
    assert any(
        evt['payload']['message']['insight_check']['clarification'] == 'missing_target'
        for evt in emitted
    )
    # Goes only to player + DM.
    recipients = {evt['to'] for evt in emitted}
    assert recipients == {'sid-alice', 'sid-dm'}


def test_handle_request_with_no_purpose_and_no_history_asks_for_purpose():
    npc = _StubEntity('npc1', 'Garrick', npc=True)
    speaker = _StubEntity('pc1', 'Alice', npc=False, memory=[])
    service, emitted, _ = _make_service(speaker, target=npc)

    response, status = service.handle_player_insight_request(
        speaker,
        'Insight check on @Garrick',
        explicit_targets=[npc],
        mentioned_targets=[npc],
    )

    assert status == 200
    assert response['insight'] == 'needs_purpose'
    assert any(
        evt['payload']['message']['insight_check']['clarification'] == 'missing_purpose'
        for evt in emitted
    )


def test_handle_request_rolls_and_adjudicates():
    npc = _StubEntity('npc1', 'Garrick', npc=True)
    speaker = _StubEntity(
        'pc1', 'Alice', npc=False,
        memory=[{'source': npc, 'message': 'I never met the missing scribe.'}],
    )
    rag = _StubRagHandler(verdict={'assessment': 'lie', 'reason': 'He hesitated.'})
    service, emitted, _ = _make_service(speaker, target=npc, rag_handler=rag)

    response, status = service.handle_player_insight_request(
        speaker,
        'Insight check on @Garrick about the missing scribe',
        explicit_targets=[npc],
        mentioned_targets=[npc],
    )

    assert status == 200
    assert response['success'] is True
    assert response['insight']['assessment'] == 'lie'
    assert response['insight']['roll_total'] == 17
    assert speaker.insight_calls, 'insight_check must be invoked on the player'
    assert rag.eval_calls, 'DM LLM adjudicator must be consulted'
    assert rag.log_calls, 'social check must be logged for participants'
    private_payload = next(
        evt['payload']['message'] for evt in emitted
        if evt['payload']['message'].get('insight_check', {}).get('assessment')
    )
    assert private_payload['insight_check']['assessment'] == 'lie'
    assert 'You sense deception' in private_payload['message']
