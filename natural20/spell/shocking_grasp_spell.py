from dataclasses import dataclass
from typing import List
from natural20.spell.spell import Spell
from natural20.die_roll import DieRoll
from natural20.utils.spell_attack_util import evaluate_spell_attack

class ShockingGraspSpell(Spell):

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
                    'range': 5,
                    'target_types': ['enemies']
                }
            ],
            'next': set_target
        }

    def resolve(self, entity, battle, spell_action):
        target = spell_action.target
        advantage_override = {}

        if any(armor["metallic"] for armor in target.equipped_armor()):
            advantage_override['advantage'] = ['shocking_grasp_metallic']

        hit, attack_roll, advantage_mod, cover_ac_adjustments = evaluate_spell_attack(battle, entity, target, self.properties, advantage_override)

        if hit:
            level = 1
            if entity.level() >= 5:
                level += 1
            if entity.level() >= 11:
                level += 1
            if entity.level() >= 17:
                level += 1

            damage_roll = DieRoll.roll(f"{level}d8", crit=attack_roll.nat_20(), battle=battle, entity=entity, description=self.t('dice_roll.spells.generic_damage', spell=self.t('spell.shocking_grasp')))
            return [
                {
                    'source': entity,
                    'target': target,
                    'attack_name': self.t('spell.shocking_grasp'),
                    'damage_type': self.properties['damage_type'],
                    'attack_roll': attack_roll,
                    'damage_roll': damage_roll,
                    'advantage_mod': advantage_mod,
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
            ]
        else:
            return [
                {
                    'type': 'spell_miss',
                    'source': entity,
                    'target': target,
                    'attack_name': self.t('spell.shocking_grasp'),
                    'damage_type': self.properties['damage_type'],
                    'attack_roll': attack_roll,
                    'damage_roll': damage_roll,
                    'advantage_mod': advantage_mod,
                    'cover_ac': cover_ac_adjustments,
                    'spell': self.properties
                }
            ]

    @staticmethod
    def apply(battle, item):
        if item['type'] == 'shocking_grasp':
            battle.entity_state_for(item['target']).update(reaction=0)

