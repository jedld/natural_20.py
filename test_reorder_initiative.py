#!/usr/bin/env python3
"""
Simple test to verify the reorder_initiative functionality
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from natural20.battle import Battle
from natural20.entity import Entity


class MockEntity:
    def __init__(self, name, uid):
        self.name = name
        self.entity_uid = uid
    
    def __str__(self):
        return f"MockEntity({self.name}, {self.entity_uid})"


class MockSession:
    def __init__(self):
        self.event_manager = None


def test_reorder_initiative():
    """Test the reorder_initiative method"""
    print("Testing reorder_initiative functionality...")
    
    # Create mock session and battle
    session = MockSession()
    battle = Battle(session, None)
    
    # Create mock entities
    entities = [
        MockEntity("Fighter", "fighter_1"),
        MockEntity("Rogue", "rogue_1"), 
        MockEntity("Wizard", "wizard_1"),
        MockEntity("Orc", "orc_1")
    ]
    
    # Add entities to battle
    for i, entity in enumerate(entities):
        battle.entities[entity] = {
            'initiative': 20 - i * 5,  # 20, 15, 10, 5
            'group': 'a' if i < 2 else 'b'
        }
        battle.combat_order.append(entity)
    
    print("Initial order:")
    for i, entity in enumerate(battle.combat_order):
        print(f"  {i}: {entity.name} ({entity.entity_uid}) - initiative {battle.entities[entity]['initiative']}")
    
    # Test reordering
    new_order = ["wizard_1", "fighter_1", "orc_1", "rogue_1"]
    print(f"\nReordering to: {new_order}")
    
    try:
        battle.reorder_initiative(new_order)
        print("Reorder successful!")
        
        print("New order:")
        for i, entity in enumerate(battle.combat_order):
            print(f"  {i}: {entity.name} ({entity.entity_uid}) - initiative {battle.entities[entity]['initiative']}")
        
        # Verify the order
        actual_order = [entity.entity_uid for entity in battle.combat_order]
        if actual_order == new_order:
            print("✓ Order matches expected!")
        else:
            print(f"✗ Order mismatch! Expected: {new_order}, Got: {actual_order}")
        
    except Exception as e:
        print(f"✗ Error during reorder: {e}")
    
    # Test with invalid UID
    print("\nTesting with invalid UID...")
    try:
        battle.reorder_initiative(["invalid_uid", "fighter_1", "rogue_1"])
        print("✗ Should have failed with invalid UID")
    except ValueError as e:
        print(f"✓ Correctly rejected invalid UID: {e}")
    
    # Test with wrong number of entities
    print("\nTesting with wrong number of entities...")
    try:
        battle.reorder_initiative(["fighter_1", "rogue_1"])  # Missing entities
        print("✗ Should have failed with wrong count")
    except ValueError as e:
        print(f"✓ Correctly rejected wrong count: {e}")
    
    print("\nTest completed!")


if __name__ == "__main__":
    test_reorder_initiative()
