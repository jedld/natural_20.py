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
        self.battle_map.place((0, 5), self.entity, "G")
        self.door = self.battle_map.object_at(1, 4)

    def test_opening_and_closing_doors(self):
        print(MapRenderer(self.battle_map).render())
        build = InteractAction.build(self.session, self.entity)
        build = build['next'](self.door)
        self.assertEqual(build['param'], [{'type': 'interact', 'target': self.door }])
        self.assertEqual(set(self.door.available_interactions(self.entity).keys()),set(['open', 'lock']))

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

    def test_autobuild(self):
        self.assertTrue(self.door.closed())
        self.assertEqual(set(self.door.available_interactions(self.entity).keys()), set(['open', 'lock']))
        action_list = autobuild(self.session, InteractAction, self.entity, self.battle)
        self.assertEqual([str(item) for item in action_list], ['Interact(front_door,open)', 'Interact(front_door,lock)'])

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

