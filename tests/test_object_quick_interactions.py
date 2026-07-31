import os
import unittest

from natural20.battle import Battle
from natural20.item_library.chest import Chest
from natural20.item_library.door_object import DoorObject
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.web.object_quick_interactions import quick_interact_actions_for


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
        self.assertEqual([a['action'] for a in actions], ['open', 'lock'])
        open_action = next(a for a in actions if a['action'] == 'open')
        self.assertEqual(open_action['image'], 'interact_open')
        self.assertFalse(open_action['disabled'])
        self.assertFalse(open_action['needs_approach'])

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

    def test_non_door_chest_returns_empty(self):
        switch = self.battle_map.object_at(1, 1)
        self.assertNotIsInstance(switch, (DoorObject, Chest))
        self.assertEqual(quick_interact_actions_for(switch, self.entity, self.battle), [])

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


if __name__ == '__main__':
    unittest.main()
