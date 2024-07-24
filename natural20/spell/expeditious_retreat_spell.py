from dataclasses import dataclass
from typing import List
from natural20.spell.spell import Spell
from natural20.die_roll import DieRoll
from natural20.utils.spell_attack_util import evaluate_spell_attack
from natural20.utils.spell_attack_util import consume_resource

class ExpeditiousRetreatSpell(Spell):
    def build_map(self, action):
        return {
            'param': None,
            'next': lambda: action
        }

    @staticmethod
    def apply(battle, item):
        if item['type'] == 'expeditious_retreat':
            item['source'].add_casted_effect({
                'target': item['target'],
                'effect': item['effect'],
                'expiration': battle.session.game_time + 10 * 60
            })
            item['target'].register_effect('dash_override', ExpeditiousRetreatSpell, effect=item['effect'], source=item['source'],
                                           duration=10 * 60)
            battle.event_manager.received_event({ "event" : 'spell_buf', "spell": item['effect'], "source" : item['source'],
                                                  "target" : item['target']})
            consume_resource(battle, item)

    @staticmethod
    def dash_override(entity, effect, opts={}):
        return True

    def resolve(self, entity, battle, spell_action):
        return [{
            'type': 'expeditious_retreat',
            'target': entity,
            'source': entity,
            'effect': self,
            'spell': self.properties
        }]
