"""Geometry tests for Map.squares_in_radius / squares_in_line / squares_in_emanation."""

import unittest
from natural20.session import Session
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.battle import Battle


class TestMapTargeting(unittest.TestCase):
    def setUp(self):
        em = EventManager()
        self.session = Session(root_path='tests/fixtures', event_manager=em)
        self.map = Map(self.session, 'battle_sim')
        self.feet_per_grid = self.map.feet_per_grid

    # --- squares_in_radius ---------------------------------------------

    def test_radius_zero_returns_only_center(self):
        sq = self.map.squares_in_radius((3, 3), 0)
        self.assertEqual(sq, [(3, 3)])

    def test_radius_one_square(self):
        # 5 ft = 1 square Chebyshev sphere -> 3x3 (with center)
        sq = self.map.squares_in_radius((3, 3), self.feet_per_grid)
        self.assertEqual(len(sq), 9)
        self.assertIn((2, 2), sq)
        self.assertIn((4, 4), sq)
        self.assertIn((3, 3), sq)

    def test_radius_excludes_center(self):
        sq = self.map.squares_in_radius((3, 3), self.feet_per_grid, include_center=False)
        self.assertNotIn((3, 3), sq)
        self.assertEqual(len(sq), 8)

    def test_radius_clipped_to_map(self):
        sq = self.map.squares_in_radius((0, 0), self.feet_per_grid * 5)
        # No negative coords
        self.assertTrue(all(x >= 0 and y >= 0 for (x, y) in sq))

    # --- squares_in_emanation ------------------------------------------

    def test_emanation_requires_entity_on_map(self):
        caster = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        # Not yet placed -> empty
        self.assertEqual(self.map.squares_in_emanation(caster, self.feet_per_grid), [])

    def test_emanation_excludes_origin_by_default(self):
        caster = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        battle = Battle(self.session, self.map)
        battle.add(caster, 'a', position=[3, 5])
        sq = self.map.squares_in_emanation(caster, self.feet_per_grid)
        self.assertNotIn((3, 5), sq)

    def test_emanation_includes_origin_when_requested(self):
        caster = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        battle = Battle(self.session, self.map)
        battle.add(caster, 'a', position=[3, 5])
        sq = self.map.squares_in_emanation(caster, self.feet_per_grid, include_origin=True)
        self.assertIn((3, 5), sq)

    # --- squares_in_line -----------------------------------------------

    def test_line_zero_length_returns_empty_when_same_point(self):
        sq = self.map.squares_in_line((2, 2), (2, 2), self.feet_per_grid)
        self.assertEqual(sq, [])

    def test_line_axial_east(self):
        # 15 ft east, width 5 ft -> 3 cells in a row (single row width)
        sq = self.map.squares_in_line((1, 3), (5, 3), self.feet_per_grid * 3)
        self.assertIn((2, 3), sq)
        self.assertIn((3, 3), sq)
        self.assertIn((4, 3), sq)
        self.assertNotIn((1, 3), sq)  # origin excluded by default

    def test_line_includes_origin_when_requested(self):
        sq = self.map.squares_in_line((1, 3), (5, 3), self.feet_per_grid * 3, include_origin=True)
        self.assertIn((1, 3), sq)


if __name__ == '__main__':
    unittest.main()
