import unittest
from natural20.ai.path_compute import PathCompute
from natural20.session import Session
from natural20.player_character import PlayerCharacter
from natural20.map_renderer import MapRenderer
from natural20.map import Map

class TestPathCompute(unittest.TestCase):
    def setUp(self):
        self.session = Session(root_path='tests/fixtures')
        self.map = Map(self.session, 'path_finding_test')
        self.map.size = (8, 7)  # Example size, adjust as necessary
        self.fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.path_compute = PathCompute(self.session, self.map, self.fighter)
        self.map_renderer = MapRenderer(self.map)

    def test_compute_path(self):
        self.assertEqual(
            self.map_renderer.render(),
            "········\n" +
            "····#···\n" +
            "···##···\n" +
            "····#···\n" +
            "········\n" +
            "·######·\n" +
            "········\n"
        )
        expected_path = [(0, 0), (1, 1), (2, 2), (3, 3), (4, 4), (5, 4), (6, 4), (7, 5), (6, 6)]
        self.assertEqual(self.path_compute.compute_path(0, 0, 6, 6), expected_path)
        self.assertEqual(
            self.map_renderer.render(path=self.path_compute.compute_path(0, 0, 6, 6), path_char='+'),
            "········\n" +
            "·+··#···\n" +
            "··+##···\n" +
            "···+#···\n" +
            "····+++·\n" +
            "·######+\n" +
            "······+·\n"
        )

        # 2nd case
        expected_path2 = [(1, 3), (2, 4), (3, 4), (4, 4), (5, 4), (6, 4), (7, 4)]
        self.assertEqual(self.path_compute.compute_path(1, 3, 7, 4), expected_path2)

        print(self.map_renderer.render(path=self.path_compute.compute_path(1, 1, 7, 4), path_char='+'))

    def test_compute_paths_to_multiple_destinations(self):
        """Test the new method that computes paths to multiple destinations in a single pass."""
        print(MapRenderer(self.map).render())
        # Define multiple destinations
        destinations = [(6, 6), (7, 4), (3, 3)]

        # Compute paths to all destinations in a single pass
        paths = self.path_compute.compute_paths_to_multiple_destinations(0, 0, destinations)

        # Verify we got paths for all destinations
        self.assertEqual(len(paths), len(destinations))

        # Verify each path is correct
        expected_path1 = [(0, 0), (1, 1), (2, 2), (3, 3), (4, 4), (5, 4), (6, 4), (7, 5), (6, 6)]
        expected_path2 = [(0, 0), (1, 1), (2, 2), (3, 3), (4, 4), (5, 4), (6, 4), (7, 4)]
        expected_path3 = [(0, 0), (1, 1), (2, 2), (3, 3)]

        self.assertEqual(paths[(6, 6)], expected_path1)
        self.assertEqual(paths[(7, 4)], expected_path2)
        self.assertEqual(paths[(3, 3)], expected_path3)

        print(MapRenderer(self.map).render(path=paths[(6, 6)], path_char='+'))
        print(MapRenderer(self.map).render(path=paths[(7, 4)], path_char='+'))
        print(MapRenderer(self.map).render(path=paths[(3, 3)], path_char='+'))

        # Test with a destination that's unreachable
        destinations_with_unreachable = [(6, 6), (4, 5), (3, 3)]  # (4, 5) is unreachable due to being surrounded by walls
        paths_with_unreachable = self.path_compute.compute_paths_to_multiple_destinations(0, 0, destinations_with_unreachable)

        # Verify we got paths for all destinations, with None for unreachable ones
        self.assertEqual(len(paths_with_unreachable), len(destinations_with_unreachable))
        self.assertIsNone(paths_with_unreachable[(4, 5)])
        self.assertEqual(paths_with_unreachable[(6, 6)], expected_path1)
        self.assertEqual(paths_with_unreachable[(3, 3)], expected_path3)

        # Test with movement cost limit
        paths_with_cost_limit = self.path_compute.compute_paths_to_multiple_destinations(
            0, 0, destinations, available_movement_cost=20
        )

        # Verify paths are trimmed to respect the movement cost limit
        self.assertTrue(len(paths_with_cost_limit[(6, 6)]) < len(paths[(6, 6)]))
        self.assertTrue(len(paths_with_cost_limit[(7, 4)]) < len(paths[(7, 4)]))
        self.assertEqual(paths_with_cost_limit[(3, 3)], paths[(3, 3)])  # This path should be unchanged as it's short

    def test_difficult_terrain(self):
        map = Map(self.session, 'path_finding_test_2')
        map_renderer = MapRenderer(map)
        self.path_compute = PathCompute(self.session, map, self.fighter)
        expected_path = [(2, 2), (1, 3), (1, 4), (2, 5), (3, 5)]
        self.assertEqual(self.path_compute.compute_path(2, 2, 3, 5), expected_path)
        self.assertEqual(
            map_renderer.render(path=self.path_compute.compute_path(2, 2, 3, 5), path_char='+'),
            "········\n" +
            "········\n" +
            "········\n" +
            "·+^^^···\n" +
            "·+^^^···\n" +
            "··++····\n" +
            "········\n"
        )

    def test_no_path(self):
        self.map = Map(self.session, 'battle_sim_4')
        self.npc = self.session.npc('ogre')
        self.map.add(self.npc, 0, 1)
        self.map_renderer = MapRenderer(self.map)
        self.path_compute = PathCompute(self.session, self.map, self.npc)
        self.assertEqual(
            self.map_renderer.render(),
            "#######\n" +
            "O┐····#\n" +
            "└┘····#\n" +
            "#######\n" +
            "······#\n" +
            "······#\n" +
            "#######\n"
        )
        self.assertIsNone(self.path_compute.compute_path(0, 1, 0, 4))

if __name__ == '__main__':
    unittest.main()
