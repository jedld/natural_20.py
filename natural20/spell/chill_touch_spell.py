from dataclasses import dataclass
from typing import List
from natural20.spell.spell import Spell
from natural20.die_roll import DieRoll
from natural20.utils.spell_attack_util import evaluate_spell_attack

class ChillTouchSpell(Spell):
    def build_map(self, action):
        def set_target(target):
            action.target = target
            return {
                'param': None,
                'next': lambda: action
            }
        return {
            'param': [
                {
                    'type': 'select_target',
                    'num': 1,
                    'range': self.properties['range'],
                    'target_types': ['enemies'],
                },
            ],
            'next': set_target,
        }

    def resolve(self, entity, battle, spell_action):
        target = spell_action.target

        hit, attack_roll, advantage_mod, cover_ac_adjustments = evaluate_spell_attack(battle, entity, target, self.properties)

        if hit:
            level = 1
            if entity.level() >= 5:
                level += 1 
            if entity.level() >= 11:
                level += 1
            if entity.level() >= 17:
                level += 1 

            damage_roll = DieRoll.roll(f"{level}d8", crit=attack_roll.nat_20(), battle=battle, entity=entity,
                                       description="dice_roll.spells.chill_touch")
            return [{
                'source': entity,
                'target': target,
                'attack_name': "spell.chill_touch",
                'damage_type': self.properties['damage_type'],
                'attack_roll': attack_roll,
                'damage_roll': damage_roll,
                'advantage_mod': advantage_mod,
                'damage': damage_roll,
                'cover_ac': cover_ac_adjustments,
                'type': 'spell_damage',
                'spell': self.properties,
            },
            {
                'source': entity,
                'target': target,
                'type': 'chill_touch',
                'effect': self,
            }]
        else:
            return [{
                'type': 'spell_miss',
                'source': entity,
                'target': target,
                'attack_name': "spell.chill_touch",
                'damage_type': self.properties['damage_type'],
                'attack_roll': attack_roll,
                'damage_roll': damage_roll,
                'advantage_mod': advantage_mod,
                'cover_ac': cover_ac_adjustments,
                'spell': self.properties,
            }]

    @staticmethod
    def heal_override(entity, opt=None):
        return 0

    @staticmethod
    def start_of_turn(entity, opt=None):
        opt['effect'].action.target.dismiss_effect(opt['effect'])

    @staticmethod
    def attack_advantage_modifier(entity, opt=None):
        return [[], ['chill_touch_disadvantage']]

    @staticmethod
    def apply(battle, item):
        if item['type'] == 'chill_touch':
            item['source'].add_casted_effect({ "target": item['target'], "effect" : item['effect'] })
            item['target'].register_effect('heal_override', ChillTouchSpell, effect=item['effect'], source=item['source'])
            item['source'].register_event_hook('start_of_turn', ChillTouchSpell, effect=item['effect'])
            if item['target'].undead():
                item['target'].register_effect('attack_advantage_modifier', ChillTouchSpell, effect=item['effect'], source=item['source'])