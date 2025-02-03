import unittest
from natural20.map import Map, Terrain
from natural20.map_renderer import MapRenderer
from natural20.session import Session
from natural20.player_character import PlayerCharacter
import pdb

class TestMap(unittest.TestCase):
    def test_controller(self):
        session = Session(root_path='tests/fixtures')
        map = Map(session, 'templates/maps/game_map.yml')
        render = MapRenderer(map)
        render.render()

    def test_line_of_sight(self):
        session = Session(root_path='tests/fixtures')
        map = Map(session, 'tests/fixtures/maps/game_map.yml')
        character = PlayerCharacter.load(session, 'characters/halfling_rogue.yml')
        character2 = PlayerCharacter.load(session, 'characters/high_elf_fighter.yml')
        map.place((0,0), character)
        map.place((5,5), character2)

        assert map.can_see_square(character, (1, 1)) == True

        los = map.line_of_sight(0, 0, 2, 2, inclusive=False, log_path=True)
        print(los)
        los = map.line_of_sight(0, 0, 5, 4, inclusive=False, log_path=True)
        print(los)
        render = MapRenderer(map)
        print(render.render(entity=character, line_of_sight=character))
        
        print("\n")

    def test_squares_in_path(self):
        session = Session(root_path='tests/fixtures')
        map = Map(session, 'tests/fixtures/maps/game_map.yml')
        path = map.squares_in_path(0, 0, 5, 5)
        assert path == [(0, 0), (1, 1), (2, 2), (3, 3), (4, 4), (5, 5)], f"Path: {path}"
        
    def test_directional_walls(self):
        session = Session(root_path='tests/fixtures')
        map = Map(session, 'tests/fixtures/maps/game_map.yml')
        assert map.wall(0, 0) == False
        assert map.wall(0, 1) == True
        assert map.wall(1, 0) == True