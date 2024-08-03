from natural20.action import Action
from natural20.actions.spell_action import SpellAction
import itertools
import pdb

# build list of lists of possible parameters
def build_params(session, entity, battle, build_info) -> list:
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
            spell_range = param.get("range", 0)
            possible_targets = set()

                # check target type
            if 'enemies' in param["target_types"]:
                    # get all enemies
                targets = battle.opponents_of(entity)
                if spell_range > 0 and battle.map:
                    for t in targets:
                        if battle.distance(entity, t) <= spell_range:
                            possible_targets.add(t)
            elif 'allies' in param["target_types"]:
                    # get all allies
                targets = battle.allies_of(entity)
                if spell_range > 0 and battle.map:
                    for t in targets:
                        if battle.map.distance(entity, t) <= spell_range:
                            possible_targets.add(t)
            elif 'self' in param["target_types"]:
                possible_targets.add(entity)

            if len(possible_targets) == 0:
                return None

            # get all possible combination of possible 1 to num_targets targets
            for i in range(1, param.get("num", 1) + 1):
                if not param.get("allow_retarget", False):
                    for target_combination in itertools.combinations(possible_targets, i):
                        selected_target_combinations.append(target_combination)
                else:
                    for target_combination in itertools.combinations_with_replacement(possible_targets, i):
                        selected_target_combinations.append(target_combination)

            params.append(selected_target_combinations)
        else:
            raise ValueError(f"Unknown param type {param['type']}")

    return params


def autobuild(session, action_class, entity, battle):
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

            possible_params = build_params(session, entity, battle, current_build_info)

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
