import os
from typing import List, Union
from termcolor import colored
from prompt_toolkit import prompt
import i18n

class EventManager:
    event_listeners = {}

    class EventLogger:
        def __init__(self, log_level: Union[int, str]):
            self.log_level = int(log_level)

        def debug(self, message: str = ""):
            if self.log_level < 1:
                print(message)

    @staticmethod
    def clear():
        EventManager.event_listeners = {}

    @staticmethod
    def register_event_listener(events: Union[str, List[str]], callable):
        if isinstance(events, str):
            events = [events]
        for event in events:
            if event not in EventManager.event_listeners:
                EventManager.event_listeners[event] = []
            if callable not in EventManager.event_listeners[event]:
                EventManager.event_listeners[event].append(callable)

    @staticmethod
    def received_event(event):
        if EventManager.event_listeners is None:
            return
        if event['event'] in EventManager.event_listeners:
            for callable in EventManager.event_listeners[event['event']]:
                callable(event)

    @staticmethod
    def set_context(battle, entities=[]):
        EventManager.battle = battle
        EventManager.current_entity_context = entities

    @staticmethod
    def logger():
        log_level = os.environ.get("NAT20_LOG_LEVEL", "1")
        return EventManager.EventLogger(log_level)

    @staticmethod
    def standard_cli():
        EventManager.clear()
        event_handlers = {
            'died': lambda event: print(f"{EventManager.show_name(event)} died."),
            'unconscious': lambda event: print(f"{EventManager.show_name(event)} unconscious."),
            'attacked': lambda event: print(f"{EventManager.show_name(event)} attacked."),
            # Add more event handlers here
        }
        for event, handler in event_handlers.items():
            EventManager.register_event_listener(event, handler)

    @staticmethod
    def show_name(event):
        return EventManager.decorate_name(event['source'])

    @staticmethod
    def output(string):
        print(f"{string}")

    @staticmethod
    def decorate_name(entity):
        return entity.name

    @staticmethod
    def t(token, **options):
        return i18n.t(token, **options)
