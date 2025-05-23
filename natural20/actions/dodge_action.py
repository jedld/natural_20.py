from typing import Callable
from dataclasses import dataclass
from natural20.action import Action
from natural20.event_manager import EventManager

@dataclass
class DodgeAction(Action):
    as_bonus_action: bool

    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.as_bonus_action = False

    def __repr__(self):
        if self.as_bonus_action:
            return "dodge as a bonus action"
        else:
            return "dodge"

    @staticmethod
    def can(entity, battle):
        return battle and entity.total_actions(battle) > 0

    def build_map(self):
        return self

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
    def apply(battle, item, session=None):
        item_type = item.get('type')
        if item_type == 'dodge':
            # print(f"{item.get('source').name} dodges")
            battle.session.event_manager.received_event({'source': item.get('source'), 'event': 'dodge'})
            item.get('source').do_dodge(battle)

            if item.get('as_bonus_action'):
                battle.consume(item['source'], 'bonus_action')
            else:
                battle.consume(item['source'], 'action')
