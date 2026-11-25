"""Player instruction following through the System One (JEV) decision model.

``InstructionPlanner.follow_instruction_step`` turns a free-text player
instruction into one legal leaf action per decision call, with loop-control
sentinels for stop / end-turn / ready. ``parse_player_instruction`` answers
the Ready (hold) trigger + action questions with two flat Choice calls.
"""

import random
import unittest

from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session

from natural20.utils.instruction_follow import (
    InstructionEndTurn,
    InstructionReady,
    InstructionStop,
    follow_instruction_step,
    is_instruction_sentinel,
    parse_player_instruction,
    provider_can_follow_instructions,
)


class _FakeProvider:
    """Decides by keyword; falls back to the last option (the stop leaf)."""

    is_available = True

    def __init__(self, keyword=None):
        self.keyword = keyword
        self.calls = []

    def decide_action(self, state, options):
        self.calls.append((state, list(options)))
        if self.keyword:
            for i, opt in enumerate(options):
                if opt.startswith(self.keyword):
                    return {'index': i}
        return {'index': len(options) - 1}


class _SequenceProvider:
    """Returns queued option indexes, one per decision call."""

    is_available = True

    def __init__(self, indexes):
        self._indexes = list(indexes)
        self.calls = []

    def decide_action(self, state, options):
        self.calls.append((state, list(options)))
        idx = self._indexes.pop(0) if self._indexes else len(options) - 1
        return {'index': idx}


class _UnavailableProvider:
    is_available = False

    def decide_action(self, state, options):  # pragma: no cover
        raise AssertionError('must not be called')


def _make_battle():
    session = Session(root_path='tests/fixtures', event_manager=EventManager())
    battle_map = Map(session, 'tests/fixtures/battle_sim.yml')
    session.maps['battle_sim'] = battle_map
    battle = Battle(session, battle_map)
    fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
    goblin = session.npc('goblin', {'name': 'g'})
    battle.add(fighter, 'a', position=(0, 0), token='F')
    battle.add(goblin, 'b', position=(0, 1), token='g')
    fighter.reset_turn(battle)
    goblin.reset_turn(battle)
    battle.start()
    return session, battle_map, battle, fighter, goblin


class TestProviderGuard(unittest.TestCase):
    def test_requires_decide_action(self):
        self.assertTrue(provider_can_follow_instructions(_FakeProvider()))
        self.assertFalse(provider_can_follow_instructions(None))
        self.assertFalse(provider_can_follow_instructions(_UnavailableProvider()))
        self.assertFalse(provider_can_follow_instructions(object()))


class TestInstructionSteps(unittest.TestCase):
    def setUp(self):
        random.seed(11)
        self.session, self.map, self.battle, self.fighter, self.goblin = _make_battle()

    def test_step_picks_matching_leaf(self):
        provider = _FakeProvider(keyword='attack')
        action, desc = follow_instruction_step(
            provider, self.battle, self.fighter,
            'attack the goblin with your weapon')
        from natural20.actions.attack_action import AttackAction
        self.assertIsInstance(action, AttackAction)
        self.assertIn('attack', desc)
        # The decision state carries the instruction text.
        state = provider.calls[0][0]
        self.assertIn('The player instructed you', state)
        self.assertIn('attack the goblin with your weapon', state)
        # Stop leaf is always present and last.
        self.assertIn('stop', provider.calls[0][1][-1])

    def test_stop_when_model_refuses(self):
        provider = _FakeProvider()  # falls back to last option = stop
        action, desc = follow_instruction_step(
            provider, self.battle, self.fighter, 'do something fancy')
        self.assertIsInstance(action, InstructionStop)
        self.assertTrue(is_instruction_sentinel(action))

    def test_no_instruction_stops(self):
        action, _ = follow_instruction_step(
            _FakeProvider(keyword='attack'), self.battle, self.fighter, '  ')
        self.assertIsInstance(action, InstructionStop)

    def test_history_in_state(self):
        provider = _FakeProvider(keyword='shove')
        action, desc = follow_instruction_step(
            provider, self.battle, self.fighter, 'attack then shove',
            done=['attack g with vicious_rapier'])
        state = provider.calls[0][0]
        self.assertIn('already done for this instruction', state)
        self.assertIn('attack g with vicious_rapier', state)

    def test_end_turn_leaf_only_when_asked(self):
        provider = _FakeProvider(keyword='end the turn')
        action, _ = follow_instruction_step(
            provider, self.battle, self.fighter, 'attack then end my turn')
        self.assertIsInstance(action, InstructionEndTurn)

        provider2 = _FakeProvider(keyword='end the turn')
        action2, _ = follow_instruction_step(
            provider2, self.battle, self.fighter, 'attack the goblin')
        # No end-turn leaf offered; fallback pick is stop.
        self.assertIsInstance(action2, InstructionStop)
        options = provider2.calls[0][1]
        self.assertFalse(any('end the turn' in o for o in options))

    def test_ready_leaf_offered_in_combat(self):
        provider = _FakeProvider(keyword='ready')
        action, desc = follow_instruction_step(
            provider, self.battle, self.fighter,
            'if the goblin runs at me, shoot it')
        self.assertIsInstance(action, InstructionReady)
        self.assertIn('ready', desc)


class TestOutOfBattleSteps(unittest.TestCase):
    def test_move_leaves_without_battle(self):
        session = Session(root_path='tests/fixtures', event_manager=EventManager())
        battle_map = Map(session, 'tests/fixtures/battle_sim.yml')
        session.maps['outbattle'] = battle_map
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        battle_map.add(fighter, 0, 0)
        provider = _FakeProvider(keyword='move')
        action, desc = follow_instruction_step(
            provider, None, fighter, 'walk toward the door')
        from natural20.actions.move_action import MoveAction
        self.assertIsInstance(action, MoveAction)
        self.assertTrue(getattr(action, 'move_path', None))


class TestReadyParsing(unittest.TestCase):
    def setUp(self):
        random.seed(5)
        self.session, self.map, self.battle, self.fighter, self.goblin = _make_battle()

    def test_two_choice_calls(self):
        provider = _SequenceProvider([0, 0])  # movement + first weapon
        res = parse_player_instruction(
            provider, self.battle, self.fighter,
            'if the goblin comes through the door, I attack with my rapier',
            weapons=['vicious_rapier'], enemies=['g'])
        self.assertIsNotNone(res)
        self.assertEqual(len(provider.calls), 2)
        self.assertEqual(res['trigger']['event'], 'movement')
        self.assertEqual(res['action_spec']['kind'], 'attack')
        self.assertEqual(res['action_spec']['weapon'], 'vicious_rapier')
        # The state block quotes the player's own words.
        self.assertIn("if the goblin comes through the door", provider.calls[0][0])

    def test_requires_provider(self):
        self.assertIsNone(parse_player_instruction(
            None, self.battle, self.fighter, 'shoot anything that moves'))
        self.assertIsNone(parse_player_instruction(
            _UnavailableProvider(), self.battle, self.fighter, 'shoot anything'))

    def test_empty_description(self):
        self.assertIsNone(parse_player_instruction(
            _FakeProvider(), self.battle, self.fighter, '   '))


if __name__ == '__main__':
    unittest.main()
