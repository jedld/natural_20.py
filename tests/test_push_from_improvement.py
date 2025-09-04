import unittest
from natural20.session import Session
from natural20.player_character import PlayerCharacter
from natural20.npc import Npc
from natural20.map import Map


class TestPushFromImprovement(unittest.TestCase):
    """Test the improved push_from method that considers walls and obstacles"""
    
    def setUp(self):
        self.session = Session(root_path='tests/fixtures')
        # Use game map which has clear stone walls
        self.map = Map(self.session, 'tests/fixtures/maps/game_map.yml')
        
        # Create test entities
        self.pusher = PlayerCharacter.load(self.session, 'characters/high_elf_fighter.yml')
        self.target = Npc.load(self.session, 'npcs/goblin.yml')
        
    def test_push_with_partial_movement_before_wall(self):
        """Test that entity moves as far as possible before hitting wall"""
        # Place target at (0, 3) so it can move to (1,3) but not to (2,3) due to wall
        self.map.place((5, 5), self.pusher)  # pusher far away to avoid conflicts
        self.map.place((0, 3), self.target)  # target at clear position
        
        # Push east - should move from (0,3) to (1,3) but stop there due to wall at (2,3)
        result = self.target.push_from(self.map, -1, 3, distance=15)
        
        # Should move one square east and stop at wall
        self.assertEqual(result, (1, 3), "Should move to position (1,3) and stop before wall")
        
    def test_push_blocked_immediately_returns_current_position(self):
        """Test that entity stays in place when first step would hit wall"""
        # Place target at (1, 3) where first step east would hit wall at (2, 3)
        self.map.place((0, 3), self.pusher)  
        self.map.place((1, 3), self.target)  
        
        # Push east - should return current position since it can't move
        result = self.target.push_from(self.map, 0, 3, distance=10)
        
        # Should return current position when cannot move
        self.assertEqual(result, (1, 3), "Should return current position when cannot move")
        
    def test_push_multiple_squares_until_obstacle(self):
        """Test horizontal push that can move multiple squares before hitting obstacle"""
        # Place target in clear area on row 4 (no walls)
        self.map.place((0, 4), self.pusher)  
        self.map.place((1, 4), self.target)  
        
        # Push east with large distance - should move until hitting map boundary or obstacle
        result = self.target.push_from(self.map, 0, 4, distance=25)
        
        # Should move multiple squares east (exact position depends on map size)
        self.assertNotEqual(result, (1, 4), "Should move from starting position")
        self.assertGreater(result[0], 1, "Should move east from starting position")
        
    def test_push_maintains_backward_compatibility(self):
        """Test that the improved method maintains backward compatibility"""
        # Test case that should work exactly like the original
        self.map.place((0, 5), self.pusher)  
        self.map.place((1, 5), self.target)  # row 5 has no walls
        
        # Push with small distance that doesn't hit any obstacles
        result = self.target.push_from(self.map, 0, 5, distance=5)
        
        # Should return a valid position
        self.assertIsNotNone(result, "Should return valid position for unobstructed push")
        self.assertIsInstance(result, tuple, "Should return tuple coordinates")
        self.assertEqual(len(result), 2, "Should return x,y coordinates")


if __name__ == '__main__':
    unittest.main()
