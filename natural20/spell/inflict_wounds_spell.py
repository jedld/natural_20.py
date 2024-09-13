from natural20.die_roll import DieRoll
from natural20.utils.spell_attack_util import evaluate_spell_attack
from natural20.spell.extensions.hit_computations import AttackSpell
from natural20.utils.ac_utils import effective_ac

class InflictWoundsSpell(AttackSpell):

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
                    'range': 5,
                    'target_types': ['enemies']
                }
            ],
            'next': set_target
        }
    
    def _damage(self, battle, opts=None):
        if opts is None:
            opts = {}
        entity = self.source
        dmg_level = 3
        at_level = opts.get("at_level", 1)
        if at_level > 1:
            dmg_level += at_level - 1
        return DieRoll.roll(f"{dmg_level}d10", battle=battle, entity=entity, description="dice_roll.spells.inflict_wounds")

    def compute_hit_probability(self, battle, opts = None):
        if opts is None:
            opts = {}

        _, attack_roll, _, _, _ = evaluate_spell_attack(battle, self.source, self.action.target, self.properties)
        target_ac, _cover_ac = effective_ac(battle, self.source, self.action.target)
        return attack_roll.prob(target_ac)

    def avg_damage(self, battle, opts=None):
        return self._damage(battle, opts).expected()

    def resolve(self, entity, battle, spell_action):
        target = spell_action.target

        hit, attack_roll, advantage_mod, cover_ac_adjustments, adv_info = evaluate_spell_attack(battle, entity, target, self.properties)

        if hit:
            damage_roll = self._damage(battle)

            return [
                {
                    'source': entity,
                    'target': target,
                    'attack_name': self.t('spell.inflict_wounds'),
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
            ]
        else:
            return [
                {
                    'type': 'spell_miss',
                    'source': entity,
                    'target': target,
                    'attack_name': self.t('spell.inflict_wounds'),
                    'damage_type': self.properties['damage_type'],
                    'attack_roll': attack_roll,
                    'damage_roll': None,
                    'advantage_mod': advantage_mod,
                    'adv_info': adv_info,
                    'cover_ac': cover_ac_adjustments,
                    'spell': self.properties
                }
            ]



