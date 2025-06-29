import unittest
from natural20.session import Session
from natural20.event_manager import EventManager
from natural20.web.json_renderer import JsonRenderer
from natural20.map import Map


class TestDialogBubble(unittest.TestCase):
    def make_session(self):
        event_manager = EventManager()
        event_manager.standard_cli()
        return Session(root_path='tests/fixtures', event_manager=event_manager)
    
    def setUp(self) -> None:
        self.session = self.make_session()
        self.map = Map(self.session, 'tests/fixtures/battle_sim.yml')
        self.session.register_map('test_map', self.map)
        return super().setUp()

    def test_dialog_property_on_npc(self):
        """Test that NPCs with dialog enabled have the dialog property set correctly"""
        # Create an NPC with dialog enabled
        npc = self.session.npc('goblin', {
            "name": "Test Goblin",
            "overrides": {
                "dialog": True
            }
        })
        
        # Add NPC to map
        self.map.add(npc, 1, 1)
        
        # Create JSON renderer
        renderer = JsonRenderer(self.map)
        
        # Render the map
        tiles = renderer.render()
        
        # Find the tile with our NPC
        npc_tile = None
        for row in tiles:
            for tile in row:
                if isinstance(tile, dict) and tile.get('entity') and tile.get('id') == npc.entity_uid:
                    npc_tile = tile
                    break
            if npc_tile:
                break
        
        # Verify the dialog property is set correctly
        self.assertIsNotNone(npc_tile, "NPC tile should be found")
        self.assertTrue(npc_tile.get('dialog'), "Dialog property should be True for dialog-capable NPC")
        self.assertEqual(npc_tile.get('id'), npc.entity_uid, "Tile should have correct entity ID")

    def test_dialog_property_on_regular_npc(self):
        """Test that regular NPCs without dialog have dialog property set to False"""
        # Create a regular NPC without dialog
        npc = self.session.npc('goblin', {
            "name": "Regular Goblin"
        })
        
        # Add NPC to map
        self.map.add(npc, 1, 1)
        
        # Create JSON renderer
        renderer = JsonRenderer(self.map)
        
        # Render the map
        tiles = renderer.render()
        
        # Find the tile with our NPC
        npc_tile = None
        for row in tiles:
            for tile in row:
                if isinstance(tile, dict) and tile.get('entity') and tile.get('id') == npc.entity_uid:
                    npc_tile = tile
                    break
            if npc_tile:
                break
        
        # Verify the dialog property is set correctly
        self.assertIsNotNone(npc_tile, "NPC tile should be found")
        self.assertFalse(npc_tile.get('dialog'), "Dialog property should be False for regular NPC")

    def test_dialog_property_on_player_character(self):
        """Test that player characters have dialog property set correctly"""
        from natural20.player_character import PlayerCharacter
        
        # Create a player character
        pc = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        
        # Add PC to map
        self.map.add(pc, 1, 1)
        
        # Create JSON renderer
        renderer = JsonRenderer(self.map)
        
        # Render the map
        tiles = renderer.render()
        
        # Find the tile with our PC
        pc_tile = None
        for row in tiles:
            for tile in row:
                if isinstance(tile, dict) and tile.get('entity') and tile.get('id') == pc.entity_uid:
                    pc_tile = tile
                    break
            if pc_tile:
                break
        
        # Verify the dialog property is set correctly
        self.assertIsNotNone(pc_tile, "PC tile should be found")
        # Player characters should have dialog capability by default
        self.assertTrue(pc_tile.get('dialog'), "Dialog property should be True for player characters")


if __name__ == '__main__':
    unittest.main() 