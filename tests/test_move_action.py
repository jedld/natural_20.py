import unittest
from natural20.actions.move_action import MoveAction
from natural20.session import Session
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.battle import Battle
from natural20.player_character import PlayerCharacter
from natural20.utils.movement import opportunity_attack_list
from natural20.utils.action_builder import autobuild
import pdb

class TestMoveAction(unittest.TestCase):
    def make_session(self):
            event_manager = EventManager()
            event_manager.register_event_listener(['died'], lambda event: print(f"{event['source'].name} died."))
            event_manager.register_event_listener(['unconscious'], lambda event: print(f"{event['source'].name} unconscious."))
            event_manager.register_event_listener(['initiative'], lambda event: print(f"{event['source'].name} rolled a {event['roll']} = ({event['value']}) with dex tie break for initiative."))
            return Session(root_path='tests/fixtures', event_manager=event_manager)

    def setUp(self):
        self.session = self.make_session()
        self.map = Map(self.session, 'battle_sim')
        self.battle = Battle(self.session, self.map)
        self.fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.npc = self.session.npc('goblin')
        self.battle.add(self.fighter, 'a', position='spawn_point_1', token='G')
        self.battle.add(self.npc, 'b', position='spawn_point_2', token='g')
        self.fighter.reset_turn(self.battle)
        self.npc.reset_turn(self.battle)
        cont = MoveAction.build(self.session, self.fighter)
        movement_path = [[[2, 3], [2, 2], [1, 2]], []]
        while isinstance(cont, dict):
            params = []
            for p in cont['param']:
                if p['type'] == 'movement':
                    params.append(movement_path)
            cont = cont['next'](*params)

        self.action = cont

    def test_auto_build(self):
        self.battle.action(self.action)
        self.battle.commit(self.action)
        self.assertEqual(self.map.position_of(self.fighter), [1, 2])

    def test_opportunity_attack_list(self):
        self.action.move_path = [[2, 5], [3, 5]]
        self.assertEqual(opportunity_attack_list(self.action.source, self.action.move_path, self.battle, self.map), [{'source': self.npc, 'path': 1}])

    def test_opportunity_attack_large_creature(self):
        self.map = Map(self.session, 'battle_sim_2')
        self.ogre = self.session.npc('ogre')
        self.battle.add(self.ogre, 'b', position=[1, 1], token='g')
        self.ogre.reset_turn(self.battle)
        self.assertEqual(len(opportunity_attack_list(self.action.source, [[1, 0], [2, 0], [3, 0]], self.battle, self.map)), 0)

    def test_auto_generate(self):
        ogre = self.session.npc('ogre')
        self.battle.add(ogre, 'b', position=[1, 1], token='g')
        ogre.reset_turn(self.battle)
        move_actions = autobuild(self.session, MoveAction, ogre, self.battle)
        self.assertEqual(len(move_actions), 3)
    # def opportunity_attack_handler(self, battle, session, entity, map, event):
    #     action = self.npc.available_actions(session, battle).filter(lambda s: s.action_type == 'attack').filter(lambda s: s.npc_action['type'] == 'melee_attack').first()
    #     action.target = event['target']
    #     action.as_reaction = True
    #     return action

    # def test_opportunity_attack_triggers(self):
    #     Natural20.EventManager.standard_cli()
    #     self.npc.attach_handler('opportunity_attack', self.opportunity_attack_handler)
    #     self.action.move_path = [[2, 5], [3, 5]]
    #     self.assertEqual(self.fighter.hp, 67)
    #     self.battle.action(self.action)
    #     self.battle.commit(self.action)
    #     self.assertEqual(self.fighter.hp, 60)

    # def test_handles_traps(self):
    #     self.map = Natural20.BattleMap(self.session, 'fixtures/traps')
    #     self.battle = Natural20.Battle(self.session, self.map)
    #     self.fighter = Natural20.PlayerCharacter.load(self.session, 'fixtures/high_elf_fighter.yml')
    #     self.npc = self.session.npc('goblin')
    #     self.battle.add(self.fighter, 'a', position='spawn_point_1', token='G')
    #     self.fighter.reset_turn(self.battle)
    #     action = self.battle.action(self.fighter, 'move', move_path=[[0, 3], [1, 3], [2, 3], [3, 3], [4, 3]])
    #     self.battle.commit(action)
    #     self.assertEqual(self.fighter.hp, 63)
    #     self.assertEqual(self.map.position_of(self.fighter), [1, 3])

    # def test_jumps(self):
    #     self.map = Natural20.BattleMap(self.session, 'fixtures/battle_sim_objects')
    #     Natural20.EventManager.standard_cli()
    #     self.battle = Natural20.Battle(self.session, self.map)
    #     self.fighter = Natural20.PlayerCharacter.load(self.session, 'fixtures/high_elf_fighter.yml')
    #     self.battle.add(self.fighter, 'a', position=[0, 6], token='G')
    #     self.fighter.reset_turn(self.battle)
    #     self.assertEqual(Natural20.MapRenderer(self.map).render(), '')
    #     movement = self.fighter.compute_actual_moves([[0, 6], [1, 6], [2, 6]], self.map, self.battle, 6)
    #     self.assertEqual(movement.movement, [[0, 6], [1, 6]])
    #     movement = self.fighter.compute_actual_moves([[0, 6], [1, 6], [2, 6], [3, 6]], self.map, self.battle, 6)
    #     self.assertEqual(movement.movement, [[0, 6], [1, 6], [2, 6], [3, 6]])
    #     movement = self.fighter.compute_actual_moves([[0, 6], [1, 6], [2, 6], [3, 6], [4, 6], [5, 6]], self.map, self.battle, 6)
    #     self.assertEqual(movement.movement, [[0, 6], [1, 6], [2, 6], [3, 6], [4, 6]])
    #     movement = self.fighter.compute_actual_moves([[1, 6], [2, 6], [3, 6], [4, 6], [5, 6], [6, 6], [7, 6]], self.map, self.battle, 6)
    #     self.assertEqual(movement.impediment, 'movement_budget')
    #     self.assertEqual(movement.movement, [[1, 6], [2, 6], [3, 6], [4, 6]])
    #     self.assertEqual(movement.acrobatics_check_locations, [[3, 6]])
    #     self.assertEqual(movement.jump_locations, [[2, 6], [5, 6], [6, 6]])
    #     self.assertEqual(movement.jump_start_locations, [[2, 6], [5, 6]])
    #     self.assertEqual(movement.land_locations, [[3, 6]])

    # def test_manual_jumps(self):
    #     self.map = Natural20.BattleMap(self.session, 'fixtures/battle_sim_objects')
    #     Natural20.EventManager.standard_cli()
    #     self.battle = Natural20.Battle(self.session, self.map)
    #     self.fighter = Natural20.PlayerCharacter.load(self.session, 'fixtures/high_elf_fighter.yml')
    #     self.battle.add(self.fighter, 'a', position=[0, 6], token='G')
    #     self.fighter.reset_turn(self.battle)
    #     self.assertEqual(Natural20.MapRenderer(self.map).render(), '')
    #     movement = self.fighter.compute_actual_moves([[0, 6], [1, 6], [2, 6], [3, 6], [4, 6]], self.map, self.battle, 6, manual_jump=[2, 3])
    #     self.assertIsNone(movement.impediment)
    #     self.assertEqual(movement.movement, [[0, 6], [1, 6], [2, 6], [3, 6], [4, 6]])
    #     self.assertEqual(movement.budget, 2)

    # def test_handle_acrobatics_during_jumps(self):
    #     self.map.move_to(self.fighter, 1, 6, self.battle)
    #     self.assertEqual(Natural20.MapRenderer(self.map).render(), '')
    #     self.assertEqual(self.fighter.available_movement(self.battle), 30)
    #     action = self.battle.action(self.fighter, 'move', move_path=[[1, 6], [2, 6], [3, 6], [4, 6], [5, 6], [6, 6], [7, 6]])
    #     self.battle.commit(action)
    #     self.assertEqual(self.map.position_of(self.fighter), [4, 6])

    # def test_handles_prone_condition(self):
    #     self.fighter.prone()
    #     movement = self.fighter.compute_actual_moves([[0, 6], [1, 6], [2, 6], [3, 6]], self.map, self.battle, 6)
    #     self.assertEqual(movement.movement, [[0, 6], [1, 6]])

if __name__ == '__main__':
    unittest.main()
