from typing import Any
from dataclasses import dataclass
from natural20.action import Action

class MultiattackAction(Action):
    as_bonus_action: Any

    @staticmethod
    def can(entity, battle):
        return battle and entity.total_actions(battle) > 0

    def build_map(self):
        return {
            'param': None,
            'next': lambda: self
        }

    @staticmethod
    def build(session, source):
        action = MultiattackAction(session, source, 'multiattack')
        return action.build_map()

    def resolve(self, session, _map, opts=None):
        self.result = [{
            'source': self.source,
            'type': 'multiattack',
            'battle': opts.get('battle')
        }]
        return self

    @staticmethod
    def apply(battle, item):
        if item['type'] == 'multiattack':
            battle.consume('action', 1)