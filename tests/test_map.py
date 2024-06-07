import unittest
from natural20.map import Map, Terrain
from natural20.map_renderer import MapRenderer
from natural20.utils.utils import Session

class TestController(unittest.TestCase):
    def test_controller(self):
        session = Session(root_path='tests/fixtures')
        map = Map(session, 'templates/maps/game_map.yml')
        render = MapRenderer(map)
        render.render()