from natural20.spell.spell import Spell
from natural20.die_roll import DieRoll

class HealingWordSpell(Spell):
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
                    'target_types': ['allies', 'self', 'enemies']
                }
            ],
            'next': set_target
        }

    def _heal(self, battle, opts=None):
        entity = self.source
        level = 1
        if self.action.at_level > 1:
            level += self.action.at_level - 1
        return DieRoll.roll(f"{level}d4+{entity.cleric_spell_casting_modifier()}", battle=battle, entity=entity, description=self.t('dice_roll.spells.cure_wounds'))

    def compute_hit_probability(self, battle, opts=None):
        return 1.0

    def avg_damage(self, battle, opts=None):
        return -self._heal(battle, opts).expected()

    def resolve(self, entity, battle, spell_action):
        target = spell_action.target

        heal_roll = self._heal(battle)

        return [{
            "source": entity,
            "target": target,
            "type": "spell_heal",
            "heal_roll": heal_roll,
            "spell": self.properties
        }]