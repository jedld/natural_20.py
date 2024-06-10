import gymnasium as gym
import numpy as np
from typing import Any, Dict, List, Tuple, Union
from natural20.map import Map, Terrain
from natural20.battle import Battle
from natural20.player_character import PlayerCharacter
from natural20.map_renderer import MapRenderer
from natural20.die_roll import DieRoll
from natural20.generic_controller import GenericController
from natural20.utils.utils import Session
from natural20.actions.move_action import MoveAction
from natural20.action import Action
from natural20.gym.types import EnvObject, Environment
from natural20.entity import Entity
from natural20.actions.look_action import LookAction
from natural20.actions.stand_action import StandAction
from natural20.gym.dndenv_controller import DndenvController
from natural20.gym.tools import dndenv_action_to_nat20action, build_observation, compute_available_moves, render_terrain
import random
import os

"""
This is a custom environment for the game Dungeons and Dragons 5e. It is based on the OpenAI Gym environment.
"""
class dndenv(gym.Env):
    TOTAL_ACTIONS = 8
    def __init__(self, view_port_size=(12, 12), max_rounds=200, render_mode = None, **kwargs):
        """
        Initializes the environment with the following parameters:
        - view_port_size: the size of the view port for the agent
        - max_rounds: the maximum number of rounds before the game ends
        - render_mode: the mode to render the game in
        - root_path: the root path for the game
        - map_file: the file to load the map from
        - profiles: the profiles to load for the heroes
        - enemies: the profiles to load for the enemies
        - hero_names: the names of the heroes
        - enemy_names: the names of the enemies
        - show_logs: whether to show logs
        - custom_controller: a custom controller to use
        - custom_agent: a custom agent to use
        - custom_initializer: a custom initializer to use
        """
        super().__init__()

        self.render_mode = render_mode
        self.view_port_size = view_port_size
        self.max_rounds = max_rounds
        self.current_round = 0
        self.time_step = 0
        self.terminal = False
        self.metadata = {
            'render_modes': ['ansi']
        }

        self.observation_space = gym.spaces.Dict(spaces={
            "map": gym.spaces.Box(low=-1, high=255, shape=(view_port_size[0], view_port_size[0], 3), dtype=int),
            "turn_info" : gym.spaces.Box(low=0, high=1, shape=(3,), dtype=int),
            "health_pct": gym.spaces.Box(low=0, high=1, shape=(1,), dtype=float),
            "health_enemy": gym.spaces.Box(low=0, high=1, shape=(1,), dtype=float),
            "movement": gym.spaces.Discrete(255)
        })

        self.action_space = gym.spaces.Tuple([
            gym.spaces.Box(low=-1, high=8, shape=(1,), dtype=int),
            gym.spaces.Box(low=-1, high=1, shape=(2,), dtype=int),
            gym.spaces.Box(low=-view_port_size[0]//2, high=view_port_size[0]//2, shape=(2,), dtype=int),
            gym.spaces.Discrete(2)
        ])
        
        self.reward_range = (-1, 1)
        self.metadata = {}
        self.spec = None
        self._seed = None
        self.root_path = kwargs.get('root_path', 'templates')
        self.map_file = kwargs.get('map_file', 'maps/game_map.yml')
        self.heroes = kwargs.get('profiles', ['high_elf_fighter.yml'])
        self.enemies = kwargs.get('enemies', ['high_elf_fighter.yml'])
        self.hero_names = kwargs.get('hero_names', ['gomerin'])
        self.enemy_names = kwargs.get('enemy_names', ['rumblebelly'])
        self.show_logs = kwargs.get('show_logs', True)
        self.custom_controller = kwargs.get('custom_controller', None)
        self.custom_agent = kwargs.get('custom_agent', None)
        self.custom_initializer = kwargs.get('custom_initializer', None)

    
    def seed(self, seed=None):
        self._seed = seed
        return [seed]
    
    def log(self, msg):
        if self.show_logs:
            print(msg)
    

    
    def _render_terrain_ansi(self):
        result = []
        current_player = self.battle.current_turn()
        pos_x, pos_y = self.map.position_of(current_player)
        view_w, view_h = self.view_port_size
        map_w, map_h = self.map.size
        for y in range(-view_w//2, view_w//2):
            col_arr = []
            for x in range(-view_h//2, view_h//2):
                if pos_x + x < 0 or pos_x + x >= map_w or pos_y + y < 0 or pos_y + y >= map_h:
                    col_arr.append("_")
                else:
                    render_char = None
                    abs_x = pos_x + x
                    abs_y = pos_y + y

                    terrain = self.map.base_map[abs_x][abs_y]
                    entity = self.map.entity_at(abs_x, abs_y)
                    if self.map.can_see_square(current_player, (abs_x, abs_y)):
                        if entity == None:
                            if terrain == None:
                                render_char = "."
                            else:
                                render_char = "#"
                        elif entity == current_player:
                            render_char = "P"
                        elif self.battle.opposing(current_player, entity):
                            render_char = "E"
                        else:
                            render_char = "?"
                    else:
                        render_char = " "

                    col_arr.append(render_char)
            result.append("".join(col_arr))
        return "\n".join(result)

    def render(self):
        if self.render_mode == 'ansi':
            return self._render_terrain_ansi()
        else:
            return None

    def reset(self, **kwargs) -> Dict[str, Any]:
        # set seed, use random seed if not provided
        seed = kwargs.get('seed', None)

        if seed is None:
            seed = random.randint(0, 1000000)

        self.seed = seed # take note of seed for reproducibility
        random.seed(seed)
        map_location = kwargs.get('map_location', os.path.join(self.root_path, self.map_file))
        self.log(f"loading map from {map_location}")
        self.session = Session(self.root_path)
        self.map = Map(self.session, map_location)
        self.battle = Battle(self.session, self.map)
        self.players = []
        self.current_round = 0
        self.terminal = False

        enemy_pos = None
        player_pos = None

        if self.custom_initializer:
            enemy_pos, player_pos = self.custom_initializer(self.map, self.battle)
        else:
            character_sheet_path = 'characters'
            for index, p in enumerate(self.heroes):
                if index < len(self.hero_names):
                    name = self.hero_names[index]

                pc = PlayerCharacter.load(self.session, f'{character_sheet_path}/{p}', { "name" : name})
                self._describe_hero(pc)
                # set random starting positions, make sure there are no obstacles in the map
                while player_pos is None or self.map.placeable(pc, player_pos[0], player_pos[1]) == False:
                    player_pos = [random.randint(0, self.map.size[0] - 1), random.randint(0, self.map.size[1] - 1)]
                self.players.append(('a', 'H', pc, player_pos))

            for index, p in enumerate(self.enemies):
                if index < len(self.enemy_names):
                    name = self.enemy_names[index]

                pc = PlayerCharacter.load(self.session, f'{character_sheet_path}/{p}', {"name":  name})
                self._describe_hero(pc)
                while  enemy_pos is None or enemy_pos==player_pos or self.map.placeable(pc, enemy_pos[0], enemy_pos[1]) == False:
                    enemy_pos = [random.randint(0, self.map.size[0] - 1), random.randint(0, self.map.size[1] - 1)]
                self.players.append(('b', 'E', pc , enemy_pos))

            # add fighter to the battle at position (0, 0) with token 'G' and group 'a'
            for group, token, player, position in self.players:
                if group == 'b':
                    if self.custom_agent:
                        self.log(f"Setting up custom agent for enemy player {self.custom_agent}")
                        controller = DndenvController(self.session, self.custom_agent)
                        controller.register_handlers_on(player)
                    elif self.custom_controller:
                        controller = self.custom_controller
                        controller.register_handlers_on(player)
                    else: # basic AI
                        controller = GenericController(self.session)
                        controller.register_handlers_on(player)

                    self.battle.add(player, group, position=position, token=token, add_to_initiative=True, controller=controller)
                else:
                    self.battle.add(player, group, position=position, token=token, add_to_initiative=True, controller=None)

        self.battle.start()
        self.battle.start_turn()
        if self.battle.current_turn().conscious():
                self.battle.current_turn().reset_turn(self.battle)
        current_player = self.battle.current_turn()

        # get the first player which is not the same group as the current one
        
        enemy_health = self._enemy_health(current_player)

        observation = {
            "map": render_terrain(self.battle, self.map, self.view_port_size),
            "turn_info": np.array([current_player.total_actions(self.battle), current_player.total_bonus_actions(self.battle), current_player.total_reactions(self.battle)]),
            "health_pct": np.array([current_player.hp() / current_player.max_hp()]),
            "health_enemy" : np.array([enemy_health]),
            "movement": self.battle.current_turn().available_movement(self.battle)
        }
        return observation, { "available_moves": compute_available_moves(self.session, self.map, self.battle.current_turn(), self.battle), "current_index" : self.battle.current_turn_index }

    def _enemy_health(self, current_player):
        for player in self.battle.entities.keys():
            if self.battle.entity_group_for(player) != self.battle.entity_group_for(current_player):
                return player.hp() / player.max_hp()
        return 0

    def _describe_hero(self, pc: Entity):
        self.log("==== Player Character ====")
        self.log(f"name: {pc.name}")
        self.log(f"level: {pc.level()}")
        self.log(f"character class: {pc.c_class()}")
        self.log(f"hp: {pc.hp()}")
        self.log(f"max hp: {pc.max_hp()}")
        self.log(f"ac: {pc.armor_class()}")
        self.log(f"speed: {pc.speed()}")
        self.log("\n\n")

    def step(self, action):
        if self.terminal:
            observation, info = self._terminal_observation()
            return observation, 0, True, False, info
        
        if self.current_round >= self.max_rounds:
            return None, 0, True, True, None
        self.time_step += 1
        entity = self.battle.current_turn()

        available_actions = entity.available_actions(self.session, self.battle)
        truncated = False
        end_turn = False
        reward = 0

        # convert from Gym action space to Natural20 action space
        action = dndenv_action_to_nat20action(entity, self.battle, self.map, available_actions, action)
        if action is None:
            reward = -1
        elif action == -1:
            end_turn = True
        else:
            self.battle.action(action)
            self.battle.commit(action)

        # additional check for tpk
        if self.battle.battle_ends():
            if entity.conscious() and self.battle.entity_group_for(entity) == 'a':
                reward = 10
            else:
                reward = -10
            done = True
            self.terminal = True

            observation, info = self._terminal_observation()
            return observation, reward, True, False, info

        available_actions = entity.available_actions(self.session, self.battle)
        done = False

        if len(available_actions) == 0 or end_turn:
            self.battle.end_turn()
            self.log("==== end turn ===")
            result = self.battle.next_turn(max_rounds=self.max_rounds)
            if result == 'tpk' and entity.conscious() and self.battle.entity_group_for(entity) == 'a':
                reward = 10
                done = True
            else:
                self.battle.start_turn()
                current_player = self.battle.current_turn()
                current_player.reset_turn(self.battle)
                self.log(f"==== current turn {current_player.name} {current_player.hp()}/{current_player.max_hp()}===")

                if current_player.dead():
                    self.log(f"{current_player.name} is dead")
                    if self.battle.entity_group_for(entity) == 'a':
                        reward = 10
                    else:
                        reward = -10

                    observation, info = self._terminal_observation()
                    return observation, reward, True, False, info
                
                while True:
                    player_group = self.battle.entity_group_for(current_player)
                    if not player_group == 'a':
                        controller = self.battle.controller_for(current_player)
                        while True:
                            action = controller.move_for(current_player, self.battle)
                            if action is None or action == -1:
                                self.log(f"no move for {current_player.name}")
                                break
                            self.battle.action(action)
                            self.battle.commit(action)

                            if self.battle.battle_ends():
                                break

                        self.battle.end_turn()
                        result = self.battle.next_turn(max_rounds=self.max_rounds)

                        if result == 'tpk':
                            break

                        self.battle.start_turn()
                        current_player = self.battle.current_turn()
                    elif player_group == 'a':
                        if current_player.conscious():
                            current_player.reset_turn(self.battle)
                        break

                self.log(f"Result: {result}")

                if result == 'tpk':
                    # Victory!!!!
                    if entity.conscious() and self.battle.entity_group_for(entity) == 'a':
                        reward = 10
                    else:
                        reward = -10
                    done = True
        
        observation = build_observation(self.battle, self.map, entity, self.view_port_size)
        _available_moves = compute_available_moves(self.session, self.map, self.battle.current_turn(), self.battle)
        if not done:
            # print(f"Available moves: {available_actions}")
            assert len(_available_moves) > 0

        self.current_round += 1
        
        if self.current_round >= self.max_rounds:
            done = True
            truncated = True

        return observation, reward, done, truncated, { "available_moves": _available_moves,
                                                       "current_index" : self.battle.current_turn_index,
                                                       "time_step": self.time_step,
                                                       "round" : self.current_round }      

    
    def _terminal_observation(self):
        observation = {
            "map": render_terrain(self.battle, self.map, self.view_port_size),
            "turn_info": np.array([0, 0, 0]),
            "health_pct": np.array([0]),
            "health_enemy" : np.array([0]),
            "movement": 0
        }
        info = {
            "available_moves": [],
            "current_index" : self.battle.current_turn_index,
            "time_step": self.time_step,
            "round" : self.current_round
        }
        return observation, info

def action_type_to_int(action_type):
    if action_type == "attack":
        return 0
    elif action_type == "move":
        return 1
    elif action_type == "disengage":
        return 2
    elif action_type == "dodge":
        return 3
    elif action_type == "dash":
        return 4
    elif action_type == "dash_bonus":
        return 5
    elif action_type == "stand":
        return 6
    elif action_type == "look":
        return 7
    elif action_type == "second_wind":
        return 8
    else:
        return -1    

gym.register(id='dndenv-v0', entry_point=lambda **kwargs: dndenv(**kwargs))