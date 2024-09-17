from natural20.actions.look_action import LookAction
from natural20.actions.stand_action import StandAction
from natural20.actions.attack_action import AttackAction
from natural20.actions.spell_action import SpellAction
from natural20.actions.multiattack_action import MultiattackAction
# from natural20.actions.prone_action import ProneAction
from natural20.actions.move_action import MoveAction
from natural20.gym.types import EnvObject, Environment
from natural20.entity import Entity
from natural20.action import Action
from natural20.controller import Controller
from natural20.ai.path_compute import PathCompute
import math
import copy
import pdb

class GenericController(Controller):
    def __init__(self, session):
        self.state = {}
        self.session = session
        self.battle_data = {}

    # @param entity [Natural20::Entity]
    def register_handlers_on(self, entity):
        entity.attach_handler("opportunity_attack", self.opportunity_attack_listener)

    def begin_turn(self, entity):
        # print(f"{entity.name} begins turn")
        pass

    def roll_for(self, entity, stat, advantage=False, disadvantage=False):
        return None

    def opportunity_attack_listener(self, battle, session, entity, map, event):
        actions = [s for s in entity.available_actions(session, battle, opportunity_attack=True)]

        valid_actions = []
        for action in actions:
            valid_targets = battle.valid_targets_for(entity, action)
            if event['target'] in valid_targets:
                action.target = event['target']
                action.as_reaction = True
                valid_actions.append(action)

        _, entity = self._build_environment(battle, entity)
        selected_action = self.select_action(battle, entity, valid_actions )

        return selected_action

    def select_action(self, battle, entity, available_actions = None) -> Action:
        if available_actions is None:
            available_actions = []
        if len(available_actions) > 0:
            action = self._sort_actions(entity, battle, available_actions)[0]
            # print(f"{entity.name}: {action}")
            return action

        # no action, end turn
        return None

    def select_reaction(self, entity, battle, map, valid_actions, event):
        if len(valid_actions) == 0:
            return None
        action = self._sort_actions(entity, battle, valid_actions)[0]
        return action

    def move_for(self, entity: Entity, battle):
        # choose available moves at random and return it
        available_actions = self._compute_available_moves(entity, battle)
        # environment, entity = self._build_environment(battle, entity)
        selected_action = self.select_action(battle, entity, available_actions)
        if isinstance(selected_action, MoveAction):
            battle_data = self._battle_data(battle, entity)
            for p in selected_action.move_path:
                battle_data['visited_location'][tuple(p)] = True

        return selected_action
    
    # Build a suitable environment for Reinforcement Learning
    def _build_environment(self, battle, entity):
        enemy_positions = {}
        self._observe_enemies(battle, entity, enemy_positions)
        objects = []
        
        for enemy, location in enemy_positions.items():
            equipped_items = []
            for item in enemy.equipped_items():
                equipped_items.append(item['name'])
            is_enemy = enemy in battle.opponents_of(entity)
            env_object = EnvObject(enemy.name, 'pc', enemy.hp()/enemy.max_hp(), location, equipped_items, is_enemy=is_enemy)
            objects.append(env_object)
        environment = Environment(battle.map, objects, {
            "available_movement" : entity.available_movement(battle),
            "available_actions" : entity.total_actions(battle),
            "available_reactions" : entity.total_reactions(battle),
            "available_bonus_actions" : entity.total_bonus_actions(battle)
        })
        # clone a copy of entity
        entity = copy.deepcopy(entity)
        return environment, entity

    # gain information about enemies in a fair and realistic way (e.g. using line of sight)
    # @param battle [Natural20::Battle]
    # @param entity [Natural20::Entity]
    def _observe_enemies(self, battle, entity, enemy_positions=None):
        if enemy_positions is None:
            enemy_positions = {}

        objects_around_me = battle.map.look(entity)

        my_group = battle.entity_group_for(entity)
        width, height = battle.map.size
        path_compute = PathCompute(battle, battle.map, entity)
        entity_x, entity_y = battle.map.position_of(entity)

        for object, location in objects_around_me.items():
            group = battle.entity_group_for(object)
            if group == "none":
                continue
            if not group:
                continue
            if not object.conscious():
                continue

            if group != my_group:
                path_compute.build_structures(entity_x, entity_y)
                path_compute.path((location[0], location[1]))
                path = path_compute.backtrace(entity_x, entity_y, location[0], location[1])
                enemy_positions[object] = (location, path)

    def _initialize_battle_data(self, battle, entity):
        if battle not in self.battle_data:
            self.battle_data[battle] = {}
        if entity not in self.battle_data[battle]:
            self.battle_data[battle][entity] = {
                'known_enemy_positions': {},
                'hiding_spots': {},
                'investigate_location': {},
                'visited_location': {}
            }

    def _compute_available_moves(self, entity, battle):
        self._initialize_battle_data(battle, entity)

        battle_data = self._battle_data(battle, entity)
        investigate_location = battle_data['investigate_location']

        enemy_positions = {}
        self._observe_enemies(battle, entity, enemy_positions)
        available_actions = entity.available_actions(self.session, battle)

        # generate available targets
        valid_actions = []
        # check if enemy positions is empty
        if len(enemy_positions.keys()) == 0 and len(investigate_location) == 0 and LookAction.can(entity, battle):
            action = LookAction(self.session, entity, "look")
            valid_actions.append(action)

        # try to stand if prone
        if entity.prone() and StandAction.can(entity, battle):
            valid_actions.append(StandAction(None, entity, "stand"))

        for action in available_actions:
            if action.action_type == "attack":
                valid_actions.append(action)
            elif action.action_type == "move":
                valid_actions.append(action)
            elif action.action_type == "disengage":
                valid_actions.append(action)
            elif action.action_type == 'dodge':
                valid_actions.append(action)
            elif action.action_type == 'dash':
                valid_actions.append(action)
            elif action.action_type == 'dash_bonus':
                valid_actions.append(action)
            elif action.action_type == 'second_wind':
                valid_actions.append(action)
            elif action.action_type == 'spell':
                valid_actions.append(action)

        return valid_actions

    def _get_enemy_positions(self, battle, entity):
        enemy_positions = {}
        self._observe_enemies(battle, entity, enemy_positions)
        return enemy_positions

    def _battle_data(self, battle, entity):
        if battle not in self.battle_data:
            self.battle_data[battle] = {}
        if entity not in self.battle_data[battle]:
            self.battle_data[battle][entity] = {
                'known_enemy_positions': {},
                'hiding_spots': {},
                'investigate_location': {},
                'visited_location': {}
            }
        return self.battle_data[battle][entity]

    # Sort actions based on success rate and damage
    def _sort_actions(self, entity, battle, available_actions):
        """
        Simple rules for performing combat actions:
        - Attack if available
        - Move towards the closest enemy
        """
        enemy_distance_pair = []

        enemy_positions = self._get_enemy_positions(battle, entity)

        move_square_score = {}
        for enemy, location_pair in enemy_positions.items():
            _, path = location_pair

            if path is None:
                continue

            distance = len(path)
            square_key = (path[1][0], path[1][1])
            move_square_score[square_key] = 1.0 / distance
            enemy_distance_pair.append((enemy, distance))

        enemy_distance_pair.sort(key=lambda a: a[1])

        sorted_actions = []
        for action in available_actions:
            if isinstance(action, AttackAction) or isinstance(action, SpellAction):
                if isinstance(action, AttackAction):
                    attack_available = True
                base_score = action.compute_hit_probability(battle) * action.avg_damage(battle)
                sorted_actions.append((action, base_score))
            elif isinstance(action, MoveAction):
                new_position = action.move_path[-1]
                print(f"move_square_score: {move_square_score}")
                print(f"New position: {new_position}")
                position_key = (new_position[0], new_position[1])
                score = move_square_score.get(position_key, 0)
                sorted_actions.append((action, score))
            else:
                sorted_actions.append((action, 0))
        sorted_actions.sort(key=lambda a: a[1], reverse=True)
        sorted_actions = [a[0] for a in sorted_actions]
        return sorted_actions