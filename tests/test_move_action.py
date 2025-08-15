import unittest
from natural20.actions.move_action import MoveAction
from natural20.session import Session
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.battle import Battle
from natural20.player_character import PlayerCharacter
from natural20.utils.movement import opportunity_attack_list
from natural20.utils.action_builder import autobuild
from natural20.map_renderer import MapRenderer
from natural20.utils.movement import compute_actual_moves
import pdb
import random

class TestMoveAction(unittest.TestCase):
    def make_session(self):
            event_manager = EventManager()
            event_manager.standard_cli()
            event_manager.register_event_listener(['died'], lambda event: print(f"{event['source'].name} died."))
            event_manager.register_event_listener(['unconscious'], lambda event: print(f"{event['source'].name} unconscious."))
            event_manager.register_event_listener(['initiative'], lambda event: print(f"{event['source'].name} rolled a {event['roll']} = ({event['value']}) with dex tie break for initiative."))
            return Session(root_path='tests/fixtures', event_manager=event_manager)

    def setUp(self):
        random.seed(7000)
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
        map = Map(self.session, 'battle_sim_2')
        battle = Battle(self.session, map)
        fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        battle.add(fighter, 'a', position='spawn_point_1', token='G')
        ogre = self.session.npc('ogre')
        battle.add(ogre, 'b', position=[1, 1], token='g')
        battle.start()
        print(MapRenderer(map).render())
        ogre.reset_turn(battle)
        self.assertEqual(len(opportunity_attack_list(self.action.source, [[1, 0], [2, 0], [3, 0]], self.battle, self.map)), 0)

    def test_auto_generate(self):
        ogre = self.session.npc('ogre')
        self.battle.add(ogre, 'b', position=[1, 1], token='g')
        ogre.reset_turn(self.battle)
        move_actions = autobuild(self.session, MoveAction, ogre, self.battle)
        self.assertEqual(len(move_actions), 3)

    def test_opportunity_attack_list_2(self):
        def extract_position(move_path, attack_list):
            positions = [[0, 0]]
            for attack in attack_list:
                positions.append(move_path[attack['path']])
            return positions
        self.action.move_path = [[2, 3], [1, 3], [0, 4], [0, 5], [1, 6], [2, 6], [3, 6]]
        map_renderer = MapRenderer(self.map)
        print(map_renderer.render(self.battle, path=self.tupleize(self.action.move_path), path_char='*'))
        attack_list = opportunity_attack_list(self.action.source, self.action.move_path, self.battle, self.map)
        self.assertEqual(attack_list, [{'path': 6, 'source': self.npc}])
        hit_positions = extract_position(self.action.move_path, attack_list)
        self.assertEqual(hit_positions,[[0, 0], [3, 6]])
        print(map_renderer.render(self.battle, path=self.tupleize(hit_positions), path_char='*'))
        self.action.move_path = [[2, 3], [1, 3], [0, 4], [0, 5], [1, 6], [2, 6], [2, 5],[3, 5]]
        attack_list = opportunity_attack_list(self.action.source, self.action.move_path, self.battle, self.map)
        self.assertEqual(attack_list, [{'path': 7, 'source': self.npc}])
        print(map_renderer.render(self.battle, path=self.tupleize(self.action.move_path), path_char='*'))

    def test_opportunity_attack_triggers(self):
        def opportunity_attack_handler(battle, session, entity, map, event):
            actions = [
                a for a in self.npc.available_actions(session, battle, opportunity_attack=True, auto_target=False)
                if a.action_type == 'attack' and a.npc_action.get('type') == 'melee_attack'
            ]

            if not actions:
                return None

            action = actions[0]
            action.target = event['target']
            action.as_reaction = True
            return action
        self.npc.attach_handler('opportunity_attack', opportunity_attack_handler)
        self.action.move_path = [[2, 3], [1, 3], [0, 4], [0, 5], [1, 6], [2, 6], [3, 6]]
        map_renderer = MapRenderer(self.map)
        print(map_renderer.render(self.battle, path=self.tupleize(self.action.move_path), path_char='*'))
        self.assertEqual(self.fighter.hp(), 67)
        self.battle.action(self.action)
        self.battle.commit(self.action)
        print(map_renderer.render(self.battle))
        self.assertEqual(self.fighter.hp(), 67)

    def tupleize(self, path):
        return [(p[0], p[1]) for p in path]

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

    def test_jumps(self):
        # Use map with pits and water to exercise jump rules
        battle_map = Map(self.session, 'battle_sim_objects')
        battle = Battle(self.session, battle_map)
        fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        # Start at [1,6] to avoid the chest at [1,6] blocking initial movement
        battle.add(fighter, 'a', position=[1, 6], token='G')
        fighter.reset_turn(battle)

        # Moving onto (2,6) requires a jump over a pit; ending on a pit is allowed (triggers handled elsewhere).
        movement = compute_actual_moves(fighter, [[1, 6], [2, 6]], battle_map, battle, 6)
        self.assertEqual(movement.movement, [[1, 6], [2, 6]])

        # With a landing square after the pit, the jump is valid and we include the jump square + landing.
        movement = compute_actual_moves(fighter, [[1, 6], [2, 6], [3, 6]], battle_map, battle, 6)
        self.assertEqual(movement.movement, [[1, 6], [2, 6], [3, 6]])

        # Ending on a pit is allowed; path includes pit as landing.
        movement = compute_actual_moves(fighter, [[1, 6], [2, 6], [3, 6], [4, 6], [5, 6]], battle_map, battle, 6)
        self.assertEqual(movement.movement, [[1, 6], [2, 6], [3, 6], [4, 6], [5, 6]])

        # Longer path shows budget and check/jump markers
        movement = compute_actual_moves(fighter, [[1, 6], [2, 6], [3, 6], [4, 6], [5, 6], [6, 6], [7, 6]], battle_map, battle, 6)
        self.assertEqual(movement.impediment, 'movement_budget')
        self.assertEqual(movement.movement, [[1, 6], [2, 6], [3, 6], [4, 6], [5, 6], [6, 6]])
        self.assertEqual(movement.acrobatics_check_locations, [[3, 6]])
        self.assertEqual(movement.jump_locations, [[2, 6], [5, 6]])
        self.assertEqual(movement.jump_start_locations, [[2, 6], [5, 6]])
        self.assertEqual(movement.land_locations, [[3, 6], [6, 6]])

    def test_manual_jumps(self):
        battle_map = Map(self.session, 'battle_sim_objects')
        battle = Battle(self.session, battle_map)
        fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        battle.add(fighter, 'a', position=[1, 6], token='G')
        fighter.reset_turn(battle)

        # manual_jump indices specify inclusive start/end in the path to treat as a jump
        # [1,2] is too short and should fail with jump_distance_not_enough
        movement = compute_actual_moves(
            fighter,
            [[1, 6], [2, 6], [3, 6], [4, 6]],
            battle_map,
            battle,
            6,
            manual_jump=[1, 2],
        )
        self.assertEqual(movement.impediment, 'jump_distance_not_enough')
        self.assertEqual(movement.movement, [[1, 6], [2, 6]])

        # Valid manual jump from index 1 to 3 should succeed and consume budget accordingly
        movement = compute_actual_moves(
            fighter,
            [[1, 6], [2, 6], [3, 6], [4, 6]],
            battle_map,
            battle,
            6,
            manual_jump=[1, 3],
        )
        self.assertIsNone(movement.impediment)
        self.assertEqual(movement.movement, [[1, 6], [2, 6], [3, 6], [4, 6]])

    def test_handle_acrobatics_during_jumps(self):
        # Start the fighter just before the pit and attempt a long jump over water
        battle_map = Map(self.session, 'battle_sim_objects')
        battle = Battle(self.session, battle_map)
        fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        battle.add(fighter, 'a', position=[1, 6], token='G')
        fighter.reset_turn(battle)
        # Build and commit a move action across pit -> water -> pits
        action_map = MoveAction.build(self.session, fighter)
        path = [[[1, 6], [2, 6], [3, 6], [4, 6], [5, 6], [6, 6], [7, 6]], []]
        while isinstance(action_map, dict):
            params = []
            for p in action_map['param']:
                if p['type'] == 'movement':
                    params.append(path)
            action_map = action_map['next'](*params)
        action = action_map
        battle.action(action)
        battle.commit(action)
        # With the fixed seed, the acrobatics check succeeds and the fighter reaches [6,6]
        self.assertEqual(battle_map.position_of(fighter), [6, 6])

    def test_handles_prone_condition(self):
        battle_map = Map(self.session, 'battle_sim_objects')
        battle = Battle(self.session, battle_map)
        fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        battle.add(fighter, 'a', position=[0, 6], token='G')
        fighter.reset_turn(battle)
        fighter.do_prone()
        movement = compute_actual_moves(fighter, [[0, 6], [1, 6]], battle_map, battle, 6)
        # Cannot end on chest at [1,6], so no movement when prone
        self.assertEqual(movement.movement, [[0, 6]])

    def test_jump_over_enemy_traversal_allowed(self):
        """
        When a step requires a jump (e.g., a pit), the engine should allow
        traversing a square even if it is occupied by an opposing creature.
        Landing square must still be free.
        """
        battle_map = Map(self.session, 'battle_sim_objects')
        battle = Battle(self.session, battle_map)
        fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        goblin = self.session.npc('goblin')

        # Start at [1,6]; the square [2,6] is a pit (jump-required)
        battle.add(fighter, 'a', position=[1, 6], token='G')
        # Place an enemy on the pit square being jumped over
        battle.add(goblin, 'b', position=[2, 6], token='g')
        fighter.reset_turn(battle)
        goblin.reset_turn(battle)

        # Attempt to move across the pit and land on [3,6] which is empty
        movement = compute_actual_moves(
            fighter,
            [[1, 6], [2, 6], [3, 6]],
            battle_map,
            battle,
            6,
        )

        # Should succeed: include the jump square [2,6] despite enemy there, and land on [3,6]
        self.assertIsNone(movement.impediment)
        self.assertEqual(movement.movement, [[1, 6], [2, 6], [3, 6]])
        self.assertIn([2, 6], movement.jump_locations)
        self.assertIn([3, 6], movement.land_locations)

    def test_jump_cannot_land_on_enemy(self):
        """
        Traversal over an enemy during a jump is allowed, but landing on an
        occupied square isn't: the path should be blocked/trimmed.
        """
        battle_map = Map(self.session, 'battle_sim_objects')
        battle = Battle(self.session, battle_map)
        fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        goblin = self.session.npc('goblin')

        # Start at [1,6]; put the goblin on intended landing square [3,6]
        battle.add(fighter, 'a', position=[1, 6], token='G')
        battle.add(goblin, 'b', position=[3, 6], token='g')
        fighter.reset_turn(battle)
        goblin.reset_turn(battle)

        # Try to jump across [2,6] (pit) and land on [3,6] (occupied)
        movement = compute_actual_moves(
            fighter,
            [[1, 6], [2, 6], [3, 6]],
            battle_map,
            battle,
            6,
        )

        # Path should not allow landing on [3,6]
        self.assertEqual(movement.impediment, 'path_blocked')
        # The final placeable location should not be the occupied square
        self.assertNotEqual(movement.movement[-1], [3, 6])

if __name__ == '__main__':
    unittest.main()
