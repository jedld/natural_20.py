import types
from collections import namedtuple
from natural20.die_roll import DieRoll
from natural20.action import Action

class SecondWindAction(Action):
    @staticmethod
    def can(entity, battle):
        # return false if attribute second_wind_count does not exist
        if not hasattr(entity, 'second_wind_count'):
            return False

        return (battle is None or entity.total_bonus_actions(battle) > 0) and entity.second_wind_count > 0

    def label(self):
        return 'Second Wind'
    
    def __str__(self):
        return f"SecondWind"
    
    def __repr__(self):
        return f"SecondWind"


    def build_map(self):
        return self

    @staticmethod
    def build(session, source):
        action = SecondWindAction(session, source, 'second_wind')
        return action.build_map()

    def resolve(self, _session, _map, opts={}):
        second_wind_roll = DieRoll.roll(self.source.second_wind_die(), description='dice_roll.second_wind',
                                                  entity=self.source, battle=opts.get('battle'))
        self.result = [{
            'source': self.source,
            'roll': second_wind_roll,
            'type': 'second_wind',
            'battle': opts.get('battle')
        }]
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if session is None:
            session = battle.session
        if item['type'] == 'second_wind':
            # print(f"{item['source'].name} uses Second Wind with {item['roll']} healing")
            session.event_manager.received_event({'source': item['source'], 'value': item['roll'], 'event': 'second_wind'})
            item['source'].second_wind(item['roll'].result())
            if battle:
                battle.entity_state_for(item['source'])['bonus_action'] -= 1

    @staticmethod
    def describe(event):
        return f"{event['source'].name.colorize('green')} uses Second Wind with {event['roll']} healing"
