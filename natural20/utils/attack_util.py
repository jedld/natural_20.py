from natural20.action import Action
from natural20.die_roll import Rollable
import pdb

def to_advantage_str(item):
    if 'adv_info' not in item or item['adv_info'] is None:
        return ''
    advantage_info, disadvantage_info = item['adv_info']
    advantage_str = f' with advantage{advantage_info}' if item['advantage_mod'] > 0 else f' with disadvantage{disadvantage_info}' if item['advantage_mod'] < 0 else ''
    return advantage_str

def damage_event(item, battle):
    if battle:
        session = battle.session
    else:
        session = item['source'].session

    target = item['target']
    dmg = item['damage'].result() if isinstance(item['damage'], Rollable) else item['damage']
    dmg += item['sneak_attack'].result() if item.get('sneak_attack') is not None else 0


    if target.resistant_to(item['damage_type']):
        total_damage = int(dmg // 2)
    elif target.vulnerable_to(item['damage_type']):
        total_damage = dmg * 2
    else:
        total_damage = dmg

    session.event_manager.received_event({
        'source': item['source'],
        'attack_roll': item.get('attack_roll', None),
        'target': item['target'],
        'event': 'attacked',
        'attack_name': item['attack_name'],
        'damage_type': item['damage_type'],
        'advantage_mod': item.get('advantage_mod', None),
        'as_reaction': item.get('as_reaction', False),
        'damage_roll': item['damage'],
        'sneak_attack': item.get('sneak_attack',False),
        'adv_info': item.get('adv_info', None),
        'thrown': item.get('thrown', False),
        'spell_save': item.get('spell_save', None),
        'dc': item.get('dc', None),
        'resistant': target.resistant_to(item['damage_type']),
        'vulnerable': target.vulnerable_to(item['damage_type']),
        'value': dmg,
        'total_damage': total_damage
    })

    critical = item['attack_roll'].nat_20() if item.get('attack_roll') else False

    item['target'].take_damage(total_damage, battle=battle, critical=critical, roll_info=item['damage'], sneak_attack=item.get('sneak_attack', False))

    if battle and total_damage > 0:
        item['target'].on_take_damage(battle, item)

def after_attack_roll_hook(battle, target, source, attack_roll, effective_ac, opts=None):
    if opts is None:
        opts = {}
    force_miss = False

    # check prepared spells of target for a possible reaction
    events = []

    if attack_roll:
        target.resolve_trigger('after_attack_roll_target', { 'attack_roll': attack_roll } )
    if not isinstance(target, list) and not isinstance(target, tuple):
        targets = [target]
    else:
        targets = target

    for target in targets:
        for spell in target.prepared_spells():
            spell_details = battle.session.load_spell(spell)
            qty, resource = spell_details['casting_time'].split(':')

            if target.has_reaction(battle) and resource == 'reaction':
                spell_name = spell_details['spell_class'].replace("Natural20::", "")

                if spell_name == 'Shield':
                    from natural20.spell.shield_spell import ShieldSpell
                    spell_class = ShieldSpell
                else:
                    raise Exception(f"spell class (reaction) not found {spell_name}")
                if hasattr(spell_class, 'after_attack_roll'):
                    result, force_miss_result = spell_class.after_attack_roll(battle, target, source, attack_roll,
                                                                            effective_ac, opts)
                    force_miss = True if force_miss_result == 'force_miss' else force_miss
                    events.append(result)

        events = [item for sublist in events for item in sublist]

        for item in events:
            for klass in Action.__subclasses__():
                if not isinstance(item, dict):
                    raise Exception(f"item is not a dict: {item}")
                klass.apply(battle, item, session=None)

    return force_miss
