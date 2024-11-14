import unittest
from natural20.map import Map, Terrain
from natural20.web.json_renderer import JsonRenderer
from natural20.map_renderer import MapRenderer
from natural20.session import Session
from natural20.player_character import PlayerCharacter
import pdb

class TestMap(unittest.TestCase):
    def test_controller(self):
        session = Session(root_path='tests/fixtures')
        map = Map(session, 'templates/maps/game_map.yml')
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        map.place((0, 1), fighter, 'G')
        ascii_renderer = MapRenderer(map)
        print(ascii_renderer.render())
        render = JsonRenderer(map)
        print(render.render())
        self.assertEqual(render.render(),"")