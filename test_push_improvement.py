import unittest
from natural20.session import Session
from natural20.player_character import PlayerCharacter
from natural20.npc import Npc
from natural20.map import Map
from natural20.map_renderer import MapRenderer


class TestPushFromWithWalls(unittest.TestCase):
    def setUp(self):
        self.session = Session(root_path='tests/fixtures')
        # Use game map which has clear stone walls (H)
        self.map = Map(self.session, 'tests/fixtures/maps/game_map.yml')
        
        # Create test entities
        self.pusher = PlayerCharacter.load(self.session, 'characters/high_elf_fighter.yml')
        self.target = Npc.load(self.session, 'npcs/goblin.yml')
        
    def test_push_into_stone_wall(self):
        """Test pushing entity into a stone wall - should stop before the wall"""
        print("\nMap layout:")
        print(MapRenderer(self.map).render())
        
        # Place pusher at (1, 3) and target at (2, 3)
        # There are stone walls at (2, 3) and (3, 3)
        self.map.place((0, 3), self.pusher)
        self.map.place((1, 3), self.target)
        
        print("\nWith entities placed:")
        print(MapRenderer(self.map).render())
        
        # Test what's at different positions
        for x in range(6):
            placeable = self.map.placeable(self.target, x, 3)
            wall = self.map.wall(x, 3)
            print(f"Position ({x}, 3): placeable={placeable}, wall={wall}")
            obj = self.map.object_at(x, 3)
            if obj:
                print(f"  Object: {obj.name}")
                print(f"  Object wall: {obj.wall()}")
                print(f"  Object placeable: {obj.placeable() if hasattr(obj, 'placeable') else 'N/A'}")
                print(f"  Object passable: {obj.passable(None) if hasattr(obj, 'passable') else 'N/A'}")
        
        # Now test pushing east with distance 10
        # Should not be able to place at (2,3) or (3,3) due to stone walls
        # Should return (1,3) as the furthest valid position
        result = self.target.push_from(self.map, 0, 3, distance=10)
        print(f"Push east with distance 10: {result}")
        
        # Test with different distances
        result_5 = self.target.push_from(self.map, 0, 3, distance=5)
        print(f"Push east with distance 5: {result_5}")
        
        result_1 = self.target.push_from(self.map, 0, 3, distance=1)
        print(f"Push east with distance 1: {result_1}")
        
        # The improved implementation should return (1,3) since that's the furthest valid position
        self.assertEqual(result, (1, 3), "Should return furthest valid position before wall")
        self.assertEqual(result_5, (1, 3), "Should return furthest valid position before wall")
        self.assertEqual(result_1, (1, 3), "Should return furthest valid position")
        
    def test_current_behavior(self):
        """Test to understand current behavior of push_from"""
        print("\nThinwall Map layout:")
        thinwall_map = Map(self.session, 'tests/fixtures/maps/thinwall_map.yml')
        print(MapRenderer(thinwall_map).render())
        
        # Place entities on the thinwall map
        thinwall_map.place((1, 3), self.pusher)
        thinwall_map.place((2, 3), self.target)
        
        print("\nWith entities placed:")
        print(MapRenderer(thinwall_map).render())
        
        # Test what's at different positions
        for x in range(6):
            print(f"Position ({x}, 3): placeable={thinwall_map.placeable(self.target, x, 3)}, wall={thinwall_map.wall(x, 3)}")
            obj = thinwall_map.object_at(x, 3)
            if obj:
                print(f"  Object: {obj.name} (wall: {obj.wall()}, placeable: {obj.placeable() if hasattr(obj, 'placeable') else 'N/A'})")
                print(f"  Object passable: {obj.passable(None) if hasattr(obj, 'passable') else 'N/A'}")
        
        # Test pushing east (should hit wall at x=4)
        result = self.target.push_from(thinwall_map, 1, 3, distance=10)
        print(f"Push east with distance 10: {result}")
        
        # Test pushing with smaller distance
        result2 = self.target.push_from(thinwall_map, 1, 3, distance=5)
        print(f"Push east with distance 5: {result2}")
        
        # Test what happens when we try to push further
        result3 = self.target.push_from(thinwall_map, 1, 3, distance=15)
        print(f"Push east with distance 15: {result3}")
        
    def test_wall_collision_horizontal(self):
        """Test horizontal push that hits a wall"""
        # Place target at (1, 3) where there are walls at (2,3) and (3,3)
        self.map.place((0, 3), self.pusher)  # pusher at (0,3)
        self.map.place((1, 3), self.target)  # target at (1,3)
        
        print(f"\nMap with wall collision setup:")
        print(MapRenderer(self.map).render())
        
        # Check what's at the positions around the target
        for check_x in range(5):
            placeable = self.map.placeable(self.target, check_x, 3)
            wall = self.map.wall(check_x, 3)
            print(f"Position ({check_x}, 3): placeable={placeable}, wall={wall}")
        
        # Push east with large distance - should hit wall at (2,3)
        result = self.target.push_from(self.map, 0, 3, distance=15)
        print(f"Push result: {result}")
        
        # Since (2,3) has a wall and is not placeable, target should stay at (1,3)
        self.assertEqual(result, (1, 3), "Should stay at current position when next step hits wall")
        
    def test_wall_collision_with_movement(self):
        """Test push where entity can move some distance before hitting wall"""
        # Place target at (0, 3) so it can move to (1,3) but not to (2,3)
        self.map.place((5, 5), self.pusher)  # pusher far away to avoid placement conflicts
        self.map.place((0, 3), self.target)  # target at (0,3)
        
        print(f"\nMap with movement before wall collision:")
        print(MapRenderer(self.map).render())
        
        # Use a horizontal push from (-1, 3) conceptually, but since that's off-map,
        # let's use the proper diagonal logic
        # Actually, let me use a proper pusher position to the left
        
        # Move pusher to conceptually push from the left
        # For target at (0,3), if pusher is at (-1,3) it would push east
        # But we can't place at (-1,3), so let's trigger the condition differently
        
        # Check the direction calculation for pushing from left to right
        target_pos = self.map.entity_or_object_pos(self.target)
        print(f"Target at: {target_pos}")
        
        # For horizontal push east, I need pusher to be to the left of target
        # But since we can't place at (-1,3), let me use a different approach
        # Let's manually test the algorithm by calling it directly with known parameters
        
        # Simulate push from position (-1, 3) which should push target east
        # This should trigger: pos_y in range(y, y + 1) and pos_x not in range(x, x + 1)
        # where pos_x (-1) < x (0), so ofs_x = +distance
        result = self.target.push_from(self.map, -1, 3, distance=10)
        print(f"Push result from (-1, 3): {result}")
        
        # Should move from (0,3) to (1,3) but stop there due to wall at (2,3)
        self.assertEqual(result, (1, 3), "Should move one square east and stop at wall")
        
    def test_cannot_move_at_all(self):
        """Test case where entity cannot move at all due to immediate wall"""
        # Place target at (1, 3) where first step would hit wall at (2, 3)
        self.map.place((0, 3), self.pusher)  
        self.map.place((1, 3), self.target)  
        
        # Push east - should return current position since it can't move
        result = self.target.push_from(self.map, 0, 3, distance=10)
        print(f"Cannot move result: {result}")
        
        # Should return current position (1, 3) instead of None
        self.assertEqual(result, (1, 3), "Should return current position when cannot move")


if __name__ == '__main__':
    unittest.main()
