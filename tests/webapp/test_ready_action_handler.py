"""Tests for the webapp Ready/Hold action helper."""

import json
import os
import random
import sys
import unittest

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session

from webapp.ready_action_handler import (
    parse_ready_action_request,
    make_llm_resolver,
)


class _ScriptedProvider:
    """Minimal LLM provider stub returning a queued response per call."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def send_message(self, messages, context=None):
        self.calls.append(messages)
        if not self._responses:
            return ''
        return self._responses.pop(0)


class _StubLLMHandler:
    def __init__(self, provider):
        self.current_provider = provider

    def send_message(self, messages, context=None):
        return self.current_provider.send_message(messages, context)


def _make_battle():
    em = EventManager()
    em.standard_cli()
    session = Session(root_path='tests/fixtures', event_manager=em)
    bmap = Map(session, 'tests/fixtures/battle_sim.yml')
    battle = Battle(session, bmap)
    fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
    goblin = session.npc('goblin', {'name': 'g'})
    battle.add(fighter, 'a', position=(0, 0), token='F')
    battle.add(goblin, 'b', position=(0, 5), token='g')
    fighter.reset_turn(battle)
    goblin.reset_turn(battle)
    battle.start()
    return session, battle, fighter, goblin


class TestParseReadyActionRequest(unittest.TestCase):
    def setUp(self):
        random.seed(2024)
        self.session, self.battle, self.fighter, self.goblin = _make_battle()

    def test_empty_description_rejected(self):
        result = parse_ready_action_request(self.fighter, self.battle, '   ', None)
        self.assertFalse(result['approved'])
        self.assertIn('describe', result['reason'].lower())

    def test_heuristic_fallback_no_provider(self):
        result = parse_ready_action_request(
            self.fighter, self.battle,
            'When the goblin steps next to me I attack with my rapier.',
            None,
        )
        self.assertTrue(result['approved'])
        self.assertEqual(result['trigger']['event'], 'movement')
        self.assertEqual(result['trigger']['condition'], 'adjacent_to_self')
        self.assertEqual(result['action_spec']['kind'], 'attack')

    def test_heuristic_within_range_parses_distance(self):
        result = parse_ready_action_request(
            self.fighter, self.battle,
            'When anything comes within 20 ft, attack.',
            None,
        )
        self.assertEqual(result['trigger']['condition'], 'within_range')
        self.assertEqual(result['trigger']['range_ft'], 20)

    def test_llm_response_parsed(self):
        provider = _ScriptedProvider([
            json.dumps({
                'approved': True,
                'reason': 'Very well, Sir Knight.',
                'trigger': {
                    'event': 'movement',
                    'condition': 'adjacent_to_self',
                    'subject_filter': 'enemies',
                },
                'action_spec': {'kind': 'attack', 'weapon': 'vicious_rapier'},
            }),
        ])
        handler = _StubLLMHandler(provider)
        result = parse_ready_action_request(
            self.fighter, self.battle,
            'When the goblin steps adjacent, hit it with my rapier.',
            handler,
        )
        self.assertTrue(result['approved'])
        self.assertEqual(result['reason'], 'Very well, Sir Knight.')
        self.assertEqual(result['trigger']['condition'], 'adjacent_to_self')
        self.assertEqual(result['action_spec']['weapon'], 'vicious_rapier')
        self.assertEqual(len(provider.calls), 1)

    def test_llm_rejection_passes_through(self):
        provider = _ScriptedProvider([
            json.dumps({
                'approved': False,
                'reason': 'You may only take one reaction per round.',
                'trigger': {'event': 'movement'},
                'action_spec': {'kind': 'attack'},
            }),
        ])
        result = parse_ready_action_request(
            self.fighter, self.battle,
            'When the goblin moves, I make three attacks.',
            _StubLLMHandler(provider),
        )
        self.assertFalse(result['approved'])
        self.assertIn('reaction', result['reason'].lower())

    def test_llm_unknown_weapon_rejected_by_validator(self):
        provider = _ScriptedProvider([
            json.dumps({
                'approved': True,
                'reason': 'Sure.',
                'trigger': {'event': 'movement', 'condition': 'adjacent_to_self'},
                'action_spec': {'kind': 'attack', 'weapon': 'lightsaber'},
            }),
        ])
        result = parse_ready_action_request(
            self.fighter, self.battle,
            'When the goblin steps adjacent, hit it with my lightsaber.',
            _StubLLMHandler(provider),
        )
        self.assertFalse(result['approved'])
        self.assertIn('lightsaber', result['reason'])


class TestLLMResolverFactory(unittest.TestCase):
    def test_resolver_falls_back_to_default_without_provider(self):
        resolver = make_llm_resolver(None)
        self.assertTrue(callable(resolver))
        # default_resolver returns None for non-attack specs; just verify the
        # closure is invokable with sane arguments.
        from natural20.ready_action import ReadyActionState
        state = ReadyActionState(
            entity_uid='x',
            description='',
            trigger={'event': 'movement'},
            action_spec={'kind': 'attack'},
        )
        result = resolver(state, 'movement', {}, None, None)
        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()
