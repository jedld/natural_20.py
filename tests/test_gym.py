import unittest
from natural20.player_character import PlayerCharacter
from natural20.map_renderer import MapRenderer
from natural20.generic_controller import GenericController
from natural20.controller import Controller
from natural20.session import Session
from natural20.actions.move_action import MoveAction
from gymnasium import make
import random
from natural20.event_manager import EventManager
# trunk-ignore(ruff/F401)
from natural20.gym import dndenv
from natural20.gym.dndenv import GymInternalController
import pdb

class TestGym(unittest.TestCase):
    def test_reset(self):
        env = make("dndenv-v0", render_mode="ansi", root_path='tests/fixtures', debug=True)
        observation, info = env.reset(seed=42)
        # sample a move from info
        while True:
            action = random.choice(info["available_moves"])
            observation, reward, done, truncated, info = env.step(action)
            assert observation is not None
            assert reward is not None
            if done or truncated:
                break
        assert env is not None
        assert info is not None
        self.assertEqual(observation['player_type'], [3])

    def test_character_sampling(self):
        def sample_character():
            character_profiles = ['high_elf_mage', 'halfling_rogue', 'high_elf_fighter' ]
            return random.choice(character_profiles)

        env = make("dndenv-v0", render_mode="ansi", root_path='tests/fixtures', debug=True,
                   profiles=sample_character)
        observation, info = env.reset(seed=42)
        self.assertIsNotNone(observation)
        observation, info = env.reset(seed=43)
        self.assertIsNotNone(observation)
        observation, info = env.reset(seed=44)
        self.assertIsNotNone(observation)

    def test_ability_info(self):
        env = make("dndenv-v0", render_mode="ansi", root_path='tests/fixtures', debug=True)
        observation, info = env.reset(seed=42)
        self.assertEqual(observation['ability_info'][0], 0)
        _, _, main_player, _ = env.players[0]
        main_player.second_wind_count = 0
        observation = env.generate_observation(main_player)
        self.assertEqual(observation['ability_info'][0], 0)

    def test_pc_mage_available_actions(self):
        env = make("dndenv-v0", render_mode="ansi", root_path='tests/fixtures', debug=True, profiles=['high_elf_mage.yml'])

        _, info = env.reset(seed=42)
        print(info['available_moves'])
        self.assertIsNotNone(info['available_moves'])
        self.assertEqual(len(info['available_moves']), 16)

    def test_custom_setup(self):
        def make_session():
            event_manager = EventManager()
            event_manager.standard_cli()
            random.seed(7001)
            return Session(root_path='tests/fixtures', event_manager=event_manager)

        session = make_session()

        def custom_dndenv_initializer(env):
            character = PlayerCharacter.load(session, 'elf_rogue.yml', { "equipped" : ['dagger', 'dagger'] })
            npc = session.npc('ogre')
            # those that are in group a are being controlled by the agent
            env.battle.add(character, 'a', position='spawn_point_1', token='G', controller=GenericController(session))
            env.battle.add(npc, 'b', position='spawn_point_2', token='g', controller=GenericController(session))
            env.map.move_to(character, 0, 0, env.battle)
            env.map.move_to(npc, 1, 0, env.battle)
            map_renderer = MapRenderer(env.map, battle=env.battle)
            print(map_renderer.render(env.battle))

        env = make("dndenv-v0", render_mode="ansi", root_path='tests/fixtures', debug=True, map_file='battle_sim',
                   custom_initializer=custom_dndenv_initializer,
                   session=session)
        observation, info = env.reset(seed=44)
        self.assertIsNotNone(observation)
        self.assertIn((0, (0, 0), (0, 2), 2, 1), info['available_moves'])
        observation, reward, done, truncate, info = env.step((0, (0, 0), (0, 2), 2, 1))
        self.assertEqual(reward, 0)
        self.assertEqual(info['available_moves'], [
            (5, (-1, -1), (0, 0), 0, 0),
            (11, (-1, -1), (0, 0), 0, 0),
            (1, (0, 1), (0, 0), 0, 0),
            (1, (1, 0), (0, 0), 0, 0),
            (1, (1, 1), (0, 0), 0, 0),
            (10, (-1, -1), (0, 0), 0, 0),
            (-1, (0, 0), (0, 0), 0, 0)])
        # check for presence of 2 weapon attack
        actions = [action for action in info['available_moves'] if action[0] == 9]

        self.assertEqual(len(actions), 4)


    def test_reaction_interupt(self):
        class MoveAwayController(Controller):
            def move_for(self, entity, battle):
                # choose available moves at random and return it
                available_actions = self._compute_available_moves(entity, battle)

                opponents = battle.opponents_of(entity)

                for action in available_actions:
                    if isinstance(action, MoveAction):
                        for opponent in opponents:
                            orig_distance = battle.map.distance(entity, opponent)
                            new_distance = battle.map.distance(entity, opponent, entity_1_pos=action.move_path[-1])
                            if new_distance > orig_distance:
                                return action
                return None

        def make_session():
            event_manager = EventManager()
            event_manager.standard_cli()
            random.seed(7000)
            return Session(root_path='tests/fixtures', event_manager=event_manager)

        session = make_session()
        def reaction_callback(observation, reward, done, truncated, info):
            return (0, (0, 0), (1, 0), 2, 0)

        def custom_dndenv_initializer(env):
            character = PlayerCharacter.load(session, 'elf_rogue.yml', { "equipped" : ['dagger', 'dagger'] })
            npc = session.npc('goblin')
            # those that are in group a are being controlled by the agent
            controller = GymInternalController(session, env, reaction_callback=reaction_callback)
            controller.register_handlers_on(character)

            env.battle.add(character, 'a', position='spawn_point_1', token='G', controller=controller)
            env.battle.add(npc, 'b', position='spawn_point_2', token='g', controller=MoveAwayController(session))
            env.map.move_to(character, 0, 0, env.battle)
            env.map.move_to(npc, 1, 0, env.battle)

            return [character, npc]

        env = make("dndenv-v0", render_mode="ansi", root_path='tests/fixtures', debug=True, map_file='battle_sim',
                   custom_initializer=custom_dndenv_initializer,
                   reaction_callback=reaction_callback,
                   session=session)
        observation, info = env.reset(seed=44)
        print(env.render())
        self.assertIsNotNone(observation)
        observation, reward, done, truncate, info = env.step((-1, (0, 0), (0, 0), 0, 0))
        self.assertEqual(reward, 10)


    def test_render(self):
        env = make("dndenv-v0", render_mode="ansi", root_path='tests/fixtures', debug=True)
        observation, info = env.reset(seed=42)
        assert observation is not None
        assert info is not None

        
        # sample a move from info
        render = env.render()
        expected = """____________
____________
____________
____________
____________
____________
_·····P_____
_······_____
_······_____
_··##··_____
_·   ··_____
_   ···_____"""
        assert render==expected, f"render: {render}"

