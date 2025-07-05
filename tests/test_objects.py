import unittest
from natural20.actions.use_item_action import UseItemAction
from natural20.actions.move_action import MoveAction
from natural20.session import Session
from natural20.battle import Battle
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.event_manager import EventManager
from natural20.map_renderer import MapRenderer
from natural20.utils.action_builder import autobuild
from natural20.item_library.switch import Switch
from natural20.item_library.door_object import DoorObject
from natural20.actions.look_action import LookAction
from natural20.actions.interact_action import InteractAction
import random
from natural20.ai.path_compute import PathCompute
import pdb

class TestObjects(unittest.TestCase):
    def setUp(self):
        random.seed(7000)
        event_manager = EventManager()
        event_manager.standard_cli()
        self.session = Session(root_path='tests/fixtures', event_manager=event_manager)
        self.map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.map)
        self.entity = PlayerCharacter.load(self.session, "high_elf_fighter.yml")
        self.battle.add(self.entity, 'a', position='spawn_point_1', token='G')
        self.entity.reset_turn(self.battle)
        self.switch = self.map.objects_at(1, 1, match=Switch)[0]
        self.door = self.map.objects_at(1, 4, match=DoorObject)[0]

    def test_concealed_objects(self):
        self.assertIsInstance(self.switch, Switch)
        self.assertEqual(self.switch.state, 'off')
        self.assertEqual(self.switch.concealed(), True)
        print(MapRenderer(self.map).render(self.battle))
        self.assertEqual(self.map.can_see(self.entity, self.switch), False)
        action = autobuild(self.session, LookAction, self.entity, self.battle)[0]
        self.battle.action(action)
        self.battle.commit(action)
        self.assertEqual(self.map.can_see(self.entity, self.switch), True)
        self.assertEqual(self.switch.concealed(), False)
        print(MapRenderer(self.map).render(self.battle))
        available_options = self.switch.available_interactions(self.entity, self.battle)
        self.assertEqual(available_options, {'on': {}})
        turn_on_interaction = autobuild(self.session, InteractAction, self.entity, self.battle, match=[self.switch, 'on'])[0]
        self.assertIsInstance(turn_on_interaction, InteractAction)
        self.assertTrue(self.door.closed())
        self.battle.action(turn_on_interaction)
        self.battle.commit(turn_on_interaction)
        print(MapRenderer(self.map).render(self.battle))
        # the door now opens due to the switch
        self.assertEqual(self.switch.state, 'on')
        self.assertTrue(self.door.opened())

    def test_proximity_trigger(self):
        self.map.move_to(self.entity, 1, 5)
        print(MapRenderer(self.map).render(self.battle))
        action = autobuild(self.session, MoveAction, self.entity, self.battle, match=[[2, 5]])[0]
        self.assertEqual(self.entity.hp(), 67)
        self.battle.action(action)
        self.battle.commit(action)
        print(MapRenderer(self.map).render(self.battle))
        self.assertEqual(self.entity.hp(), 66)

    def test_proximity_spawner(self):
        def count_goblins():
            return sum(1 for entity in self.map.entities.keys() if entity.name == 'Krizzit')
        self.map = Map(self.session, 'battle_sim')
        self.battle = Battle(self.session, self.map)
        self.entity = PlayerCharacter.load(self.session, "high_elf_fighter.yml")
        self.battle.add(self.entity, 'a', position=[1, 6], token='G')
        self.assertIsNotNone(self.map.entity_at(1, 6))
        self.entity.reset_turn(self.battle)
        print(MapRenderer(self.map).render(self.battle))
        path = PathCompute(self.battle, self.map, self.entity).compute_path(1, 6, 4, 6)
        self.assertEqual(path, [(1, 6), (2, 6), (3, 6), (4, 6)])
        action = MoveAction(self.session,self.entity, 'move')
        action.move_path = path
        self.assertEqual(count_goblins(), 1)
        self.battle.execute_action(action)
        print(MapRenderer(self.map).render(self.battle))
        self.assertEqual(count_goblins(), 2)
