import unittest
from natural_20.py.map import Terrain, Map

class TestController(unittest.TestCase):
    def test_controller(self):
        terrain = Terrain("dirt", True, 1.0)
        self.assertEqual(terrain.name, "dirt")
        self.assertEqual(terrain.passable, True)
        self.assertEqual(terrain.movement_cost, 1.0)
        self.assertEqual(terrain.symbol, "D")
        self.assertEqual(terrain.symbol(), "D")