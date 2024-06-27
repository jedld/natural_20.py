from dataclasses import dataclass
from typing import List
from natural20.spell.spell import Spell
from natural20.die_roll import DieRoll
from natural20.utils.spell_attack_util import evaluate_spell_attack

class FireboltSpell(Spell):
    def __init__(self, session, source, spell_name, details):
        super().__init__(session, source, spell_name, details)
        self.range = 60
        self.damage_type = "fire"

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

        hit, attack_roll, advantage_mod, cover_ac_adjustments = evaluate_spell_attack(battle, entity, target, self.properties)

        if hit:
            level = 1
            if entity.level() >= 5:
                level += 1
            if entity.level() >= 11:
                level += 1
            if entity.level() >= 17:
                level += 1

            damage_roll = DieRoll.roll(f"{level}d10", crit=attack_roll.nat_20(), battle=battle, entity=entity, description=self.t('dice_roll.spells.generic_damage', spell=self.t('spell.firebolt')))
            return [{
                "source": entity,
                "target": target,
                "attack_name": "firebolt",
                "damage_type": self.damage_type,
                "attack_roll": attack_roll,
                "damage_roll": damage_roll,
                "advantage_mod": advantage_mod,
                "damage": damage_roll,
                "cover_ac": cover_ac_adjustments,
                "type": "spell_damage",
                "spell": self.properties
            }]
        else:
            return [{
                "type": "spell_miss",
                "source": entity,
                "target": target,
                "attack_name": "firebolt",
                "damage_type": self.damage_type,
                "attack_roll": attack_roll,
                "damage_roll": None,
                "advantage_mod": advantage_mod,
                "cover_ac": cover_ac_adjustments,
                "spell": self.properties
            }]
