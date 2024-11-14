import types
from collections import namedtuple
from natural20.action import Action

class DropConcentrationAction(Action):
    @staticmethod
    def can(entity, battle):
        # return false if attribute second_wind_count does not exist
        if not hasattr(entity, 'action_surge_count'):
            return False

        return battle and entity.concentration is not None

    def label(self):
        return 'Drop Concentration'

    def __str__(self):
        return "Drop Concentration"

    def __repr__(self):
        return "drops concentration"

    def build_map(self):
        return self

    @staticmethod
    def build(session, source):
        action = DropConcentrationAction(session, source, 'second_wind')
        return action.build_map()

    def resolve(self, _session, _map, opts=None):
        if opts is None:
            opts = {}
        self.result = [{
            'source': self.source,
            'type': 'drop_concentration',
            'battle': opts.get('battle')
        }]
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if battle and session is None:
            session = battle.session
        if item['type'] == 'drop_concentration':
            session.event_manager.received_event({'source': item['source'], 'event': 'drop_concentration'})
            if item['source'].concentration:
                item['source'].dismiss_effect(item['source'].concentration)

    @staticmethod
    def describe(event):
        return f"{event['source'].name} drops concentration"
