from natural20.actions.look_action import LookAction
from natural20.actions.stand_action import StandAction
from natural20.entity import Entity
from natural20.action import Action
import pdb

class Controller:
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
        selected_action = self.select_action(battle, entity, valid_actions )
        return selected_action

    def select_action(self, battle, entity, available_actions = None) -> Action:
        return None
    
    def move_for(self, entity: Entity, battle):
        # choose available moves at random and return it
        available_actions = self._compute_available_moves(entity, battle)
        # environment, entity = self._build_environment(battle, entity)
        return self.select_action(battle, entity, available_actions)
    
    def _compute_available_moves(self, entity, battle):
        self._initialize_battle_data(battle, entity)

        # known_enemy_positions = self.battle_data[battle][entity]['known_enemy_positions']
        # hiding_spots = self.battle_data[battle][entity]['hiding_spots']
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

        return valid_actions

    def _initialize_battle_data(self, battle, entity):
        self.battle_data = {
            battle : {
                entity : {
                    'known_enemy_positions': {},
                    'hiding_spots': {},
                    'investigate_location': {},
                    'visited_location': {}
                }
            }
        }
    
    def _observe_enemies(self, battle, entity, enemy_positions):
        return None
    
    # Sort actions based on success rate and damage
    def _sort_actions(self, battle, available_actions):
        return available_actions