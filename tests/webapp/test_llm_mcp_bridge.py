"""Tests for the upgraded LLM function-call parser and the MCP bridge."""

import pytest

from webapp.llm_handler import LLMHandler


@pytest.fixture
def handler():
    return LLMHandler()


def test_extract_function_calls_dotted_name_and_json_args(handler):
    response = (
        'Sure: [FUNCTION_CALL: world.list_entities({"kind": "npc", '
        '"name_contains": "goblin, sneaky"})]'
    )
    matches = handler._extract_function_calls(response)
    assert len(matches) == 1
    name, arg_str = matches[0]
    assert name == 'world.list_entities'
    assert arg_str == '{"kind": "npc", "name_contains": "goblin, sneaky"}'


def test_extract_function_calls_legacy_format_still_works(handler):
    response = '[FUNCTION_CALL: get_entities()]\n[FUNCTION_CALL: get_entity_details("Goblin King")]'
    matches = handler._extract_function_calls(response)
    assert [m[0] for m in matches] == ['get_entities', 'get_entity_details']
    assert matches[1][1] == '"Goblin King"'


def test_extract_function_calls_comma_json_args(handler):
    response = '[FUNCTION_CALL: dm.spawn_npc_near, {"npc_type": "goblin", "near_entity": "gabba"}]'
    matches = handler._extract_function_calls(response)
    assert len(matches) == 1
    name, arg_str = matches[0]
    assert name == 'dm.spawn_npc_near'
    assert arg_str == '{"npc_type": "goblin", "near_entity": "gabba"}'


def test_parse_function_args_handles_json_object(handler):
    args, kwargs = handler._parse_function_args('"world.list_entities", {"kind": "npc"}')
    assert args == ['world.list_entities', {'kind': 'npc'}]
    assert kwargs == {}


def test_parse_function_args_handles_kwargs(handler):
    args, kwargs = handler._parse_function_args('entity_name="Goblin King", verbose=true')
    assert args == []
    assert kwargs == {'entity_name': 'Goblin King', 'verbose': True}


def test_parse_function_args_handles_numbers_and_booleans(handler):
    args, kwargs = handler._parse_function_args('42, 3.14, true, false, null')
    assert args == [42, 3.14, True, False, None]
    assert kwargs == {}


def test_mcp_bridge_dispatches_to_registry(handler):
    """Register a fake `mcp` function and verify the parser routes a JSON
    object argument through correctly."""
    captured = {}

    def fake_mcp(tool_name, arguments=None):
        captured['tool'] = tool_name
        captured['args'] = arguments
        return {'ok': True, 'count': 0}

    handler.register_game_context_function('mcp', fake_mcp, 'fake bridge')
    response = (
        '[FUNCTION_CALL: mcp("world.list_entities", {"kind": "npc", '
        '"name_contains": "goblin"})]'
    )
    results = handler.parse_and_execute_function_calls(response)
    assert captured == {
        'tool': 'world.list_entities',
        'args': {'kind': 'npc', 'name_contains': 'goblin'},
    }
    # Result key uses positional repr; just check the value made it through.
    assert any(v == {'ok': True, 'count': 0} for v in results.values())


def test_bare_dotted_mcp_tool_name_is_routed_to_mcp_bridge(handler):
    captured = {}

    def fake_mcp(tool_name, arguments=None):
        captured['tool'] = tool_name
        captured['args'] = arguments
        return {'ok': True}

    handler.register_game_context_function('mcp', fake_mcp, 'fake bridge')
    response = '[FUNCTION_CALL: world.list_npc_types()]'

    results = handler.parse_and_execute_function_calls(response)

    assert captured == {'tool': 'world.list_npc_types', 'args': {}}
    assert any(v == {'ok': True} for v in results.values())


def test_bare_dotted_mcp_tool_name_accepts_kwargs(handler):
    captured = {}

    def fake_mcp(tool_name, arguments=None):
        captured['tool'] = tool_name
        captured['args'] = arguments
        return {'ok': True, 'n': 1}

    handler.register_game_context_function('mcp', fake_mcp, 'fake bridge')
    response = '[FUNCTION_CALL: world.list_entities(kind="npc", name_contains="goblin")]'

    results = handler.parse_and_execute_function_calls(response)

    assert captured == {
        'tool': 'world.list_entities',
        'args': {'kind': 'npc', 'name_contains': 'goblin'},
    }
    assert any(v == {'ok': True, 'n': 1} for v in results.values())


def test_comma_style_bare_dotted_name_routes_to_mcp(handler):
    captured = {}

    def fake_mcp(tool_name, arguments=None):
        captured['tool'] = tool_name
        captured['args'] = arguments
        return {'ok': True}

    handler.register_game_context_function('mcp', fake_mcp, 'fake bridge')
    response = '[FUNCTION_CALL: dm.spawn_npc_near, {"npc_type": "goblin", "near_entity": "gabba"}]'

    results = handler.parse_and_execute_function_calls(response)

    assert captured == {
        'tool': 'dm.spawn_npc_near',
        'args': {'npc_type': 'goblin', 'near_entity': 'gabba'},
    }
    assert any(v == {'ok': True} for v in results.values())


def test_count_query_short_circuits_after_mcp_process(handler):
    captured = {}

    class FakeMcp:
        def __call__(self, tool_name, arguments=None):
            captured['tool'] = tool_name
            return {'entities': [], 'count': 8, 'filters': {'kind': 'npc'}}

    handler.register_game_context_function('mcp', FakeMcp(), 'fake')
    response = (
        '[FUNCTION_CALL: mcp("world.list_entities", '
        '{"kind": "npc", "npc_type_contains": "goblin"})]'
    )
    processed = handler._process_function_calls(response, None)
    out = handler._try_count_query_reply('How many goblins are there?', processed)
    assert captured['tool'] == 'world.list_entities'
    assert out == 'There are 8 goblins on the current map.'
    assert '_payload' in processed[0]


def test_format_function_results_count_query_uses_payload_count(handler):
    class NeverCalledProvider:
        def send_message(self, _messages):
            raise AssertionError('provider should not be called for deterministic count formatting')

    handler.current_provider = NeverCalledProvider()
    processed = [{
        'role': 'system',
        'content': (
            '[FUNCTION_CALL: mcp("world.list_entities", {"kind": "npc"})]: '
            "Function mcp returned: {'entities': [], 'count': 8, 'filters': {'kind': 'npc'}}"
        ),
    }]
    out = handler._format_function_results(processed, original_message='How many goblins are there?')
    assert out == 'There are 8 goblins on the current map.'


def test_format_function_results_count_query_uses_structured_payload(handler):
    class NeverCalledProvider:
        def send_message(self, _messages):
            raise AssertionError('provider should not be called for deterministic count formatting')

    handler.current_provider = NeverCalledProvider()
    processed = [{
        'role': 'user',
        'content': '[FUNCTION_CALL: mcp("world.list_entities", {"kind": "npc"})]: Function mcp returned: {...}',
        '_payload': {'entities': [{'name': 'a'}], 'count': 3},
    }]
    out = handler._format_function_results(processed, original_message='How many goblins are there?')
    assert out == 'There are 3 goblins on the current map.'


def test_format_function_results_count_query_uses_entities_length(handler):
    class NeverCalledProvider:
        def send_message(self, _messages):
            raise AssertionError('provider should not be called when entities list is present')

    handler.current_provider = NeverCalledProvider()
    processed = [{
        'role': 'system',
        'content': (
            '[FUNCTION_CALL: mcp("world.list_entities", {"kind": "npc"})]: '
            "Function mcp returned: {'entities': [{'name': 'a'}, {'name': 'b'}]}"
        ),
    }]
    out = handler._format_function_results(processed, original_message='How many goblins are there?')
    assert out == 'There are 2 goblins on the current map.'


def test_build_system_prompt_reads_nested_context_map(handler):
    prompt = handler._build_system_prompt({
        'get_map_info': {'name': 'index'},
        'session': {'current_map': 'index'},
        'get_entities': [{'name': 'a'}, {'name': 'b'}],
        'get_battle_status': {'active': False},
    })
    assert 'Current Map: index' in prompt
    assert 'Entities on Map: 2' in prompt
    assert 'Current map entity roster' in prompt
    assert '- a |' in prompt and '- b |' in prompt


def test_compact_entity_roster_respects_uid_and_hp(handler):
    prompt = handler._build_system_prompt({
        'get_map_info': {'name': 'tavern'},
        'get_entities': [{
            'name': 'RumbleBelly',
            'entity_uid': 'rumblebelly',
            'type': 'PlayerCharacter',
            'position': [1, 4],
            'hp': 16,
            'max_hp': 16,
        }],
        'get_battle_status': {'active': False},
    })
    assert 'uid=rumblebelly' in prompt
    assert '16/16 HP' in prompt
    assert 'pos=[1, 4]' in prompt


def test_entity_mutation_fallback_sets_generic_property(handler):
    captured = {}

    def fake_mcp(tool_name, arguments=None):
        captured['tool'] = tool_name
        captured['args'] = arguments
        return {'ok': True}

    handler.register_game_context_function('mcp', fake_mcp, 'fake bridge')
    function_results = [{
        'role': 'system',
        'content': (
            "[FUNCTION_CALL: get_entities()]: Function get_entities returned: "
            "[{'name': 'RumbleBelly', 'entity_uid': 'rumblebelly'}]"
        ),
    }]

    out = handler._maybe_execute_entity_mutation_from_context(
        'Set RumbleBelly initiative to 9',
        function_results,
    )

    assert out is not None
    assert captured == {
        'tool': 'dm.set_property',
        'args': {'entity_uid': 'rumblebelly', 'key': 'initiative', 'value': 9},
    }


def test_dm_add_item_fallback_after_world_list_entities(handler):
    captured = {}

    def fake_mcp(tool_name, arguments=None):
        captured['tool'] = tool_name
        captured['args'] = arguments
        return {'entity_uid': 'rumblebelly', 'item_name': 'healing_potion', 'qty': 1}

    handler.register_game_context_function('mcp', fake_mcp, 'fake bridge')
    function_results = [{
        'role': 'system',
        'content': (
            '[FUNCTION_CALL: mcp("world.list_entities", {"name_contains": "rumblebelly"})]: '
            "Function mcp returned: {'entities': [{'entity_uid': 'rumblebelly', "
            "'name': 'RumbleBelly'}], 'count': 1}"
        ),
    }]

    out = handler._maybe_execute_dm_add_item_from_context(
        'Give rumblebelly a health potion',
        function_results,
    )

    assert out is not None
    assert captured == {
        'tool': 'dm.add_item',
        'args': {'entity_uid': 'rumblebelly', 'item_name': 'healing_potion', 'qty': 1},
    }


def test_dm_add_item_fallback_skips_when_add_item_already_ran(handler):
    calls = []

    def fake_mcp(tool_name, arguments=None):
        calls.append(tool_name)
        return {}

    handler.register_game_context_function('mcp', fake_mcp, 'fake bridge')
    function_results = [{
        'role': 'system',
        'content': (
            '[FUNCTION_CALL: mcp("dm.add_item", {"entity_uid": "rumblebelly", '
            '"item_name": "healing_potion"})]: '
            "Function mcp returned: {'ok': True}"
        ),
    }]

    out = handler._maybe_execute_dm_add_item_from_context(
        'Give rumblebelly a health potion',
        function_results,
    )

    assert out is None
    assert calls == []


def test_entity_mutation_fallback_sets_temp_hp_resource(handler):
    captured = {}

    def fake_mcp(tool_name, arguments=None):
        captured['tool'] = tool_name
        captured['args'] = arguments
        return {'ok': True}

    handler.register_game_context_function('mcp', fake_mcp, 'fake bridge')
    function_results = [{
        'role': 'system',
        'content': (
            "[FUNCTION_CALL: get_entities()]: Function get_entities returned: "
            "[{'name': 'RumbleBelly', 'entity_uid': 'rumblebelly'}]"
        ),
    }]

    out = handler._maybe_execute_entity_mutation_from_context(
        'Set temp hp for RumbleBelly to 7',
        function_results,
    )

    assert out is not None
    assert captured == {
        'tool': 'dm.set_resource',
        'args': {
            'entity_uid': 'rumblebelly',
            'resource_type': 'temp_hp',
            'op': 'set',
            'value': 7,
        },
    }


def test_only_first_message_may_be_system_coerces_llama_compatible_roles(handler):
    """llama.cpp rejects transcripts with ``system`` after the first message."""
    msgs = [
        {'role': 'system', 'content': 'instructions'},
        {'role': 'user', 'content': 'hi'},
        {'role': 'system', 'content': 'tool trace'},
    ]
    LLMHandler._only_first_message_may_be_system(msgs)
    assert [m['role'] for m in msgs] == ['system', 'user', 'user']
