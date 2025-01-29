import unittest
from unittest.mock import Mock
from collections import namedtuple
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
        # print(self.map_renderer.render(path=self.path_compute.compute_path(0, 0, 6, 6), path_char='+'))
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

    # def test_large_creatures(self):
    #     self.map.size = (8, 7)  # Update size if necessary
    #     self.npc = Mock()  # Assuming npc is mocked or created
    #     self.map.place = Mock()
    #     self.path_compute = PathCompute(self.session, self.map, self.npc)
    #     self.map_renderer.render().return_value = (
    #         "#######\n" +
    #         "O┐····#\n" +
    #         "└┘····#\n" +
    #         "####··#\n" +
    #         "······#\n" +
    #         "······#\n" +
    #         "·······\n"
    #     )
    #     self.assertEqual(
    #         self.map_renderer.render(),
    #         "#######\n" +
    #         "O┐····#\n" +
    #         "└┘····#\n" +
    #         "####··#\n" +
    #         "······#\n" +
    #         "······#\n" +
    #         "·······\n"
    #     )
    #     self.npc.melee_squares.return_value = [(0, 0), (0, 3), (1, 0), (1, 3), (2, 0), (2, 1), (2, 2), (2, 3)]
    #     self.assertEqual(
    #         sorted(self.npc.melee_squares(self.map, adjacent_only=True)),
    #         [(0, 0), (0, 3), (1, 0), (1, 3), (2, 0), (2, 1), (2, 2), (2, 3)]
    #     )
    #     expected_path = [(0, 1), (1, 1), (2, 1), (3, 2), (4, 3), (3, 4), (2, 4), (1, 4), (0, 4)]
    #     self.assertEqual(self.path_compute.compute_path(0, 1, 0, 4), expected_path)
    #     self.map_renderer.render.return_value = (
    #         "#######\n" +
    #         "O++···#\n" +
    #         "└┘·+··#\n" +
    #         "####+·#\n" +
    #         "++++··#\n" +
    #         "······#\n" +
    #         "·······\n"
    #     )
    #     self.assertEqual(
    #         self.map_renderer.render(path=self.path_compute.compute_path(0, 1, 0, 4), path_char='+'),
    #         "#######\n" +
    #         "O++···#\n" +
    #         "└┘·+··#\n" +
    #         "####+·#\n" +
    #         "++++··#\n" +
    #         "······#\n" +
    #         "·······\n"
    #     )
    #     self.assertEqual(self.path_compute.compute_path(3, 4, 4, 5), [(3, 4), (4, 5)])

    # def test_tight_spaces(self):
    #     self.map.size = (8, 7)  # Update size if necessary
    #     self.npc = Mock()  # Assuming npc is mocked or created
    #     self.map.place = Mock()
    #     self.path_compute = PathCompute(self.session, self.map, self.npc)
    #     self.assertEqual(
    #         self.map_renderer.render(),
    #         "#######\n" +
    #         "O┐····#\n" +
    #         "└┘··#·#\n" +
    #         "#####·#\n" +
    #         "····#·#\n" +
    #         "······#\n" +
    #         "·······\n"
    #     )
    #     expected_path = [(0, 1), (1, 1), (2, 1), (3, 2), (4, 1), (5, 2), (5, 3), (5, 4), (4, 5), (3, 5), (2, 4), (1, 4), (0, 4)]
    #     self.assertEqual(self.path_compute.compute_path(0, 1, 0, 4), expected_path)
    #     self.assertEqual(
    #         self.map_renderer.render(path=self.path_compute.compute_path(0, 1, 0, 4), path_char='+'),
    #         "#######\n" +
    #         "O++·+·#\n" +
    #         "└┘·+#+#\n" +
    #         "#####+#\n" +
    #         "+++·#+#\n" +
    #         "···++·#\n" +
    #         "·······\n"
    #     )
    #     self.assertEqual(self.path_compute.compute_path(3, 4, 4, 5), [(3, 4), (4, 5)])
    #     path_back = [(0, 4), (1, 4), (2, 4), (3, 5), (4, 5), (5, 4), (5, 3), (5, 2), (4, 1), (3, 1), (2, 1), (1, 1), (0, 1)]
    #     self.assertEqual(self.path_compute.compute_path(0, 4, 0, 1), path_back)

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
