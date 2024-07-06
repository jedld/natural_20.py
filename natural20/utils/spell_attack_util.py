from natural20.weapons import target_advantage_condition
from natural20.utils.attack_util import effective_ac, after_attack_roll_hook

def evaluate_spell_attack(battle, entity, target, spell_properties, opts={}):
    # DnD 5e advantage/disadvantage checks
    advantage_mod, _adv_info = target_advantage_condition(battle, entity, target, spell_properties, overrides=opts)

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

    return [hit, attack_roll, advantage_mod, cover_ac_adjustments]


def consume_resource(battle, item):
    amt, resource = item["spell"]["casting_time"].split(":")
    spell_level = item["spell"]["level"]

    if resource == "action":
        battle.consume(item["source"], "action")
    elif resource == "reaction":
        battle.consume(item["source"], "reaction")

    item["source"].consume_spell_slot(spell_level) if spell_level > 0 else None
