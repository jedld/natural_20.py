"""Ensure battle combatants are blocked in pathfinding cost map."""

import unittest
from types import SimpleNamespace

from natural20.ai.path_compute import PathCompute
from natural20.ai.pathfinding_cost_map import (
    build_pathfinding_snapshot,
    compute_path_from_snapshot,
)
from natural20.battle import Battle
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session


class TestPathfindingBattleEntities(unittest.TestCase):
    """Tests for enemy blocking in pathfinding during combat."""

    def setUp(self):
        self.session = Session(root_path='tests/fixtures')
        self.fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')

    def test_snapshot_marks_enemy_as_blocked(self):
        """An opposing combatant's tile should appear in the 'blocked' array."""
        battle_map = Map(self.session, 'path_finding_test')
        goblin = self.session.npc('goblin')
        battle_map.add(goblin, 2, 2)

        # Create a mock battle object (SimpleNamespace allows attribute assignment)
        battle = SimpleNamespace()
        battle.entities = [goblin, self.fighter]

        def opposing_mock(combatant, entity):
            return combatant is goblin

        battle.opposing = opposing_mock
        battle.entity_or_object_pos = lambda e: battle_map.entities.get(e)

        snapshot = build_pathfinding_snapshot(battle_map, self.fighter, battle)
        w, h = battle_map.size
        idx = 2 + 2 * w  # (2, 2)
        self.assertTrue(snapshot['blocked'][idx], "Goblin tile should be blocked")

    def test_pathcompute_avoids_enemy(self):
        """PathCompute with battle should avoid enemy positions."""
        battle_map = Map(self.session, 'path_finding_test')
        goblin = self.session.npc('goblin')
        battle_map.add(goblin, 3, 0)

        # The fighter is at (0, 0), goblin at (3, 0)
        # Path from (0, 0) to (4, 0) should go around goblin
        pc = PathCompute(None, battle_map, self.fighter)
        path = pc.compute_path(0, 0, 4, 0)
        # The path should not include (3, 0)
        self.assertIsNotNone(path, "Path should exist")
        self.assertNotIn((3, 0), path, "Path should not go through goblin")

    def test_snapshot_path_avoids_enemy(self):
        """Snapshot-based A* should avoid enemy positions."""
        battle_map = Map(self.session, 'path_finding_test')
        goblin = self.session.npc('goblin')
        battle_map.add(goblin, 3, 0)

        battle = SimpleNamespace()
        battle.entities = [goblin, self.fighter]

        def opposing_mock(combatant, entity):
            return combatant is goblin

        battle.opposing = opposing_mock
        battle.entity_or_object_pos = lambda e: battle_map.entities.get(e)

        snapshot = build_pathfinding_snapshot(battle_map, self.fighter, battle)
        # Try to path from (0, 0) to (4, 0) with goblin at (3, 0)
        path = compute_path_from_snapshot(snapshot, 0, 0, 4, 0)
        self.assertIsNotNone(path, "Path should exist around goblin")
        if path is not None:
            self.assertNotIn((3, 0), path, "Path should not go through goblin position")

    def test_snapshot_excludes_enemy_from_pass_bits(self):
        """Enemy positions should not appear in pass_normal or pass_squeeze bits."""
        battle_map = Map(self.session, 'path_finding_test')
        goblin = self.session.npc('goblin')
        battle_map.add(goblin, 1, 0)

        battle = SimpleNamespace()
        battle.entities = [goblin, self.fighter]

        def opposing_mock(combatant, entity):
            return combatant is goblin

        battle.opposing = opposing_mock
        battle.entity_or_object_pos = lambda e: battle_map.entities.get(e)

        snapshot = build_pathfinding_snapshot(battle_map, self.fighter, battle)
        w = battle_map.size[0]
        # Tile (1, 0) should be blocked
        idx = 1 + 0 * w
        self.assertTrue(snapshot['blocked'][idx], "Goblin tile (1, 0) should be blocked")


class TestPathfindingBattleEntitiesWithRealBattle(unittest.TestCase):
    """Integration tests using a real Battle object."""

    def setUp(self):
        self.session = Session(root_path='tests/fixtures')
        self.fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')

    def test_battle_snapshot_blocks_opposing_combatant(self):
        """Real battle: opposing combatant tile should be blocked."""
        battle_map = Map(self.session, 'path_finding_test')
        goblin = self.session.npc('goblin')
        battle_map.add(goblin, 2, 2)

        # Create a real battle
        battle = Battle(self.session, battle_map)
        battle.add(self.fighter, 'a')
        battle.add(goblin, 'b')
        battle.start()

        # Verify goblin is opposing to fighter
        self.assertTrue(battle.opposing(goblin, self.fighter))

        snapshot = build_pathfinding_snapshot(battle_map, self.fighter, battle)
        w, h = battle_map.size
        idx = 2 + 2 * w  # (2, 2)
        self.assertTrue(snapshot['blocked'][idx], "Goblin tile should be blocked in battle")

    def test_battle_snapshot_path_avoids_opponent(self):
        """Real battle: path should go around opposing combatant."""
        battle_map = Map(self.session, 'path_finding_test')
        goblin = self.session.npc('goblin')
        battle_map.add(goblin, 3, 0)

        # Create a real battle
        battle = Battle(self.session, battle_map)
        battle.add(self.fighter, 'a')
        battle.add(goblin, 'b')
        battle.start()

        snapshot = build_pathfinding_snapshot(battle_map, self.fighter, battle)
        # Try to path from (0, 0) to (4, 0) with goblin at (3, 0)
        path = compute_path_from_snapshot(snapshot, 0, 0, 4, 0)
        self.assertIsNotNone(path, "Path should exist around goblin")
        if path is not None:
            self.assertNotIn((3, 0), path, "Path should not go through goblin")


class TestPathfindingFriendlyEntities(unittest.TestCase):
    """Tests that friendly entities do NOT block movement."""

    def setUp(self):
        self.session = Session(root_path='tests/fixtures')
        self.fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')

    def test_friendly_not_blocked(self):
        """A friendly combatant's tile should NOT be blocked."""
        battle_map = Map(self.session, 'path_finding_test')
        # Load another fighter as a friendly
        friendly = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        friendly.name = "Friendly Fighter"
        battle_map.add(friendly, 2, 2)

        battle = SimpleNamespace()
        battle.entities = [friendly, self.fighter]

        def opposing_mock(combatant, entity):
            # friendly is NOT opposing
            return False

        battle.opposing = opposing_mock
        battle.entity_or_object_pos = lambda e: battle_map.entities.get(e)

        snapshot = build_pathfinding_snapshot(battle_map, self.fighter, battle)
        w, h = battle_map.size
        idx = 2 + 2 * w  # (2, 2)
        # Friendly tile should NOT be blocked (it's not a wall)
        self.assertFalse(snapshot['blocked'][idx], "Friendly tile should NOT be blocked")


if __name__ == '__main__':
    unittest.main()
