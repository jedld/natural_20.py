"""DM Assistant chat history persistence helpers."""

from webapp.llm_handler import LLMHandler


def test_displayable_conversation_history_skips_function_traces():
    history = [
        {'role': 'user', 'content': 'How many goblins are there?'},
        {
            'role': 'user',
            'content': (
                '[FUNCTION_CALL: mcp("world.list_entities", {"kind": "npc"})]: '
                'Function mcp returned: {"count": 8}'
            ),
            '_payload': {'count': 8},
        },
        {'role': 'assistant', 'content': 'There are 8 goblins on the current map.'},
    ]
    display = LLMHandler.displayable_conversation_history(history)
    assert display == [
        {'role': 'user', 'content': 'How many goblins are there?'},
        {'role': 'assistant', 'content': 'There are 8 goblins on the current map.'},
    ]


def test_conversation_history_for_storage_strips_payload():
    history = [
        {'role': 'user', 'content': 'hi', '_payload': {'count': 1}},
        {'role': 'assistant', 'content': 'hello'},
    ]
    stored = LLMHandler.conversation_history_for_storage(history)
    assert stored == [
        {'role': 'user', 'content': 'hi'},
        {'role': 'assistant', 'content': 'hello'},
    ]
