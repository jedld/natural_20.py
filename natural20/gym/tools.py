import numpy as np
from natural20.entity import Entity
from natural20.player_character import PlayerCharacter
# from natural20.actions.look_action import LookAction
# from natural20.actions.stand_action import StandAction

def enemy_stats(battle, current_player, entity_type_mappings):
    """
    Returns the enemy stats for the current player
    """
    for player in battle.entities.keys():
        if battle.entity_group_for(player) != battle.entity_group_for(current_player):
            enemy_hp = player.hp() / 1000.0
            enemy_reactions = player.total_reactions(battle)
            enemy_conditions = condition_stats(player, battle)
            return enemy_hp, enemy_reactions, enemy_conditions, map_entity_to_index(player, entity_type_mappings), player.armor_class()
    return 0, 0, np.zeros((8), dtype=np.int64), 0

def condition_stats(entity, battle):
    """
    Returns the condition stats for the entity
    """
    return np.array([int(entity.prone()), int(entity.dodge(battle)), int(entity.grappled()), int(entity.disengage(battle)), 0, 0, 0, 0])

def build_observation(battle, map, entity, entity_type_mappings, weapon_type_mappings, view_port_size=(12, 12)):
    """
    Builds the observation for the environment
    """
    e_health, e_reactions, e_conditions, enemy_type, e_ac = enemy_stats(battle, entity, entity_type_mappings=entity_type_mappings)

    pc_entity_type = map_entity_to_index(entity, entity_type_mappings)

    mapped_equipments = []
    for index, equipment in enumerate(entity.equipped_items()):
        if index < 5:
            mapped_equipments.append(weapon_type_mappings[equipment['name']])

    if len(mapped_equipments) < 5:
        mapped_equipments += [0] * (5 - len(mapped_equipments))

    obs = {
        "map": render_terrain(battle, map, view_port_size),
        "turn_info": np.array([entity.total_actions(battle), entity.total_bonus_actions(battle), entity.total_reactions(battle)]),
        "conditions": condition_stats(entity, battle),
        "health_pct": np.array([entity.hp() / 1000.0]),
        "player_equipped": np.array(mapped_equipments),
        "health_enemy" : np.array([e_health]),
        "enemy_conditions": e_conditions,
        "enemy_reactions" : np.array([e_reactions]),
        "player_ac" : np.array([entity.armor_class() / 30.0]),
        "enemy_ac" : np.array([e_ac / 30.0]),
        "ability_info": ability_info(entity),
        "player_type": pc_entity_type,
        "enemy_type": enemy_type,
        "movement": np.array([battle.current_turn().available_movement(battle)])
    }
    return obs

def map_entity_to_index(entity, entity_type_mappings):
    if isinstance(entity, PlayerCharacter):
        return entity_type_mappings[entity.class_descriptor()]
    else:
        return entity_type_mappings[entity.name.lower()]

def ability_info(entity):
    """
    Returns the ability information for the entity
    """
    ability_info = np.zeros((8), dtype=np.int64)

    SECOND_WIND = 0

    if hasattr(entity, 'second_wind_count'):
        ability_info[SECOND_WIND] = entity.second_wind_count
        
    return ability_info

def dndenv_action_to_nat20action(entity, battle, map, available_actions, gym_action, weapon_mappings=None, spell_mappings=None):
    """
    Converts the simple gym vector action to a Natural20 action. This
    basically finds the closest action in the available actions list
    """
    action_type, param1, param2, param3, param4 = gym_action

    if len(available_actions) == 0:
        if action_type == -1:
            return -1

    for action in available_actions:
        if (action.action_type == "attack" and action_type == 0) or (action.action_type == "two_weapon_attack" and action_type == 9):
            # convert from relative position to absolute map position
            entity_position = map.position_of(entity)
            target_x = entity_position[0] + param2[0]
            target_y = entity_position[1] + param2[1]
            if weapon_mappings is not None:
                if weapon_mappings.get(action.using) is None:
                    raise  ValueError(f"Cannot tokenize {action.using}, make sure to generate a new weapon mapping file")
                if weapon_mappings[action.using] == param3 and (param4 ==0 or (param4 == 1 and action.ranged_attack())):
                    return action
            elif param3==0 or (param4 == 1 and action.ranged_attack()):
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
        elif action.action_type == "two_weapon_attack" and action_type == 9:
            return action
        elif action.action_type == "prone" and action_type == 10:
            return action
        elif action.action_type == "disengage_bonus" and action_type == 11:
            return action
        elif action.action_type == "spell" and action_type == 12:
            if spell_mappings is not None:
                if spell_mappings.get(action.spell_action.short_name()) == param3 and action.at_level == param4:
                    return action
            else:
                return action
        elif action_type == -1:
            return -1
    raise ValueError(f"No action match for {gym_action} {action_type}")

def render_object_token(map, pos_x, pos_y):
    object_meta = map.object_at(pos_x, pos_y)
    if not object_meta:
        return None

    m_x, m_y = map.interactable_objects[object_meta]

    if not object_meta.token():
        return None
    if object_meta.token() == 'inherit':
        return 'inherit'

    if isinstance(object_meta.token(), list):
        return object_meta.token()[pos_y - m_y][pos_x - m_x]
    else:
        return object_meta.token()

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
                col_arr.append([-1, -1, 0, 0])
            else:
                if not map.can_see_square(current_player,(pos_x + x, pos_y + y)):
                    col_arr.append([255, 255, 255, 255])
                else:
                    terrain = render_object_token(map, pos_x + x, pos_y + y)

                    if terrain is None:
                        terrain_int = 0
                    elif terrain == '~':
                        terrain_int = 2
                    elif terrain == 'o':
                        terrain_int = 3
                    elif terrain == '#':
                        terrain_int = 1
                    else:
                        raise ValueError(f"Unknown terrain {terrain}")

                    entity = map.entity_at(pos_x + x, pos_y + y)

                    if entity is None:
                        entity_int = 0
                    elif entity == current_player:
                        entity_int = 1
                    elif battle.opposing(current_player, entity):
                        entity_int = 2
                    elif battle.allies(current_player, entity):
                        entity_int = 3
                    else:
                        entity_int = 4

                    if entity is not None:
                        health_pct = int((entity.hp() / (entity.max_hp() + 0.00001)) * 255)
                    else:
                        health_pct = 0

                    status_int = 0
                    if entity is not None:
                        # add an 8-bit mask for status effects
                        if entity.prone():
                            status_int |= 1
                        if entity.dodge(battle):
                            status_int |= 2
                        if entity.unconscious():
                            status_int |= 16
                        if entity.dead():
                            status_int |= 32
 
                    col_arr.append([entity_int, terrain_int, health_pct, status_int])
        
        result.append(col_arr)
    return np.array(result)

def compute_available_moves(session, map, entity: Entity, battle, weapon_mappings=None, spell_mappings=None):
    available_actions = entity.available_actions(session, battle)
    # generate available targets
    valid_actions = []       

    entity_pos = map.position_of(entity)

    for action in available_actions:
        if action.action_type == "attack" or action.action_type == "two_weapon_attack":
            valid_targets = battle.valid_targets_for(entity, action)
            if valid_targets:
                action.target = valid_targets[0]
                targets = map.entity_squares(valid_targets[0])
                
                for target in targets:
                    relative_pos = (target[0] - entity_pos[0], target[1] - entity_pos[1])
                    attack_type = 0
                    attack_sub_type = 1 if action.ranged_attack() else 0

                    if weapon_mappings is not None and weapon_mappings.get(action.using) is not None:
                        attack_type = weapon_mappings[action.using]
                    action_type = 0 if action.action_type == "attack" else 9
                    valid_actions.append((action_type, (0 , 0), (relative_pos[0], relative_pos[1]), attack_type, attack_sub_type))
        elif action.action_type == "move":
            relative_x = action.move_path[-1][0]
            relative_y = action.move_path[-1][1]
            relative_pos = (relative_x - entity_pos[0], relative_y - entity_pos[1])
            valid_actions.append((1, (relative_pos[0], relative_pos[1]), (0, 0), 0, 0))
        elif action.action_type == "disengage":
            valid_actions.append((2, (-1, -1),(0, 0), 0, 0))
        elif action.action_type == 'dodge':
            valid_actions.append((3, (-1, -1),(0, 0), 0, 0))
        elif action.action_type == 'dash':
            valid_actions.append((4, (-1, -1),(0, 0), 0, 0))
        elif action.action_type == 'dash_bonus':
            valid_actions.append((5, (-1, -1),(0, 0), 0, 0))
        elif action.action_type == 'stand':
            valid_actions.append((6, (-1, -1),(0, 0), 0, 0))
        elif action.action_type == 'second_wind':
            valid_actions.append((8, (-1, -1),(0, 0), 0, 0))
        elif action.action_type == 'prone':
            valid_actions.append((10, (-1, -1),(0, 0), 0, 0))
        elif action.action_type == 'disengage_bonus':
            valid_actions.append((11, (-1, -1),(0, 0), 0, 0))
        elif action.action_type == 'spell':
            spell_type = spell_mappings[action.spell_action.short_name()]
            valid_actions.append((12, (-1, -1),(0, 0), spell_type, action.at_level))


    valid_actions.append((-1, (0, 0), (0, 0), 0, 0)) # end turn should always be available
    for action in valid_actions:
        assert len(action) == 5, f"Invalid action {action}"

    return valid_actions

def generate_entity_token_map(session, output_filename = 'entity_token_map.csv'):
    """
    Generates an numeric index map for each entity in the session. This can
    be used for embedding the entity token in the model.
    """

    entity_map = {}
    # load characters
    for idx, pc in enumerate(session.load_characters()):
        entity_map[idx] = pc.class_descriptor()

    # load npcs
    for idx, npc in enumerate(session.load_npcs()):
        entity_map[idx + len(session.load_characters())] = npc.name.lower()

    with open(output_filename, "w") as f:
        for idx, entity in entity_map.items():
            f.write(f"{entity},{idx}\n")


def generate_weapon_token_map(session, output_filename = 'weapon_token_map.csv'):
    """
    Generates an numeric index map for each weapon in the session. This can
    be used for embedding the weapon token in the model.
    """

    weapon_map = {}
    weapon_map[0] = "unarmed"
    for idx, (name, _) in enumerate(session.load_weapons().items()):
        weapon_map[idx+1] = name

    for idx, (name, _) in enumerate(session.load_all_equipments().items()):
        weapon_map[idx+len(session.load_weapons())+1] = name

    with open(output_filename, "w") as f:
        for idx, weapon in weapon_map.items():
            f.write(f"{weapon},{idx}\n")

def generate_spell_token_map(session, output_filename = 'spell_token_map.csv'):
    """
    Generates an numeric index map for each spell in the session. This can
    be used for embedding the spell token in the model.
    """

    spell_map = {}
    for idx, spell in enumerate(session.load_all_spells().keys()):
        spell_map[idx] = spell

    with open(output_filename, "w") as f:
        for idx, spell in spell_map.items():
            f.write(f"{spell},{idx}\n")

def generate_npc_token_map(session, output_filename):
    """
    Generates an numeric index map for each npc in the session. This can
    be used for embedding the npc token in the model.
    """

    npc_map = {}
    for idx, npc in enumerate(session.load_npcs().keys()):
        npc_map[idx] = npc

    with open(output_filename, "w") as f:
        for idx, npc in npc_map.items():
            f.write(f"{npc},{idx}\n")