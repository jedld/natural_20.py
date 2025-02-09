import pdb

def compute_max_weapon_range(session, action, range=None):
    if isinstance(action, dict):
        return action.get('max_range', action.get('range'))

    if action.action_type == 'grapple':
        return 5
    elif action.action_type == 'help':
        return 5
    elif action.action_type in ['attack', 'two_weapon_attack']:
        if action.npc_action:
            return action.npc_action.get('range_max') or action.npc_action.get('range')
        elif action.using:
            weapon = session.load_weapon(action.using)
            if action.thrown:
                return weapon.get('thrown', {}).get('range_max') or weapon.get('thrown', {}).get('range') or weapon.get('range')
            else:
                return weapon.get('range_max') or weapon.get('range')
    elif action.action_type == 'spell':
        spell = action.spell_action.properties
        return spell.get('range')

    return range

def damage_modifier(entity, weapon, second_hand=False):
    damage_mod = entity.attack_ability_mod(weapon)

    if second_hand and not entity.class_feature('two_weapon_fighting'):
        damage_mod = min(damage_mod, 0)

    # compute damage roll using versatile weapon property
    if 'versatile' in weapon.get('properties', []) and entity.used_hand_slots() <= 1.0:
        damage_roll = weapon.get('damage_2')
    else:
        damage_roll = weapon.get('damage')

    # duelist class feature
    if entity.class_feature('dueling') and weapon.get('type') == 'melee_attack' and entity.used_hand_slots(weapon_only=True) <= 1.0:
        damage_mod += 2

    return f"{damage_roll}{f'+{damage_mod}' if damage_mod >= 0 else damage_mod}"


def target_advantage_condition(battle, source, target, weapon, source_pos=None, overrides=None, thrown=False):
    if overrides is None:
        overrides = {}
    if target is None:
        raise ValueError("target is mandatory")
    if battle is None:
        return [0, [[],[]]]
    advantages, disadvantages = compute_advantages_and_disadvantages(battle, source, target, weapon,
                                                                     source_pos=source_pos, overrides=overrides, thrown=thrown)
    advantage_ctr = 0
    advantage_ctr += 1 if advantages else 0
    advantage_ctr -= 1 if disadvantages else 0
    return [advantage_ctr, [advantages, disadvantages]]

def compute_advantages_and_disadvantages(battle, source, target, weapon, source_pos=None, overrides=None, thrown=False):
    if target is None:
        raise ValueError("target is mandatory")
    if overrides is None:
        overrides = {}
    weapon = battle.session.load_weapon(weapon) if isinstance(weapon, str) or isinstance(weapon, str) else weapon
    advantage = overrides.get('advantage', [])
    disadvantage = overrides.get('disadvantage', [])

    if source.has_effect('attack_advantage_modifier'):
        advantage_mod, disadvantage_mod = source.eval_effect('attack_advantage_modifier', { "target" : target })
        advantage += advantage_mod
        disadvantage += disadvantage_mod

    if target.has_effect('targeted_advantage_override'):
        advantage_mod, disadvantage_mod = target.eval_effect('targeted_advantage_override', { "source" : source })
        advantage += advantage_mod
        disadvantage += disadvantage_mod

    if source.prone():
        disadvantage.append('prone')
    if source.squeezed():
        disadvantage.append('squeezed')
    if target.dodge(battle):
        disadvantage.append('target_dodge')
    if not source.proficient_with_equipped_armor():
        disadvantage.append('armor_proficiency')
    if target.squeezed():
        advantage.append('squeezed')
    if battle and battle.help_with(target):
        advantage.append('being_helped')

    if weapon and (thrown or weapon['type'] == 'ranged_attack'):
        if battle.enemy_in_melee_range(source, source_pos=source_pos):
            disadvantage.append('ranged_with_enemy_in_melee')
        if target.prone():
            disadvantage.append('target_is_prone_range')
        if weapon['range'] and battle.map_for(source).distance(source, target, entity_1_pos=source_pos) > weapon['range']:
            disadvantage.append('target_long_range')

    if source.class_feature('pack_tactics') and battle.ally_within_enemy_melee_range(source, target, source_pos=source_pos):
        advantage.append('pack_tactics')

    if weapon and 'heavy' in weapon.get('properties', []) and source.size == 'small':
        disadvantage.append('small_creature_using_heavy')

    if weapon and (not thrown and weapon['type'] == 'melee_attack') and target.prone():
        advantage.append('target_is_prone')

    if battle and not battle.can_see(target, source, entity_2_pos=source_pos):
        advantage.append('unseen_attacker')

    if battle and not battle.can_see(source, target, entity_1_pos=source_pos):
        disadvantage.append('invisible_attacker')

    return [advantage, disadvantage]
