import numpy as np
from natural20.entity import Entity
from natural20.actions.look_action import LookAction
from natural20.actions.stand_action import StandAction

def enemy_health(battle, current_player):
    for player in battle.entities.keys():
        if battle.entity_group_for(player) != battle.entity_group_for(current_player):
            return player.hp() / player.max_hp()
    return 0

def build_observation(battle, map, entity, view_port_size=(12, 12)):
    """
    Builds the observation for the environment
    """
    e_health = enemy_health(battle, entity)
    obs = {
        "map": render_terrain(battle, map, view_port_size),
        "turn_info": np.array([entity.total_actions(battle), entity.total_bonus_actions(battle), entity.total_reactions(battle)]),
        "health_pct": np.array([entity.hp() / entity.max_hp()]),
        "health_enemy" : np.array([e_health]),
        "movement": battle.current_turn().available_movement(battle)
    }
    return obs

def dndenv_action_to_nat20action(entity, battle, map, available_actions, action):
    """
    Converts the simple gym vector action to a Natural20 action. This
    basically finds the closest action in the available actions list
    """
    action_type, param1, param2, param3 = action

    for action in available_actions:
        if action.action_type == "attack" and action_type == 0:
            # convert from relative position to absolute map position
            entity_position = map.position_of(entity)
            target_x = entity_position[0] + param2[0]
            target_y = entity_position[1] + param2[1]
            target = map.entity_at(target_x, target_y)

            valid_targets = battle.valid_targets_for(entity, action)
            if valid_targets:
                action.target = valid_targets[0]
                if param3==0 or (param3 == 1 and action.ranged_attack()):
                    for valid_target in valid_targets:
                        if target == valid_target:
                            action.target = target
                            break
                    return action
                
                return action
        elif action.action_type == "move" and action_type == 1:
            entity_position = map.position_of(entity)
            target_x = entity_position[0] + param1[0]
            target_y = entity_position[1] + param1[1]
            if action.move_path[-1] == [target_x, target_y]:
                return action
        elif action.action_type == "disengage" and action_type == 2:
            return action
        elif action.action_type == "dodge" and action_type == 3:
            return action
        elif action.action_type == "dash" and action_type == 4:
            return action
        elif action.action_type == "dash_bonus" and action_type == 5:
            return action
        elif action.action_type == "stand" and action_type == 6:
            return action
        elif action.action_type == "look" and action_type == 7:
            return action
        elif action.action_type == "second_wind" and action_type == 8:
            return action
        elif action_type == -1:
            return -1
    return None

def render_terrain(battle, map, view_port_size=(12, 12)):
    result = []
    current_player = battle.current_turn()
    pos_x, pos_y = map.position_of(current_player)
    view_w, view_h = view_port_size
    map_w, map_h = map.size
    for y in range(-view_w//2, view_w//2):
        col_arr = []
        for x in range(-view_h//2, view_h//2):
            if pos_x + x < 0 or pos_x + x >= map_w or pos_y + y < 0 or pos_y + y >= map_h:
                col_arr.append([-1, -1, 0])
            else:
                if not map.can_see_square(current_player,(pos_x + x, pos_y + y)):
                    col_arr.append([255, 255, 255])
                else:
                    terrain = map.base_map[pos_x + x][pos_y + y]

                    if terrain == None:
                        terrain_int = 0
                    else:
                        terrain_int = 1

                    entity = map.entity_at(pos_x + x, pos_y + y)

                    if entity == None:
                        entity_int = 0
                    elif entity == current_player:
                        entity_int = 1
                    elif battle.opposing(current_player, entity):
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

def compute_available_moves(session, map, entity: Entity, battle):
    available_actions = entity.available_actions(session, battle)
    # generate available targets
    valid_actions = []       
    # try to stand if prone
    if entity.prone() and StandAction.can(entity, battle):
        valid_actions.append((6, (0, 0), (0, 0), 0))
    
    entity_pos = map.position_of(entity)

    for action in available_actions:
        if action.action_type == "attack":
            valid_targets = battle.valid_targets_for(entity, action)
            if valid_targets:
                action.target = valid_targets[0]
                targets = map.entity_squares(valid_targets[0])
                
                for target in targets:
                    relative_pos = (target[0] - entity_pos[0], target[1] - entity_pos[1])
                    attack_type = 0
                    if action.ranged_attack():
                        attack_type = 1
                    valid_actions.append((0, (0 , 0), (relative_pos[0], relative_pos[1]), attack_type))
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