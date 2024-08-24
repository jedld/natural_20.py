import types
from collections import namedtuple
from natural20.action import Action

class ActionSurgeAction(Action):
    @staticmethod
    def can(entity, battle):
        # return false if attribute second_wind_count does not exist
        if not hasattr(entity, 'action_surge_count'):
            return False

        return battle and not battle.entity_state_for(entity).get('action_surge', False) and entity.action_surge_count > 0

    def label(self):
        return 'Action Surge'

    def __str__(self):
        return "uses Action Surge"

    def __repr__(self):
        return "uses Action Surge"

    def build_map(self):
        ActionMap = namedtuple('ActionMap', ['action', 'param', 'next'])
        return ActionMap(action=self, param=None, next=types.MethodType(lambda self: self, self))

    @staticmethod
    def build(session, source):
        action = ActionSurgeAction(session, source, 'second_wind')
        return action.build_map()

    def resolve(self, _session, _map, opts=None):
        self.result = [{
            'source': self.source,
            'type': 'action_surge',
            'battle': opts.get('battle')
        }]
        return self

    @staticmethod
    def apply(battle, item):
        if item['type'] == 'action_surge':
            battle.event_manager.received_event({'source': item['source'], 'event': 'action_surge'})
            item['source'].action_surge()
            battle.entity_state_for(item['source'])['action'] += 1
            battle.entity_state_for(item['source'])['action_surge'] = True

    @staticmethod
    def describe(event):
        return f"{event['source'].name.colorize('green')} uses Action Surge"
