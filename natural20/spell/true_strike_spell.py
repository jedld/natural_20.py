from natural20.die_roll import DieRoll
from natural20.spell.spell import Spell
import pdb

# True Strike
# Divination cantrip
# Casting Time:1 action
# Range:30 feet
# Components:S
# Duration:Concentration, up to 1 round
#
# You extend your hand and point a finger at a target in range. Your magic grants you a brief insight
# into the target’s defenses. On your next turn, you gain advantage on your first attack roll against
# the target, provided that this spell hasn’t ended.
class TrueStrikeSpell(Spell):
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

    def resolve(self, entity, battle, spell_action, _battle_map):
        result = []
        target = spell_action.target

        result.extend([{
            'source': entity,
            'target': target,
            'type': 'true_strike',
            'effect': self
        }])
        return result

    def start_of_turn(self, entity, opt=None):
        self.action.target.register_effect('targeted_advantage_override', self,
                                           effect=self, source=entity)
        entity.register_event_hook('end_of_turn', self, effect=self)
        self.action.target.register_event_hook('after_attack_roll_target', self, effect=self)

    def end_of_turn(self, entity, opt=None):
        entity.dismiss_effect(self)

    def targeted_advantage_override(self, entity, opt=None):
        return [['true_strike_advantage'], []]

    def after_attack_roll_target(self, entity, opt=None):
        if entity == self.action.target:
            return [
                {
                    'type': 'dismiss_effect',
                    'source': self.action.source,
                    'target': self.action.target,
                    'effect': self
                }
            ]
        return []

    @staticmethod
    def apply(battle, item, session=None):
        if item['type'] == 'true_strike':
            if not item['source'].current_concentration()==item['effect']:
                item['source'].concentration_on(item['effect'])
            item['source'].add_casted_effect({ "target": item['target'], "effect" : item['effect'] })

            if battle:
                item['source'].register_event_hook('start_of_turn', item['effect'], effect=item['effect'])
            else:
                item['target'].register_effect('targeted_advantage_override', item['effect'],
                                           effect=item['effect'], source=item['source'])
                item['source'].register_event_hook('end_of_turn', item['effect'], effect=item['effect'])
                item['target'].register_event_hook('after_attack_roll_target', item['effect'], effect=item['effect'])
