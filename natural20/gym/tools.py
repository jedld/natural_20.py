import numpy as np
from natural20.entity import Entity
from natural20.player_character import PlayerCharacter
import pdb
# from natural20.actions.look_action import LookAction
# from natural20.actions.stand_action import StandAction

def enemy_stats(battle, current_player, entity_type_mappings):
    """
    Returns the enemy stats for the current player
    """
    for player in battle.entities.keys():
        if battle.entity_group_for(player) != battle.entity_group_for(current_player):
            enemy_hp = player.hp() / player.max_hp()
            enemy_reactions = player.total_reactions(battle)
            enemy_conditions = condition_stats(player, battle)
            return enemy_hp, enemy_reactions, enemy_conditions, map_entity_to_index(player, entity_type_mappings), player.armor_class()
    return 0, 0, np.zeros((8), dtype=np.int64), 0

def condition_stats(entity, battle):
    """
    Returns the condition stats for the entity
    """
    return np.array([int(entity.prone()), int(entity.dodge(battle)), int(entity.grappled()), int(entity.disengage(battle)), 0, 0, 0, 0])

def build_info(battle, available_moves, current_player, weapon_mappings, spell_mappings, entity_mappings):
    return  {
                "available_moves": available_moves,
                "current_index" : battle.current_turn_index,
                "group": battle.entity_group_for(current_player),
                "round" : battle.current_round(),
                "health" : current_player.hp(),
                "max_health" : current_player.max_hp(),
                "weapon_mappings": weapon_mappings,
                "spell_mappings": spell_mappings,
                "entity_mappings": entity_mappings,
                "players" : battle.allies_of(current_player) + [current_player],
                "enemies" : battle.opponents_of(current_player)
            }

def build_observation(battle, map, entity, entity_type_mappings, weapon_type_mappings, view_port_size=(12, 12), is_reaction=False):
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

    # compute current available spell slots
    spell_slots = np.zeros((9), dtype=np.int64)
    for spell_level in range(1, 10):
        spell_slots[spell_level - 1] = entity.spell_slots_count(spell_level)

    obs = {
        "map": render_terrain(battle, map, entity_type_mappings, view_port_size),
        "turn_info": np.array([entity.total_actions(battle), entity.total_bonus_actions(battle), entity.total_reactions(battle)]),
        "conditions": condition_stats(entity, battle),
        "health_pct": np.array([entity.hp() / entity.max_hp()]),
        "player_equipped": np.array(mapped_equipments),
        "health_enemy" : np.array([e_health]),
        "enemy_conditions": e_conditions,
        "enemy_reactions" : np.array([e_reactions]),
        "player_ac" : np.array([entity.armor_class() / 30.0]),
        "enemy_ac" : np.array([e_ac / 30.0]),
        "ability_info": ability_info(entity),
        "player_type": np.array([pc_entity_type]),
        "enemy_type": np.array([enemy_type]),
        "spell_slots" : spell_slots,
        "movement": np.array([battle.current_turn().available_movement(battle)]),
        "is_reaction" : np.array([1 if is_reaction else 0])
    }
    return obs

def map_entity_to_index(entity, entity_type_mappings):
    if isinstance(entity, PlayerCharacter):
        return entity_type_mappings[entity.class_descriptor()]
    else:
        if entity.is_npc():
            return entity_type_mappings.get(entity.npc_type.lower(), 0)

    return entity_type_mappings.get(entity.name.lower())

def ability_info(entity):
    """
    Returns the ability information for the entity
    """
    ability_info = np.zeros((8), dtype=np.int64)

    SECOND_WIND = 0
    ACTION_SURGE = 1

    if hasattr(entity, 'second_wind_count'):
        ability_info[SECOND_WIND] = entity.second_wind_count
    if hasattr(entity, 'action_surge_count'):
        ability_info[ACTION_SURGE] = entity.action_surge_count

    return ability_info

def dndenv_action_to_nat20action(entity, battle, map, available_actions, gym_action, weapon_mappings=None, spell_mappings=None):
    """
    Converts a gym vector action to a Natural20 action by finding the closest match
    in the available actions list.
    
    Args:
        entity: The entity performing the action
        battle: The current battle context
        map: The game map
        available_actions: List of available Natural20 actions
        gym_action: Tuple of (action_type, param1, param2, param3, param4)
        weapon_mappings: Dictionary mapping weapon names to indices
        spell_mappings: Dictionary mapping spell names to indices
   
    Returns:
        The matched Natural20 action or -1 for end turn
    """
    action_type, param1, param2, param3, param4 = gym_action

    if action_type == -1:
        return -1

    if not available_actions:
        return None

    simple_actions = {
        2: "disengage", 3: "dodge", 4: "dash", 5: "dash_bonus", 
        6: "stand", 7: "look", 8: "second_wind", 10: "prone", 
        11: "disengage_bonus", 13: "shove", 14: "help", 15: "hide", 
        16: "use_item", 17: "action_surge"
    }
    
    # Check for simple action matches
    if action_type in simple_actions:
        for action in available_actions:
            if action.action_type == simple_actions[action_type]:
                return action
    
    entity_position = map.position_of(entity)
    
    # Handle complex action types
    for action in available_actions:
        # Attack actions
        if (action.action_type == "attack" and action_type == 0) or (action.action_type == "two_weapon_attack" and action_type == 9):
            if weapon_mappings is not None:
                weapon_match = False

                # Determine weapon token name
                if hasattr(action, 'using') and action.using in weapon_mappings:
                    weapon_match = weapon_mappings[action.using] == param3
                elif getattr(action, 'npc_action', None):
                    token_name = f"{entity.npc_type}_{action.npc_action['name']}".lower()
                    if token_name in weapon_mappings:
                        weapon_match = weapon_mappings[token_name] == param3
                    else:
                        raise ValueError(f"Unknown weapon token {token_name}")

                # Check weapon and attack type match
                # print(f"weapon_match: {weapon_match}, param4: {param4}, ranged_attack: {action.ranged_attack()}")
                if weapon_match and (param4 == 0 or (param4 == 1 and action.ranged_attack())):
                    return action
            elif param3 == 0 or (param4 == 1 and action.ranged_attack()):
                return action

        # Move action
        elif action.action_type == "move" and action_type == 1:
            target_x = entity_position[0] + param1[0]
            target_y = entity_position[1] + param1[1]
            if action.move_path[-1] == [target_x, target_y]:
                return action

        # Spell action
        elif action.action_type == "spell" and action_type == 12:
            if spell_mappings is not None:
                spell_name = action.spell_action.short_name()
                if spell_name in spell_mappings and spell_mappings[spell_name] == param3 and action.at_level == param4:
                    return action
            else:
                return action
    pdb.set_trace()
    # No matching action found
    action_name = simple_actions.get(action_type, f"action type {action_type}")
    raise ValueError(f"No matching {action_name} action found for gym_action {gym_action}")

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

def render_terrain(battle, map, entity_type_mappings, view_port_size=(12, 12)):
    result = []
    current_player = battle.current_turn()
    pos_x, pos_y = map.position_of(current_player)
    view_w, view_h = view_port_size
    map_w, map_h = map.size
    for y in range(-view_w//2, view_w//2):
        col_arr = []
        for x in range(-view_h//2, view_h//2):
            if pos_x + x < 0 or pos_x + x >= map_w or pos_y + y < 0 or pos_y + y >= map_h:
                col_arr.append([0, 0, 0, 0, 0])
            else:
                if not map.can_see_square(current_player,(pos_x + x, pos_y + y)):
                    col_arr.append([255, 255, 255, 255, 255])
                else:
                    terrain = render_object_token(map, pos_x + x, pos_y + y)

                    if terrain is None:
                        terrain_int = 1
                    elif terrain == '~':
                        terrain_int = 3
                    elif terrain == 'o':
                        terrain_int = 4
                    elif terrain == '#':
                        terrain_int = 2
                    elif terrain == '·':
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
                    if entity is not None:
                        entity_type = entity_type_mappings.get(entity.class_descriptor(), 0)
                    else:
                        entity_type = 0
                    col_arr.append([entity_type, terrain_int, entity_int, health_pct, status_int])
        
        result.append(col_arr)
    return np.array(result)

def action_to_gym_action(entity, map, available_actions, weapon_mappings=None, spell_mappings=None):
    entity_pos = map.position_of(entity)
    valid_actions = []
    for action in available_actions:
        if action.action_type == "attack" or action.action_type == "two_weapon_attack":
            target = map.position_of(action.target)
            relative_pos = (target[0] - entity_pos[0], target[1] - entity_pos[1])
            attack_type = 0
            attack_sub_type = 1 if action.ranged_attack() else 0

            if weapon_mappings is not None:
                if action.using and weapon_mappings.get(action.using) is not None:
                    attack_type = weapon_mappings[action.using]
                elif getattr(action, 'npc_action', None):
                    token_name = f"{entity.npc_type}_{action.npc_action['name']}".lower()
                    if token_name in weapon_mappings:
                        attack_type = weapon_mappings[token_name]
                    else:
                        raise ValueError(f"Unknown weapon token {token_name}")
                else:
                    raise ValueError(f"Unknown weapon token {action.using}")
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
        # elif action.action_type == 'shove':
        #     target = map.position_of(action.target)
        #     relative_pos = (target[0] - entity_pos[0], target[1] - entity_pos[1])
        #     valid_actions.append((13, (0, 0), (relative_pos[0], relative_pos[1]), 0, 0))
        elif action.action_type == 'help':
            valid_actions.append((14, (-1, -1),(0, 0), 0, 0))
        elif action.action_type == 'hide':
            valid_actions.append((15, (-1, -1),(0, 0), 0, 0))
        elif action.action_type == 'use_item':
            valid_actions.append((16, (-1, -1),(0, 0), 0, 0))
        elif action.action_type == 'action_surge':
            valid_actions.append((17, (-1, -1),(0, 0), 0, 0))


    valid_actions.append((-1, (0, 0), (0, 0), 0, 0)) # end turn should always be available
    for action in valid_actions:
        assert len(action) == 5, f"Invalid action {action}"
    return valid_actions

def compute_available_moves(session, map, entity: Entity, battle, weapon_mappings=None, spell_mappings=None):
    available_actions = entity.available_actions(session, battle)
    return action_to_gym_action(entity, map, available_actions, weapon_mappings=weapon_mappings, spell_mappings=spell_mappings)

def generate_entity_token_map(session, output_filename = 'entity_token_map.csv'):
    """
    Generates an numeric index map for each entity in the session. This can
    be used for embedding the entity token in the model.
    """

    entity_map = {}
    # load characters
    for idx, pc in enumerate(session.load_characters()):
        entity_map[idx + 1] = pc.class_descriptor()

    # load npcs
    for idx, npc in enumerate(session.load_npcs()):
        entity_map[idx + len(session.load_characters()) + 1] = npc.properties['kind'].lower()

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

    # load all npcs and their actions
    start_index = len(session.load_weapons()) + len(session.load_all_equipments()) + 1
    for npc in session.load_npcs():
        npc_kind = npc.properties['kind'].lower()
        for action in npc.properties['actions']:
            weapon_map[start_index] = f"{npc_kind}_{action['name'].lower()}"
            start_index += 1

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
        spell_map[idx + 1] = spell

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
        npc_map[idx+1] = npc

    with open(output_filename, "w") as f:
        for idx, npc in npc_map.items():
            f.write(f"{npc},{idx+1}\n")