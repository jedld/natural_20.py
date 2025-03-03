import os
from natural20.actions.interact_action import InteractAction
from natural20.session import Session
from natural20.player_character import PlayerCharacter
import unittest
from natural20.battle import Battle
from natural20.map import Map
from natural20.map_renderer import MapRenderer
from natural20.event_manager import EventManager
from natural20.utils.action_builder import autobuild
import random
import pdb

# typed: false
class TestInteractAction(unittest.TestCase):
    def make_session(self):
        event_manager = EventManager()
        event_manager.standard_cli()
        random.seed(7000)
        return Session(root_path='tests/fixtures', event_manager=event_manager)

    def setUp(self):
        self.session = self.make_session()
        self.entity = PlayerCharacter.load(self.session, os.path.join("high_elf_fighter.yml"))
        self.battle_map = Map(self.session, "battle_sim_objects")
        self.battle = Battle(self.session, self.battle_map)
        self.battle_map.place((1, 5), self.entity, "G")
        self.door = self.battle_map.object_at(1, 4)
        self.chest = self.battle_map.object_at(1, 6)
        self.battle.add(self.entity, group='a')
        self.battle.start()
        self.entity.reset_turn(self.battle)

    def test_ability_checks(self):
        self.battle.add(self.entity, group='a')
        self.battle.start()
        self.entity.reset_turn(self.battle)
        print(MapRenderer(self.battle_map).render())
        action = autobuild(self.session, InteractAction, self.entity, self.battle, match=[self.door, "investigation_check"], verbose=True)[0]

        self.assertIsInstance(action, InteractAction)
        self.assertEqual(action.button_label(), 'Investigation Check')
        self.assertEqual(action.button_prompt(), 'Inspect Door')
        self.assertListEqual(self.door.investigate_details(self.entity), [])

        self.assertEqual(self.door.closed(), True)
        self.battle.action(action)
        self.battle.commit(action)
        self.assertEqual(self.door.closed(), False)
        print(MapRenderer(self.battle_map).render())
        _investigate_list = self.door.investigate_details(self.entity)
  
        self.assertListEqual(_investigate_list, ['(success) The door is not trapped'])

    def test_opening_and_closing_doors(self):
        print(MapRenderer(self.battle_map).render())
        build = InteractAction.build(self.session, self.entity)
        build = build['next'](self.door)
        self.assertEqual(build['param'], [{'type': 'interact', 'target': self.door }])
        self.assertEqual(set(self.door.available_interactions(self.entity).keys()),set(['open','investigation_check']))

        self.assertFalse(self.door.opened())
        build = build['next']('open')
        self.assertIsInstance(build, InteractAction)
        build.resolve(self.session)
        InteractAction.apply(None, build.result[0], session=self.session)
        self.assertTrue(self.door.opened())
        self.assertIn(self.door, self.battle_map.objects_near(self.entity, None))
        print(MapRenderer(self.battle_map).render())
        door_close = self.build_door_close()
        door_close.resolve(self.session)
        InteractAction.apply(None, door_close.result[0], session=self.session)
        self.assertFalse(self.door.opened())
        print(MapRenderer(self.battle_map).render())

    def test_opening_and_closing_chests(self):
        print(MapRenderer(self.battle_map).render())
        build = InteractAction.build(self.session, self.entity)
        build = build['next'](self.chest)
        self.assertEqual(build['param'], [{'type': 'interact', 'target': self.chest }])
        self.assertEqual(set(self.chest.available_interactions(self.entity).keys()),set(['open']))

        self.assertFalse(self.chest.opened())
        build = build['next']('open')
        self.assertIsInstance(build, InteractAction)
        build.resolve(self.session)
        InteractAction.apply(None, build.result[0], session=self.session)
        self.assertTrue(self.chest.opened())
        self.assertIn(self.chest, self.battle_map.objects_near(self.entity, None))
        print(MapRenderer(self.battle_map).render())
        chest_close = self.build_chest_close()
        chest_close.resolve(self.session)
        InteractAction.apply(None, chest_close.result[0], session=self.session)
        self.assertFalse(self.chest.opened())
        print(MapRenderer(self.battle_map).render())

    def test_player_item_transfer(self):
        self.entity2 = PlayerCharacter.load(self.session, os.path.join("dwarf_cleric.yml"))
        self.battle_map.place((0, 6), self.entity2, "G")
        self.assertListEqual([str(s) for s in self.battle_map.objects_near(self.entity, self.battle)], ['Shor Valu', 'front_door', 'chest','Ground'])
        print(MapRenderer(self.battle_map).render())
        self.assertListEqual([str(a) for a in self.entity.available_actions(self.session, self.battle)], ['Hide',
            'Dash',
            'Disengage',
            'Dodge',
            'move to [0, 5]',
            'move to [2, 5]',
            'Prone',
            'SecondWind',
            'Grapple',
            'Shove',
            'UseItem: healing_potion',
            'Interact(Shor Valu,give)',
            'Interact(front_door,investigation_check)',
            'Interact(front_door,open)',
            'Interact(chest,open)',
            'Interact(Ground,pickup_drop)',
            'Look'])


    def test_autobuild(self):
        self.assertTrue(self.door.closed())
        self.assertEqual(set(self.door.available_interactions(self.entity).keys()), set(['open', 'investigation_check']))
        action_list = autobuild(self.session, InteractAction, self.entity, self.battle)
        self.assertEqual([str(item) for item in action_list], ['Interact(front_door,investigation_check)',
            'Interact(front_door,open)',
            'Interact(chest,open)',
            'Interact(Ground,pickup_drop)'])

    def build_door_open(self):
        build = InteractAction.build(self.session, self.entity)
        build = build['next'](self.door)
        build = build['next']('open')
        return build

    def build_door_close(self):
        build = InteractAction.build(self.session, self.entity)
        build = build['next'](self.door)
        build = build['next']('close')
        return build
    
    def build_chest_open(self):
        build = InteractAction.build(self.session, self.entity)
        build = build['next'](self.chest)
        build = build['next']('open')
        return build
    
    def build_chest_close(self):
        build = InteractAction.build(self.session, self.entity)
        build = build['next'](self.chest)
        build = build['next']('close')
        return build

