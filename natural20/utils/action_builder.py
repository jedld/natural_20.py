from natural20.action import Action
from natural20.actions.spell_action import SpellAction
import itertools
from natural20.utils.movement import compute_actual_moves
import pdb

def acquire_targets(param, entity, battle, map=None):
    spell_range = param.get("range", 0)
    possible_targets = set()

        # check target type
    if 'enemies' in param["target_types"]:
            # get all enemies
        targets = battle.opponents_of(entity)
        if spell_range > 0 and battle.map:
            for t in targets:
                if battle.map.can_see(entity, t) and battle.map.distance(entity, t) <= spell_range:
                    possible_targets.add(t)
    elif 'allies' in param["target_types"]:
            # get all allies
        if battle:
            targets = battle.allies_of(entity)
            if map is None:
                map = battle.map
        else:
            targets = map.entities.keys()
        if spell_range > 0 and map:
            for t in targets:
                if map.can_see(entity, t) and map.distance(entity, t) <= spell_range:
                    possible_targets.add(t)
    elif 'self' in param["target_types"]:
        possible_targets.add(entity)

    return possible_targets

# build list of lists of possible parameters
def build_params(session, entity, battle, build_info, map=None) -> list:
    params = []
    for param in build_info["param"]:
        if param["type"] == "select_spell":
            possible_spells = []

            for spell_name in entity.available_spells(battle):
                    # get spell available levels
                if SpellAction.can_cast(entity, battle, spell_name):
                    spell_info = session.load_spell(spell_name)
                    possible_spells.append((spell_name, spell_info['level']))
                else:
                    build_info = None
                    break
            params.append(possible_spells)
        elif param["type"] == "select_target":
            selected_target_combinations = []

            possible_targets = acquire_targets(param, entity, battle, map)

            if len(possible_targets) == 0:
                return None

            # get all possible combination of possible 1 to num_targets targets
            total_targets = param.get("num", 1)
            min_targets = param.get("min", total_targets)
            max_targets = param.get("max", total_targets)
            for i in range(min_targets, max_targets + 1):
                target_combinations = itertools.combinations_with_replacement(possible_targets, i) if param.get("allow_retarget", False) else itertools.combinations(possible_targets, i)
                for target_combination in target_combinations:
                    selected_target_combinations.append(target_combination[0] if total_targets == 1 else target_combination)
            params.append(selected_target_combinations)
        elif param["type"] == "movement":
            if map is None and battle:
                map = battle.map
            if map is None:
                return None
            cur_x, cur_y = map.position_of(entity)
            selected_movement_combinations = []
            for x_pos in range(-1, 2):
                for y_pos in range(-1, 2):
                    if x_pos == 0 and y_pos == 0:
                        continue
                    if map.passable(entity, cur_x + x_pos, cur_y + y_pos, battle, allow_squeeze=False) and \
                        map.placeable(entity, cur_x + x_pos, cur_y + y_pos, battle, squeeze=False):
                        chosen_path = [[cur_x, cur_y], [cur_x + x_pos, cur_y + y_pos]]
                        shortest_path = compute_actual_moves(entity, chosen_path, map, battle, entity.available_movement(battle) // 5).movement
                        if len(shortest_path) > 1:
                            selected_movement_combinations.append([shortest_path, []])
            params.append(selected_movement_combinations)
        else:
            raise ValueError(f"Unknown param type {param['type']}")

    return params


def autobuild(session, action_class, entity, battle, map=None, auto_target=True):
    def param_permutator(num_choices_per_param, param_index, current_params):
        if param_index == len(num_choices_per_param):
            return [current_params]
        else:
            all_permutations = []
            for choice in range(num_choices_per_param[param_index]):
                all_permutations += param_permutator(num_choices_per_param, param_index + 1, current_params + [choice])
            return all_permutations

    build_info = action_class.build(session, entity)
    previous_act = []
    next_act = [build_info]

    while any(isinstance(next_act[i], dict) for i in range(len(next_act))):
        previous_act = next_act
        next_act = []

        for current_build_info in previous_act:
            if isinstance(current_build_info, Action) or current_build_info is None:
                next_act.append(current_build_info)
                continue

            possible_params = build_params(session, entity, battle, current_build_info, map=map)

            if possible_params is None:
                next_act.append(None)
                continue

            num_choices_per_param = [len(p) for p in possible_params]
            permutate_params = param_permutator(num_choices_per_param, 0, [])

            for params in permutate_params:
                selected_params = []
                for i, p in enumerate(params):
                    selected_params.append(possible_params[i][p])
                build_info = current_build_info['next'](*selected_params)
                next_act.append(build_info)

    # remove any None values
    next_act = [act for act in next_act if act is not None]

    return next_act
