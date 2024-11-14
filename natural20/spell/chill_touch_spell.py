from natural20.spell.spell import Spell
from natural20.die_roll import DieRoll
from natural20.utils.spell_attack_util import evaluate_spell_attack
from natural20.spell.extensions.hit_computations import AttackSpell
import pdb
class ChillTouchSpellUndeadEffect:
    def __init__(self, source, target):
        self.source = source
        self.target = target

    @staticmethod
    def attack_advantage_modifier(entity, opt=None):
        if opt['target'] == opt['effect'].source:
            return [[], ['chill_touch_disadvantage']]

    @staticmethod
    def end_of_turn(entity, opt=None):
        if opt['effect'].target:
            opt['effect'].target.dismiss_effect(opt['effect'])

    @staticmethod
    def start_of_turn(entity, opt=None):
        entity.register_event_hook('end_of_turn', ChillTouchSpellUndeadEffect, effect=opt['effect'])
class ChillTouchSpell(AttackSpell):
    def build_map(self, orig_action):
        def set_target(target):
            if not target:
                raise ValueError("Invalid target")

            action = orig_action.clone()
            action.target = target
            return action
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

    def _damage(self, battle, opts=None):
        entity = self.source
        level = 1
        if entity.level() >= 5:
            level += 1
        if entity.level() >= 11:
            level += 1
        if entity.level() >= 17:
            level += 1
        return DieRoll.roll(f"{level}d8", battle=battle, entity=entity, description="dice_roll.spells.chill_touch")

    def avg_damage(self, battle, opts=None):
        return self._damage(battle, opts).expected()

    def resolve(self, entity, battle, spell_action):
        target = spell_action.target

        hit, attack_roll, advantage_mod, cover_ac_adjustments, adv_info = evaluate_spell_attack(battle, entity, target, self.properties)

        if hit:
            damage_roll = self._damage(battle)
            return [{
                'source': entity,
                'target': target,
                'attack_name': "spell.chill_touch",
                'damage_type': self.properties['damage_type'],
                'attack_roll': attack_roll,
                'damage_roll': damage_roll,
                'advantage_mod': advantage_mod,
                'adv_info': adv_info,
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
                'advantage_mod': advantage_mod,
                'adv_info': adv_info,
                'cover_ac': cover_ac_adjustments,
                'spell': self.properties,
            }]

    @staticmethod
    def heal_override(entity, opt=None):
        return 0

    @staticmethod
    def start_of_turn(entity, opt=None):
        if opt['effect'].action.target:
            opt['effect'].action.target.dismiss_effect(opt['effect'])

    @staticmethod
    def apply(battle, item, session=None):
        if item['type'] == 'chill_touch':
            item['source'].add_casted_effect({ "target": item['target'], "effect" : item['effect'] })
            item['target'].register_effect('heal_override', ChillTouchSpell, effect=item['effect'], source=item['source'])

            item['source'].register_event_hook('start_of_turn', ChillTouchSpell, effect=item['effect'])

            if item['target'].undead():
                chill_touch_undead_efffect = ChillTouchSpellUndeadEffect(item['source'], item['target'])
                item['source'].register_event_hook('start_of_turn', ChillTouchSpellUndeadEffect, effect=chill_touch_undead_efffect)
                item['target'].register_effect('attack_advantage_modifier', ChillTouchSpellUndeadEffect, effect=chill_touch_undead_efffect, source=item['source'])
