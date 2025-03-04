from typing import Callable
from dataclasses import dataclass
from types import SimpleNamespace
from natural20.action import Action
from natural20.event_manager import EventManager

class DashAction(Action):
    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.as_bonus_action = False

    def build_map(self):
        return self

    def __repr__(self) -> str:
        if self.as_bonus_action:
            return f"dash as a bonus action"
        else:
            return f"dash"


    @staticmethod
    def can(entity, battle, _options=None):
        return battle and entity.total_actions(battle) > 0

    def resolve(self, _session, _map, opts=None):
        self.result = [{
            'source': self.source,
            'type': 'dash',
            'battle': opts.get('battle'),
            'as_bonus_action': self.as_bonus_action
        }]
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if item['type'] == 'dash':
            battle.session.event_manager.received_event({'source': item['source'], 'event': 'dash', 'as_bonus_action': item['as_bonus_action']})
            battle.entity_state_for(item['source'])['movement'] += item['source'].speed()
            if item['as_bonus_action']:
                battle.entity_state_for(item['source'])['bonus_action'] -= 1
            else:
                battle.entity_state_for(item['source'])['action'] -= 1


class DashBonusAction(DashAction):
    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.as_bonus_action = True

    @staticmethod
    def can(entity, battle, options=None):
        return battle and (entity.class_feature('cunning_action') or entity.eval_effect('dash_override')) and entity.total_bonus_actions(battle) > 0
