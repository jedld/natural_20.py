import os
from typing import List, Union
import i18n
from natural20.utils.attack_util import to_advantage_str

class EventLogger:
    def __init__(self, log_level: Union[int, str]):
        self.log_level = int(log_level)

    def debug(self, message: str = ""):
        if self.log_level < 1:
            print(message)

class EventManager:
    def __init__(self):
        self.event_listeners = {}
        self.battle = None

    def clear(self):
        self.event_listeners = {}

    def register_event_listener(self, events: Union[str, List[str]], callable):
        if isinstance(events, str):
            events = [events]
        for event in events:
            if event not in self.event_listeners:
                self.event_listeners[event] = []
            if callable not in self.event_listeners[event]:
                self.event_listeners[event].append(callable)

    def received_event(self, event):
        if self.event_listeners is None:
            return
        if event['event'] in self.event_listeners:
            for callable in self.event_listeners[event['event']]:
                callable(event)

    def set_context(self, battle, entities=None):
        if entities is None:
            entities = []
        self.battle = battle
        self.current_entity_context = entities

    def logger(self):
        log_level = os.environ.get("NAT20_LOG_LEVEL", "1")
        return EventLogger(log_level)

    def standard_cli(self):
        self.clear()

        def attack_roll(event):
            msg = f"{self.show_name(event)} attacked {self.show_target_name(event)}{to_advantage_str(event)}{' with opportunity' if event['as_reaction'] else ''} with {event['attack_name']}{'(thrown)' if event['thrown'] else ''} and hits"
            if event['attack_roll']:
                msg += f" with attack roll {event['attack_roll']} = {event['attack_roll'].result()}"
            print(f"{msg}.")

        event_handlers = {
            'second_wind': lambda event: print(f"{self.show_name(event)} uses second wind to recover {event['value']}={event['value'].result()} hit points."),    
            'disengage': lambda event: print(f"{self.show_name(event)} disengages."),
            'dodge': lambda event: print(f"{self.show_name(event)} dodges."),
            'died': lambda event: print(f"{self.show_name(event)} died."),
            'dash': lambda event: print(f"{self.show_name(event)} dashes."),
            'stand': lambda event: print(f"{self.show_name(event)} stands up."),
            'prone': lambda event: print(f"{self.show_name(event)} goes prone."),
            'unconscious': lambda event: print(f"{self.show_name(event)} unconscious."),
            'attacked': attack_roll,
            'damage': lambda event: print(f"{self.show_name(event)} took {event['value']} damage."),
            'spell_damage': lambda event: print(f"{self.show_name(event)} cast {event['spell']['name']} on {self.show_target_name(event)} and hit with {event['attack_roll']}= {event['attack_roll'].result()} for {event['damage']} damage."),
            'miss': lambda event: print(f"{self.show_name(event)} tried to attack {self.show_target_name(event)}{to_advantage_str(event)}{' with opportunity' if event['as_reaction'] else ''} with {event['attack_name']} but missed with {event['attack_roll']}= {event['attack_roll'].result()}."),
            'move': lambda event: print(f"{self.show_name(event)} moved to {event['position']} {event['move_cost']} feet"),
            'initiative': lambda event: print(f"{self.show_name(event)} rolled initiative {event['roll']} value {event['value']}"),
            'start_of_turn': lambda event: print(f"{self.show_name(event)} starts their turn."),
        }
        for event, handler in event_handlers.items():
            self.register_event_listener(event, handler)

    def show_name(self, event):
        return self.decorate_name(event['source'])
    
    def show_target_name(self, event):
        return self.decorate_name(event['target'])

    def output(self, string):
        print(f"{string}")

    def decorate_name(self, entity):
        return entity.name

    def t(self, token, **options):
        return i18n.t(token, **options)