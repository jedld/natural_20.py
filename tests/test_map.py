import unittest
from natural20.map import Map, Terrain
from natural20.map_renderer import MapRenderer

class TestController(unittest.TestCase):
    def test_controller(self):
        map = Map('templates/maps/game_map.yml')
        render = MapRenderer(map)

        assert map.get_terrain(0, 0) == Terrain.WALL
        assert map.get_terrain(4, 4) == Terrain.FLOOR
        assert map.get_terrain(4, 5) == Terrain.PLAYER
        assert map.get_terrain(5, 6) == Terrain.ENEMY