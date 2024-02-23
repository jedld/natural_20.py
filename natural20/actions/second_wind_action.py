import types
from collections import namedtuple
from natural20.die_roll import DieRoll
from natural20.action import Action

class SecondWindAction(Action):
    @staticmethod
    def can_(entity, battle):
        return (battle is None or entity.total_bonus_actions(battle) > 0) and entity.second_wind_count > 0

    def label(self):
        return 'Second Wind'

    def build_map(self):
        ActionMap = namedtuple('ActionMap', ['action', 'param', 'next'])
        return ActionMap(action=self, param=None, next=types.MethodType(lambda self: self, self))

    @staticmethod
    def build(session, source):
        action = SecondWindAction(session, source, 'second_wind')
        return action.build_map()

    def resolve(self, _session, _map, opts={}):
        second_wind_roll = DieRoll.roll(self.source.second_wind_die, description='dice_roll.second_wind',
                                                  entity=self.source, battle=opts.get('battle'))
        self.result = [{
            'source': self.source,
            'roll': second_wind_roll,
            'type': 'second_wind',
            'battle': opts.get('battle')
        }]
        return self

    @staticmethod
    def apply_(battle, item):
        if item['type'] == 'second_wind':
            # Natural20.EventManager.received_event(action=SecondWindAction, source=item['source'], roll=item['roll'],
            #                                       event='second_wind')
            item['source'].second_wind(item['roll'].result)
            battle.entity_state_for(item['source'])['bonus_action'] -= 1

    @staticmethod
    def describe(event):
        return f"{event['source'].name.colorize('green')} uses Second Wind.colorize('blue') with {event['roll']} healing"
