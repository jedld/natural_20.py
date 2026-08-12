"""Proximity touch interactions must work without vision (darkness / no darkvision)."""

import os
import unittest

from natural20.actions.interact_action import InteractAction
from natural20.battle import Battle
from natural20.item_library.chest import Chest
from natural20.item_library.switch import Switch
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.utils.action_builder import autobuild
from natural20.web.json_renderer import JsonRenderer
from natural20.web.object_quick_interactions import quick_interact_actions_for


class TestProximityInteractInDarkness(unittest.TestCase):
    def setUp(self):
        self.session = Session(root_path='tests/fixtures')
        self.map = Map(self.session, 'battle_sim_objects')
        # Force total darkness regardless of campfires / ambient lights.
        self.map.light_at = lambda x, y: 0.0  # type: ignore[method-assign]
        self.map.magical_darkness_at = lambda x, y: False  # type: ignore[method-assign]
        # Human fighter: strip any inherited darkvision for this scenario.
        self.entity = PlayerCharacter.load(self.session, os.path.join('human_fighter.yml'))
        self.entity.properties.pop('darkvision', None)
        self.assertFalse(self.entity.darkvision(5))
        self.battle = Battle(self.session, self.map)
        self.chest = self.map.object_at(1, 6)
        self.assertIsInstance(self.chest, Chest)
        self.chest.open()

    def test_cannot_see_adjacent_chest_in_total_darkness(self):
        self.map.place((1, 5), self.entity, 'G')
        self.assertEqual(self.map.light_at(1, 6), 0.0)
        self.assertFalse(self.map.can_see(self.entity, self.chest))

    def test_objects_near_includes_adjacent_chest_in_darkness(self):
        self.map.place((1, 5), self.entity, 'G')
        self.assertFalse(self.map.can_see(self.entity, self.chest))
        nearby = self.map.objects_near(self.entity, None)
        self.assertIn(self.chest, nearby)

    def test_objects_near_includes_same_tile_chest_in_darkness(self):
        self.map.place((1, 6), self.entity, 'G')
        self.assertFalse(self.map.can_see(self.entity, self.chest))
        nearby = self.map.objects_near(self.entity, None)
        self.assertIn(self.chest, nearby)

    def test_loot_action_available_in_darkness_when_adjacent(self):
        self.map.place((1, 5), self.entity, 'G')
        self.battle.add(self.entity, 'a')
        self.entity.reset_turn(self.battle)
        actions = autobuild(
            self.session, InteractAction, self.entity, self.battle, match=[self.chest, 'loot']
        )
        self.assertTrue(actions, 'Expected loot InteractAction when adjacent in darkness')
        self.assertIsInstance(actions[0], InteractAction)

    def test_quick_interact_loot_when_adjacent_in_darkness(self):
        self.map.place((1, 5), self.entity, 'G')
        actions = quick_interact_actions_for(self.chest, self.entity, None)
        loot = next((a for a in actions if a['action'] == 'loot'), None)
        self.assertIsNotNone(loot)
        self.assertFalse(loot['needs_approach'])

    def test_quick_interact_loot_when_standing_on_chest_in_darkness(self):
        self.map.place((1, 6), self.entity, 'G')
        actions = quick_interact_actions_for(self.chest, self.entity, None)
        loot = next((a for a in actions if a['action'] == 'loot'), None)
        self.assertIsNotNone(loot)
        self.assertFalse(loot['needs_approach'])

    def test_renderer_includes_adjacent_chest_quick_interact_in_darkness(self):
        self.map.place((1, 5), self.entity, 'G')
        renderer = JsonRenderer(self.map, None)
        result = renderer.render(entity_pov=[self.entity])
        tile = None
        for row in result:
            for cell in row:
                if cell.get('x') == 1 and cell.get('y') == 6:
                    tile = cell
                    break
            if tile is not None:
                break
        self.assertIsNotNone(tile)
        objects = tile.get('objects') or []
        chest_info = next((o for o in objects if o.get('name') == self.chest.name), None)
        self.assertIsNotNone(chest_info, 'Adjacent chest must remain in map JSON in darkness')
        quick = chest_info.get('quick_interact') or []
        self.assertIn('loot', [a['action'] for a in quick])

    def test_concealed_switch_still_hidden_in_darkness(self):
        """Touch bypass must not reveal concealed fixtures without Look/perception."""
        switch = self.map.objects_at(1, 1, match=Switch)[0]
        self.map.place((1, 2), self.entity, 'G')
        self.assertTrue(switch.concealed())
        self.assertFalse(self.map.can_see(self.entity, switch))
        self.assertNotIn(switch, self.map.objects_near(self.entity, None))
        self.assertFalse(self.map.can_interact_by_proximity(self.entity, switch))


if __name__ == '__main__':
    unittest.main()
