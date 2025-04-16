from natural20.spell.spell import Spell
from natural20.die_roll import DieRoll
from natural20.utils.spell_attack_util import evaluate_spell_attack
from natural20.utils.ac_utils import effective_ac
from natural20.spell.extensions.hit_computations import AttackSpell
import pdb

class RayOfFrostSpell(AttackSpell):
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

    def _damage(self, battle, crit=False, opts=None):
        entity = self.source
        level = 1
        if entity.level() >= 5:
            level += 1
        if entity.level() >= 11:
            level += 1
        if entity.level() >= 17:
            level += 1
        return DieRoll.roll(f"{level}d8", crit=crit, battle=battle, entity=entity, description=self.t('dice_roll.spells.ray_of_frost'))

    def avg_damage(self, battle, opts=None):
        return self._damage(battle, opts).expected()

    def resolve(self, entity, battle, spell_action, _battle_map):
        target = spell_action.target

        hit, attack_roll, advantage_mod, cover_ac_adjustments, adv_info, events = evaluate_spell_attack(battle, entity, target, self.properties, opts={"action": spell_action})
        result = []
        for event in events:
            result.append(event)

        if hit:
            damage_roll = self._damage(battle, crit=attack_roll.nat_20())
            result.extend([
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
            ])
        else:
            result.extend([
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
            ])

        return result


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
    def apply(battle, item, session=None):
        if item['type'] == 'ray_of_frost':
            item['source'].add_casted_effect({ "target" : item['target'], "effect" : item['effect']})
            item['target'].register_effect('speed_override', RayOfFrostSpell, effect=item['effect'], source=item['source'])
            item['source'].register_event_hook('start_of_turn', RayOfFrostSpell, effect=item['effect'])
