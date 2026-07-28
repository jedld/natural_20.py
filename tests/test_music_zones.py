import unittest

from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.session import Session


class TestMusicZones(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session = Session(root_path='tests/fixtures', event_manager=EventManager())

    def test_soundtrack_for_position_uses_highest_priority_zone(self):
        battle_map = Map(self.session, 'battle_sim')
        battle_map.properties['default_soundtrack'] = 'background'
        battle_map.properties['music_zones'] = [
            {
                'id': 'outer',
                'soundtrack': 'background',
                'priority': 0,
                'bounds': {'x1': 0, 'y1': 0, 'x2': 5, 'y2': 6},
            },
            {
                'id': 'inner',
                'soundtrack': 'tavern_interior',
                'priority': 10,
                'bounds': {'x1': 1, 'y1': 1, 'x2': 3, 'y2': 3},
            },
        ]

        self.assertEqual(battle_map.soundtrack_for_position(2, 2), 'tavern_interior')
        self.assertEqual(battle_map.soundtrack_for_position(5, 5), 'background')

    def test_soundtrack_for_position_falls_back_to_map_default(self):
        battle_map = Map(self.session, 'battle_sim')
        battle_map.properties['default_soundtrack'] = 'forest_ambient'
        battle_map.properties['music_zones'] = []

        self.assertEqual(battle_map.soundtrack_for_position(0, 0), 'forest_ambient')
        self.assertIsNone(Map(self.session, 'battle_sim').soundtrack_for_position(0, 0))


if __name__ == '__main__':
    unittest.main()
