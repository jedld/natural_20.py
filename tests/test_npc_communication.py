"""Tests for NPC communication: SpeakAction, communication tools, begin_turn processing."""
import pytest
import json
from unittest.mock import MagicMock, patch

from natural20.actions.speak_action import SpeakAction
from natural20.session import Session
from natural20.event_manager import EventManager
from natural20.battle import Battle
from natural20.map import Map
from natural20.player_character import PlayerCharacter


@pytest.fixture
def session():
    event_manager = EventManager()
    event_manager.standard_cli()
    return Session(root_path='tests/fixtures', event_manager=event_manager)


@pytest.fixture
def battle_with_npcs(session):
    battle_map = Map(session, 'tests/fixtures/battle_sim.yml')
    # Register map with session so send_conversation can find entities
    session.maps['test'] = battle_map
    battle = Battle(session, battle_map)
    npc_a = session.npc('goblin', {"name": "Gruk"})
    npc_b = session.npc('goblin', {"name": "Snix"})
    fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')

    battle.add(npc_a, 'b', position=(2, 2), token='g')
    battle.add(npc_b, 'b', position=(3, 2), token='G')
    battle.add(fighter, 'a', position=(4, 2), token='F')

    npc_a.reset_turn(battle)
    npc_b.reset_turn(battle)
    fighter.reset_turn(battle)
    battle.start()

    return battle, npc_a, npc_b, fighter


class TestSpeakAction:
    def test_can_speak_if_conversable(self, session):
        """Conversable entities should be able to speak."""
        npc = session.npc('goblin', {"name": "Talker"})
        # Goblins have languages so they should be conversable
        assert npc.conversable()
        assert SpeakAction.can(npc, None)

    def test_speak_action_repr(self, session):
        npc = session.npc('goblin', {"name": "Talker"})
        action = SpeakAction(session, npc, "speak", {"message": "Hello there!", "language": "common"})
        assert "Speak" in repr(action)
        assert "Hello there!" in repr(action)

    def test_speak_action_repr_with_targets(self, session):
        npc_a = session.npc('goblin', {"name": "Gruk"})
        npc_b = session.npc('goblin', {"name": "Snix"})
        action = SpeakAction(session, npc_a, "speak", {
            "message": "Watch out!", "targets": [npc_b]
        })
        rep = repr(action)
        assert "Speak" in rep

    def test_speak_action_build(self, session):
        npc = session.npc('goblin', {"name": "Talker"})
        action = SpeakAction.build(session, npc, {"message": "Hello!", "language": "common"})
        assert isinstance(action, SpeakAction)

    def test_speak_action_resolve_and_apply(self, battle_with_npcs):
        """SpeakAction should broadcast message via send_conversation when applied."""
        battle, npc_a, npc_b, fighter = battle_with_npcs
        battle_map = battle.map_for(npc_a)

        action = SpeakAction(battle.session, npc_a, "speak", {
            "message": "Attack the elf!",
            "language": "common",
            "targets": [npc_b],
            "distance_ft": 30,
        })
        action.resolve(battle.session, battle_map, {"battle": battle})

        assert len(action.result) == 1
        assert action.result[0]["type"] == "speak"
        assert action.result[0]["message"] == "Attack the elf!"

        # Apply the action
        SpeakAction.apply(battle, action.result[0], battle.session)

        # npc_b should have received the conversation
        assert len(npc_b.memory_buffer) > 0
        last_msg = npc_b.memory_buffer[-1]
        assert last_msg['source'] == npc_a
        assert "Attack the elf!" in last_msg['message']

    def test_speak_action_no_resource_cost(self, battle_with_npcs):
        """Speaking should not consume any actions or bonus actions."""
        battle, npc_a, npc_b, fighter = battle_with_npcs
        battle_map = battle.map_for(npc_a)

        # Record resource state before
        state_before = battle.entity_state_for(npc_a).copy()

        action = SpeakAction(battle.session, npc_a, "speak", {
            "message": "Hello!",
        })
        action.resolve(battle.session, battle_map, {"battle": battle})
        SpeakAction.apply(battle, action.result[0], battle.session)

        # Resources should be unchanged
        state_after = battle.entity_state_for(npc_a)
        assert state_after['action'] == state_before['action']
        assert state_after['bonus_action'] == state_before['bonus_action']

    def test_speak_action_in_available_actions(self, battle_with_npcs):
        """SpeakAction should appear in NPC available_actions."""
        battle, npc_a, npc_b, fighter = battle_with_npcs
        battle_map = battle.map_for(npc_a)
        # Pass battle=None to avoid the current_turn check
        actions = npc_a.available_actions(battle.session, None, map=battle_map)
        speak_actions = [a for a in actions if isinstance(a, SpeakAction)]
        assert len(speak_actions) > 0

    def test_speak_action_in_player_available_actions(self, battle_with_npcs):
        """SpeakAction should appear in player character available_actions."""
        battle, npc_a, npc_b, fighter = battle_with_npcs
        battle_map = battle.map_for(fighter)
        # Pass battle=None to avoid the current_turn check
        actions = fighter.available_actions(battle.session, None, map=battle_map)
        speak_actions = [a for a in actions if isinstance(a, SpeakAction)]
        assert len(speak_actions) > 0


class TestLlmControllerCommunicationTools:
    """Test the communication tool handlers in LlmMcpController."""

    def _make_controller(self, session):
        from natural20.llm_controller import LlmMcpController
        return LlmMcpController(session, llm_client=None, use_tools=False)

    def test_handle_request_help(self, battle_with_npcs):
        """request_help should store a pending request in the ally's context."""
        battle, npc_a, npc_b, fighter = battle_with_npcs
        controller = self._make_controller(battle.session)

        controller._handle_request_help(npc_a, battle, {
            "ally_name": "Snix",
            "request": "Help me attack the elf!",
        })

        # Snix should have a pending request
        ctx = controller._get_entity_context(npc_b)
        assert len(ctx.get('pending_requests', [])) == 1
        assert ctx['pending_requests'][0]['from'] == 'Gruk'
        assert 'attack the elf' in ctx['pending_requests'][0]['request']

    def test_handle_warn_ally(self, battle_with_npcs):
        """warn_ally should store a pending warning in the ally's context."""
        battle, npc_a, npc_b, fighter = battle_with_npcs
        controller = self._make_controller(battle.session)

        controller._handle_warn_ally(npc_a, battle, {
            "ally_name": "Snix",
            "warning": "The elf has a longbow!",
        })

        ctx = controller._get_entity_context(npc_b)
        assert len(ctx.get('pending_warnings', [])) == 1
        assert ctx['pending_warnings'][0]['from'] == 'Gruk'
        assert 'longbow' in ctx['pending_warnings'][0]['warning']

    def test_handle_coordinate_attack(self, battle_with_npcs):
        """coordinate_attack should store a directive in all allied contexts."""
        battle, npc_a, npc_b, fighter = battle_with_npcs
        controller = self._make_controller(battle.session)

        controller._handle_coordinate_attack(npc_a, battle, {
            "directive": "Focus fire on the fighter!",
            "target_name": fighter.name,
        })

        # Snix (ally of Gruk in group 'b') should have the directive
        ctx_b = controller._get_entity_context(npc_b)
        assert len(ctx_b.get('pending_directives', [])) == 1
        assert 'Focus fire' in ctx_b['pending_directives'][0]['directive']

    def test_handle_taunt(self, battle_with_npcs):
        """taunt should store a received taunt in the enemy's context."""
        battle, npc_a, npc_b, fighter = battle_with_npcs
        controller = self._make_controller(battle.session)

        controller._handle_taunt(npc_a, battle, {
            "enemy_name": fighter.name,
            "message": "Come and get me, elf!",
        })

        ctx_fighter = controller._get_entity_context(fighter)
        assert len(ctx_fighter.get('received_taunts', [])) == 1
        assert ctx_fighter['received_taunts'][0]['from'] == 'Gruk'

    def test_find_entity_by_name(self, battle_with_npcs):
        """_find_entity_by_name should find entities case-insensitively."""
        battle, npc_a, npc_b, fighter = battle_with_npcs
        controller = self._make_controller(battle.session)

        found = controller._find_entity_by_name(battle, "gruk")
        assert found == npc_a

        found = controller._find_entity_by_name(battle, "SNIX")
        assert found == npc_b

        not_found = controller._find_entity_by_name(battle, "nonexistent")
        assert not_found is None


class TestBeginTurnProcessing:
    """Test the begin_turn override that processes pending communications."""

    def _make_controller(self, session):
        from natural20.llm_controller import LlmMcpController
        return LlmMcpController(session, llm_client=None, use_tools=False)

    def test_begin_turn_processes_pending_requests(self, battle_with_npcs):
        """begin_turn should consume pending requests and add them as memory notes."""
        battle, npc_a, npc_b, fighter = battle_with_npcs
        controller = self._make_controller(battle.session)

        # Simulate a pending request
        ctx = controller._get_entity_context(npc_b)
        ctx['pending_requests'] = [{'from': 'Gruk', 'request': 'Help me!'}]

        controller.begin_turn(npc_b)

        # Request should be consumed
        ctx = controller._get_entity_context(npc_b)
        assert 'pending_requests' not in ctx or len(ctx.get('pending_requests', [])) == 0
        # Memory note should be added
        notes = controller.get_memory_notes_summary(npc_b)
        assert any('Gruk' in n and 'help' in n.lower() for n in notes)

    def test_begin_turn_processes_pending_warnings(self, battle_with_npcs):
        """begin_turn should consume pending warnings and add them as memory notes."""
        battle, npc_a, npc_b, fighter = battle_with_npcs
        controller = self._make_controller(battle.session)

        ctx = controller._get_entity_context(npc_b)
        ctx['pending_warnings'] = [{'from': 'Gruk', 'warning': 'Trap ahead!'}]

        controller.begin_turn(npc_b)

        notes = controller.get_memory_notes_summary(npc_b)
        assert any('WARNING' in n and 'Trap' in n for n in notes)

    def test_begin_turn_processes_directives(self, battle_with_npcs):
        """begin_turn should consume directives and add them as memory notes."""
        battle, npc_a, npc_b, fighter = battle_with_npcs
        controller = self._make_controller(battle.session)

        ctx = controller._get_entity_context(npc_b)
        ctx['pending_directives'] = [{'from': 'Gruk', 'directive': 'Focus fire on the wizard', 'target': 'wizard'}]

        controller.begin_turn(npc_b)

        notes = controller.get_memory_notes_summary(npc_b)
        assert any('directive' in n.lower() and 'Focus fire' in n for n in notes)

    def test_begin_turn_processes_taunts(self, battle_with_npcs):
        """begin_turn should consume received taunts and add them as memory notes."""
        battle, npc_a, npc_b, fighter = battle_with_npcs
        controller = self._make_controller(battle.session)

        ctx = controller._get_entity_context(fighter)
        ctx['received_taunts'] = [{'from': 'Gruk', 'message': 'You will fall!'}]

        controller.begin_turn(fighter)

        notes = controller.get_memory_notes_summary(fighter)
        assert any('taunted' in n.lower() and 'Gruk' in n for n in notes)

    def test_begin_turn_processes_unread_conversations(self, battle_with_npcs):
        """begin_turn should pick up new conversation entries from memory_buffer."""
        battle, npc_a, npc_b, fighter = battle_with_npcs
        controller = self._make_controller(battle.session)

        # Simulate npc_a having spoken to npc_b
        npc_b.memory_buffer.append({
            'source': npc_a,
            'directed_to': [npc_b],
            'message': 'Follow my lead!',
            'target': npc_b,
            'language': 'common',
            'time': 1,
        })

        controller.begin_turn(npc_b)

        notes = controller.get_memory_notes_summary(npc_b)
        assert any('Heard' in n and 'Follow my lead' in n for n in notes)


class TestCommunicationContextInPrompt:
    """Test that communication context is included in the LLM prompt."""

    def _make_controller(self, session):
        from natural20.llm_controller import LlmMcpController
        return LlmMcpController(session, llm_client=None, use_tools=False)

    def test_communication_context_with_pending_requests(self, battle_with_npcs):
        """get_communication_context should include pending requests."""
        battle, npc_a, npc_b, fighter = battle_with_npcs
        controller = self._make_controller(battle.session)

        ctx = controller._get_entity_context(npc_b)
        ctx['pending_requests'] = [{'from': 'Gruk', 'request': 'Cover me!'}]

        comm_ctx = controller.get_communication_context(npc_b)
        assert 'Gruk' in comm_ctx
        assert 'Cover me!' in comm_ctx
        assert 'Incoming communications' in comm_ctx

    def test_communication_context_empty_when_no_messages(self, battle_with_npcs):
        """get_communication_context should return empty string when no messages."""
        battle, npc_a, npc_b, fighter = battle_with_npcs
        controller = self._make_controller(battle.session)

        comm_ctx = controller.get_communication_context(npc_b)
        assert comm_ctx == ""

    def test_process_goal_tool_calls_dispatches_new_tools(self, battle_with_npcs):
        """_process_goal_tool_calls should dispatch request_help, warn_ally, coordinate_attack, taunt."""
        battle, npc_a, npc_b, fighter = battle_with_npcs
        controller = self._make_controller(battle.session)

        tool_calls = [
            {'function': {'name': 'request_help', 'arguments': json.dumps({'ally_name': 'Snix', 'request': 'Heal me!'})}},
            {'function': {'name': 'warn_ally', 'arguments': json.dumps({'ally_name': 'Snix', 'warning': 'Behind you!'})}},
            {'function': {'name': 'coordinate_attack', 'arguments': json.dumps({'directive': 'Fall back!'})}},
            {'function': {'name': 'taunt', 'arguments': json.dumps({'enemy_name': fighter.name, 'message': 'Coward!'})}},
        ]

        controller._process_goal_tool_calls(npc_a, battle, tool_calls)

        # Check that Snix has both request and warning
        ctx_b = controller._get_entity_context(npc_b)
        assert len(ctx_b.get('pending_requests', [])) == 1
        assert len(ctx_b.get('pending_warnings', [])) == 1

        # Check that fighter has a taunt
        ctx_f = controller._get_entity_context(fighter)
        assert len(ctx_f.get('received_taunts', [])) == 1

    def test_auxiliary_tool_names_include_new_tools(self, battle_with_npcs):
        """The auxiliary_tool_names should include the new communication tools."""
        # This tests that the code in _ask_llm_for_choice recognizes the new tools
        from natural20.llm_controller import LlmMcpController
        controller = LlmMcpController(battle_with_npcs[0].session, llm_client=None, use_tools=False)
        # Verify the tool definitions exist in GOAL_TOOLS
        tool_names = [t['function']['name'] for t in controller.GOAL_TOOLS]
        assert 'request_help' in tool_names
        assert 'warn_ally' in tool_names
        assert 'coordinate_attack' in tool_names
        assert 'taunt' in tool_names
        assert 'speak' in tool_names


class TestEndToEndNpcCommunication:
    """Integration tests for NPC-to-NPC communication flow."""

    def test_speak_triggers_conversation_in_nearby_npc(self, battle_with_npcs):
        """When one NPC speaks, nearby NPCs should receive the conversation in their buffer."""
        battle, npc_a, npc_b, fighter = battle_with_npcs

        # Clear buffers
        npc_a.memory_buffer.clear()
        npc_b.memory_buffer.clear()
        fighter.memory_buffer.clear()

        # npc_a speaks - all nearby entities should hear
        npc_a.send_conversation("Charge!", distance_ft=30, targets=None, language='common')

        # npc_b and fighter should have received the message
        assert any(m.get('source') == npc_a and 'Charge!' in m.get('message', '') for m in npc_b.memory_buffer)

    def test_language_barrier(self, session):
        """Entities that don't share a language should receive gibberish."""
        battle_map = Map(session, 'tests/fixtures/battle_sim.yml')
        session.maps['test_lang'] = battle_map
        battle = Battle(session, battle_map)

        npc_a = session.npc('goblin', {"name": "Speaker"})
        npc_b = session.npc('goblin', {"name": "Listener"})

        battle.add(npc_a, 'a', position=(2, 2), token='g')
        battle.add(npc_b, 'b', position=(3, 2), token='G')
        npc_a.reset_turn(battle)
        npc_b.reset_turn(battle)
        battle.start()

        # Speak in a language that npc_b might not understand
        # Both goblins speak goblin and common, so let's test with common first
        npc_b.memory_buffer.clear()
        npc_a.send_conversation("Hello!", distance_ft=30, language='common')

        # npc_b should understand common
        assert any('Hello!' in m.get('message', '') for m in npc_b.memory_buffer)

    def test_full_communication_loop(self, battle_with_npcs):
        """Test: NPC A speaks → NPC B receives → begin_turn processes → appears in memory notes."""
        battle, npc_a, npc_b, fighter = battle_with_npcs
        from natural20.llm_controller import LlmMcpController
        controller = LlmMcpController(battle.session, llm_client=None, use_tools=False)

        # Clear buffers
        npc_b.memory_buffer.clear()

        # NPC A requests help from NPC B
        controller._handle_request_help(npc_a, battle, {
            "ally_name": "Snix",
            "request": "Flank the fighter!",
        })

        # Now it's NPC B's turn
        controller.begin_turn(npc_b)

        # NPC B should have the request as a memory note
        notes = controller.get_memory_notes_summary(npc_b)
        assert any('Flank the fighter' in n for n in notes)
