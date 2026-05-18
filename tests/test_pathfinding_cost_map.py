"""Ensure snapshot-based pathfinding matches PathCompute."""

import unittest

from natural20.ai.path_compute import PathCompute
from natural20.ai.pathfinding_cost_map import (
    build_pathfinding_snapshot,
    compute_path_from_snapshot,
)
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session


class TestPathfindingCostMap(unittest.TestCase):
    def setUp(self):
        self.session = Session(root_path='tests/fixtures')
        self.fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')

    def test_snapshot_matches_path_compute_basic(self):
        battle_map = Map(self.session, 'path_finding_test')
        pc = PathCompute(None, battle_map, self.fighter)
        snapshot = build_pathfinding_snapshot(battle_map, self.fighter, None)

        for src, dst in [((0, 0), (6, 6)), ((1, 3), (7, 4)), ((0, 0), (3, 3))]:
            expected = pc.compute_path(*src, *dst)
            actual = compute_path_from_snapshot(snapshot, *src, *dst)
            self.assertEqual(actual, expected, msg=f'{src} -> {dst}')

    def test_snapshot_matches_difficult_terrain(self):
        battle_map = Map(self.session, 'path_finding_test_2')
        pc = PathCompute(None, battle_map, self.fighter)
        snapshot = build_pathfinding_snapshot(battle_map, self.fighter, None)
        expected = pc.compute_path(2, 2, 3, 5)
        actual = compute_path_from_snapshot(snapshot, 2, 2, 3, 5)
        self.assertEqual(actual, expected)

    def test_snapshot_unreachable(self):
        battle_map = Map(self.session, 'battle_sim_4')
        ogre = self.session.npc('ogre')
        battle_map.add(ogre, 0, 1)
        pc = PathCompute(None, battle_map, ogre)
        snapshot = build_pathfinding_snapshot(battle_map, ogre, None)
        self.assertIsNone(pc.compute_path(0, 1, 0, 4))
        self.assertIsNone(compute_path_from_snapshot(snapshot, 0, 1, 0, 4))

    def test_snapshot_structure(self):
        battle_map = Map(self.session, 'path_finding_test')
        snapshot = build_pathfinding_snapshot(battle_map, self.fighter, None)
        w, h = battle_map.size
        n = w * h
        self.assertEqual(snapshot['version'], 1)
        self.assertEqual(len(snapshot['difficult']), n)
        self.assertEqual(len(snapshot['pass_normal']), n)


if __name__ == '__main__':
    unittest.main()
