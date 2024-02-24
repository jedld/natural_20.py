from typing import Callable
from dataclasses import dataclass
from natural20.action import Action

@dataclass
class DodgeAction(Action):
    as_bonus_action: bool

    @staticmethod
    def can_(entity, battle):
        return battle and entity.total_actions(battle) > 0

    def build_map(self):
        return {
            'param': None,
            'next': lambda: self
        }

    @staticmethod
    def build(session, source):
        action = DodgeAction(session, source, 'attack')
        return action.build_map()

    def resolve(self, session, _map, opts=None):
        opts = opts or {}
        self.result = [{
            'source': self.source,
            'type': 'dodge',
            'as_bonus': self.as_bonus_action,
            'battle': opts.get('battle')
        }]
        return self

    @staticmethod
    def apply(battle, item):
        item_type = item.get('type')
        if item_type == 'dodge':
            print(f"{item.get('source').name} dodges")
            # Natural20.EventManager.received_event({'source': item.get('source'), 'event': 'dodge'})
            item.get('source').do_dodge(battle)

            if item.get('as_bonus_action'):
                battle.entity_state_for(item.get('source'))['bonus_action'] -= 1
            else:
                battle.entity_state_for(item.get('source'))['action'] -= 1
