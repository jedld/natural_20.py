import unittest
from natural20.map import Map, Terrain
from natural20.map_renderer import MapRenderer
from natural20.session import Session
from natural20.player_character import PlayerCharacter
from natural20.ai.path_compute import PathCompute
import pdb

class TestMap(unittest.TestCase):
    def test_map_loader_tolerates_null_player_and_npc_lists(self):
        session = Session(root_path='tests/fixtures')
        battle_map = Map(session, 'tests/fixtures/maps/null_actor_lists.yml')

        self.assertEqual(len(battle_map.entities), 0)
        self.assertEqual(battle_map.size, [4, 4])

    def test_controller(self):
        session = Session(root_path='tests/fixtures')
        session.render_for_text = False
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
        map = Map(session, 'tests/fixtures/maps/thinwall_map.yml')
        character = PlayerCharacter.load(session, 'characters/halfling_rogue.yml')
        character2 = PlayerCharacter.load(session, 'characters/high_elf_fighter.yml')
        character3 = PlayerCharacter.load(session, 'characters/high_elf_mage.yml')
        map.place((0,4), character)
        map.place((2,4), character2)
        map.place((1,4), character3)
        print(MapRenderer(map).render())
        self.assertEqual(map.can_see_square(character, (2, 4)), False)
        self.assertEqual(map.can_see_square(character, (1, 4)), True)
        self.assertEqual(map.can_see(character3, character2), True)
        self.assertEqual(map.can_see(character2, character3), True)

        self.assertEqual(map.can_see(character, character3), False)
        self.assertEqual(map.can_see(character3, character), False)

    def test_directional_walls_diagonals(self):
        session = Session(root_path='tests/fixtures')
        map = Map(session, 'tests/fixtures/maps/thinwall_map.yml')
        character = PlayerCharacter.load(session, 'characters/halfling_rogue.yml')
        character2 = PlayerCharacter.load(session, 'characters/high_elf_fighter.yml')
        character3 = PlayerCharacter.load(session, 'characters/high_elf_mage.yml')
        character4 = PlayerCharacter.load(session, 'characters/dwarf_cleric.yml')
        print(MapRenderer(map).render())
        map.place((1,3), character)
        map.place((2,4), character2)
        map.place((0,5), character3)
        map.place((1,4), character4)
        print(MapRenderer(map).render())
        self.assertEqual(map.can_see(character3, character2), False)
        self.assertEqual(map.can_see(character2, character3), False)
        self.assertEqual(map.can_see(character, character2), True)
        self.assertEqual(map.can_see(character3, character4), False)
        self.assertEqual(map.can_see(character, character4), True)

    def test_directional_walls_pathing(self):
        session = Session(root_path='tests/fixtures')
        map = Map(session, 'tests/fixtures/maps/thinwall_map.yml')
        character4 = PlayerCharacter.load(session, 'characters/dwarf_cleric.yml')
        map.place((0,5), character4)
        print(MapRenderer(map).render())
        path_compute = PathCompute(session, map, character4)
        computed_path = path_compute.compute_path(0, 5, 1, 4)
        self.assertEqual(computed_path, [(0, 5), (0, 4), (1, 3), (1, 4)])
        render = MapRenderer(map)
        print(render.render(path=computed_path, path_char='+'))
        computed_path = path_compute.compute_path(0, 5, 1, 5)
        self.assertEqual(computed_path, [(0, 5), (1, 6), (2, 5), (1, 5)])
        render = MapRenderer(map)
        print(render.render(path=computed_path, path_char='+'))
        computed_path = path_compute.compute_path(1, 5, 0, 5)
        render = MapRenderer(map)
        print(render.render(path=computed_path, path_char='+'))
        self.assertEqual(computed_path, [(1, 5), (2, 5), (1, 6), (0, 5)])


    def test_directional_doors_pathing(self):
        session = Session(root_path='tests/fixtures')
        map = Map(session, 'tests/fixtures/maps/thinwall_map_doors.yml')
        character4 = PlayerCharacter.load(session, 'characters/dwarf_cleric.yml')
        map.place((0,5), character4)
        door1 = map.object_at(1, 3)
        door1.open()
        door2 = map.object_at(2, 5)
        door3 = map.object_at(3, 3)
        door4 = map.object_at(3, 4)
        self.assertTrue(door1.opened())
        print(MapRenderer(map).render())
        path_compute = PathCompute(session, map, character4)
        computed_path = path_compute.compute_path(0, 5, 1, 4)
        # self.assertEqual(computed_path, [(0, 5), (0, 4), (1, 3), (1, 4)])
        render = MapRenderer(map)
        print(render.render(path=computed_path, path_char='+'))
        door1.close()
        door2.open()
        computed_path = path_compute.compute_path(0, 5, 1, 4)
        # computed_path = path_compute.compute_path(0, 5, 1, 5)
        self.assertEqual(computed_path, [(0, 5), (1, 6), (2, 5), (1, 4)])
        render = MapRenderer(map)
        print(render.render(path=computed_path, path_char='+'))
        computed_path = path_compute.compute_path(0, 5, 4, 2)
        self.assertIsNone(computed_path)
        door3.open()
        computed_path = path_compute.compute_path(0, 5, 4, 2)
        self.assertListEqual(computed_path, [(0, 5), (1, 6), (2, 5), (2, 4), (2, 3), (3, 3), (4, 2)])
        computed_path = path_compute.compute_path(1, 5, 0, 5)
        # render = MapRenderer(map)
        print(render.render(path=computed_path, path_char='+'))
        computed_path = path_compute.compute_path(0, 5, 4, 5)
        print(render.render(path=computed_path, path_char='+'))
        self.assertIsNone(computed_path)
        door4.open()
        computed_path = path_compute.compute_path(0, 5, 4, 5)
        print(render.render(path=computed_path, path_char='+'))
        # self.assertEqual(computed_path, [(0, 5), (1, 6), (2, 5), (3, 4), (4, 5)])
        computed_path = path_compute.compute_path(0, 5, 5, 6)
        print(render.render(path=computed_path, path_char='+'))
        self.assertListEqual(computed_path, [(0, 5),(0, 4),(0, 3),(0, 2),(0, 1),(1, 0),(2, 1),(3, 1),(4, 1),(5, 2),(5, 3),(5, 4),(5, 5),(5, 6)])

    def test_directional_walls_closed(self):
        """
        Tests that a character can NOT travel to any point inside the boxed area"""
        session = Session(root_path='tests/fixtures')
        session.render_for_text = False
        map = Map(session, 'tests/fixtures/maps/thinwall_map_closed.yml')
        character4 = PlayerCharacter.load(session, 'characters/dwarf_cleric.yml')
        map.place((0,4), character4)
        path_compute = PathCompute(None, map, character4)
        print(MapRenderer(map).render())
        seen_squares = []
        traveled_squares = []
        for i in range(1, 5):
            for j in range(2, 6):
                if map.can_see_square(character4, (i, j)):
                    seen_squares.append((i, j))
                if path_compute.compute_path(0, 4, i, j) is not None:
                    traveled_squares.append((i, j))
        self.assertEqual(traveled_squares, [])
        self.assertEqual(seen_squares, [])

        character = PlayerCharacter.load(session, 'characters/halfling_rogue.yml')
        map.place((1,4), character)
        print(MapRenderer(map).render())
        seen_squares = []
        traveled_squares = []
        for i in range(0, 6):
            for j in range(0, 2):
                if map.can_see_square(character, (i, j)):
                    seen_squares.append((i, j))
                if path_compute.compute_path(1, 4, i, j) is not None:
                    traveled_squares.append((i, j))
        print(MapRenderer(map).render(path=traveled_squares, path_char='+'))
        self.assertEqual(traveled_squares, [])

    def test_conal_attacks(self):
        session = Session(root_path='tests/fixtures')
        map = Map(session, 'tests/fixtures/maps/empty_map.yml')
        squares = map.squares_in_cone((3, 3), (3, 5), 3)
        self.assertEqual(squares,[(2, 6), (3, 4), (3, 5), (3, 6), (4, 6)])
        print(MapRenderer(map).render(selected_positions=squares))
        squares = map.squares_in_cone((0, 0), (1, 1), 4)
        print(MapRenderer(map).render(selected_positions=squares))
        self.assertEqual(squares,[(1, 1), (1, 2), (2, 1), (2, 2), (2, 3), (2, 4), (3, 2), (3, 3), (4, 2)])

    def test_multimap_transitions(self):
        session = Session(root_path='tests/fixtures')
        session.render_for_text = False
        map1 = Map(session, 'tests/fixtures/maps/thinwall_map_teleport.yml')
        map2 = Map(session, 'tests/fixtures/maps/thinwall_map.yml')
        map1.add_linked_map("map2", map2)
        character = PlayerCharacter.load(session, 'characters/halfling_rogue.yml')
        map1.place((0,4), character)
        map1.move_to(character, 5, 6, None)
        self.assertEqual(map1.entity_at(0, 4), None)
        self.assertEqual(map2.entity_at(2, 1), character)
        print(MapRenderer(map1).render())
        print(MapRenderer(map2).render())

    def test_map_transitions(self):
        session = Session(root_path='tests/fixtures')
        session.render_for_text = False
        map1 = Map(session, 'tests/fixtures/maps/thinwall_map_teleport.yml')
        character = PlayerCharacter.load(session, 'characters/halfling_rogue.yml')
        map1.place((0,4), character)
        map1.move_to(character, 1, 6, None)
        print(MapRenderer(map1).render())
        self.assertEqual(map1.entity_at(0, 0), character)

    def test_map_difficult_terrain(self):
        session = Session(root_path='tests/fixtures')
        session.render_for_text = False
        map = Map(session, 'tests/fixtures/battle_sim_objects.yml')
        character = PlayerCharacter.load(session, 'characters/halfling_rogue.yml')
        map.place((0,2), character)
        print(MapRenderer(map).render())
        self.assertTrue(map.difficult_terrain(character, 3, 2))
        self.assertFalse(map.difficult_terrain(character, 6, 2))

    def test_complex_map(self):
        session = Session(root_path='tests/fixtures')
        session.render_for_text = False
        map = Map(session, 'tests/fixtures/maps/complex_map.yml')

        character = PlayerCharacter.load(session, 'characters/halfling_rogue.yml')
        map.place((5,11), character)
        # print(MapRenderer(map).render(line_of_sight=character))
        self.assertTrue(map.difficult_terrain(character, 5, 8))
        self.assertTrue(map.opaque(2, 11, origin=(3, 11)))
        self.assertFalse(map.passable(character, 2, 11, origin=(3, 11)))
        self.assertFalse(map.can_see_square(character, (2, 11)))

    def test_can_see_with_none_passive_perception(self):
        """can_see must not crash when passive_perception() returns None."""
        from unittest.mock import patch, MagicMock

        session = Session(root_path='tests/fixtures')
        map = Map(session, 'tests/fixtures/maps/game_map.yml')
        observer = PlayerCharacter.load(session, 'characters/halfling_rogue.yml')
        target = PlayerCharacter.load(session, 'characters/high_elf_fighter.yml')
        map.place((0, 0), observer)
        map.place((1, 1), target)

        # Patch observer.passive_perception to return None
        with patch.object(observer, 'passive_perception', return_value=None):
            # Hidden target — should not raise TypeError
            target.statuses.append('hidden')
            target.hidden_stealth = 15
            result = map.can_see(observer, target)
            self.assertFalse(result)
            target.statuses.remove('hidden')

            # Concealed target — should not raise TypeError
            with patch.object(target, 'concealed', return_value=True), \
                 patch.object(target, 'conceal_perception_dc', return_value=12):
                result = map.can_see(observer, target)
                self.assertFalse(result)

            # Secret target — should not raise TypeError
            with patch.object(target, 'secret', return_value=True), \
                 patch.object(target, 'secret_perception_dc', return_value=10):
                result = map.can_see(observer, target)
                self.assertFalse(result)

            # With active_perception high enough to see a hidden target
            target.statuses.append('hidden')
            target.hidden_stealth = 5
            result = map.can_see(observer, target, active_perception=20)
            self.assertTrue(result)
            target.statuses.remove('hidden')

            # active_perception=None should not raise TypeError
            target.statuses.append('hidden')
            target.hidden_stealth = 15
            result = map.can_see(observer, target, active_perception=None)
            self.assertFalse(result)
            target.statuses.remove('hidden')

    def test_can_see_secret_door(self):
        """Secret doors that pass the perception DC check should be visible."""
        from unittest.mock import patch

        session = Session(root_path='tests/fixtures')
        map = Map(session, 'tests/fixtures/maps/game_map.yml')
        observer = PlayerCharacter.load(session, 'characters/halfling_rogue.yml')

        # Place a secret door (DoorObjectWall is opaque when closed)
        door_props = session.load_object('attic_secret_door')
        door_props['type'] = 'attic_secret_door'
        door_props['secret'] = True
        door_props['secret_perception_dc'] = 15
        from natural20.item_library.door_object import DoorObjectWall
        door = DoorObjectWall(session, map, door_props)
        map.place_object(door, 2, 0)
        map.place((0, 0), observer)

        # Without sufficient perception, secret door should not be visible
        with patch.object(observer, 'passive_perception', return_value=10):
            result = map.can_see(observer, door, active_perception=0)
            self.assertFalse(result)

        # With perception beating the DC, secret door should be visible
        with patch.object(observer, 'passive_perception', return_value=10):
            result = map.can_see(observer, door, active_perception=20)
            self.assertTrue(result)

