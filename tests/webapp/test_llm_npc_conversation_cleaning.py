import os
import sys

WEBAPP_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'webapp')
if WEBAPP_DIR not in sys.path:
    sys.path.insert(0, WEBAPP_DIR)

from webapp.llm_handler import LLMHandler


def test_conversation_mode_preserves_let_me_dialogue():
    handler = LLMHandler()
    line = "Let me go."

    cleaned_dm = handler._clean_response(line, response_mode='dm')
    cleaned_npc = handler._clean_response(line, response_mode='conversation')

    assert 'help with your D&D game' in cleaned_dm
    assert cleaned_npc == line


def test_conversation_mode_empty_fallback_is_silent():
    handler = LLMHandler()
    thinking_only = """<think>
Let me think about how to answer...
</think>"""

    cleaned = handler._clean_response(thinking_only, response_mode='conversation')

    assert cleaned == '...'
    assert 'help with your D&D game' not in cleaned


def test_json_response_is_complete_without_continuation():
    handler = LLMHandler()
    payload = '{"spoken": "Hello.", "narrative": []}'
    assert handler._response_looks_complete(payload) is True


def test_dialogue_with_internal_ellipsis_is_complete():
    handler = LLMHandler()
    line = "It's in the basement... Please will you help us?"
    assert handler._response_looks_complete(line) is True


def test_dm_mode_empty_fallback_stays_assistant():
    handler = LLMHandler()
    thinking_only = """<think>
Only internal reasoning here.
</think>"""

    cleaned = handler._clean_response(thinking_only, response_mode='dm')

    assert 'help with your D&D game' in cleaned
