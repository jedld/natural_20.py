import os
import unittest

from natural20.battle import Battle
from natural20.item_library.chest import Chest
from natural20.item_library.door_object import DoorObject
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.web.object_quick_interactions import (
    entity_quick_interact_actions_for,
    pov_self_quick_interact_actions_for,
    pov_self_quick_interact_anchor,
    quick_interact_actions_for,
    quick_interact_layout_for,
)


class TestObjectQuickInteractions(unittest.TestCase):
    def setUp(self):
        self.session = Session(root_path='tests/fixtures')
        self.entity = PlayerCharacter.load(self.session, os.path.join('high_elf_fighter.yml'))
        self.battle_map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.battle_map)
        self.battle_map.place((1, 5), self.entity, 'G')
        self.door = self.battle_map.object_at(1, 4)
        self.chest = self.battle_map.object_at(1, 6)
        self.battle.add(self.entity, group='a')
        self.battle.start()
        self.entity.reset_turn(self.battle)

    def test_door_open_when_adjacent(self):
        actions = quick_interact_actions_for(self.door, self.entity, self.battle)
        action_names = [a['action'] for a in actions]
        self.assertIn('open', action_names)
        self.assertIn('lock', action_names)
        open_action = next(a for a in actions if a['action'] == 'open')
        self.assertEqual(open_action['image'], 'interact_open')
        self.assertFalse(open_action['disabled'])
        self.assertFalse(open_action['needs_approach'])

    def test_no_quick_interact_on_pov_entity_tile(self):
        door_x, door_y = self.battle_map.position_of(self.door)
        self.battle_map.move_to(self.entity, door_x, door_y, self.battle)
        actions = quick_interact_actions_for(self.door, self.entity, self.battle)
        self.assertEqual(actions, [])

    def test_door_open_when_far_sets_needs_approach(self):
        self.battle_map.move_to(self.entity, 6, 6, self.battle)
        actions = quick_interact_actions_for(self.door, self.entity, self.battle)
        open_action = next(a for a in actions if a['action'] == 'open')
        self.assertTrue(open_action['needs_approach'])

    def test_chest_open_when_adjacent(self):
        actions = quick_interact_actions_for(self.chest, self.entity, self.battle)
        self.assertEqual([a['action'] for a in actions], ['open', 'lock'])
        open_action = next(a for a in actions if a['action'] == 'open')
        self.assertEqual(open_action['image'], 'open_chest')
        self.assertFalse(open_action['needs_approach'])

    def test_locked_door_shows_unlock(self):
        self.door.locked = True
        self.door.lockable = True
        actions = quick_interact_actions_for(self.door, self.entity, self.battle)
        self.assertEqual(actions[0]['action'], 'unlock')
        self.assertTrue(actions[0]['disabled'])

    def test_open_door_shows_close(self):
        self.door.open()
        actions = quick_interact_actions_for(self.door, self.entity, self.battle)
        self.assertEqual(actions[0]['action'], 'close')

    def test_far_interactable_object_shows_needs_approach_actions(self):
        object_map = Map(self.session, 'maps/object_map')
        object_battle = Battle(self.session, object_map)
        far_entity = PlayerCharacter.load(self.session, os.path.join('high_elf_fighter.yml'))
        object_battle.add(far_entity, 'a', position=[0, 0])
        far_entity.reset_turn(object_battle)
        dumbwaiter = object_map.object_at(2, 4)
        actions = quick_interact_actions_for(dumbwaiter, far_entity, object_battle)
        self.assertGreaterEqual(len(actions), 2)
        self.assertTrue(all(action['needs_approach'] for action in actions))

    def test_dumbwaiter_multi_switch_quick_actions(self):
        object_map = Map(self.session, 'maps/object_map')
        object_battle = Battle(self.session, object_map)
        nearby_entity = PlayerCharacter.load(self.session, os.path.join('high_elf_fighter.yml'))
        object_battle.add(nearby_entity, 'a', position=[2, 3])
        nearby_entity.reset_turn(object_battle)
        dumbwaiter = object_map.object_at(2, 4)
        actions = quick_interact_actions_for(dumbwaiter, nearby_entity, object_battle)
        action_names = {action['action'] for action in actions}
        self.assertEqual(action_names, {'servants_quarters', 'master_bedroom'})
        self.assertTrue(all(action.get('show_label') for action in actions))
        layout = quick_interact_layout_for(actions)
        self.assertEqual(layout['columns'], 2)

    def test_no_pov_returns_empty(self):
        self.assertEqual(quick_interact_actions_for(self.door, None, self.battle), [])

    def test_door_quick_actions_when_pov_not_on_map_returns_empty(self):
        off_map = PlayerCharacter.load(self.session, os.path.join('high_elf_fighter.yml'))
        self.assertEqual(quick_interact_actions_for(self.door, off_map, self.battle), [])

    def test_door_available_interactions_when_entity_not_on_map(self):
        off_map = PlayerCharacter.load(self.session, os.path.join('high_elf_fighter.yml'))
        result = self.door.available_interactions(off_map, self.battle)
        self.assertIsInstance(result, dict)
        self.assertNotIn('open', result)

    def test_door_quick_interact_anchor_opposite_facing(self):
        from natural20.web.object_quick_interactions import door_quick_interact_anchor

        self.door.front_direction = 'left'
        self.assertEqual(door_quick_interact_anchor(self.door), 'right')

    def test_door_quick_interact_anchor_toward_pov(self):
        from natural20.web.object_quick_interactions import door_quick_interact_anchor

        door_x, door_y = self.battle_map.position_of(self.door)
        self.battle_map.move_to(self.entity, door_x, door_y + 2, self.battle)
        self.assertEqual(door_quick_interact_anchor(self.door, self.entity), 'bottom')

    def test_door_quick_interact_anchor_on_blind_side_approach_square(self):
        from natural20.web.object_quick_interactions import door_open_approach_anchors, door_quick_interact_anchor

        self.door.front_direction = 'up'
        door_x, door_y = self.battle_map.position_of(self.door)
        self.battle_map.move_to(self.entity, door_x, door_y + 1, self.battle)
        self.assertIn('bottom', door_open_approach_anchors(self.door))
        self.assertEqual(door_quick_interact_anchor(self.door, self.entity), 'bottom')

    def test_door_quick_interact_anchor_prefers_visible_approach_side(self):
        from natural20.web.object_quick_interactions import door_quick_interact_anchor

        self.door.front_direction = 'left'
        door_x, door_y = self.battle_map.position_of(self.door)
        self.battle_map.move_to(self.entity, door_x, door_y + 3, self.battle)

        def approach_tile_visible(ax, ay):
            return ax == door_x + 1 and ay == door_y

        anchor = door_quick_interact_anchor(
            self.door,
            self.entity,
            approach_tile_visible=approach_tile_visible,
        )
        self.assertEqual(anchor, 'right')

    def test_opened_chest_shows_loot_quick_action(self):
        self.chest.open()
        actions = quick_interact_actions_for(self.chest, self.entity, self.battle)
        self.assertIn('loot', [a['action'] for a in actions])
        loot = next(a for a in actions if a['action'] == 'loot')
        self.assertIn('Loot', loot['label'])
        self.assertEqual(loot['image'], 'interact_loot')
        self.assertFalse(loot['needs_approach'])

    def test_dead_npc_shows_loot_quick_action_when_adjacent(self):
        dead_goblin = next(
            ent for ent in self.battle_map.entities if getattr(ent, 'dead', lambda: False)()
        )
        gx, gy = self.battle_map.position_of(dead_goblin)
        self.battle_map.move_to(self.entity, gx + 1, gy, self.battle)
        actions = entity_quick_interact_actions_for(
            dead_goblin, self.entity, self.battle, map_obj=self.battle_map,
        )
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]['action'], 'loot')
        self.assertIn(dead_goblin.label(), actions[0]['label'])
        self.assertFalse(actions[0]['needs_approach'])

    def test_dead_npc_loot_needs_approach_when_far(self):
        dead_goblin = next(
            ent for ent in self.battle_map.entities if getattr(ent, 'dead', lambda: False)()
        )
        self.battle_map.move_to(self.entity, 6, 6, self.battle)
        actions = entity_quick_interact_actions_for(
            dead_goblin, self.entity, self.battle, map_obj=self.battle_map,
        )
        self.assertEqual(len(actions), 1)
        self.assertTrue(actions[0]['needs_approach'])

    def test_living_npc_has_no_loot_quick_action(self):
        living = next(
            ent for ent in self.battle_map.entities
            if not getattr(ent, 'dead', lambda: False)() and ent is not self.entity
        )
        actions = entity_quick_interact_actions_for(
            living, self.entity, self.battle, map_obj=self.battle_map,
        )
        self.assertEqual(actions, [])

    def test_pov_self_perception_quick_action_for_player(self):
        actions = pov_self_quick_interact_actions_for(
            self.entity, self.battle, map_obj=self.battle_map,
        )
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]['action'], 'perception_check')
        self.assertEqual(actions[0]['kind'], 'pov_perception')
        self.assertEqual(actions[0]['label'], 'action.look')
        self.assertEqual(actions[0]['image'], 'look')
        self.assertFalse(actions[0]['show_label'])

    def test_pov_self_perception_anchor_toward_map_interior(self):
        self.battle_map.move_to(self.entity, 0, 0, self.battle)
        self.assertEqual(
            pov_self_quick_interact_anchor(self.battle_map, self.entity),
            'bottom',
        )
        height = self.battle_map.size[1]
        self.battle_map.move_to(self.entity, 0, height - 1, self.battle)
        self.assertEqual(
            pov_self_quick_interact_anchor(self.battle_map, self.entity),
            'top',
        )

    def test_pov_self_perception_not_offered_without_perception_check(self):
        class _NoPerception:
            entity_uid = 'dummy'

        actions = pov_self_quick_interact_actions_for(
            _NoPerception(), self.battle, map_obj=self.battle_map,
        )
        self.assertEqual(actions, [])

    def test_json_renderer_includes_pov_self_perception_on_pov_tile(self):
        from natural20.web.json_renderer import JsonRenderer

        renderer = JsonRenderer(self.battle_map, self.battle, padding=[0, 0])
        result = renderer.render(entity_pov=[self.entity])
        tile = next(
            cell
            for row in result
            for cell in row
            if cell.get('id') == self.entity.entity_uid
        )
        self.assertIn('pov_self_quick_interact', tile)
        self.assertEqual(tile['pov_self_quick_interact'][0]['action'], 'perception_check')
        self.assertIn('pov_self_quick_interact_anchor', tile)

    def test_map_objects_with_null_inventory_expose_no_usable_items(self):
        self.assertIsNone(self.door.inventory)
        self.assertEqual(self.door.usable_items(), [])
        self.assertEqual(self.door.other_items(), [])
        self.assertEqual(self.door.inventory_items(self.session), [])


if __name__ == '__main__':
    unittest.main()
