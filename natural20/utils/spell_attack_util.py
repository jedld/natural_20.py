from natural20.weapons import target_advantage_condition
from natural20.utils.attack_util import after_attack_roll_hook
from natural20.utils.ac_utils import effective_ac
from natural20.die_roll import DieRoll

def evaluate_spell_attack(battle, entity, target, spell_properties, opts=None):
    if opts is None:
        opts = {}
    # DnD 5e advantage/disadvantage checks
    advantage_mod, adv_info = target_advantage_condition(battle, entity, target, spell_properties, overrides=opts)

    action = opts.get('action', None)

    if action and hasattr(action, 'attack_roll'):
        attack_roll = action.attack_roll
    else:
        attack_roll = None

    if attack_roll is None:
        if spell_properties.get('type') == 'melee_attack':
            if entity.familiar():
                attack_roll = entity.owner.melee_spell_attack(battle, spell_properties, advantage=advantage_mod > 0,
                                                disadvantage=advantage_mod < 0)
            else:
                attack_roll = entity.melee_spell_attack(battle, spell_properties, advantage=advantage_mod > 0,
                                                disadvantage=advantage_mod < 0)
        else:
            attack_roll = entity.ranged_spell_attack(battle, spell_properties, advantage=advantage_mod > 0,
                                                                                    disadvantage=advantage_mod < 0)

        if entity.has_effect('bless'):
            bless_roll = DieRoll.roll("1d4", description='dice_roll.bless', entity=entity, battle=battle)
            attack_roll += bless_roll
        
        if action:
            action.attack_roll = attack_roll

    target_ac, _cover_ac = effective_ac(battle, entity, target)

    entity.resolve_trigger('attack_resolved', { "target" : target})

    force_miss, events = after_attack_roll_hook(battle, target,
                                        entity, attack_roll, target_ac, { "spell" : spell_properties})
    if not force_miss:
        cover_ac_adjustments = 0
        hit = True if attack_roll.nat_20() else False if attack_roll.nat_1() else attack_roll.result() >= target_ac
    else:
        cover_ac_adjustments = None
        hit = False

    return [hit, attack_roll, advantage_mod, cover_ac_adjustments, adv_info, events]
