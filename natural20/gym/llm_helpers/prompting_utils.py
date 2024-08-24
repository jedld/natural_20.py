from natural20.gym.dndenv import action_type_to_int

def _look_up_attack_name(weapon_id, weapon_mappings=None):
    # swap the values and keys
    weapon_mappings = {v: k for k, v in weapon_mappings.items()}
    if weapon_mappings and weapon_id in weapon_mappings:
        return weapon_mappings.get(weapon_id, "")
    else:
        return ""

def _lookup_spell_name(spell_id, spell_mappings=None):
    # swap the values and keys
    spell_mappings = {v: k for k, v in spell_mappings.items()}
    if spell_mappings and spell_id in spell_mappings:
        return spell_mappings.get(spell_id, "")
    else:
        return ""

def action_to_prompt(action, weapon_mappings=None, spell_mappings=None):
    if weapon_mappings is None:
        raise ValueError("weapon_mappings is None")
    if spell_mappings is None:
        raise ValueError("spell_mappings is None")
    action_type, param1, param2, param3, param4 = action
    if action_type == action_type_to_int("move"):
        message = "move 5ft "
        x, y = param1
        if (x < 0 and y==0):
            message += "to the left"
        elif (x > 0 and y==0):
            message += "to the right"
        elif (x == 0 and y < 0):
            message += "up"
        elif (x == 0 and y > 0):
            message += "down"
        elif (x < 0 and y < 0):
            message += "up and to the left"
        elif (x < 0 and y > 0):
            message += "down and to the left"
        elif (x > 0 and y < 0):
            message += "up and to the right"
        elif (x > 0 and y > 0):
            message += "down and to the right"

    elif action_type == action_type_to_int("attack"):
        attack_name = _look_up_attack_name(param3, weapon_mappings)
        message = "attack enemy "
        if param4 == 1:
            message += f"with ranged weapon: {attack_name}"
        else:
            message += f"with melee weapon: {attack_name}"
    elif action_type == action_type_to_int("dash"):
        message = "dash action"
    elif action_type == action_type_to_int("disengage"):
        message = "disengage action"
    elif action_type == action_type_to_int("dodge"):
        message = "dodge action"
    elif action_type == action_type_to_int("help"):
        message = "help action"
    elif action_type == action_type_to_int("hide"):
        message = "hide action"
    elif action_type == action_type_to_int("stand"):
        message = "stand action"
    elif action_type == action_type_to_int("second_wind"):
        message = "second wind action"
    elif action_type == action_type_to_int("two_weapon_attack"):
        message = "two weapon attack bonus action"
    elif action_type == action_type_to_int("prone"):
        message = "go prone"
    elif action_type == action_type_to_int("disengage_bonus"):
        message = "disengage as bonus action action"
    elif action_type == action_type_to_int("spell"):
        message = "cast the "
        attack_name = _lookup_spell_name(param3, spell_mappings)
        message += f" {attack_name} spell"
    elif action_type == action_type_to_int("shove"):
        message = "shove action"
    elif action_type == action_type_to_int("action_surge"):
        message = "action surge"
    elif action_type == -1:
        message = "end my turn"
    else:
        message = f"unknown action {action_type}"
        raise ValueError(f"Unknown action type {action_type}")
    return message

def actions_to_prompt(actions, weapon_mappings=None, spell_mappings=None):
    prompt = "\n\nHere are the available actions you can take, please choose the number corresponding to the action:\n"
    prompt += "0: end my turn\n"
    for index, action in enumerate(actions):
        message = action_to_prompt(action, weapon_mappings, spell_mappings)
        prompt += f"{index + 1}: {message}\n"
    return prompt