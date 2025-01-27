import os
from typing import List, Union
import i18n
from collections import deque
from natural20.utils.attack_util import to_advantage_str

class EventLogger:
    """
    A simple logger for engine related events that logs to stdout
    """
    def __init__(self, log_level: Union[int, str]):
        self.log_level = int(log_level)

    def debug(self, message: str = ""):
        if self.log_level < 1:
            print(message)

class OutputLogger:
    """
    A simple logger that logs to stdout
    """
    def __init__(self):
        pass

    def log(self, event_msg):
        print(event_msg)

class FileOutputLogger:
    """
    A simple logger that logs to a file
    """
    def __init__(self, file_path):
        self.file_path = file_path

    def log(self, event_msg):
        with open(self.file_path, "a") as f:
            f.write(event_msg)

class EventManager:
    def __init__(self, output_logger=None, output_file=None):
        self.event_listeners = {}
        self.battle = None
        self.event_buffer = deque(maxlen=1000)
        if output_file:
            self.output_logger = FileOutputLogger(output_file)
        else:
            if output_logger is None:
                self.output_logger = OutputLogger()
            else:
                self.output_logger = output_logger

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
        self.event_buffer.append(event)
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
            msg = f"{self.show_name(event)} attacked {self.show_target_name(event)}{to_advantage_str(event)}{' with opportunity' if event['as_reaction'] else ''} with {self.t(event['attack_name'])}{'(thrown)' if event['thrown'] else ''} and hits"
            if event['attack_roll']:
                msg += f" with attack roll {event['attack_roll']} = {event['attack_roll'].result()}"
            self.output_logger.log(f"{msg}.")

        def miss(event):
            if event.get('spell_save'):
                self.output_logger.log(f"{self.show_name(event)} tried to attack {self.show_target_name(event)}{to_advantage_str(event)}{' with opportunity' if event['as_reaction'] else ''} with {event['attack_name']}{'(thrown)' if event['thrown'] else ''} but succeeded on save with {event['spell_save']} > DC: {event['dc']}.")
            else:
                self.output_logger.log(f"{self.show_name(event)} tried to attack {self.show_target_name(event)}{to_advantage_str(event)}{' with opportunity' if event['as_reaction'] else ''} with {event['attack_name']}{'(thrown)' if event['thrown'] else ''} but missed with {event['attack_roll']}= {event['attack_roll'].result()}.")

        def concentration_check(event):
            if event['result'] == 'success':
                self.output_logger.log(f"{self.show_name(event)} makes a concentration check and succeeds: {event['roll']} >= {event['dc']}")
            else:
                self.output_logger.log(f"{self.show_name(event)} makes a concentration check and fails: {event['roll']} < {event['dc']}")

        def death_fail(event):
            if event.get('roll'):
                self.output_logger.log(f"{self.show_name(event)} failed a death saving throw: {event['roll']} = {event['roll'].result()}")
            else:
                self.output_logger.log(f"{self.show_name(event)} received damage that caused a death saving throw failure.")

        def shove(event):
            rolls_description = f"Contested role for shove: {event['source_roll']} vs {event['target_roll']}"
            if event.get('success'):
                self.output_logger.log(f"{self.show_name(event)} shoves {self.show_target_name(event)} and succeeds. {rolls_description}")
            else:
                self.output_logger.log(f"{self.show_name(event)} shoves {self.show_target_name(event)} and fails. {rolls_description}")

        def spell_damage(event):
            if event.get('spell_save', None):
                self.output_logger.log(f"{self.show_name(event)} cast {event['spell']['name']} on {self.show_target_name(event)} and hits with {event['spell_save']}={event['spell_save'].result()} < DC: {event['dc']} for {event['damage']} damage.")
            else:
                self.output_logger.log(f"{self.show_name(event)} cast {event['spell']['name']} on {self.show_target_name(event)} and hit with {event['attack_roll']}{to_advantage_str(event)}= {event['attack_roll'].result()} for {event['damage']} damage.")

        def hide(event):
            if event['result'] == 'success':
                self.output_logger.log(f"{self.show_name(event)} successfully hides with a {event['roll']}={event['roll'].result()} stealth.")
            else:
                self.output_logger.log(f"{self.show_name(event)} tries to hide but fails. {','.join(event['reason'])}")

        def damage(event):
            if event.get('roll_info'):
                damage = event.get('roll_info').result()
            else:
                damage = event['value']
            if event.get('sneak_attack'):
                self.output_logger.log(f"{self.show_name(event)} took {event.get('roll_info','')} = {damage} damage and {event['sneak_attack']}={event['sneak_attack'].result()} sneak attack damage.")
            else:
                self.output_logger.log(f"{self.show_name(event)} took {event.get('roll_info','')} = {damage} damage."),

            if event.get('instant_death'):
                self.output_logger.log(f"{self.show_name(event)} died instantly.")

        def first_aid(event):
            if event['success']:
                self.output_logger.log(f"{self.show_name(event)} performs first aid on {self.show_target_name(event)} and stabilizes them with a {event['roll']}={event['roll'].result()} medicine check.")
            else:
                self.output_logger.log(f"{self.show_name(event)} performs first aid on {self.show_target_name(event)} and fails to stabilize them with a {event['roll']}={event['roll'].result()} medicine check.")

        def start_of_combat(event):
            players = []
            for p in event['players'].keys():
                p_str = f"<p>{self.decorate_name(p)} ({p.class_descriptor()}) Team {event['players'][p]['group']}</p>"
                players.append(p_str)

            self.output_logger.log(f"Combat begins with {len(players)} players.")
            self.output_logger.log("Players: " + '\n'.join(players))

        def ice_knife(event):
            if event['success']:
                self.output_logger.log(f"{self.show_target_name(event)} failed the dexterity saving throw for ice knife. {event['roll']} < {event['source'].spell_save_dc()}")
            else:
                self.output_logger.log(f"{self.show_target_name(event)} succeeded the dexterity saving throw for ice knife. {event['roll']} >= {event['source'].spell_save_dc()}")

        event_handlers = {
            'multiattack' : lambda event: self.output_logger.log(f"{self.show_name(event)} uses multiattack."),
            'action_surge': lambda event: self.output_logger.log(f"{self.show_name(event)} uses action surge."),
            'death_fail' : death_fail,
            'death_save': lambda event: self.output_logger.log(f"{self.show_name(event)} makes a death saving throw and succeeds: {event['roll']} = {event['roll'].result()}"),
            'drop_concentration': lambda event: self.output_logger.log(f"{self.show_name(event)} drops concentration."),
            'concentration_check': concentration_check,
            'second_wind': lambda event: self.output_logger.log(f"{self.show_name(event)} uses second wind to recover {event['value']}={event['value'].result()} hit points."),    
            'disengage': lambda event: self.output_logger.log(f"{self.show_name(event)} disengages."),
            'dodge': lambda event: self.output_logger.log(f"{self.show_name(event)} dodges."),
            'died': lambda event: self.output_logger.log(f"{self.show_name(event)} died."),
            'dash': lambda event: self.output_logger.log(f"{self.show_name(event)} {'bonus action' if event['as_bonus_action'] else ''} dashes."),
            'stand': lambda event: self.output_logger.log(f"{self.show_name(event)} stands up."),
            'prone': lambda event: self.output_logger.log(f"{self.show_name(event)} goes prone."),
            'unconscious': lambda event: self.output_logger.log(f"{self.show_name(event)} unconscious."),
            'first_aid': first_aid,
            'shove': shove,
            'attacked': attack_roll,
            'damage': damage,
            'spell_damage': spell_damage,
            'spell_miss': miss,
            'miss': miss,
            'hide': hide,
            'ice_knife': ice_knife,
            'flavor': lambda event: self.output_logger.log(self.t(f"event.flavor.{event['text']}", **event)),
            'lucky_reroll': lambda event: self.output_logger.log(f"{self.show_name(event)} uses luck to reroll from {event['old_roll']} to {event['roll']}"),
            'grapple_success': lambda event: self.output_logger.log(f"{self.show_name(event)} grapples {self.show_target_name(event)}"),            'move': lambda event: self.output_logger.log(f"{self.show_name(event)} moved to {event['position']} {event['move_cost'] * 5} feet"),
            'grapple_failed': lambda event: self.output_logger.log(f"{self.show_name(event)} failed to grapple {self.show_target_name(event)}"),
            'drop_grapple': lambda event: self.output_logger.log(f"{self.show_name(event)} drops grapple on {self.show_target_name(event)}"),
            'initiative': lambda event: self.output_logger.log(f"{self.show_name(event)} rolled initiative {event['roll']} value {event['value']}"),
            'start_of_turn': lambda event: self.output_logger.log(f"======== {self.show_name(event)} starts their turn. ========"),
            'spell_buf': lambda event: self.output_logger.log(f"{self.show_name(event)} cast {event['spell'].name} on {self.show_target_name(event)}"),
            'spell_heal': lambda event: self.output_logger.log(f"{self.show_name(event)} cast {event['spell']['name']} on {self.show_target_name(event)} and healed for {event['heal_roll']}={event['heal_roll'].result()} hit points."),
            'save_success': lambda event: self.output_logger.log(f"{self.show_name(event)} succeeded on a saving throw against DC {event['dc']} with {event['roll']}={event['roll'].result()}"),
            'save_fail': lambda event: self.output_logger.log(f"{self.show_name(event)} failed on a saving throw against {event['dc']} with {event['roll']}={event['roll'].result()}"),
            'start_of_combat': start_of_combat,
        }

        for event, handler in event_handlers.items():
            self.register_event_listener(event, handler)

    def show_name(self, event):
        return self.decorate_name(event['source'])

    def show_target_name(self, event):
        if 'source' in event:
            if event['source'] == event['target']:
                return "themselves"
        return self.decorate_name(event['target'])

    def output(self, string):
        self.output_logger.log(f"{string}")

    def decorate_name(self, entity):
        return entity.label()

    def t(self, token, **options):
        return i18n.t(token, **options)