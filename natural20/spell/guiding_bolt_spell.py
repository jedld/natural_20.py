from natural20.die_roll import DieRoll
from natural20.utils.spell_attack_util import evaluate_spell_attack
from natural20.spell.extensions.hit_computations import AttackSpell
import pdb

class GuidingBoltSpell(AttackSpell):
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

    def _damage(self, battle, crit=False, opts=None):
        if opts is None:
            opts = {}
        entity = self.source
        dmg_level = 4
        at_level = opts.get("at_level", 1)
        if at_level > 1:
            dmg_level += at_level - 1
        return DieRoll.roll(f"{dmg_level}d6", crit=crit, battle=battle, entity=entity, description="dice_roll.spells.guiding_bolt")

    def avg_damage(self, battle, opts=None):
        return self._damage(battle, opts).expected()

    def resolve(self, entity, battle, spell_action, _battle_map):
        result = []
        target = spell_action.target

        hit, attack_roll, advantage_mod, cover_ac_adjustments, adv_info, events = evaluate_spell_attack(battle, entity, target, self.properties, opts={"action": spell_action})
        for event in events:
            result.append(event)

        if hit:
            damage_roll = self._damage(battle, crit=attack_roll.nat_20(), opts={"at_level": spell_action.at_level})
            result.extend([{
                'source': entity,
                'target': target,
                'attack_name': "spell.guiding_bolt",
                'damage_type': self.properties['damage_type'],
                'attack_roll': attack_roll,
                'damage_roll': damage_roll,
                'advantage_mod': advantage_mod,
                'adv_info': adv_info,
                'damage': damage_roll,
                'cover_ac': cover_ac_adjustments,
                'type': 'spell_damage',
                'spell': self.properties
            }, {
                'source': entity,
                'target': target,
                'type': 'guiding_bolt',
                'effect': self
            }])
        else:
            result.extend([{
                'source': entity,
                'target': target,
                'attack_name': "spell.guiding_bolt",
                'attack_roll': attack_roll,
                'advantage_mod': advantage_mod,
                'adv_info': adv_info,
                'cover_ac': cover_ac_adjustments,
                'type': 'spell_miss',
                'spell': self.properties
            }])

        return result

    @staticmethod
    def start_of_turn(entity, opt=None):
        entity.register_event_hook('end_of_turn', GuidingBoltSpell, effect=opt['effect'])

    @staticmethod
    def end_of_turn(entity, opt=None):
        if opt['effect'].action.target:
            opt['effect'].action.target.dismiss_effect(opt['effect'])

    @staticmethod
    def targeted_advantage_override(entity, opt=None):
        return [['guiding_bolt_advantage'], []]

    @staticmethod
    def after_attack_roll_target(entity, opt=None):
        return [
            {
                'type': 'dismiss_effect',
                'source': entity,
                'effect': opt['effect']
            }
        ]

    @staticmethod
    def light_override(entity, opt=None):
        return {
            'bright': opt['bright'],
            'dim': max(opt['dim'], 1)
        }

    @staticmethod
    def apply(battle, item, session=None):
        if item['type'] == 'guiding_bolt':
            item['source'].add_casted_effect({ "target": item['target'], "effect" : item['effect'] })
            item['target'].register_event_hook('after_attack_roll_target', GuidingBoltSpell, effect=item['effect'])
            item['source'].register_event_hook('start_of_turn', GuidingBoltSpell, effect=item['effect'])
            item['target'].register_effect('targeted_advantage_override', GuidingBoltSpell, effect=item['effect'], source=item['source'])
            item['target'].register_effect('light_override', GuidingBoltSpell, effect=item['effect'], source=item['source'])