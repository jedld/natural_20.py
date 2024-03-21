import unittest
from natural20.map import Map, Terrain
from natural20.map_renderer import MapRenderer

class TestController(unittest.TestCase):
    def test_controller(self):
        map = Map('templates/maps/game_map.yml')
        render = MapRenderer(map)
        assert render.render() == ""
