from natural20.action import Action
from natural20.actions.spell_action import SpellAction

def autobuild(session, action_class, entity, battle):
    build_info = action_class.build(session, entity)
    while build_info:
        params = None
        for param in build_info["param"]:
            if param["type"] == "select_spell":
                for spell_name in entity.available_spells(battle):
                    # get spell available levels
                    if SpellAction.can_cast(entity, battle, spell_name):
                        spell_info = session.load_spell(spell_name)
                        params.append((spell_name, spell_info['level']))
                    else:
                        build_info = None
                        break
            elif param["type"] == "select_target":
                selected_targets = []
                spell_range = param.get("range", 0)

                for _ in range(param["num"]):
                    # check target type
                    if 'enemies' in param["target_types"]:
                    # get all enemies
                    targets = battle.opponents_of(entity)
                    if spell_range > 0 and battle.map:
                        targets = [t for t in targets if battle.distance(entity, t) <= spell_range]
                    elif 'allies' in param["target_types"]:
                    # get all allies
                    targets = battle.allies_of(entity)
                    if spell_range > 0 and battle.map:
                        targets = [t for t in targets if battle.map.distance(entity, t) <= spell_range]
                    elif 'self' in param["target_types"]:
                    targets = [entity]

                    # select the first target for now
                    if len(targets) > 0:
                    selected_targets.append(targets[0])

                if len(selected_targets) > 0:
                    params.append(selected_targets)
                else:
                    # no targets available, skip this action
                    build_info = None
                    break
                else:
                raise ValueError(f"Unknown param type {param['type']}")
                if build_info["param"] is not None:
                    build_info = build_info["next"](*params)
                else:
                    build_info = build_info["next"]()

                if isinstance(build_info, SpellAction):
                    action_list.append(build_info)
                    break
                else:
                break
