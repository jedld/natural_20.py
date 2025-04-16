from natural20.spell.spell import Spell
from natural20.die_roll import DieRoll
from natural20.utils.spell_attack_util import evaluate_spell_attack
from natural20.weapons import damage_modifier, target_advantage_condition
from natural20.utils.ac_utils import effective_ac
from natural20.spell.extensions.hit_computations import AttackSpell

class FireboltSpell(AttackSpell):
    def __init__(self, session, source, spell_name, details):
        super().__init__(session, source, spell_name, details)
        self.range = 60
        self.damage_type = "fire"

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
        return DieRoll.roll(f"{level}d10", crit=crit, battle=battle, entity=entity, description=self.t('dice_roll.spells.generic_damage', spell=self.t('spell.firebolt')))

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
            result.extend([{
                "source": entity,
                "target": target,
                "attack_name": "firebolt",
                "damage_type": self.damage_type,
                "attack_roll": attack_roll,
                "damage_roll": damage_roll,
                "advantage_mod": advantage_mod,
                "adv_info": adv_info,
                "damage": damage_roll,
                "cover_ac": cover_ac_adjustments,
                "type": "spell_damage",
                "spell": self.properties
            }])
        else:
            result.extend([{
                "type": "spell_miss",
                "source": entity,
                "target": target,
                "attack_name": "firebolt",
                "damage_type": self.damage_type,
                "attack_roll": attack_roll,
                "damage_roll": None,
                "advantage_mod": advantage_mod,
                "adv_info": adv_info,
                "cover_ac": cover_ac_adjustments,
                "spell": self.properties
            }])

        return result
