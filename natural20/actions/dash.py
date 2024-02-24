from typing import Callable
from dataclasses import dataclass
from types import SimpleNamespace
from natural20.action import Action

class DashAction(Action):
    def __init__(self, session, source, action_type, opts={}):
        super().__init__(session, source, action_type, opts)
        self.as_bonus_action = False

    def build_map(self):
        return SimpleNamespace(
            param=None,
            next=lambda: self
        )
    
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
    def apply(battle, item):
        if item['type'] == 'dash':
            # Natural20.EventManager.received_event({'source': item['source'], 'event': 'dash'})
            battle.entity_state_for(item['source'])['movement'] += item['source'].speed()
            if item['as_bonus_action']:
                print(f"{item['source'].name} dashes as a bonus action")
                battle.entity_state_for(item['source'])['bonus_action'] -= 1
            else:
                print(f"{item['source'].name} dashes")
                battle.entity_state_for(item['source'])['action'] -= 1


class DashBonusAction(DashAction):
    @staticmethod
    def can(entity, battle, options=None):
        return battle and (entity.class_feature('cunning_action') or entity.eval_effect('dash_override')) and entity.total_bonus_actions(battle) > 0
