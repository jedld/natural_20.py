from natural20.die_roll import DieRoll
from natural20.utils.spell_attack_util import evaluate_spell_attack, spell_attack_is_critical
from natural20.spell.extensions.hit_computations import AttackSpell
from natural20.utils.ac_utils import effective_ac
import pdb

class ShockingGraspSpell(AttackSpell):

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
    
    def compute_hit_probability(self, battle, opts = None):
        target = self.action.target if self.action else None
        if target is None:
            return 0.0
        overrides = dict(opts or {})
        metallic = getattr(target, 'equipped_metallic_armor', None)
        if callable(metallic) and metallic():
            overrides.setdefault('advantage', []).append('shocking_grasp_metallic')
        # Analytic estimate via the shared AttackSpell path: no dice rolled.
        return super().compute_hit_probability(battle, overrides)

    def resolve(self, entity, battle, spell_action, _battle_map):
        result = []
        target = spell_action.target
        advantage_override = {
            "action": spell_action
        }

        if target.equipped_metallic_armor():
            advantage_override['advantage'] = ['shocking_grasp_metallic']

        hit, attack_roll, advantage_mod, cover_ac_adjustments, adv_info, events = evaluate_spell_attack(self.session, entity, target, self.properties, battle=battle, opts=advantage_override)
        for event in events:
            result.append(event)

        if hit:
            level = 1
            if entity.cantrip_level() >= 5:
                level += 1
            if entity.cantrip_level() >= 11:
                level += 1
            if entity.cantrip_level() >= 17:
                level += 1

            damage_roll = DieRoll.roll(f"{level}d8", crit=spell_attack_is_critical(attack_roll, entity, target, battle), battle=battle, entity=entity, description=self.t('dice_roll.spells.generic_damage', spell=self.t('spell.shocking_grasp')))
            result.extend([
                {
                    'source': entity,
                    'target': target,
                    'attack_name': self.t('spell.shocking_grasp'),
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
                    'type': 'shocking_grasp',
                    'effect': self
                }
            ])
        else:
            result.extend([
                {
                    'type': 'spell_miss',
                    'source': entity,
                    'target': target,
                    'attack_name': self.t('spell.shocking_grasp'),
                    'damage_type': self.properties['damage_type'],
                    'attack_roll': attack_roll,
                    'damage_roll': None,
                    'advantage_mod': advantage_mod,
                    'adv_info': adv_info,
                    'cover_ac': cover_ac_adjustments,
                    'spell': self.properties
                }
            ])

        return result

    @staticmethod
    def apply(battle, item, session=None):
        if item['type'] == 'shocking_grasp':
            battle.entity_state_for(item['target']).update(reaction=0)

