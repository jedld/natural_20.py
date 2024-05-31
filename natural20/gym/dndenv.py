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
        self.enemies = kwargs.get('enemies', ['halfling_rogue.yml'])

    def _render_terrain(self):
        result = []
        current_player = self.battle.current_turn()
        pos_x, pos_y = self.map.position_of(current_player)
        view_w, view_h = self.view_port_size
        map_w, map_h = self.map.size
        for y in range(-view_w//2, view_w//2):
            col_arr = []
            for x in range(-view_h//2, view_h//2):
                if pos_x + x < 0 or pos_x + x >= map_w or pos_y + y < 0 or pos_y + y >= map_h:
                    col_arr.append([-1, -1, 0])
                else:
                    terrain = self.map.base_map[pos_x + x][pos_y + y]

                    if terrain == None:
                        terrain_int = 0
                    else:
                        terrain_int = 1

                    entity = self.map.entity_at(pos_x + x, pos_y + y)

                    if entity == None:
                        entity_int = 0
                    elif entity == current_player:
                        entity_int = 1
                    elif self.battle.opposing(current_player, entity):
                        entity_int = 2
                    else:
                        entity_int = 3

                    if entity is not None:
                        health_pct = int((entity.hp() / (entity.max_hp() + 0.00001)) * 255)
                    else:
                        health_pct = 0

                    col_arr.append([entity_int, terrain_int, health_pct])
            
            result.append(col_arr)
        return np.array(result)
    
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
                    col_arr.append("#")
                else:
                    render_char = None
                    
                    terrain = self.map.base_map[pos_x + x][pos_y + y]

                    entity = self.map.entity_at(pos_x + x, pos_y + y)

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
        print("loading map from ", map_location)
        self.session = Session(self.root_path)
        self.map = Map(map_location)
        self.battle = Battle(self.session, self.map)
        self.players = []
        self.current_round = 0
        self.terminal = False

        enemy_pos = None
        # set random starting positions
        player_pos = [random.randint(0, self.map.size[0] - 1), random.randint(0, self.map.size[1] - 1)]

        while  enemy_pos is None or enemy_pos==player_pos:
            enemy_pos = [random.randint(0, self.map.size[0] - 1), random.randint(0, self.map.size[1] - 1)]

        character_sheet_path = os.path.join(self.root_path, 'characters')
        for p in self.heroes:
            pc = PlayerCharacter(self.session, f'{character_sheet_path}/{p}')
            self._describe_hero(pc)
            self.players.append(('a', 'H', pc, player_pos))

        for p in self.enemies:
            pc = PlayerCharacter(self.session, f'{character_sheet_path}/{p}')
            self._describe_hero(pc)
            self.players.append(('b', 'E', pc , enemy_pos))

        # add fighter to the battle at position (0, 0) with token 'G' and group 'a'
        for group, token, player, position in self.players:
            if group == 'b':
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
        observation = {
            "map": self._render_terrain(),
            "turn_info": np.array([current_player.total_actions(self.battle), current_player.total_bonus_actions(self.battle), current_player.total_reactions(self.battle)]),
            "health_pct": np.array([current_player.hp() / current_player.max_hp()]),
            "movement": self.battle.current_turn().available_movement(self.battle)
        }
        return observation, { "available_moves": self._compute_available_moves(self.battle.current_turn(), self.battle), "current_index" : self.battle.current_turn_index }

    def _describe_hero(self, pc: Entity):
        print("==== Player Character ====")
        print("name: ", pc.name)
        print("level: ", pc.level())
        print("character class: ", pc.c_class())
        print("hp: ", pc.hp())
        print("max hp: ", pc.max_hp())
        print("ac: ", pc.armor_class())
        print("speed: ", pc.speed())
        print("\n\n")


        

    def step(self, action):
        if self.terminal:
            observation, info = self._terminal_observation()
            return observation, 0, True, False, info
        
        if self.current_round >= self.max_rounds:
            return None, 0, True, True, None
        self.time_step += 1
        entity = self.battle.current_turn()
        action_type, param1, param2, param3 = action
        available_actions = entity.available_actions(self.session, self.battle)
        truncated = False
        end_turn = False
        reward = 0

        for action in available_actions:
            if action.action_type == "attack" and action_type == 0:
                # convert from relative position to absolute map position
                entity_position = self.map.position_of(entity)
                target_x = entity_position[0] + param2[0]
                target_y = entity_position[1] + param2[1]
                target = self.map.entity_at(target_x, target_y)

                valid_targets = self.battle.valid_targets_for(entity, action)
                if param3==0 or (param3 == 1 and action.ranged_attack()):
                    if valid_targets:
                        action.target = valid_targets[0]
                        for valid_target in valid_targets:
                            if target == valid_target:
                                action.target = target
                                break
                        self.battle.action(action)
                        self.battle.commit(action)
                        break
            elif action.action_type == "move" and action_type == 1:
                entity_position = self.map.position_of(entity)
                target_x = entity_position[0] + param1[0]
                target_y = entity_position[1] + param1[1]
                if action.move_path[-1] == [target_x, target_y]:
                    self.battle.action(action)
                    self.battle.commit(action)
                    break
            elif action.action_type == "disengage" and action_type == 2:
                self.battle.action(action)
                self.battle.commit(action)
                break
            elif action.action_type == "dodge" and action_type == 3:
                self.battle.action(action)
                self.battle.commit(action)
                break
            elif action.action_type == "dash" and action_type == 4:
                self.battle.action(action)
                self.battle.commit(action)
                break
            elif action.action_type == "dash_bonus" and action_type == 5:
                self.battle.action(action)
                self.battle.commit(action)
                break
            elif action.action_type == "stand" and action_type == 6:
                self.battle.action(action)
                self.battle.commit(action)
                break
            elif action.action_type == "look" and action_type == 7:
                self.battle.action(action)
                self.battle.commit(action)
                break
            elif action.action_type == "second_wind" and action_type == 8:
                self.battle.action(action)
                self.battle.commit(action)
                break
            elif action_type == -1:
                end_turn = True
                break
            else:
                reward = -1

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
            print("==== end turn ===")
            result = self.battle.next_turn(max_rounds=self.max_rounds)
            if result == 'tpk' and entity.conscious() and self.battle.entity_group_for(entity) == 'a':
                reward = 10
                done = True
            else:
                self.battle.start_turn()
                current_player = self.battle.current_turn()
                current_player.reset_turn(self.battle)
                print(f"==== current turn {current_player.name} {current_player.hp()}/{current_player.max_hp()}===")

                if current_player.dead():
                    print(f"{current_player.name} is dead")
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
                            if action is None:
                                print(f"no move for {current_player.name}")
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

                print(f"Result: {result}")

                if result == 'tpk':
                    # Victory!!!!
                    if entity.conscious() and self.battle.entity_group_for(entity) == 'a':
                        reward = 10
                    else:
                        reward = -10
                    done = True

        observation = {
            "map": self._render_terrain(),
            "turn_info": np.array([entity.total_actions(self.battle), entity.total_bonus_actions(self.battle), entity.total_reactions(self.battle)]),
            "health_pct": np.array([entity.hp() / entity.max_hp()]),
            "movement": self.battle.current_turn().available_movement(self.battle)
        }
        _available_moves = self._compute_available_moves(self.battle.current_turn(), self.battle)
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
            "map": self._render_terrain(),
            "turn_info": np.array([0, 0, 0]),
            "health_pct": np.array([0]),
            "movement": 0
        }
        info = {
            "available_moves": [],
            "current_index" : self.battle.current_turn_index,
            "time_step": self.time_step,
            "round" : self.current_round
        }
        return observation, info
    
    def _compute_available_moves(self, entity: Entity, battle):
        available_actions = entity.available_actions(self.session, battle)

        # generate available targets
        valid_actions = []       

        # try to stand if prone
        if entity.prone() and StandAction.can(entity, battle):
            valid_actions.append((6, (0, 0), (0, 0), 0))
        
        entity_pos = self.map.position_of(entity)

        for action in available_actions:
            if action.action_type == "attack":
                valid_targets = battle.valid_targets_for(entity, action)
                if valid_targets:
                    action.target = valid_targets[0]
                    targets = self.map.entity_squares(valid_targets[0])
                    
                    for target in targets:
                        relative_pos = (target[0] - entity_pos[0], target[1] - entity_pos[1])
                        valid_actions.append((0, (0 , 0), (relative_pos[0], relative_pos[1]), action.ranged_attack()))
            elif action.action_type == "move":
                relative_x = action.move_path[-1][0]
                relative_y = action.move_path[-1][1]
                relative_pos = (relative_x - entity_pos[0], relative_y - entity_pos[1])
                valid_actions.append((1, (relative_pos[0], relative_pos[1]), (0, 0), 0))
            elif action.action_type == "disengage":
                valid_actions.append((2, (-1, -1),(0, 0), 0))
            elif action.action_type == 'dodge':
                valid_actions.append((3, (-1, -1),(0, 0), 0))
            elif action.action_type == 'dash':
                valid_actions.append((4, (-1, -1),(0, 0), 0))
            elif action.action_type == 'dash_bonus':
                valid_actions.append((5, (-1, -1),(0, 0), 0))
            elif action.action_type == 'stand':
                valid_actions.append((6, (-1, -1),(0, 0), 0))
            elif action.action_type == 'second_wind':
                valid_actions.append((8, (-1, -1),(0, 0), 0))
        valid_actions.append((-1, (0, 0), (0, 0), 0))
        return valid_actions

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