"""Tests for the MCP tool surface in webapp/mcp/."""

from unittest.mock import ANY, MagicMock

import pytest


@pytest.fixture
def context_and_registry():
    from natural20.actions.interact_action import InteractAction
    from webapp.mcp import MCPContext, build_default_registry

    def _action_class_resolver(action_type: str):
        if action_type == 'InteractAction':
            return InteractAction
        return None

    fake_entity = MagicMock()
    fake_entity.entity_uid = 'e1'
    fake_entity.name = 'Goblin'
    fake_entity.label.return_value = 'Goblin'
    fake_entity.hp.return_value = 7
    fake_entity.max_hp.return_value = 12
    fake_entity.armor_class.return_value = 13
    fake_entity.statuses = []
    fake_entity.dead.return_value = False
    fake_entity.unconscious.return_value = False
    fake_entity.is_npc.return_value = True
    fake_entity.attributes = {'hp': 7}
    fake_entity.ability_scores = {'str': 10}
    fake_entity.properties = {}
    fake_entity.inventory = {}

    fake_map = MagicMock()
    fake_map.name = 'index'
    fake_map.size = (10, 10)
    fake_map.feet_per_grid = 5
    fake_map.entities = {fake_entity: {'group': 'a'}}
    fake_map.interactable_objects = {}
    fake_map.entity_or_object_pos.return_value = (3, 4)
    fake_map.background_image.return_value = None
    fake_map.entity_by_uid.return_value = fake_entity
    fake_map.object_by_uid.return_value = None

    fake_game = MagicMock()
    fake_game.maps = {'index': fake_map}
    fake_game.get_entity_by_uid.return_value = fake_entity
    fake_game.get_map_for_entity.return_value = fake_map
    fake_game.get_current_battle.return_value = None

    fake_session = MagicMock()
    fake_session.root_path = None

    ctx = MCPContext(
        game_session_getter=lambda: fake_session,
        current_game_getter=lambda: fake_game,
        action_class_resolver=_action_class_resolver,
    )
    registry = build_default_registry()
    return ctx, registry, fake_entity, fake_map, fake_game


def test_registry_contains_expected_tools(context_and_registry):
    _, registry, *_ = context_and_registry
    names = {t['name'] for t in registry.list()}
    expected = {
        'world.list_maps', 'world.list_entities', 'world.get_entity',
        'world.get_map', 'world.get_battle',
        'dm.set_hp', 'dm.heal', 'dm.damage', 'dm.add_status',
        'dm.spawn_npc', 'dm.teleport', 'dm.add_item',
        'actions.list_available', 'actions.execute', 'actions.move',
        'actions.end_turn', 'actions.start_battle', 'actions.end_battle',
    }
    assert expected.issubset(names)


def test_world_list_maps(context_and_registry):
    ctx, registry, *_ = context_and_registry
    env = registry.call('world.list_maps', {}, context=ctx)
    assert env['isError'] is False
    payload = env['content'][0]['json']
    assert payload['maps'][0]['name'] == 'index'
    assert payload['maps'][0]['size'] == [10, 10]


def test_world_get_entity(context_and_registry):
    ctx, registry, fake_entity, *_ = context_and_registry
    env = registry.call('world.get_entity', {'entity_uid': 'e1'}, context=ctx)
    assert env['isError'] is False
    data = env['content'][0]['json']
    assert data['entity_uid'] == 'e1'
    assert data['hp'] == 7


def test_dm_set_hp_clamps_to_max(context_and_registry):
    ctx, registry, fake_entity, *_ = context_and_registry
    env = registry.call('dm.set_hp', {'entity_uid': 'e1', 'hp': 999}, context=ctx)
    assert env['isError'] is False
    assert fake_entity.attributes['hp'] == 12


def test_dm_add_and_remove_status(context_and_registry):
    ctx, registry, fake_entity, *_ = context_and_registry
    registry.call('dm.add_status',
                  {'entity_uid': 'e1', 'status': 'Prone'}, context=ctx)
    assert 'prone' in fake_entity.statuses
    registry.call('dm.remove_status',
                  {'entity_uid': 'e1', 'status': 'prone'}, context=ctx)
    assert 'prone' not in fake_entity.statuses


def test_unknown_tool_returns_error(context_and_registry):
    ctx, registry, *_ = context_and_registry
    env = registry.call('does.not.exist', {}, context=ctx)
    assert env['isError'] is True
    assert 'Unknown tool' in env['content'][0]['text']


def test_missing_required_argument_returns_error(context_and_registry):
    ctx, registry, *_ = context_and_registry
    env = registry.call('world.get_entity', {}, context=ctx)
    assert env['isError'] is True
    assert 'entity_uid' in env['content'][0]['text']


def test_entity_not_found_error(context_and_registry):
    ctx, registry, _fake_entity, _fake_map, fake_game = context_and_registry
    fake_game.get_entity_by_uid.return_value = None
    for m in fake_game.maps.values():
        m.entity_by_uid.return_value = None
        m.object_by_uid.return_value = None
    env = registry.call('dm.heal',
                        {'entity_uid': 'missing', 'amount': 5}, context=ctx)
    assert env['isError'] is True


def test_world_list_entities_filters_by_npc_type(context_and_registry):
    ctx, registry, fake_entity, *_ = context_and_registry
    fake_entity.name = 'Thakbar'
    fake_entity.label.return_value = 'Thakbar'
    fake_entity.npc_type = 'goblin'

    env = registry.call(
        'world.list_entities',
        {'kind': 'npc', 'npc_type_contains': 'goblin'},
        context=ctx,
    )
    assert env['isError'] is False
    payload = env['content'][0]['json']
    assert payload['count'] == 1
    assert payload['entities'][0]['name'] == 'Thakbar'


def test_world_list_entities_npc_type_filter_can_return_zero(context_and_registry):
    ctx, registry, fake_entity, *_ = context_and_registry
    fake_entity.npc_type = 'orc'

    env = registry.call(
        'world.list_entities',
        {'kind': 'npc', 'npc_type_contains': 'goblin'},
        context=ctx,
    )
    assert env['isError'] is False
    payload = env['content'][0]['json']
    assert payload['count'] == 0
    assert payload['entities'] == []


def test_infer_action_type_from_opts_for_interactions():
    from webapp.mcp.tools_actions import _infer_action_type_from_opts

    assert _infer_action_type_from_opts({'action': 'open'}) == 'InteractAction'
    assert _infer_action_type_from_opts({'object_action': 'close'}) == 'InteractAction'
    assert _infer_action_type_from_opts({}) is None


def test_execute_interact_dm_direct_omits_entity_uid(context_and_registry):
    """DM can open doors without naming a PC — anchor falls back to the target object."""
    ctx, registry, fake_entity, fake_map, fake_game = context_and_registry
    door = MagicMock()
    door.entity_uid = 'door-uid'
    door.label.return_value = 'Door'

    fake_map.entity_by_uid.return_value = None
    fake_map.object_by_uid.return_value = door
    fake_game.get_entity_by_uid.return_value = None
    fake_game.commit_and_update = MagicMock()

    env = registry.call(
        'actions.execute',
        {
            'action_type': 'InteractAction',
            'target': 'door-uid',
            'opts': {'action': 'open'},
        },
        context=ctx,
    )
    assert env['isError'] is False
    data = env['content'][0]['json']
    assert data['actor'] == 'dungeon_master'
    assert data['target_uid'] == 'door-uid'
    assert 'context_entity_uid' not in data
    fake_game.commit_and_update.assert_called_once_with('dm', ANY, [door])


def test_execute_interact_explicit_context_entity_still_supported(context_and_registry):
    ctx, registry, fake_entity, fake_map, fake_game = context_and_registry
    door = MagicMock()
    door.entity_uid = 'door-uid'
    door.label.return_value = 'Door'

    fake_map.entity_by_uid.side_effect = lambda uid: fake_entity if uid == 'e1' else None
    fake_map.object_by_uid.side_effect = lambda uid: door if uid == 'door-uid' else None
    fake_game.get_entity_by_uid.side_effect = lambda uid: fake_entity if uid == 'e1' else None
    fake_game.commit_and_update = MagicMock()

    env = registry.call(
        'actions.execute',
        {
            'entity_uid': 'e1',
            'action_type': 'InteractAction',
            'target': 'door-uid',
            'opts': {'action': 'open'},
        },
        context=ctx,
    )
    assert env['isError'] is False
    data = env['content'][0]['json']
    assert data['context_entity_uid'] == 'e1'
    fake_game.commit_and_update.assert_called_once_with('dm', ANY, [fake_entity])
