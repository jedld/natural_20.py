from natural20.weapons import target_advantage_condition
from natural20.utils.attack_util import after_attack_roll_hook
from natural20.utils.ac_utils import effective_ac

def evaluate_spell_attack(battle, entity, target, spell_properties, opts=None):
    if opts is None:
        opts = {}
    # DnD 5e advantage/disadvantage checks
    advantage_mod, adv_info = target_advantage_condition(battle, entity, target, spell_properties, overrides=opts)

    attack_roll = entity.ranged_spell_attack(battle, spell_properties['name'], advantage=advantage_mod > 0,
                                                                                   disadvantage=advantage_mod < 0)

    target_ac, _cover_ac = effective_ac(battle, entity, target)

    entity.resolve_trigger('attack_resolved', { "target" : target})

    force_miss = after_attack_roll_hook(battle, target,
                                        entity, attack_roll, target_ac, { "spell" : spell_properties})
    if not force_miss:
        cover_ac_adjustments = 0
        hit = True if attack_roll.nat_20() else False if attack_roll.nat_1() else attack_roll.result() >= target_ac
    else:
        hit = False

    return [hit, attack_roll, advantage_mod, cover_ac_adjustments, adv_info]
