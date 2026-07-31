"""Tests for ``Battle.tpk()`` and the ``player_groups()`` helper."""
import random
import unittest

from natural20.battle import Battle
from natural20.die_roll import DieRoll
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session


def _session():
    em = EventManager()
    return Session(root_path='tests/fixtures', event_manager=em)


def _session_with_groups():
    session = _session()
    session.game_properties['groups'] = {
        'a': {'default': True, 'enemies': ['b', 'c']},
        'b': {'enemies': ['a', 'c']},
        'c': {'enemies': ['b']},
    }
    return session


class TestBattleTPK(unittest.TestCase):
    def test_pcs_alive_is_not_tpk(self):
        session = _session()
        battle_map = Map(session, 'tests/fixtures/battle_sim_objects')
        battle = Battle(session, battle_map)
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        goblin = session.npc('goblin', {"name": 'g1'})
        battle.add(fighter, 'a')
        battle.add(goblin, 'b')

        random.seed(7)
        battle.start(combat_order=[fighter, goblin])

        # Combat ongoing — neither helper should declare a winner.
        self.assertFalse(battle.battle_ends())
        self.assertFalse(battle.tpk())

        # Drop the goblin; PCs win, not a TPK.
        goblin.take_damage(DieRoll([20], 80).result(), session=session)
        self.assertTrue(battle.battle_ends())
        self.assertFalse(battle.tpk())
        self.assertIn('a', battle.winning_groups())

    def test_pcs_wiped_is_tpk(self):
        session = _session()
        battle_map = Map(session, 'tests/fixtures/battle_sim_objects')
        battle = Battle(session, battle_map)
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        goblin = session.npc('goblin', {"name": 'g1'})
        battle.add(fighter, 'a')
        battle.add(goblin, 'b')

        random.seed(7)
        battle.start(combat_order=[fighter, goblin])

        # KO the only PC outright.
        fighter.take_damage(DieRoll([20], 999).result(), session=session)
        self.assertTrue(fighter.dead() or fighter.unconscious())
        self.assertTrue(battle.battle_ends())
        self.assertTrue(battle.tpk())
        self.assertIn('a', battle.player_groups())
        self.assertNotIn('a', battle.winning_groups())

    def test_player_groups_empty_without_pcs(self):
        session = _session_with_groups()
        battle_map = Map(session, 'tests/fixtures/battle_sim_objects')
        battle = Battle(session, battle_map)
        groups = battle.player_groups()
        self.assertEqual(groups, set())
        self.assertFalse(battle.has_player_combatants())

    def test_npc_only_battle_ends_by_group_decimation_not_tpk(self):
        session = _session_with_groups()
        battle_map = Map(session, 'tests/fixtures/battle_sim_objects')
        battle = Battle(session, battle_map)
        goblin_a = session.npc('goblin', {"name": 'g1'})
        goblin_b = session.npc('goblin', {"name": 'g2'})
        battle.add(goblin_a, 'b')
        battle.add(goblin_b, 'c')

        random.seed(7)
        battle.start(combat_order=[goblin_a, goblin_b])

        self.assertFalse(battle.has_player_combatants())
        self.assertFalse(battle.battle_ends())
        self.assertFalse(battle.tpk())

        goblin_b.take_damage(DieRoll([20], 80).result(), session=session)
        self.assertTrue(battle.battle_ends())
        self.assertIn('b', battle.winning_groups())
        self.assertNotIn('c', battle.winning_groups())
        self.assertFalse(battle.tpk())


if __name__ == '__main__':
    unittest.main()
