#!/usr/bin/env python3
"""
Demo script showing the improved push_from method in action.
This demonstrates how entities now move as far as possible before hitting walls.
"""

from natural20.session import Session
from natural20.player_character import PlayerCharacter
from natural20.npc import Npc
from natural20.map import Map

def main():
    # Setup session and map
    session = Session(root_path='tests/fixtures')
    game_map = Map(session, 'tests/fixtures/maps/game_map.yml')
    
    # Create test entities
    pusher = PlayerCharacter.load(session, 'characters/high_elf_fighter.yml')
    target = Npc.load(session, 'npcs/goblin.yml')
    
    print("=== Push From Improvement Demo ===\n")
    
    # Test 1: Push entity that can move partially before hitting wall
    print("Test 1: Partial movement before wall")
    game_map.place((5, 5), pusher)  # pusher far away
    game_map.place((0, 3), target)  # target in clear area
    
    print(f"Target starting position: {game_map.position_of(target)}")
    
    # Push east - should move one square before hitting wall
    result = target.push_from(game_map, -1, 3, distance=15)
    print(f"Push result: {result}")
    print(f"Expected: Should move to (1,3) and stop before wall at (2,3)\n")
    
    # Test 2: Push entity that's immediately blocked
    print("Test 2: Immediate blockage")
    game_map.place((1, 3), target)  # Place at position where next step hits wall
    
    print(f"Target starting position: {game_map.position_of(target)}")
    
    # Try to push east - should return current position
    result = target.push_from(game_map, 0, 3, distance=10)
    print(f"Push result: {result}")
    print(f"Expected: Should return current position (1,3) when cannot move\n")
    
    # Test 3: Push in clear area 
    print("Test 3: Movement in clear area")
    game_map.place((1, 4), target)  # Row 4 has no walls
    
    print(f"Target starting position: {game_map.position_of(target)}")
    
    # Push east in clear area
    result = target.push_from(game_map, 0, 4, distance=10)
    print(f"Push result: {result}")
    print(f"Expected: Should move multiple squares east until hitting boundary\n")
    
    print("=== Demo Complete ===")
    print("The improved push_from method now:")
    print("1. Moves entities step-by-step along the push path")
    print("2. Stops at the first obstacle (wall/entity/boundary)")
    print("3. Returns the furthest valid position reached")
    print("4. Returns current position when no movement is possible")

if __name__ == '__main__':
    main()
