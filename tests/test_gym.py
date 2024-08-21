import unittest
from natural20.player_character import PlayerCharacter
from natural20.map_renderer import MapRenderer
from natural20.generic_controller import GenericController
from natural20.session import Session
from gymnasium import make
import random
from natural20.event_manager import EventManager
# trunk-ignore(ruff/F401)
from natural20.gym import dndenv

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
        self.assertEqual(observation['player_type'], [0])

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
        assert observation['ability_info'][0] == 1, observation['ability_info']
        _, _, main_player, _ = env.players[0]
        main_player.second_wind_count = 0
        observation = env.generate_observation(main_player)
        assert observation['ability_info'][0] == 0

    def test_pc_mage_available_actions(self):
        env = make("dndenv-v0", render_mode="ansi", root_path='tests/fixtures', debug=True, profiles=['high_elf_mage.yml'])

        _, info = env.reset(seed=42)
        print(info['available_moves'])
        self.assertIsNotNone(info['available_moves'])
        self.assertEqual(len(info['available_moves']), 14)

    def test_custom_setup(self):
        def make_session():
            event_manager = EventManager()
            event_manager.standard_cli()
            random.seed(7000)
            return Session(root_path='tests/fixtures', event_manager=event_manager)

        session = make_session()

        def custom_dndenv_initializer(map, battle):
            character = PlayerCharacter.load(session, 'elf_rogue.yml', { "equipped" : ['dagger', 'dagger'] })
            npc = session.npc('goblin')
            # those that are in group a are being controlled by the agent
            battle.add(character, 'a', position='spawn_point_1', token='G', controller=GenericController(session))

            battle.add(npc, 'b', position='spawn_point_2', token='g', controller=GenericController(session))
            map.move_to(character, 0, 0, battle)
            map.move_to(npc, 1, 0, battle)
            map_renderer = MapRenderer(map, battle=battle)
            print(map_renderer.render(battle))

        env = make("dndenv-v0", render_mode="ansi", root_path='tests/fixtures', debug=True, map_file='battle_sim',
                   custom_initializer=custom_dndenv_initializer,
                   session=session)
        observation, info = env.reset(seed=44)
        self.assertIsNotNone(observation)
        observation, reward, done, truncate, info = env.step((0, (0, 0), (1, 0), 2, 0))
        self.assertEqual(reward, 10)
        self.assertEqual(info['available_moves'], [])

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
_.....P_____
_......_____
_......_____
_..##.._____
_.   .._____
_   ..._____"""
        assert render==expected, f"render: {render}"

