from natural20.spell.spell import Spell
from natural20.die_roll import DieRoll
from natural20.utils.spell_attack_util import evaluate_spell_attack
import pdb

class RayOfFrostSpell(Spell):
    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [
                {
                    'type': 'select_target',
                    'num': 1,
                    'range': self.properties['range'],
                    'target_types': ['enemies']
                }
            ],
            'next': set_target
        }

    def resolve(self, entity, battle, spell_action):
        target = spell_action.target

        hit, attack_roll, advantage_mod, cover_ac_adjustments, adv_info = evaluate_spell_attack(battle, entity, target, self.properties)

        if hit:
            level = 1
            if entity.level() >= 5:
                level += 1
            if entity.level() >= 11:
                level += 1
            if entity.level() >= 17:
                level += 1

            damage_roll = DieRoll.roll(f"{level}d8", crit=attack_roll.nat_20(), battle=battle, entity=entity,
                                       description=self.t('dice_roll.spells.ray_of_frost'))
            return [
                {
                    'source': entity,
                    'target': target,
                    'attack_name': 'ray_of_frost',
                    'damage_type': self.properties['damage_type'],
                    'attack_roll': attack_roll,
                    'damage_roll': damage_roll,
                    'advantage_mod': advantage_mod,
                    'adv_info': adv_info,
                    'damage': damage_roll,
                    'cover_ac': cover_ac_adjustments,
                    'type': 'spell_damage',
                    'spell': self.properties
                },
                {
                    'source': entity,
                    'target': target,
                    'type': 'ray_of_frost',
                    'effect': self
                }
            ]
        else:
            return [
                {
                    'type': 'spell_miss',
                    'source': entity,
                    'target': target,
                    'attack_name': 'ray_of_frost',
                    'damage_type': self.properties['damage_type'],
                    'attack_roll': attack_roll,
                    'advantage_mod': advantage_mod,
                    'adv_info': adv_info,
                    'cover_ac': cover_ac_adjustments,
                    'spell': self.properties
                }
            ]

    @staticmethod
    def start_of_turn(entity, opt=None):
        if not opt:
            opt = {}
        opt['effect'].action.target.dismiss_effect(opt['effect'])

    @staticmethod
    def speed_override(entity, opt=None):
        if opt is None:
            opt = {}
        return max(opt['value'] - 10, 0)

    @staticmethod
    def apply(battle, item):
        if item['type'] == 'ray_of_frost':
            item['source'].add_casted_effect({ "target" : item['target'], "effect" : item['effect']})
            item['target'].register_effect('speed_override', RayOfFrostSpell, effect=item['effect'], source=item['source'])
            item['source'].register_event_hook('start_of_turn', RayOfFrostSpell, effect=item['effect'])