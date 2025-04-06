from itertools import combinations, combinations_with_replacement, product
from natural20.action import Action
from natural20.actions.spell_action import SpellAction
from natural20.utils.movement import compute_actual_moves
import pdb


def acquire_targets(param, entity, battle, map=None):
    """
    Acquire all possible targets based on the target_types in `param`,
    filtering by line-of-sight and range if applicable.
    """
    if battle and map is None:
        map = battle.map_for(entity)

    spell_range = param.get("range", 0)
    possible_targets = set()

    # Helper function to filter by range & visibility if we have a valid map.
    def in_range_and_visible(targets):
        if not map or spell_range <= 0:
            return set(targets)
        return {
            t
            for t in targets
            if map.can_see(entity, t) and t.allow_targeting() and map.distance(entity, t) <= spell_range
        }

    target_types = param.get("target_types", ['enemies'])

    # Handle multiple target types in a single param (if needed).
    # If your logic only ever expects one target type per param, 
    # just switch these to if/elif/else blocks accordingly.
    if "enemies" in target_types:
        enemies = battle.opponents_of(entity) if battle else []
        possible_targets |= in_range_and_visible(enemies)

    if "allies" in target_types:
        if battle:
            allies = battle.allies_of(entity)
        else:
            # If no battle is present, but a map is provided:
            allies = map.entities.keys() if map else []
        possible_targets |= in_range_and_visible(allies)

    if "self" in target_types:
        possible_targets.add(entity)

    return possible_targets


def build_params(session, entity, battle, build_info, map=None, auto_target=True, match=None, is_verbose=False):
    """
    Build a list (parallel to build_info["param"]) containing all possible
    parameter choices for each param in build_info["param"].
    """
    if battle and map is None:
        map = battle.map_for(entity)

    params_list = []

    for param in build_info["param"]:
        param_type = param["type"]

        # -----------------------------
        # 1) SELECT SPELL
        # -----------------------------
        if param_type == "select_spell":
            possible_spells = []
            for spell_name in entity.available_spells(battle):
                # Check if the entity can cast the spell
                if SpellAction.can_cast(entity, battle, spell_name):
                    spell_info = session.load_spell(spell_name)
                    possible_spells.append((spell_name, spell_info["level"]))
                else:
                    # If any spell is not castable, 
                    # original code breaks and sets build_info to None
                    return None
            if match:
                possible_spells = [spell for spell in possible_spells if spell[0] in match]
            params_list.append(possible_spells)

        # -----------------------------
        # 2) SELECT ITEM
        # -----------------------------
        elif param_type == "select_item":
            usable_items = [item["name"] for item in entity.usable_items()]
            params_list.append(usable_items)

        # -----------------------------
        # 3) SELECT TARGET
        # -----------------------------
        elif param_type == "select_target":
            possible_targets = acquire_targets(param, entity, battle, map)
            if not possible_targets:
                # No valid targets => entire build fails
                if is_verbose:
                    print("Unable to select target, no possible targets.")
                return None

            if match:
                possible_targets = [target for target in possible_targets if target in match]

            if is_verbose and len(possible_targets) == 0:
                print(f"Unable to select target, possible targets: {possible_targets}")

            selected_target_combinations = []
            total_targets = param.get("num", 1)
            min_targets = param.get("min", total_targets)
            max_targets = param.get("max", total_targets)
            allow_retarget = param.get("allow_retarget", False)

            combo_func = (
                combinations_with_replacement if allow_retarget else combinations
            )

            # Generate all combinations of targets from min to max count
            for n in range(min_targets, max_targets + 1):
                for combo in combo_func(possible_targets, n):
                    # If only 1 target, flatten the tuple
                    if total_targets == 1:
                        selected_target_combinations.append(combo[0])
                    else:
                        selected_target_combinations.append(combo)

            params_list.append(selected_target_combinations)

        # -----------------------------
        # 4) MOVEMENT
        # -----------------------------
        elif param_type == "movement":
            if not map:
                # Cannot determine movement without a map
                return None

            cur_x, cur_y = map.position_of(entity)
            selected_movement_options = []

            # Check all 8 directions (3x3 grid minus the center)
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    if dx == 0 and dy == 0:
                        continue

                    new_x = cur_x + dx
                    new_y = cur_y + dy
                    if (map.bidirectionally_passable(entity, new_x, new_y, (cur_x, cur_y), battle, allow_squeeze=False)
                            and map.placeable(entity, new_x, new_y, battle, squeeze=False)):
                        
                        if match and [new_x, new_y] not in match:
                            continue

                        chosen_path = [[cur_x, cur_y], [new_x, new_y]]
                        max_moves = entity.available_movement(battle) // 5
                        
                        movement_result = compute_actual_moves(
                            entity, chosen_path, map, battle, max_moves
                        )

                        # We only add this option if movement is actually possible
                        shortest_path = movement_result.movement
                        if len(shortest_path) > 1:
                            # The second element ([]) might be for additional param data
                            selected_movement_options.append([shortest_path, []])

            params_list.append(selected_movement_options)

        # -----------------------------
        # 5) SELECT OBJECT
        # -----------------------------
        elif param_type == "select_object":
            possible_objects = []
            if map:
                nearby_objects = map.objects_near(entity)
                possible_objects = [obj for obj in nearby_objects if obj.interactable(entity)]

                if match:
                    possible_objects = [obj for obj in possible_objects if obj in match]
                    if is_verbose and not possible_objects:
                        print(f"No interactable objects matching {match} found nearby.")

                params_list.append(possible_objects)
            else:
                if is_verbose:
                    print("No map found for object selection.")
                return None

        # -----------------------------
        # 6) INTERACT
        # -----------------------------
        elif param_type == "interact":
            object = param["target"]
            interaction_actions = object.available_interactions(entity, battle, admin = entity.is_admin)
            _interaction_actions = []
            for k, v in interaction_actions.items():
                _interaction_actions.append([k, v])

            if match:
                _interaction_actions = [ action for action in _interaction_actions if action[0] in match]

            params_list.append(_interaction_actions)
        elif param_type == "select_weapon":
            if hasattr(entity, 'attack_options'):
                _usable_weapons = entity.attack_options(battle)
                if match:
                    usable_weapons = [ weapon for weapon in _usable_weapons if weapon['name'].lower() in match]
                else:
                    usable_weapons = _usable_weapons
            else:
                _usable_weapons = entity.equipped_weapons(session)
                if match:
                    usable_weapons = [weapon for weapon in _usable_weapons if weapon in match]
                else:
                    usable_weapons = _usable_weapons

            if is_verbose and not usable_weapons:
                print(f"Unable to select weapons {_usable_weapons}")

            params_list.append(usable_weapons)
        elif param_type == "select_choice":
            for choice in param["choices"]:
                if match and choice not in match:
                    continue
                params_list.append([choice])
        elif param_type == "select_items":
            return None
        elif param_type == 'select_empty_space':
            # select adjacent empty space
            if not map:
                if is_verbose:
                    print(f"No map found for {entity.name}")
                return None
            cur_x, cur_y = map.position_of(entity)
            selected_movement_options = []

            # Check all 8 directions (3x3 grid minus the center)
            position_choices = []
            _range = param.get("range", 5) // 5

            for dx in range(-_range, _range + 1):
                for dy in range(-_range, _range + 1):
                    if dx == 0 and dy == 0:
                        continue

                    new_x = cur_x + dx
                    new_y = cur_y + dy
                    if (map.passable(entity, new_x, new_y, battle, allow_squeeze=False)
                        and map.can_see_square(entity, (new_x, new_y))
                            and map.placeable(entity, new_x, new_y, battle, squeeze=False)):
                        if match and [new_x, new_y] not in match:
                            continue

                        position_choices.append([new_x, new_y])
            params_list.append(position_choices)
            if len(position_choices)==0:
                if is_verbose:
                    print(f"No valid empty space found for {entity.name} from {params_list}")
                return None
        else:
            raise ValueError(f"Unknown param type: {param_type}")

    return params_list


def autobuild(session, action_class, entity, battle, map=None, auto_target=True, match=None, **opts):
    """
    Orchestrates the building of possible actions by repeatedly calling
    `build_info['next'](...)` with all combinations of parameters
    until the next step is an Action or None.
    """
    # Build the initial set of parameters from the action class
    build_info = action_class.build(session, entity)
    previous_builds = [build_info]
    next_builds = []
    is_verbose = opts.get("verbose", False)
    if map is None and battle:
        map = battle.map_for(entity)

    while any(isinstance(item, dict) for item in previous_builds):
        next_builds.clear()

        for current_info in previous_builds:
            # If it's already an Action or None, just carry it forward
            if isinstance(current_info, Action) or current_info is None:
                next_builds.append(current_info)
                continue

            # Build a list of possible parameter options
            possible_params = build_params(session, entity, battle, current_info, map=map, auto_target=auto_target, match=match, is_verbose=is_verbose)

            if possible_params is None:
                if is_verbose:
                    print(f"Failed to build parameters for {current_info}")
                # If we can't build any parameters, we append None
                # to represent a failed/invalid build path
                next_builds.append(None)
                continue

            # For each combination of parameter choices, call `current_info['next']`
            # Instead of a custom permutator, use itertools.product
            for choice_combo in product(*possible_params):
                result = current_info["next"](*choice_combo)
                next_builds.append(result)

        # Prepare for the next iteration
        previous_builds = next_builds[:]

    # Remove any None values which represent invalid/failed builds
    final_actions = [act for act in previous_builds if act is not None]
    return final_actions
