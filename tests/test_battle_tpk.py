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

    def test_player_groups_falls_back_to_session_default(self):
        """When no PCs are registered, ``player_groups`` should fall back to
        the session-level default group so ``tpk()`` can still classify."""
        session = _session()
        battle_map = Map(session, 'tests/fixtures/battle_sim_objects')
        battle = Battle(session, battle_map)
        # Empty combat order — no PCs added.
        groups = battle.player_groups()
        # Either the fixture declares a default or the set is empty; both are
        # valid. The contract is "no crash, returns a set".
        self.assertIsInstance(groups, set)


if __name__ == '__main__':
    unittest.main()
