import random
from natural20.actions.look_action import LookAction
from natural20.actions.stand_action import StandAction
from natural20.map_renderer import MapRenderer
from natural20.entity import Entity
from natural20.action import Action

class EnvObject:
    def __init__(self, name, type, health, location, weapons):
        self.name = name
        self.type = type
        self.health = health
        self.location = location
        self.weapons = weapons

    def __str__(self):
        return f"{self.name} is a {self.type} with {self.health * 100}% health at {self.location}"

class Environment:
    def __init__(self, map, objects = [], resource = {}):
        map_renderer = MapRenderer(map)
        self.observed_map = map_renderer.render(map)
        self.objects = objects
        self.resource = resource

    def __str__(self):
        return self.observed_map
            
class GenericController:
    def __init__(self, session):
        self.state = {}
        self.session = session
        self.battle_data = {}

    def begin_turn(self, entity):
        print(f"{entity.name} begins turn")

    def roll_for(self, entity, stat, advantage=False, disadvantage=False):
        return None
    
    def select_action(self, environment, entity, available_actions = []) -> Action:
        print(environment)
        if len(available_actions) > 0:
            action = random.choice(available_actions)
            print(f"{entity.name}: {action}")
            return action
        
        # no action, end turn
        return None
    
    def move_for(self, entity: Entity, battle):
        # choose available moves at random and return it
        available_actions = self._compute_available_moves(entity, battle)
        enemy_positions = {}
        self._observe_enemies(battle, entity, enemy_positions)
        objects = []
        
        for enemy, location in enemy_positions.items():
            equipped_items = []
            for item in enemy.equipped_items():
                equipped_items.append(item['name'])
            objects.append(EnvObject(enemy.name, 'pc', enemy.hp()/enemy.max_hp(), location, equipped_items))
        environment = Environment(battle.map, objects, {
            "available_movement" : entity.available_movement(battle),
            "available_actions" : entity.total_actions(battle),
            "available_reactions" : entity.total_reactions(battle),
            "available_bonus_actions" : entity.total_bonus_actions(battle)
        })
        return self.select_action(environment, entity, available_actions)
    
        # gain information about enemies in a fair and realistic way (e.g. using line of sight)
    # @param battle [Natural20::Battle]
    # @param entity [Natural20::Entity]
    def _observe_enemies(self, battle, entity, enemy_positions={}):
        objects_around_me = battle.map.look(entity)

        my_group = battle.entity_group_for(entity)

        for object, location in objects_around_me.items():
            group = battle.entity_group_for(object)
            if group == "none":
                continue
            if not group:
                continue
            if not object.conscious:
                continue

            if group != my_group:
                enemy_positions[object] = location 

    def _initialize_battle_data(self, battle, entity):
        if battle not in self.battle_data:
            self.battle_data[battle] = {}
        if entity not in self.battle_data[battle]:
            self.battle_data[battle][entity] = {
                'known_enemy_positions': {},
                'hiding_spots': {},
                'investigate_location': {}
            }

    def _compute_available_moves(self, entity, battle):
        self._initialize_battle_data(battle, entity)

        known_enemy_positions = self.battle_data[battle][entity]['known_enemy_positions']
        hiding_spots = self.battle_data[battle][entity]['hiding_spots']
        investigate_location = self.battle_data[battle][entity]['investigate_location']

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
                valid_targets = battle.valid_targets_for(entity, action)
                if valid_targets:
                    action.target = valid_targets[0]
                    valid_actions.append(action)
            elif action.action_type == "move":
                valid_actions.append(action)
            elif action.action_type == 'dodge':
                valid_actions.append(action)

        return valid_actions

        