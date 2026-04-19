import types

from natural20.session import Session
from natural20.battle import Battle
from natural20.llm_controller import LlmMcpController


def test_llm_mcp_controller_fallback():
    # Use test fixtures session
    session = Session('tests/fixtures')
    any_map = next(iter(session.maps.values()))
    battle = Battle(session, any_map)

    goblin = session.npc('goblin', {"group": "b"})
    hero = session.npc('goblin', {"group": "a"})

    battle.add(goblin, 'b', controller=LlmMcpController, position=(0, 0))
    battle.add(hero, 'a', position=(1, 0))

    battle.start(combat_order=[goblin, hero])

    controller = battle.controller_for(goblin)
    actions = goblin.available_actions(session, battle)

    choice = controller.select_action(battle, goblin, actions)
    assert choice is None or choice in actions


def test_llm_controller_entity_context():
    """Test that entity context (goals, memory notes) can be set and retrieved."""
    session = Session('tests/fixtures')
    controller = LlmMcpController(session)
    
    # Create a mock entity
    class MockEntity:
        entity_uid = 'test-entity-456'
        name = 'Test NPC'
    
    entity = MockEntity()
    
    # Test that context starts empty
    ctx = controller._get_entity_context(entity)
    assert ctx['short_term_goal'] is None
    assert ctx['long_term_goal'] is None
    assert ctx['memory_notes'] == []
    
    # Test setting goals
    controller.set_short_term_goal(entity, 'Attack the wizard')
    controller.set_long_term_goal(entity, 'Protect the king')
    
    assert controller._get_entity_context(entity)['short_term_goal'] == 'Attack the wizard'
    assert controller._get_entity_context(entity)['long_term_goal'] == 'Protect the king'
    
    # Test goals summary
    summary = controller.get_goals_summary(entity)
    assert 'Attack the wizard' in summary
    assert 'Protect the king' in summary
    
    # Test memory notes
    controller.add_memory_note(entity, 'Enemy is weak to fire')
    controller.add_memory_note(entity, 'Door is trapped')
    
    notes = controller.get_memory_notes_summary(entity)
    assert len(notes) == 2
    assert 'Enemy is weak to fire' in notes
    assert 'Door is trapped' in notes


def test_llm_controller_memory_note_limit():
    """Test that memory notes are limited to prevent unbounded growth."""
    session = Session('tests/fixtures')
    controller = LlmMcpController(session)
    
    class MockEntity:
        entity_uid = 'test-limit-entity'
        name = 'Test'
    
    entity = MockEntity()
    
    # Add more than 10 notes
    for i in range(15):
        controller.add_memory_note(entity, f'Note {i}')
    
    notes = controller._get_entity_context(entity)['memory_notes']
    assert len(notes) == 10  # Should be capped at 10
    # Should keep the most recent notes
    assert notes[-1] == 'Note 14'
    assert notes[0] == 'Note 5'  # First 5 should have been dropped


def test_llm_controller_clear_short_term_goal():
    """Test that short-term goals can be cleared."""
    session = Session('tests/fixtures')
    controller = LlmMcpController(session)
    
    class MockEntity:
        entity_uid = 'test-clear-goal'
        name = 'Test'
    
    entity = MockEntity()
    
    controller.set_short_term_goal(entity, 'Some goal')
    assert controller._get_entity_context(entity)['short_term_goal'] == 'Some goal'
    
    controller.clear_short_term_goal(entity)
    assert controller._get_entity_context(entity)['short_term_goal'] is None


def test_llm_controller_serialization():
    """Test that controller state including entity context is serialized."""
    session = Session('tests/fixtures')
    controller = LlmMcpController(session)
    
    class MockEntity:
        entity_uid = 'serialization-test'
        name = 'Test'
    
    entity = MockEntity()
    
    controller.set_long_term_goal(entity, 'Survive')
    controller.add_memory_note(entity, 'Important observation')
    
    # Serialize
    data = controller.to_dict()
    
    assert 'entity_context' in data
    assert 'serialization-test' in data['entity_context']
    assert data['entity_context']['serialization-test']['long_term_goal'] == 'Survive'
    
    # Deserialize
    restored = LlmMcpController.from_dict(data)
    ctx = restored._get_entity_context(entity)
    assert ctx['long_term_goal'] == 'Survive'
    assert 'Important observation' in ctx['memory_notes']


def test_llm_controller_conversation_summary():
    """Test conversation summary extraction from entity memory buffer."""
    session = Session('tests/fixtures')
    controller = LlmMcpController(session)
    
    class MockSource:
        name = 'Player'
    
    class MockEntity:
        entity_uid = 'convo-test'
        name = 'NPC'
        memory_buffer = [
            {'source': MockSource(), 'message': 'Hello friend!', 'language': 'common', 'directed_to': []},
            {'source': MockSource(), 'message': 'Watch out for traps!', 'language': 'common', 'directed_to': []},
        ]
        def languages(self):
            return ['common']
    
    entity = MockEntity()
    
    summary = controller._get_conversation_summary(entity, n=5)
    assert len(summary) == 2
    assert 'Player' in summary[0]
    assert 'Hello friend!' in summary[0]


def test_llm_controller_prompt_includes_only_visible_combat_logs():
    session = Session('tests/fixtures')
    controller = LlmMcpController(session)
    any_map = next(iter(session.maps.values()))
    battle = Battle(session, any_map)

    goblin = session.npc('goblin', {"group": "b", "name": "Goblin"})
    hero = session.npc('goblin', {"group": "a", "name": "Hero"})
    battle.add(goblin, 'b', position=(0, 0))
    battle.add(hero, 'a', position=(1, 0))
    battle.start(combat_order=[goblin, hero])

    class PromptLogger:
        def get_logs_for_entity(self, entity):
            if entity is goblin:
                return [
                    '2026:04:19.12:00:00: Goblin attacked Hero.',
                    '2026:04:19.12:00:01: Hero missed Goblin.',
                ]
            return ['2026:04:19.12:00:02: Hidden watcher log.']

    session.event_manager.output_logger = PromptLogger()

    actions = goblin.available_actions(session, battle)
    prompt = controller._build_prompt(battle, goblin, actions)

    assert 'Visible combat log:' in prompt
    assert 'Goblin attacked Hero.' in prompt
    assert 'Hero missed Goblin.' in prompt
    assert 'Hidden watcher log.' not in prompt


def test_llm_controller_goal_tool_processing():
    """Test that goal tool calls are properly processed."""
    session = Session('tests/fixtures')
    controller = LlmMcpController(session)
    any_map = next(iter(session.maps.values()))
    battle = Battle(session, any_map)
    
    class MockEntity:
        entity_uid = 'tool-test'
        name = 'Test'
    
    entity = MockEntity()
    
    # Simulate tool calls from LLM
    tool_calls = [
        {
            'function': {
                'name': 'set_short_term_goal',
                'arguments': '{"goal": "Flank the enemy"}'
            }
        },
        {
            'function': {
                'name': 'add_memory_note',
                'arguments': '{"note": "Enemy caster is low on HP"}'
            }
        }
    ]
    
    controller._process_goal_tool_calls(entity, battle, tool_calls)
    
    ctx = controller._get_entity_context(entity)
    assert ctx['short_term_goal'] == 'Flank the enemy'
    assert 'Enemy caster is low on HP' in ctx['memory_notes']


def test_llm_controller_speak_tool():
    """Test that the speak tool allows entities to communicate."""
    session = Session('tests/fixtures')
    controller = LlmMcpController(session)
    any_map = next(iter(session.maps.values()))
    battle = Battle(session, any_map)
    
    # Create a mock entity with send_conversation method
    class MockEntity:
        entity_uid = 'speaker-test'
        name = 'Test Speaker'
        sent_messages = []
        
        def send_conversation(self, message, distance_ft=30, targets=None, language=None):
            self.sent_messages.append({
                'message': message,
                'distance_ft': distance_ft,
                'targets': targets,
                'language': language
            })
    
    entity = MockEntity()
    
    # Simulate a speak tool call
    tool_calls = [
        {
            'function': {
                'name': 'speak',
                'arguments': '{"message": "Surrender now or face my wrath!", "language": "common"}'
            }
        }
    ]
    
    controller._process_goal_tool_calls(entity, battle, tool_calls)
    
    # Verify the message was sent
    assert len(entity.sent_messages) == 1
    assert entity.sent_messages[0]['message'] == "Surrender now or face my wrath!"
    assert entity.sent_messages[0]['language'] == "common"
    
    # Verify it was also recorded in memory
    ctx = controller._get_entity_context(entity)
    assert any('Surrender now' in note for note in ctx['memory_notes'])

def test_llm_controller_get_visible_entities():
    """Test the get_visible_entities perception tool."""
    session = Session('tests/fixtures')
    controller = LlmMcpController(session)
    any_map = next(iter(session.maps.values()))
    battle = Battle(session, any_map)
    
    # Create two entities on opposite sides
    goblin = session.npc('goblin', {"group": "b"})
    hero = session.npc('goblin', {"group": "a"})
    hero.name = "Hero"
    
    battle.add(goblin, 'b', position=(0, 0))
    battle.add(hero, 'a', position=(2, 0))
    battle.start(combat_order=[goblin, hero])
    
    # Test perception from goblin's perspective
    result = controller._handle_get_visible_entities(goblin, battle)
    
    assert 'error' not in result or result['error'] is None
    assert 'my_position' in result
    assert result['my_position'] == [0, 0]
    assert 'entities' in result
    assert len(result['entities']) >= 1  # Should see at least the hero
    
    # Find the hero in the results
    hero_info = next((e for e in result['entities'] if e['name'] == 'Hero'), None)
    assert hero_info is not None
    assert hero_info['position'] == [2, 0]
    assert hero_info['relationship'] == 'enemy'
    assert 0 <= hero_info['hp_percent'] <= 100


def test_llm_controller_get_visible_objects():
    """Test the get_visible_objects perception tool."""
    session = Session('tests/fixtures')
    controller = LlmMcpController(session)
    any_map = next(iter(session.maps.values()))
    battle = Battle(session, any_map)
    
    goblin = session.npc('goblin', {"group": "b"})
    battle.add(goblin, 'b', position=(0, 0))
    battle.start(combat_order=[goblin])
    
    # Test perception - should return a valid result structure
    result = controller._handle_get_visible_objects(goblin, battle)
    
    assert 'my_position' in result
    assert 'objects' in result
    assert 'count' in result
    assert isinstance(result['objects'], list)


def test_llm_controller_get_terrain_at():
    """Test the get_terrain_at perception tool."""
    session = Session('tests/fixtures')
    controller = LlmMcpController(session)
    any_map = next(iter(session.maps.values()))
    battle = Battle(session, any_map)
    
    goblin = session.npc('goblin', {"group": "b"})
    hero = session.npc('goblin', {"group": "a"})
    
    battle.add(goblin, 'b', position=(0, 0))
    battle.add(hero, 'a', position=(2, 0))
    battle.start(combat_order=[goblin, hero])
    
    # Test getting terrain at the hero's position
    result = controller._handle_get_terrain_at(goblin, battle, {'x': 2, 'y': 0})
    
    assert 'position' in result
    assert result['position'] == [2, 0]
    assert 'passable' in result
    # There's an entity at (2, 0), so should show that
    assert 'entity' in result
    
    # Test invalid coordinates
    result_invalid = controller._handle_get_terrain_at(goblin, battle, {'x': -1, 'y': -1})
    assert 'error' in result_invalid
    
    # Test missing parameters
    result_missing = controller._handle_get_terrain_at(goblin, battle, {})
    assert 'error' in result_missing


def test_llm_controller_compute_path_to():
    """Test the compute_path_to pathfinding tool."""
    session = Session('tests/fixtures')
    controller = LlmMcpController(session)
    any_map = next(iter(session.maps.values()))
    battle = Battle(session, any_map)
    
    goblin = session.npc('goblin', {"group": "b"})
    battle.add(goblin, 'b', position=(0, 0))
    battle.start(combat_order=[goblin])
    
    # Test pathfinding to a nearby position
    result = controller._handle_compute_path_to(goblin, battle, {'target_x': 2, 'target_y': 0})
    
    # Should either find a path or report unreachable
    assert 'reachable' in result or 'error' in result
    
    if result.get('reachable'):
        assert 'path' in result
        assert 'movement_cost_ft' in result
        assert 'movement_available_ft' in result
        assert 'can_reach' in result
        assert 'triggers_opportunity_attack' in result
        # Path should start at (0,0) and end at (2,0)
        if result['path']:
            assert result['path'][0] == (0, 0) or result['path'][0] == [0, 0]
    
    # Test missing parameters
    result_missing = controller._handle_compute_path_to(goblin, battle, {})
    assert 'error' in result_missing


def test_llm_controller_compute_path_to_entity():
    """Test the compute_path_to_entity pathfinding tool."""
    session = Session('tests/fixtures')
    controller = LlmMcpController(session)
    any_map = next(iter(session.maps.values()))
    battle = Battle(session, any_map)
    
    goblin = session.npc('goblin', {"group": "b"})
    hero = session.npc('goblin', {"group": "a"})
    hero.name = "Hero"
    
    battle.add(goblin, 'b', position=(0, 0))
    battle.add(hero, 'a', position=(4, 0))
    battle.start(combat_order=[goblin, hero])
    
    # Test pathfinding to the hero
    result = controller._handle_compute_path_to_entity(goblin, battle, {'entity_name': 'Hero'})
    
    # Should either find a path or report unreachable
    assert 'reachable' in result or 'error' in result
    
    if result.get('reachable'):
        assert 'target_entity' in result
        assert result['target_entity'] == 'Hero'
        assert 'path' in result
        assert 'destination' in result
        assert 'adjacent_positions' in result
    
    # Test with non-existent entity
    result_missing = controller._handle_compute_path_to_entity(goblin, battle, {'entity_name': 'NonExistent'})
    assert 'error' in result_missing
    assert 'not found' in result_missing['error'].lower()


def test_llm_controller_get_reachable_positions():
    """Test the get_reachable_positions pathfinding tool."""
    session = Session('tests/fixtures')
    controller = LlmMcpController(session)
    any_map = next(iter(session.maps.values()))
    battle = Battle(session, any_map)
    
    goblin = session.npc('goblin', {"group": "b"})
    battle.add(goblin, 'b', position=(5, 5))  # Position in middle of map
    battle.start(combat_order=[goblin])
    
    # Test getting reachable positions
    result = controller._handle_get_reachable_positions(goblin, battle, {'max_positions': 10})
    
    assert 'my_position' in result
    assert 'movement_available_ft' in result
    assert 'reachable_positions' in result
    assert 'count' in result
    
    # If there's movement available, should have some reachable positions
    if result['movement_available_ft'] > 0:
        assert isinstance(result['reachable_positions'], list)
        
        # Each position should have expected fields
        for pos in result['reachable_positions']:
            assert 'position' in pos
            assert 'movement_cost_ft' in pos
            assert 'triggers_oa' in pos


def test_llm_controller_get_optimal_ranged_position():
    """Test the get_optimal_ranged_position pathfinding tool."""
    session = Session('tests/fixtures')
    controller = LlmMcpController(session)
    any_map = next(iter(session.maps.values()))
    battle = Battle(session, any_map)
    
    goblin = session.npc('goblin', {"group": "b"})
    hero = session.npc('goblin', {"group": "a"})
    hero.name = "TargetHero"
    
    # Use positions that fit within the map bounds (map is 6x7)
    battle.add(goblin, 'b', position=(1, 1))
    battle.add(hero, 'a', position=(4, 3))
    battle.start(combat_order=[goblin, hero])
    
    # Test finding optimal ranged position
    result = controller._handle_get_optimal_ranged_position(goblin, battle, {
        'target_name': 'TargetHero',
        'preferred_range_ft': 30
    })
    
    # Should have a result structure
    if 'error' not in result:
        assert 'target' in result
        assert result['target'] == 'TargetHero'
        assert 'recommended_positions' in result
        assert 'preferred_range_ft' in result
        
        # Positions should be scored
        for pos in result.get('recommended_positions', []):
            assert 'position' in pos
            assert 'tactical_score' in pos
            assert 'distance_to_target_ft' in pos
    
    # Test with non-existent target
    result_missing = controller._handle_get_optimal_ranged_position(goblin, battle, {
        'target_name': 'NonExistent'
    })
    assert 'error' in result_missing


def test_llm_controller_perception_tool_via_tool_calls():
    """Test that perception tools can be invoked through the tool call interface."""
    session = Session('tests/fixtures')
    controller = LlmMcpController(session)
    any_map = next(iter(session.maps.values()))
    battle = Battle(session, any_map)
    
    goblin = session.npc('goblin', {"group": "b"})
    hero = session.npc('goblin', {"group": "a"})
    hero.name = "VisibleHero"
    
    battle.add(goblin, 'b', position=(0, 0))
    battle.add(hero, 'a', position=(2, 0))
    battle.start(combat_order=[goblin, hero])
    
    # Simulate tool calls from LLM for perception
    tool_calls = [
        {
            'function': {
                'name': 'get_visible_entities',
                'arguments': '{}'
            }
        }
    ]
    
    # Process the tool call
    results = controller._process_goal_tool_calls(goblin, battle, tool_calls)
    
    # Should have processed the tool and returned results
    assert results is not None
    # The result should be a list of tool results
    assert isinstance(results, list)
    if len(results) > 0:
        result = results[0]
        # Result is wrapped in {'tool': ..., 'result': ...}
        assert 'tool' in result
        assert result['tool'] == 'get_visible_entities'
        assert 'result' in result
        inner_result = result['result']
        assert 'entities' in inner_result or 'error' in inner_result


def test_llm_controller_pathfinding_tool_via_tool_calls():
    """Test that pathfinding tools can be invoked through the tool call interface."""
    session = Session('tests/fixtures')
    controller = LlmMcpController(session)
    any_map = next(iter(session.maps.values()))
    battle = Battle(session, any_map)
    
    goblin = session.npc('goblin', {"group": "b"})
    battle.add(goblin, 'b', position=(0, 0))
    battle.start(combat_order=[goblin])
    
    # Simulate tool calls from LLM for pathfinding
    tool_calls = [
        {
            'function': {
                'name': 'compute_path_to',
                'arguments': '{"target_x": 3, "target_y": 0}'
            }
        }
    ]
    
    # Process the tool call
    results = controller._process_goal_tool_calls(goblin, battle, tool_calls)
    
    # Should have processed the tool and returned results
    assert results is not None
    assert isinstance(results, list)
    if len(results) > 0:
        result = results[0]
        # Result is wrapped in {'tool': ..., 'result': ...}
        assert 'tool' in result
        assert result['tool'] == 'compute_path_to'
        assert 'result' in result
        inner_result = result['result']
        assert 'path' in inner_result or 'error' in inner_result or 'reachable' in inner_result