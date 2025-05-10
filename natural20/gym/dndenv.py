import gymnasium as gym
import numpy as np
import random, os
from typing import Any, Dict
from natural20.map import Map
from natural20.battle import Battle
from natural20.player_character import PlayerCharacter
from natural20.npc import Npc
from natural20.generic_controller import GenericController
from natural20.session import Session
from natural20.entity import Entity
from natural20.gym.dndenv_controller import DndenvController
from natural20.controller import Controller
from natural20.event_manager import EventManager
from natural20.gym.tools import (
    dndenv_action_to_nat20action,
    build_observation,
    compute_available_moves,
    render_terrain,
    render_object_token,
    action_to_gym_action,
    build_info
)
from webapp.llm_conversation_handler import LLMConversationHandler

class GymInternalController(Controller):
    """
    Internal controller for gym-based DnD environments.
    Handles reaction callbacks and registers event handlers.
    """
    def __init__(self, session, dndenv, reaction_callback=None):
        self.session = session
        self.env = dndenv
        self.reaction_callback = reaction_callback
        self.state = {}
        self.battle_data = {}

    def update_reaction_callback(self, callback) -> None:
        self.reaction_callback = callback

    def register_handlers_on(self, entity: Entity) -> None:
        entity.attach_handler("opportunity_attack", self.opportunity_attack_listener)

    def opportunity_attack_listener(self, battle, session, entity, map_obj, event):
        valid_actions = []
        for action in entity.available_actions(session, battle, opportunity_attack=True):
            if event['target'] in battle.valid_targets_for(entity, action):
                action.target = event['target']
                action.as_reaction = True
                valid_actions.append(action)
        return self.select_reaction(entity, battle, map_obj, valid_actions, event)

    def select_reaction(self, entity, battle, map_obj, valid_actions, event):
        if not self.reaction_callback:
            return None
        observation = self.env.generate_observation(entity, is_reaction=True)
        available_moves = action_to_gym_action(
            entity, map_obj, valid_actions,
            weapon_mappings=self.env.weapon_mappings,
            spell_mappings=self.env.spell_mappings
        )
        info = self.env._info(available_moves, entity)
        info.update({
            'trigger': event['trigger'],
            'entity': self.env.entity_mappings[entity.class_descriptor().lower()],
            'reactor': entity.name
        })
        chosen_action = self.reaction_callback(observation, 0, False, False, info)
        if chosen_action[0] == -1:
            return None
        return dndenv_action_to_nat20action(
            entity, battle, map_obj, valid_actions, chosen_action,
            weapon_mappings=self.env.weapon_mappings,
            spell_mappings=self.env.spell_mappings
        )


def load_mapping(session, file_name: str, offset: int = 0) -> Dict[str, int]:
    mapping = {}
    path = os.path.join(session.root_path, file_name)
    with open(path, 'r') as f:
        for line in f:
            name, idx = line.strip().split(',')
            mapping[name] = int(idx) + offset
    return mapping

def embedding_loader(session, weapon_mappings=None, spell_mappings=None, entity_mappings=None, **kwargs):
    if weapon_mappings is None:
        weapon_mappings = load_mapping(session, kwargs.get('weapon_embeddings', 'weapon_token_map.csv'))
    if spell_mappings is None:
        spell_mappings = load_mapping(session, kwargs.get('spell_embeddings', 'spell_token_map.csv'), offset=100)
    if entity_mappings is None:
        entity_mappings = load_mapping(session, kwargs.get('entity_embeddings', 'entity_token_map.csv'))
    return weapon_mappings, spell_mappings, entity_mappings

ACTION_TYPE_MAP = {
    "attack": 0,
    "move": 1,
    "disengage": 2,
    "dodge": 3,
    "dash": 4,
    "dash_bonus": 5,
    "stand": 6,
    "look": 7,
    "second_wind": 8,
    "two_weapon_attack": 9,
    "prone": 10,
    "disengage_bonus": 11,
    "spell": 12,
    "shove": 13,
    "help": 14,
    "hide": 15,
    "use_item": 16,
    "action_surge": 17,
    "dismiss_familiar": 18,
    -1: -1,
}

def action_type_to_int(action_type):
    try:
        return ACTION_TYPE_MAP[action_type]
    except KeyError:
        raise ValueError(f"Unknown action type {action_type}")
    
"""
This is a custom environment for the game Dungeons and Dragons 5e. It is based on the OpenAI Gym environment.
"""
class dndenv(gym.Env):
    LOG_LEVEL_DEBUG = 0
    LOG_LEVEL_INFO = 1
    LOG_LEVEL_WARNING = 2
    LOG_LEVEL_ERROR = 3

    def __init__(self, view_port_size=(12, 12), max_rounds=200, render_mode = None, **kwargs):
        """
        Initializes the environment with the following parameters:
        - view_port_size: the size of the view port for the agent (default is 12x12)
        - max_rounds: the maximum number of rounds before the game ends
        - render_mode: the mode to render the game in
        - root_path: the root path for the game
        - map_file: the file to load the map from
        - profiles: the profiles to load for the heroes
        - enemies: the profiles to load for the enemies
        - hero_names: the names of the heroes, can be a list or a lambda function
        - enemy_names: the names of the enemies
        - show_logs: whether to show logs
        - custom_controller: a custom controller to use
        - custom_agent: a custom agent to use, can be a lambda function
        - custom_initializer: a custom initializer to use
        - control_groups: the control groups that the agent controls
        - damage_based_reward: whether to use damage based rewards, -10 * (enemy final hp / enemy initial hp)
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
            "map": gym.spaces.Box(low=-1, high=255, shape=(view_port_size[0], view_port_size[0], 5), dtype=int),
            "turn_info" : gym.spaces.Box(low=0, high=1, shape=(3,), dtype=int),
            "conditions": gym.spaces.Box(low=0, high=1, shape=(8,), dtype=int),
            "player_ac" : gym.spaces.Box(low=0, high=1, shape=(1,), dtype=float),
            "player_equipped" : gym.spaces.Box(low=0, high=255, shape=(5,), dtype=int),
            "enemy_ac" : gym.spaces.Box(low=0, high=1, shape=(1,), dtype=float),
            "health_pct": gym.spaces.Box(low=0, high=1, shape=(1,), dtype=float),
            "health_enemy": gym.spaces.Box(low=0, high=1, shape=(1,), dtype=float),
            "enemy_reactions": gym.spaces.Box(low=0, high=1, shape=(1,), dtype=int),
            "enemy_conditions": gym.spaces.Box(low=0, high=1, shape=(8,), dtype=int),
            "player_type": gym.spaces.Box(low=0, high=1, shape=(1,), dtype=int),
            "enemy_type": gym.spaces.Box(low=0, high=1, shape=(1,), dtype=int),
            "ability_info": gym.spaces.Box(low=0, high=1, shape=(8,), dtype=int),
            "movement": gym.spaces.Box(low=0, high=255, shape=(1,), dtype=int),
            "spell_slots": gym.spaces.Box(low=0, high=255, shape=(9,), dtype=int),
            "is_reaction": gym.spaces.Box(low=0, high=1, shape=(1,), dtype=int)
        })

        self.action_space = gym.spaces.Tuple([
            gym.spaces.Box(low=-1, high=255, shape=(1,), dtype=int),
            gym.spaces.Box(low=-1, high=255, shape=(2,), dtype=int),
            gym.spaces.Box(low=-view_port_size[0]//2, high=view_port_size[0]//2, shape=(2,), dtype=int),
            gym.spaces.Discrete(255),
            gym.spaces.Discrete(255)
        ])

        self.reward_range = (-1, 1)
        self.metadata = {}
        self.spec = None
        self._seed = None
        self.root_path = kwargs.get('root_path', 'templates')
        self.map_file = kwargs.get('map_file', 'maps/game_map.yml')
        self.heroes = kwargs.get('profiles', ['halfling_rogue.yml'])
        self.enemies = kwargs.get('enemies', ['halfling_rogue.yml'])
        self.hero_names = kwargs.get('hero_names', ['gomerin'])
        self.enemy_names = kwargs.get('enemy_names', ['rumblebelly'])
        self.show_logs = kwargs.get('show_logs', False)
        self.log_level = kwargs.get('log_level', 2)
        self.output_file = kwargs.get('output_file', None)
        self.custom_controller = kwargs.get('custom_controller', None)
        self.custom_agent = kwargs.get('custom_agent', None)
        self.custom_initializer = kwargs.get('custom_initializer', None)
        self.event_manager = kwargs.get('event_manager', None)
        self.control_groups = kwargs.get('control_groups', ['a'])
        self.damage_based_reward = kwargs.get('damage_based_reward', False)
        self.custom_session = kwargs.get('custom_session', None)
        self.reactions_callback = kwargs.get('reactions_callback', None)
        self.weapon_mappings = None
        self.spell_mappings = None
        self.entity_mappings = None
        self.kwargs = kwargs

    def seed(self, seed=None):
        self._seed = seed
        return [seed]

    def log(self, msg, level = 0):
        if level >= self.log_level:
            if self.output_file:
                with open(self.output_file, 'a') as f:
                    f.write(msg + "\n")
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

                    terrain = render_object_token(self.map, abs_x, abs_y)
                    entity = self.map.entity_at(abs_x, abs_y)
                    if self.map.can_see_square(current_player, (abs_x, abs_y)):
                        if entity is None:
                            if terrain is None:
                                render_char = "."
                            elif terrain == "~":
                                render_char = "~"
                            elif terrain == "o":
                                render_char = "o"
                            elif terrain == "#":
                                render_char = "#"
                            elif terrain == "·":
                                render_char = "·"
                            else:
                                raise ValueError(f"Unknown terrain {terrain}")

                        elif entity == current_player:
                            render_char = "P"
                        elif self.battle.allies(current_player, entity):
                            render_char = "A"
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
        reactions_callback = kwargs.get('reaction_callback', self.reactions_callback)

        if seed is None:
            seed = random.randint(0, 1000000)

        self.seed = seed # take note of seed for reproducibility
        random.seed(seed)

        if callable(self.map_file):
            map_filename = self.map_file()
        else:
            map_filename = self.map_file

        map_location = kwargs.get('map_location', os.path.join(self.root_path, map_filename))
        event_manager = self.event_manager

        self.log(f"loading map from {map_location}")

        if event_manager is None:
            self.log("Creating new event manager")
            output_file = kwargs.get('output_file', self.output_file)
            event_manager = EventManager(output_file=output_file)
            if self.show_logs:
                event_manager.standard_cli()

        if self.custom_session:
            if callable(self.custom_session):
                self.session = self.custom_session(self)
            else:
                self.session = self.custom_session
        else:
            self.session = Session(self.root_path, event_manager=event_manager, conversation_handlers={'llm': LLMConversationHandler})

        self.session.reset()
        self.weapon_mappings, self.spell_mappings, self.entity_mappings = embedding_loader(self.session, weapon_mappings=self.weapon_mappings, spell_mappings=self.spell_mappings, entity_mappings=self.entity_mappings, **kwargs)

        self.map = Map(self.session, map_location)
        self.battle = Battle(self.session, self.map)
        self.players = []
        self.current_round = 0
        self.terminal = False

        if self.custom_initializer:
            initiative_order = self.custom_initializer(self)
        else:
            initiative_order = self._setup_up_default_1v1(reaction_callback=reactions_callback)

        self.battle.start(combat_order=initiative_order)
        self.battle.start_turn()
        if self.battle.current_turn().conscious():
                self.battle.current_turn().reset_turn(self.battle)
        current_player = self.battle.current_turn()

        current_player, _ = self._game_loop(current_player)

        # get the first player which is not the same group as the current one
        observation = self.generate_observation(current_player)
        _available_moves = compute_available_moves(self.session, self.map, self.battle.current_turn(), self.battle,
                                                   weapon_mappings=self.weapon_mappings,
                                                   spell_mappings=self.spell_mappings)

        if not len(_available_moves) > 0:
            raise Exception("There should be at least one available move for the agent.")

        return observation, self._info(_available_moves, current_player)

    def _info(self, available_moves, current_player):
        info_r = build_info(self.battle, available_moves, current_player, self.weapon_mappings, self.spell_mappings, self.entity_mappings)
        info_r['damage_dealth'] = self._total_damage_dealt(current_player)
        return info_r

    def _describe_hero(self, pc: Entity):
        self.log("==== Player Character ====")
        ability_score_str = ""
        for attr in pc.ability_scores.items():
            ability_score_str += f"{attr[0]}: {attr[1]} "
        self.log(ability_score_str)
        self.log(f"name: {pc.name}")
        self.log(f"level: {pc.level()}")
        self.log(f"character class: {pc.c_class()}")
        self.log(f"hp: {pc.hp()}")
        self.log(f"max hp: {pc.max_hp()}")
        self.log(f"ac: {pc.armor_class()}")
        self.log(f"speed: {pc.speed()}")
        self.show_spells(pc)
        self.log("\n\n")

    def _game_loop(self, current_player):
        """
        Main game loop for the environment, make moves for groups that are not controlled by the agent
        """
        result = None
        while True:
            player_group = self.battle.entity_group_for(current_player)
            if player_group not in self.control_groups:
                controller = self.battle.controller_for(current_player)
                if controller is None:
                    raise ValueError(f"Controller for {current_player.name} is None. ")
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
                self.log(f"==== current turn {current_player.name} {current_player.hp()}/{current_player.max_hp()} AC {current_player.armor_class()}===")
                self.show_spells(current_player)
            elif player_group in self.control_groups:
                if current_player.conscious():
                    current_player.reset_turn(self.battle)
                break
        return current_player, result
    
    def _setup_up_default_1v1(self, reaction_callback=None):
        enemy_pos = None
        player_pos = None

        character_sheet_path = 'characters'
        # if a lambda function is passed for heroes or enemies, call it
        heroes = self.heroes() if callable(self.heroes) else self.heroes
        enemies = self.enemies() if callable(self.enemies) else self.enemies

        # ensure heroes and enemies are lists
        heroes = [heroes] if not isinstance(heroes, list) else heroes
        enemies = [enemies] if not isinstance(enemies, list) else enemies

        for index, p in enumerate(heroes):
            if index < len(self.hero_names):
                name = self.hero_names[index]

            if isinstance(p, tuple):
                p, name = p

            if p.startswith('npcs'):
                pc = Npc.load(self.session, p, { "name" : name})
            else:
                pc = PlayerCharacter.load(self.session, f'{character_sheet_path}/{p}', { "name" : name})
            self._describe_hero(pc)
            # set random starting positions, make sure there are no obstacles in the map
            while player_pos is None or not self.map.placeable(pc, player_pos[0], player_pos[1]):
                # trunk-ignore(bandit/B311)
                player_pos = [random.randint(0, self.map.size[0] - 1), random.randint(0, self.map.size[1] - 1)]
            self.players.append(('a', 'H', pc, player_pos))

        for index, p in enumerate(enemies):
            if index < len(self.enemy_names):
                name = self.enemy_names[index]

            if isinstance(p, tuple):
                p, name = p

            if p.startswith('npcs'):
                pc = Npc.load(self.session, f'npcs/{p}', { "name" : name})
            else:
                pc = PlayerCharacter.load(self.session, f'{character_sheet_path}/{p}', {"name":  name})

            self._describe_hero(pc)
            while enemy_pos is None or enemy_pos==player_pos or not self.map.placeable(pc, enemy_pos[0], enemy_pos[1]):
                enemy_pos = [random.randint(0, self.map.size[0] - 1), random.randint(0, self.map.size[1] - 1)]
            self.players.append(('b', 'E', pc , enemy_pos))

        # add fighter to the battle at position (0, 0) with token 'G' and group 'a'
        for group, token, player, position in self.players:
            if group not in self.control_groups:
                if self.custom_agent:
                    if callable(self.custom_agent):
                        controller = self.custom_agent(self.session, **self.kwargs)
                    else:
                        self.log(f"Setting up custom agent for enemy player {self.custom_agent}", level=self.LOG_LEVEL_INFO)
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
                controller = GymInternalController(self.session, self, reaction_callback=reaction_callback)
                controller.register_handlers_on(player)
                self.battle.add(player, group, position=position, token=token, add_to_initiative=True, controller=controller)

        return None

    def _enemy_hp_pct(self, entity):
        current_group = self.battle.entity_group_for(entity)
        enemy_players = []
        for _, _, player, _ in self.players:
            if self.battle.entity_group_for(player) != current_group:
                enemy_players.append(player)
        # get avg hp percentage of enemies
        total_hp = 0
        total_max_hp = 0

        for player in enemy_players:
            total_hp += player.hp()
            total_max_hp += player.max_hp()

        if total_max_hp > 0:
            return (total_hp / total_max_hp)

        return 1.0

    def _total_damage_dealt(self, entity):
        current_group = self.battle.entity_group_for(entity)
        enemy_players = []
        for _, _, player, _ in self.players:
            if self.battle.entity_group_for(player) != current_group:
                enemy_players.append(player)

        total_hp = 0
        total_max_hp = 0

        for player in enemy_players:
            total_hp += player.hp()
            total_max_hp += player.max_hp()

        return total_max_hp - total_hp

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
        action = dndenv_action_to_nat20action(entity, self.battle, self.map, available_actions, action,
                                              weapon_mappings=self.weapon_mappings,
                                              spell_mappings=self.spell_mappings)
        if action is None:
            reward = -1
        elif action == -1:
            end_turn = True
        else:
            self.battle.action(action)
            self.battle.commit(action)

        # additional check for tpk
        if self.battle.battle_ends():

            if entity.conscious() and self.battle.entity_group_for(entity) in self.control_groups:
                reward = 10
            else:
                if self.damage_based_reward:
                    reward = -10 * self._enemy_hp_pct(entity)
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
            # show health bar of each entity
            for _, _, player, _ in self.players:
                self.log(f"{player.name} {player.hp()}/{player.max_hp()}")
                self.show_spells(player)

            result = self.battle.next_turn(max_rounds=self.max_rounds)
            if result == 'tpk' and entity.conscious() and self.battle.entity_group_for(entity) in self.control_groups:
                reward = 10
                done = True
            else:
                self.battle.start_turn()
                current_player = self.battle.current_turn()
                current_player.reset_turn(self.battle)
                self.log(f"==== current turn {current_player.name} {current_player.hp()}/{current_player.max_hp()} AC {current_player.armor_class()}===")
                self.show_spells(current_player)
                if current_player.dead():
                    self.log(f"{current_player.name} is dead")
                    if self.battle.entity_group_for(entity) in self.control_groups:
                        reward = 10
                    else:
                        if self.damage_based_reward:
                            reward = -10 * self._enemy_hp_pct(entity)
                        else:
                            reward = -10

                    observation, info = self._terminal_observation()
                    return observation, reward, True, False, info

                _, result = self._game_loop(current_player)

                self.log(f"Result: {result}")

                if result == 'tpk':
                    # Victory!!!!
                    if self.battle.entity_group_for(entity) in self.battle.winning_groups():
                        reward = 10
                    else:
                        if self.damage_based_reward:
                            reward = -10 * self._enemy_hp_pct(entity)
                        else:
                            reward = -10
                    done = True
        observation = self.generate_observation(entity)
        _available_moves = compute_available_moves(self.session, self.map, self.battle.current_turn(), self.battle,
                                                   weapon_mappings=self.weapon_mappings,
                                                   spell_mappings=self.spell_mappings)

        if len(_available_moves) == 0:
            raise ValueError("There should be at least one available move for the agent.")

        self.current_round += 1

        if self.current_round >= self.max_rounds:
            done = True
            truncated = True

        return observation, reward, done, truncated, self._info(_available_moves, entity)

    def show_spells(self, current_player):
        if current_player.has_spells():
            for spell_level in range(1, 10):
                if current_player.max_spell_slots(spell_level) > 0:
                    self.log(f"spell slots level {spell_level}: {current_player.spell_slots_count(spell_level)}")

    def generate_observation(self, entity, is_reaction=False):
        return build_observation(self.battle, self.map, entity, self.entity_mappings, self.weapon_mappings, self.view_port_size, is_reaction=is_reaction)

    def _terminal_observation(self):
        observation = {
            "map": render_terrain(self.battle, self.map, self.entity_mappings, self.view_port_size),
            "conditions": np.array([0, 0, 0, 0, 0, 0, 0, 0]),
            "enemy_conditions": np.array([0, 0, 0, 0, 0, 0, 0, 0]),
            "player_equipped": np.array([0, 0, 0, 0, 0]),
            "player_ac": np.array([0.0]),
            "enemy_ac": np.array([0.0]),
            "turn_info": np.array([0, 0, 0]),
            "health_pct": np.array([0.0]),
            "health_enemy" : np.array([0.0]),
            "enemy_reactions": np.array([0]),
            "player_type": np.array([0]),
            "enemy_type": np.array([0]),
            "ability_info": np.array([0, 0, 0, 0, 0, 0, 0, 0]), # tracks usage of class specific abilities (e.g. second wind, rage, etc.)
            "spell_slots": np.array([0, 0, 0, 0, 0, 0, 0, 0, 0]),
            "movement": np.array([0]),
            "is_reaction": np.array([0])
        }

        return observation, self._info(end_of_turn_move(), self.battle.current_turn())

def end_of_turn_move():
    return [(-1, (0,0), (0,0), 0, 0)]

gym.register(id='dndenv-v0', entry_point=lambda **kwargs: dndenv(**kwargs))