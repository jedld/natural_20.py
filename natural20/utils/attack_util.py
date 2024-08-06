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
    target = item['target']
    dmg = item['damage'].result() if isinstance(item['damage'], Rollable) else item['damage']
    dmg += item['sneak_attack'].result() if item.get('sneak_attack') is not None else 0

    if dmg is None:
        pdb.set_trace()    
    if target.resistant_to(item['damage_type']):
        total_damage = int(dmg / 2)
    elif target.vulnerable_to(item['damage_type']):
        total_damage = dmg * 2
    else:
        total_damage = dmg
    
    battle.event_manager.received_event({
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
        'resistant': target.resistant_to(item['damage_type']),
        'vulnerable': target.vulnerable_to(item['damage_type']),
        'value': dmg,
        'total_damage': total_damage
    })
   
    critical = item['attack_roll'].nat_20() if item.get('attack_roll') else False
    item['target'].take_damage(total_damage, battle=battle, critical=critical)

    if battle and total_damage > 0:
        item['target'].on_take_damage(battle, item)

def after_attack_roll_hook(battle, target, source, attack_roll, effective_ac, opts=None):
    if opts is None:
        opts = {}
    force_miss = False

    # check prepared spells of target for a possible reaction
    events = []
    for spell in target.prepared_spells():
        spell_details = battle.session.load_spell(spell)
        qty, resource = spell_details['casting_time'].split(':')
        if target.has_reaction(battle) and resource == 'reaction':
            spell_name = spell_details['spell_class'].replace("Natural20::", "")
            #TODO: Fix reactions
            # spell_class = globals()[f"{spell_name}Spell"]
            # if hasattr(spell_class, 'after_attack_roll'):
            #     result, force_miss_result = spell_class.after_attack_roll(battle, target, source, attack_roll,
            #                                                               effective_ac, opts)
            #     force_miss = True if force_miss_result == 'force_miss' else force_miss
            #     events.append(result)

    events = [item for sublist in events for item in sublist]

    for item in events:
        for klass in Action.__subclasses__():
            klass.apply(battle, item)

    return force_miss


def effective_ac(battle, source, target):
    cover_ac_adjustments = 0
    if battle and battle.map:
        cover_ac_adjustments = calculate_cover_ac(battle.map, source, target)
        ac = target.armor_class() + cover_ac_adjustments  # calculate AC with cover
    else:
        ac = target.armor_class()
    return [ac, cover_ac_adjustments]

def calculate_cover_ac(map, source, target):
    return cover_calculation(map, source, target)

def cover_calculation(map, source, target, entity_1_pos=None, entity_2_pos=None, naturally_stealthy=False):
    source_squares = map.entity_squares_at_pos(source, *entity_1_pos) if entity_1_pos else map.entity_squares(source)
    target_squares = map.entity_squares_at_pos(target, *entity_2_pos) if entity_2_pos else map.entity_squares(target)
    source_position = map.position_of(source)
    source_melee_square = source.melee_squares(map, target_position=source_position, adjacent_only=True)

    max_ac = 0

    for source_pos in source_squares:
        for target_pos in target_squares:
            cover_characteristics = map.line_of_sight(*source_pos, *target_pos, inclusive=True, entity=naturally_stealthy)
            if not cover_characteristics:
                continue

            objs = map.objects_at(*target_pos)
            for obj in objs:
                if obj.can_hide():
                    max_ac = max(max_ac, obj.cover_ac())

            for cover in cover_characteristics:
                cover_type, pos = cover

                if cover_type == "none":
                    continue
                if pos in source_melee_square:
                    continue

                if cover_type == "half":
                    max_ac = max(max_ac, 2)
                if cover_type == "three_quarter":
                    max_ac = max(max_ac, 5)

                if isinstance(cover_type, int) and naturally_stealthy and (cover_type - target.size_identifier) >= 1:
                    return 1

            return max_ac

    return 0

