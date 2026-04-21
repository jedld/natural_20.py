import os
from typing import List, Union
import i18n
from collections import deque
from natural20.utils.attack_util import to_advantage_str
from natural20.utils.conversation import audible_entities
from natural20.utils.gibberish import gibberish

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

    def set_event_context(self, event):
        return None

    def clear_event_context(self):
        return None

    def log(self, event_msg, event=None, visibility=None):
        print(event_msg)

class FileOutputLogger:
    """
    A simple logger that logs to a file
    """
    def __init__(self, file_path):
        self.file_path = file_path

    def set_event_context(self, event):
        return None

    def clear_event_context(self):
        return None

    def log(self, event_msg, event=None, visibility=None):
        with open(self.file_path, "a") as f:
            f.write(f"{event_msg}\n")
            f.flush()

class EventManager:
    def __init__(self, output_logger=None, output_file=None, movement_consolidation=False):
        self.event_listeners = {}
        self.battle = None
        self.event_buffer = deque(maxlen=1000)
        self.movement_consolidation = movement_consolidation

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
        def process_event(event):
            set_context = getattr(self.output_logger, 'set_event_context', None)
            clear_context = getattr(self.output_logger, 'clear_event_context', None)
            if callable(set_context):
                set_context(event)
            try:
                for handler in self.event_listeners.get(event['event'], []):
                    handler(event)
            finally:
                if callable(clear_context):
                    clear_context()

        if not self.event_listeners:
            return

        if self.movement_consolidation and event.get('event') == 'move':
            prev = getattr(self, 'previous_move_event', None)

            if prev and prev['source'] == event['source']:
                prev['position'].append(event['position'])
                prev['move_cost'] += event['move_cost']
                return
            else:
                if prev:
                    self.event_buffer.append(prev)
                    process_event(prev)

            # Initialize move event positions as a list
            event['position'] = event['path']
            self.previous_move_event = event
            return

        if getattr(self, 'previous_move_event', None):
            self.event_buffer.append(self.previous_move_event)
            process_event(self.previous_move_event)
            self.previous_move_event = None

        self.event_buffer.append(event)
        process_event(event)



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

        def handle_use_item(event):
            item = event["item"]
            # Simple log entry or any additional logic needed
            f_item = self.t(f"item.{item.name}")
            # self.output_logger.log(f"{self.show_name(event)} used {f_item} on {self.show_target_name(event)}")

        def attack_roll(event):
            msg = f"{self.show_name(event)} attacked {self.show_target_name(event)}{to_advantage_str(event)}{' with opportunity' if event['as_reaction'] else ''} with {self.t(event['attack_name'])}{'(thrown)' if event['thrown'] else ''} and hits"
            if event['as_legendary_action']:
                msg = "[legendary action] " + msg
            if event['attack_roll']:
                msg += f" with attack roll {event['attack_roll']} = {event['attack_roll'].result()}"
            if event['attack_roll'] and event['attack_roll'].nat_20():
                msg += " (critical hit)."
            if event['spell_save'] and event['spell_save'].result() < event['dc']:
                msg += f" the target failed the save with {event['spell_save']} = {event['spell_save'].result()} < DC: {event['dc']}."
            elif event['spell_save'] and event['spell_save'].result() >= event['dc']:
                msg += f" the target saved with {event['spell_save']} = {event['spell_save'].result()} > DC: {event['dc']}."
            self.output_logger.log(f"{msg}.")

        def miss(event):
            msg = f"{self.show_name(event)} tried to attack {self.show_target_name(event)}{to_advantage_str(event)}{' with opportunity' if event['as_reaction'] else ''} with {event['attack_name']}{'(thrown)' if event['thrown'] else ''}"
            if event.get('as_legendary_action'):
                msg = "[legendary action] " + msg

            if event.get('spell_save'):
                self.output_logger.log(f"{msg} but {self.show_target_name(event)} succeeded on save with {event['spell_save']} > DC: {event['dc']}.")
            else:
                self.output_logger.log(f"{msg} but missed with {event['attack_roll']}= {event['attack_roll'].result()}.")

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
                self.output_logger.log(f"{self.show_name(event)} shoves {self.show_target_name(event)} and succeeds. {rolls_description}. {self.show_target_name(event)} is now at {event['shove_loc']}")
            else:
                self.output_logger.log(f"{self.show_name(event)} shoves {self.show_target_name(event)} and fails. {rolls_description}")

        def spell_damage(event):
            if event.get('spell_save', None):
                # Handle both failed and successful saves (half damage)
                cmp = '<' if event['spell_save'].result() < event['dc'] else '>='
                self.output_logger.log(f"{self.show_name(event)} cast {event['spell']['name']} on {self.show_target_name(event)} and {'hits' if cmp=='<' else 'deals'} with {event['spell_save']}={event['spell_save'].result()} {cmp} DC: {event['dc']} for {event['damage']} damage.")
            else:
                self.output_logger.log(f"{self.show_name(event)} cast {event['spell']['name']} on {self.show_target_name(event)} and hit with {event['attack_roll']}{to_advantage_str(event)}= {event['attack_roll'].result()} for {event['damage']} damage.")

        def hide(event):
            if event['result'] == 'success':
                self.output_logger.log(f"{self.show_name(event)} successfully hides with a {event['roll']}={event['roll'].result()} stealth.")
            else:
                self.output_logger.log(f"{self.show_name(event)} tries to hide but fails. {','.join(event['reason'])}")

        def damage(event):
            if event.get('roll_info'):
                damage = event.get('value', event.get('roll_info').result())
            else:
                damage = event['value']
            keyword = ""
            if event.get('roll_info'):
                if (event.get('roll_info').result() > damage):
                    keyword = "reduced to"
                elif (event.get('roll_info').result() < damage):
                    keyword = "increased to"
                else:
                    keyword = "="
            msg = ""
            if event.get('damage_threshold_active'):
                msg += f"Damage dealt to {self.show_name(event)} is too weak to have any effect."
            if event.get('total_damage') < event.get('value'):
                msg += f" {self.show_name(event)} seems to have taken less damage than expected."
            elif event.get('total_damage') > event.get('value'):
                msg += f" {self.show_name(event)} seems to be vulnerable to {event['damage_type']} damage."

            if event.get('sneak_attack'):
                self.output_logger.log(f"{self.show_name(event)} took {event.get('roll_info','')} {keyword} {damage} {event['damage_type']} damage and {event['sneak_attack']}={event['sneak_attack'].result()} sneak attack damage. {msg}")
            else:
                self.output_logger.log(f"{self.show_name(event)} took {event.get('roll_info','')} {keyword} {damage} {event['damage_type']} damage. {msg}")

            if event.get('instant_death'):
                self.output_logger.log(f"{self.show_name(event)} died instantly.")

        def first_aid(event):
            if event['success']:
                if event['roll']:
                    self.output_logger.log(f"{self.show_name(event)} performs first aid on {self.show_target_name(event)} and stabilizes them with a {event['roll']}={event['roll'].result()} medicine check.")
                else:
                    self.output_logger.log(f"{self.show_name(event)} performs first aid on {self.show_target_name(event)} and stabilizes them using a healer's kit.")
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
                self.output_logger.log(f"{self.show_target_name(event)} passed the dexterity saving throw for ice knife. {event['roll']} >= {event['source'].spell_save_dc()}")
            else:
                self.output_logger.log(f"{self.show_target_name(event)} failed the dexterity saving throw for ice knife. {event['roll']} < {event['source'].spell_save_dc()}")

        def interact(event):
            self.output_logger.log(f"{self.show_name(event)} interacted with {self.show_target_name(event)} action [{event['object_action']}]")

        def object_interaction(event):
            actor = self.show_name(event)
            target = self.show_target_name(event)
            sub_type = str(event.get('sub_type', 'interaction')).replace('_', ' ')
            result = event.get('result')
            reason = event.get('reason')
            roll = event.get('roll')
            is_lockpick = bool(event.get('lockpick')) or (event.get('sub_type') == 'unlock' and roll is not None)

            if is_lockpick:
                if result == 'success':
                    message = f"{actor} successfully lockpicked {target}"
                else:
                    message = f"{actor} failed to lockpick {target}"

                if roll is not None:
                    message += f" with {roll} = {roll.result()}"

                if reason:
                    message += f". {reason}"
                else:
                    message += "."

                self.output_logger.log(message)
                return

            if result == 'success':
                message = f"{actor} {sub_type} on {target} succeeded"
            elif result == 'failed':
                message = f"{actor} {sub_type} on {target} failed"
            else:
                message = f"{actor} {sub_type} on {target}"

            if reason:
                message += f". {reason}"
            else:
                message += "."

            self.output_logger.log(message)

        def look(event):
            if event['advantage']:
                self.output_logger.log(f"{self.show_name(event)} looked around and rolled {event['die_roll']} = {event['die_roll'].result()} perception check with advantage [{', '.join(event['advantage'])}].")
            else:
                self.output_logger.log(f"{self.show_name(event)} looked around and rolled {event['die_roll']} = {event['die_roll'].result()} perception check.")

        def secret_door_discovered(event):
            message = event.get('message') or f"{self.show_name(event)} notices a secret door."
            self.output_logger.log(message, event=event, visibility=event.get('visibility'))

        def ability_check(event):
            if event["success"]:
                self.output_logger.log(f"{self.show_target_name(event)} {self.show_name(event)} makes a successfull {event['ability']} check and rolls {event['roll']} = {event['roll'].result()} >= DC {event['dc']}")
            else:
                self.output_logger.log(f"{self.show_target_name(event)} {self.show_name(event)} makes a failed {event['ability']} check and rolls {event['roll']} = {event['roll'].result()} < DC {event['dc']}")

        def death_save(event):
            if event['roll'].nat_20():
                self.output_logger.log(f"{self.show_name(event)} makes a death saving throw and succeeds with a critical success: {event['roll']} = {event['roll'].result()}. {event['source'].label()} is now at {event['source'].hit_points()} hit points.")
            else:
                self.output_logger.log(f"{self.show_name(event)} makes a death saving throw and succeeds: {event['roll']} = {event['roll'].result()}")

        def conversation(event):
            source = event.get('source')
            language = event.get('language', 'common')
            message = event['message']

            if event['targets']:
                prefix = f"{self.show_name(event)} to {self.show_target_name(event)}[{language}]:"
            else:
                prefix = f"{self.show_name(event)} [in {language}]:"

            # Partition nearby entities into those who understand the language and those who don't
            understands_uids = set()
            not_understands_uids = set()

            # The speaker always understands their own message
            if source and hasattr(source, 'entity_uid'):
                understands_uids.add(source.entity_uid)

            # Targeted entities
            for target in (event.get('targets') or []):
                if hasattr(target, 'entity_uid'):
                    if hasattr(target, 'languages') and language in target.languages():
                        understands_uids.add(target.entity_uid)
                    else:
                        not_understands_uids.add(target.entity_uid)

            distance_ft = event.get('distance_ft', 30)

            # Nearby entities who can hear
            if source and hasattr(source, 'session'):
                try:
                    entity_map = source.session.map_for_entity(source)
                    if entity_map:
                        nearby = audible_entities(source, entity_map, distance_ft=distance_ft, mode=event.get('volume'))
                        for audience_entry in nearby:
                            listener = audience_entry['entity']
                            if not hasattr(listener, 'entity_uid'):
                                continue
                            if hasattr(listener, 'languages') and language in listener.languages():
                                understands_uids.add(listener.entity_uid)
                            else:
                                not_understands_uids.add(listener.entity_uid)
                except Exception:
                    pass

            # Remove any entity that already understands from the not-understands set
            not_understands_uids -= understands_uids

            if not not_understands_uids:
                # Everyone understands — log normally
                self.output_logger.log(f"{prefix} {message}")
            elif not understands_uids:
                # Nobody understands — log gibberish only
                self.output_logger.log(f"{prefix} {gibberish(message, language)}")
            else:
                # Mixed — emit two scoped log entries
                understands_vis = {
                    'public': False,
                    'dm_only': False,
                    'entity_uids': sorted(str(uid) for uid in understands_uids),
                    'usernames': [],
                }
                not_understands_vis = {
                    'public': False,
                    'dm_only': False,
                    'entity_uids': sorted(str(uid) for uid in not_understands_uids),
                    'usernames': [],
                }
                self.output_logger.log(f"{prefix} {message}", visibility=understands_vis)
                self.output_logger.log(f"{prefix} {gibberish(message, language)}", visibility=not_understands_vis)

        def died(event):
            if event['source'].object():
                self.output_logger.log(f"{self.show_name(event)} is destroyed.")
            else:
                self.output_logger.log(f"{self.show_name(event)} died.")

        event_handlers = {
            'ability_check': ability_check,
            'console': lambda event: self.output_logger.log(event['message']),
            'concentration_end': lambda event: self.output_logger.log(f"{self.show_name(event)} ends concentration on {event['effect']}."),
            'conversation': conversation,
            'multiattack' : lambda event: self.output_logger.log(f"{self.show_name(event)} uses multiattack."),
            'action_surge': lambda event: self.output_logger.log(f"{self.show_name(event)} uses action surge."),
            'death_fail' : death_fail,
            'death_save': death_save,
            'damage_absorption': lambda event: self.output_logger.log(f"{self.show_name(event)} absorbs {event['damage_type']} damage and is intead healed by {event['damage']} hit points."),
            'damage_immunity': lambda event: self.output_logger.log(f"{self.show_name(event)} is unaffected by {event['damage_type']} damage."),
            'generic_failed_save': lambda event: self.output_logger.log(f"[{event['effect_description']}]: {self.show_name(event)} failed a {event['save_type']} saving throw against DC {event['dc']} with {event['roll']} = {event['roll'].result()}. {event['outcome']}"),
            'generic_success_save': lambda event: self.output_logger.log(f"[{event['effect_description']}]: {self.show_name(event)} succeeded on a {event['save_type']} saving throw against DC {event['dc']} with {event['roll']} = {event['roll'].result()}. {event.get('outcome')}"),
            'drop_concentration': lambda event: self.output_logger.log(f"{self.show_name(event)} drops concentration."),
            'concentration_check': concentration_check,
            'second_wind': lambda event: self.output_logger.log(f"{self.show_name(event)} uses second wind to recover {event['value']}={event['value'].result()} hit points."),    
            'disengage': lambda event: self.output_logger.log(f"{self.show_name(event)} disengages."),
            'dodge': lambda event: self.output_logger.log(f"{self.show_name(event)} dodges."),
            'died': died,
            'dash': lambda event: self.output_logger.log(f"{self.show_name(event)} {'bonus action' if event['as_bonus_action'] else ''} dashes."),
            'stand': lambda event: self.output_logger.log(f"{self.show_name(event)} stands up."),
            'prone': lambda event: self.output_logger.log(f"{self.show_name(event)} goes prone."),
            'unconscious': lambda event: self.output_logger.log(f"{self.show_name(event)} unconscious."),
            'first_aid': first_aid,
            'shove': shove,
            'help_distract': lambda event: self.output_logger.log(f"{self.show_name(event)} distracts {self.show_target_name(event)}."),
            'help': lambda event: self.output_logger.log(f"{self.show_name(event)} has decided to help {self.show_target_name(event)} for his next task."),
            'attacked': attack_roll,
            'damage': damage,
            'spell_damage': spell_damage,
            'spell_miss': miss,
            'miss': miss,
            'hide': hide,
            'ice_knife': ice_knife,
            'flavor': lambda event: self.output_logger.log(self.t(f"event.flavor.{event['text']}", **event)),
            'lucky_reroll': lambda event: self.output_logger.log(f"{self.show_name(event)} uses luck to reroll from {event['old_roll']} to {event['roll']}"),
            'grapple_immune': lambda event: self.output_logger.log(f"For some reason, {self.show_target_name(event)} is immune to grapple."),
            'object_interaction': object_interaction,
            'grapple_success': lambda event: self.output_logger.log(f"{self.show_name(event)} grapples {self.show_target_name(event)}"),
            'move': lambda event: self.output_logger.log(f"{self.show_name(event)} moved to {event['position']} {event['move_cost'] * 5} feet"),
            'grapple_failure': lambda event: self.output_logger.log(f"{self.show_name(event)} failed to grapple {self.show_target_name(event)}"),
            'drop_grapple': lambda event: self.output_logger.log(f"{self.show_name(event)} drops grapple on {self.show_target_name(event)}"),
            'initiative': lambda event: self.output_logger.log(f"{self.show_name(event)} rolled initiative {event['roll']} value {event['value']}"),
            'start_of_turn': lambda event: self.output_logger.log(f"======== {self.show_name(event)} starts their turn. ========"),
            'spell_buf': lambda event: self.output_logger.log(f"{self.show_name(event)} cast {event['spell'].name} on {self.show_target_name(event)}"),
            'spell_heal': lambda event: self.output_logger.log(f"{self.show_name(event)} cast {event['spell']['name']} on {self.show_target_name(event)} and healed for {event['heal_roll']}={event['heal_roll'].result()} hit points."),
            'save_success': lambda event: self.output_logger.log(f"{self.show_name(event)} succeeded on a {event['save_type']} saving throw against DC {event['dc']} with {event['roll']}={event['roll'].result()}"),
            'save_fail': lambda event: self.output_logger.log(f"{self.show_name(event)} failed on a {event['save_type']} saving throw against DC {event['dc']} with {event['roll']}={event['roll'].result()}"),
            'start_of_combat': start_of_combat,
            'use_item': handle_use_item,
            'interact': interact,
            'negative_heal': lambda event: self.output_logger.log(f"An effect is preventing {self.show_name(event)} from receiving the full amount of healing. {event['previous']} -> {event['new']}"),
            'dismiss_effect': lambda event: self.output_logger.log(f"{self.show_name(event)}: {event['effect']} effect has been dismissed."),
            'resummon_familiar': lambda event: self.output_logger.log(f"{self.show_name(event)} summons {event['familiar'].name}"),
            'dismiss_familiar': lambda event: self.output_logger.log(f"{self.show_name(event)} dismisses {event['familiar'].name}"),
            'find_familiar': lambda event: self.output_logger.log(f"{self.show_name(event)} creates a familiar {event['familiar'].name}"),
            'look': look,
            'message': lambda event: self.output_logger.log(f"{self.show_name(event)}: {event['message']}"),
            'secret_door_discovered': secret_door_discovered,
            # New event handlers:
            'lockpick_success': lambda event: self.output_logger.log(
                f"{self.show_name(event)} unlocked the door using lockpick. Roll: {event['roll']}"
            ),
            'lockpick_fail': lambda event: self.output_logger.log(
                f"{self.show_name(event)} failed lockpicking. Roll: {event['roll']}. Thieves tools deducted."
            ),
            'unlock': lambda event: self.output_logger.log(
                f"{self.show_name(event)} unlocked the door. Reason: {event.get('reason', 'No reason provided')}"
            )
            ,
            'thunderwave_push': lambda event: self.output_logger.log(
                f"{self.show_target_name(event)} is pushed by thunderwave to {event.get('position')}" if event.get('position') else f"{self.show_name(event)} resisted being moved by thunderwave."
            )
        }

        for event, handler in event_handlers.items():
            self.register_event_listener(event, handler)

    def show_name(self, event):
        return self.decorate_name(event['source'])

    def show_target_name(self, event):
        if 'targets' in event:
            return ", ".join([self.decorate_name(target) for target in event['targets']])

        if 'source' in event:
            if event['source'] == event['target']:
                return "themselves"
        return self.decorate_name(event['target'])

    def output(self, string):
        self.output_logger.log(f"{string}")

    def decorate_name(self, entity):
        if isinstance(entity, tuple) or isinstance(entity, list):
            decorated_names = [self.decorate_name(e) for e in entity]
            if not decorated_names:
                return ""
            elif len(decorated_names) == 1:
                return decorated_names[0]
            else:
                return ", ".join(decorated_names[:-1]) + " and " + decorated_names[-1]
        return entity.label()

    def t(self, token, **options):
        return i18n.t(token, **options)