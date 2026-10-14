import re
import os
from contextlib import contextmanager
from typing import List, Union
import i18n
from collections import deque
from natural20.utils.attack_util import to_advantage_str
from natural20.utils.conversation import audible_entities
from natural20.utils.gibberish import gibberish


def format_pickpocket_roll_text(event):
    """Format Sleight of Hand vs passive Insight for combat-log pickpocket lines."""
    roll = event.get('roll')
    passive = event.get('passive_insight')
    roll_total = event.get('roll_total')
    roll_breakdown = event.get('roll_breakdown')

    expr = None
    if roll is not None:
        try:
            total = roll.result()
            expr = str(roll)
            if total is not None and str(total) not in expr:
                expr = f"{expr} = {total}"
        except Exception:
            expr = roll_breakdown or (str(roll_total) if roll_total is not None else str(roll))
    elif roll_total is not None:
        if roll_breakdown:
            expr = str(roll_breakdown)
            if str(roll_total) not in expr:
                expr = f"{expr} = {roll_total}" if '=' not in expr else expr
        else:
            expr = str(roll_total)

    if not expr:
        return ''

    text = f" (Sleight of Hand {expr}"
    if passive is not None:
        text += f" vs passive Insight {passive}"
    text += ')'
    return text

def _spell_label(spell):
    """Display name for a spell object, YAML dict or id."""
    label = getattr(spell, 'label', None)
    if callable(label):
        try:
            return label()
        except Exception:
            pass
    if isinstance(spell, dict):
        return spell.get('label') or spell.get('name') or 'spell'
    return getattr(spell, 'name', None) or str(spell)


def _roll_vs_dc(event, roll_key='roll'):
    """``(1d20+3=15 vs DC 14)`` for a save/check event; ``(auto-fail)`` without a roll."""
    roll = event.get(roll_key)
    if roll is None:
        return '(auto-fail)'
    try:
        return f"({roll}={roll.result()} vs DC {event.get('dc')})"
    except Exception:
        return f"({roll} vs DC {event.get('dc')})"


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

    @contextmanager
    def deferring(self, event_types):
        """Hold back *event_types* raised inside the block and dispatch them,
        in order, when it exits (e.g. "X falls unconscious" after the damage
        line that caused it)."""
        stack = self.__dict__.setdefault('_deferred', [])
        frame = (frozenset(event_types), [])
        stack.append(frame)
        try:
            yield
        finally:
            stack.remove(frame)
            for queued in frame[1]:
                self.received_event(queued)

    def received_event(self, event):
        deferred = self.__dict__.get('_deferred')
        if deferred and event.get('event') in deferred[-1][0]:
            deferred[-1][1].append(event)
            return

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
                steps = list(event.get('path') or [event['position']])
                if prev['position'] and steps and list(steps[0]) == list(prev['position'][-1]):
                    steps = steps[1:]
                prev['position'].extend(steps)
                prev['move_cost'] += event['move_cost']
                return
            else:
                if prev:
                    self.event_buffer.append(prev)
                    process_event(prev)

            # Initialize move event positions as a list
            event['position'] = list(event['path'])
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
            label = item.label() if hasattr(item, 'label') else str(getattr(item, 'name', 'an item'))
            msg = f"{self.show_name(event)} uses {label}"
            if event.get('target') is not None:
                msg += f" on {self.show_target_name(event)}"
            roll = event.get('hp_gain_roll')
            if roll is not None:
                msg += f", regaining {roll} = {roll.result()} hit points"
            temp_roll = event.get('temp_hp_roll')
            if temp_roll is not None:
                msg += f", gaining {temp_roll} = {temp_roll.result()} temporary hit points"
            self.output_logger.log(msg + ".")

        def attack_roll(event):
            msg = f"{self.show_name(event)} attacked {self.show_target_name(event)}{to_advantage_str(event)}{' with opportunity' if event['as_reaction'] else ''} with {self.attack_label(event['attack_name'])}{'(thrown)' if event['thrown'] else ''} and hits"
            if event['as_legendary_action']:
                msg = "[legendary action] " + msg
            if event['attack_roll']:
                msg += f" with attack roll {event['attack_roll']} = {event['attack_roll'].result()}"
            if event.get('critical') or (event['attack_roll'] and event['attack_roll'].nat_20()):
                msg += " (critical hit)"
            if event['spell_save'] and event['spell_save'].result() < event['dc']:
                msg += f" the target failed the save with {event['spell_save']} = {event['spell_save'].result()} < DC: {event['dc']}."
            elif event['spell_save'] and event['spell_save'].result() >= event['dc']:
                msg += f" the target saved with {event['spell_save']} = {event['spell_save'].result()} > DC: {event['dc']}."
            self.output_logger.log(f"{msg}.")

        def miss(event):
            msg = f"{self.show_name(event)} tried to attack {self.show_target_name(event)}{to_advantage_str(event)}{' with opportunity' if event['as_reaction'] else ''} with {self.attack_label(event['attack_name'])}{'(thrown)' if event['thrown'] else ''}"
            if event.get('as_legendary_action'):
                msg = "[legendary action] " + msg

            if event.get('spell_save'):
                save = event['spell_save']
                cast = f"{self.show_name(event)} cast {self.attack_label(event['attack_name'])} on {self.show_target_name(event)}"
                if event.get('as_legendary_action'):
                    cast = "[legendary action] " + cast
                self.output_logger.log(f"{cast} but {self.show_target_name(event)} succeeded on the save with {save} = {save.result()} >= DC {event['dc']}.")
            elif event.get('attack_roll') is None:
                # The spell never got to a roll: an invalid target or area.
                target = event.get('spell_target')
                target_name = self.decorate_name(target) if target is not None else None
                reasons = {
                    'not_humanoid': f"{target_name or 'the target'} is not a humanoid",
                    'immune': f"{target_name or 'the target'} is immune",
                    'no_target': 'there was no valid target',
                    'no_targets': 'there was no valid target',
                    'targets_too_far_apart': 'the targets are too far apart',
                    'invalid_area': 'the area is not valid',
                    'no_recent_corpse': 'there is no recently dead creature there',
                }
                reason = reasons.get(event.get('message') or '', 'the spell had no valid target')
                self.output_logger.log(f"{self.show_name(event)} cast {self.attack_label(event['attack_name'])} "
                                       f"but it has no effect: {reason}.")
            else:
                self.output_logger.log(f"{msg} but missed with {event['attack_roll']}= {event['attack_roll'].result()}.")

        def blind_miss(event):
            x, y = event['square']
            msg = (f"{self.show_name(event)} attacked an unseen spot at [{x}, {y}] with {self.attack_label(event['attack_name'])}"
                   f"{'(thrown)' if event.get('thrown') else ''}{' as a reaction' if event.get('as_reaction') else ''}"
                   f" (disadvantage) and missed with {event['attack_roll']}= {event['attack_roll'].result()}.")
            if event.get('as_legendary_action'):
                msg = "[legendary action] " + msg
            self.output_logger.log(msg)

        def mirror_image_duplicate(event):
            target = self.show_target_name(event)
            roll = event.get('roll')
            attack_roll = event.get('attack_roll')
            msg = f"{self.show_name(event)} attacked {target}"
            if event.get('attack_name'):
                msg += f" with {self.attack_label(event['attack_name'])}"
            if attack_roll is not None:
                msg += f" ({attack_roll} = {attack_roll.result()})"
            if event.get('model') == 'd6_on_hit':
                msg += (f" and hit, but one of {target}'s Mirror Image duplicates took the blow instead"
                        f" (duplicate roll {roll}, a {event.get('threshold')}+ on any die).")
            elif event.get('destroyed'):
                msg += (f" but struck one of {target}'s Mirror Image duplicates instead"
                        f" (duplicate roll {roll} = {roll.result()} >= {event.get('threshold')}).")
            else:
                msg += (f" but was drawn to one of {target}'s Mirror Image duplicates"
                        f" (duplicate roll {roll} = {roll.result()} >= {event.get('threshold')})"
                        f" and missed it (duplicate AC {event.get('duplicate_ac')}).")
            remaining = int(event.get('remaining') or 0)
            if event.get('destroyed'):
                msg += (" The duplicate vanishes; Mirror Image ends." if remaining <= 0
                        else f" The duplicate vanishes ({remaining} left).")
            if event.get('as_legendary_action'):
                msg = "[legendary action] " + msg
            self.output_logger.log(msg)

        def concentration_check(event):
            roll = event['roll']
            if event['result'] == 'success' and (getattr(roll, 'metadata', None) or {}).get('legendary_resistance'):
                self.output_logger.log(f"{self.show_name(event)} keeps concentration through Legendary Resistance.")
            elif event['result'] == 'success':
                self.output_logger.log(f"{self.show_name(event)} makes a concentration check and succeeds: {event['roll']} >= {event['dc']}")
            else:
                self.output_logger.log(f"{self.show_name(event)} makes a concentration check and fails: {event['roll']} < {event['dc']}")

        def death_fail(event):
            if event.get('roll'):
                self.output_logger.log(f"{self.show_name(event)} failed a death saving throw: {event['roll']} = {event['roll'].result()}")
            else:
                self.output_logger.log(f"{self.show_name(event)} received damage that caused a death saving throw failure.")

        def shove(event):
            if event.get('save_dc') is not None:
                rolls_description = f"Shove save: {event['target_roll']} vs DC {event['save_dc']}"
            else:
                rolls_description = f"Contested check for shove: {event['source_roll']} vs {event['target_roll']}"
            target_name = self.show_target_name(event)
            if event.get('success'):
                if event.get('knock_prone'):
                    outcome = f"{target_name} is knocked prone"
                elif event.get('shove_loc'):
                    outcome = f"{target_name} is now at {event['shove_loc']}"
                else:
                    outcome = f"{target_name} could not be pushed"
                self.output_logger.log(f"{self.show_name(event)} shoves {target_name} and succeeds. {rolls_description}. {outcome}")
            else:
                self.output_logger.log(f"{self.show_name(event)} shoves {target_name} and fails. {rolls_description}")

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

        def pickpocket(event):
            actor = self.show_name(event)
            target = self.show_target_name(event)
            item_label = event.get('item_label') or event.get('item_name') or 'an item'
            roll_text = format_pickpocket_roll_text(event)
            stolen = event.get('stolen', True)
            suffix = '' if stolen else ' (item was not in inventory)'
            self.output_logger.log(
                f"{actor} pickpockets {item_label} from {target}{roll_text}.{suffix}"
            )

        def pickpocket_failed(event):
            actor = self.show_name(event)
            target = self.show_target_name(event)
            item_label = event.get('item_label') or event.get('item_name') or 'an item'
            reason = event.get('reason')
            roll_text = format_pickpocket_roll_text(event)

            if reason == 'target_out_of_range':
                message = f"{actor} cannot pickpocket {item_label} from {target} — target is too far away."
            elif reason == 'item_not_found':
                message = f"{actor} cannot find {item_label} on {target}."
            elif reason == 'item_not_stealable':
                message = (
                    f"{actor} cannot pickpocket {item_label} from {target} "
                    f"— the item is too large or unavailable."
                )
            elif reason == 'pc_to_pc_disabled':
                message = (
                    f"{actor}'s pickpocket attempt on {target} is blocked "
                    f"(PC-to-PC pickpocket disabled)."
                )
            elif reason == 'detection':
                message = (
                    f"{actor} is caught trying to pickpocket {item_label} from {target}"
                    f"{roll_text}."
                )
            elif event.get('message'):
                message = str(event['message']).rstrip('.') + '.'
            else:
                message = f"{actor} fails to pickpocket {item_label} from {target}{roll_text}."

            self.output_logger.log(message)

        def damage(event):
            roll_info = event.get('roll_info')
            if not hasattr(roll_info, 'result'):
                roll_info = None
            if roll_info is not None:
                damage = event.get('value', roll_info.result())
            else:
                damage = event['value']
            keyword = ""
            sneak_attack = event.get('sneak_attack')
            if roll_info is not None:
                # ``value`` already includes any Sneak Attack dice.
                rolled = roll_info.result() + (sneak_attack.result() if hasattr(sneak_attack, 'result') else 0)
                if (rolled > damage):
                    keyword = "reduced to"
                elif (rolled < damage):
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

            if roll_info and sneak_attack:
                breakdown = f"{roll_info} + {sneak_attack} sneak attack {keyword} "
            elif roll_info:
                breakdown = f"{roll_info} {keyword} "
            else:
                breakdown = ""
            self.output_logger.log(f"{self.show_name(event)} took {breakdown}{damage} {event['damage_type']} damage. {msg}".rstrip())

            if event.get('instant_death'):
                self.output_logger.log(f"{self.show_name(event)} died instantly.")

        def first_aid(event):
            if event.get('spell'):
                self.output_logger.log(f"{self.show_name(event)} casts {event['spell']} on {self.show_target_name(event)} and stabilizes them.")
                return
            if event['success']:
                if event.get('roll'):
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
            from natural20.utils.combat_roster import start_of_combat_lines
            battle = event.get('battle') or self.battle
            for line in start_of_combat_lines(battle, event.get('combat_order')):
                self.output_logger.log(line, event=event, visibility='dm')
            from natural20.utils.combat_roster import party_briefings
            for briefing in party_briefings(battle, event.get('combat_order')):
                visibility = {'kind': 'entities', 'entity_uids': briefing['entity_uids']}
                for line in briefing['lines']:
                    self.output_logger.log(line, event=event, visibility=visibility)

        def start_of_turn(event):
            self.output_logger.log(f"======== {self.show_name(event)} starts their turn. ========")

        def turn_status(event):
            from natural20.utils.combat_roster import turn_status_line
            line = turn_status_line(event.get('battle') or self.battle, event.get('source'))
            if line:
                self.output_logger.log(line, event=event, visibility='dm')

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
            # Massive damage is reported by the damage line ("died instantly").
            if (event.get('death_info') or {}).get('cause') == 'massive_damage':
                return
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
            'legendary_resistance': lambda event: self.output_logger.log(f"{self.show_name(event)} fails a {event['save_type']} saving throw ({event['roll'].result()} vs DC {event['dc']}) but uses Legendary Resistance to succeed instead ({event['remaining']} left today)."),
            'forced_push': lambda event: self.output_logger.log(
                f"{self.decorate_name(event.get('target'))} is pushed {event.get('distance')} feet away from {self.show_name(event)}."),
            'taunt': lambda event: self.output_logger.log(
                f"{self.show_name(event)} taunts {self.show_name({'source': event['target']}) if event.get('target') is not None else 'nobody'}"
                + (" but they can't hear it" if event.get('no_effect') else
                   f" (save {event['roll'].result()} vs DC {event['dc']}): "
                   + ("they are goaded into attacking the taunter" if event.get('taunted') else "they shrug it off")
                   if event.get('roll') is not None else '')
                + "."),
            'class_feature_action': lambda event: self.output_logger.log(
                f"{self.show_name(event)} uses {event.get('label')}"
                + (f" and gains {event['temp_hp']} temporary hit points" if event.get('temp_hp') else '')
                + (f" and regains {event['restored_slots']} spell slot(s)" if event.get('restored_slots') else '')
                + "."),
            'hit_reaction': lambda event: self.output_logger.log(
                f"{self.show_name(event)} uses {event['label']} as a reaction"
                + (f" (spending a level {event['slot_level']} spell slot)" if event.get('slot_level') else '') + "."),
            'reaction_cast': lambda event: self.output_logger.log(
                f"{self.show_name(event)} casts {event.get('spell')} as a reaction."),
            'spell_rider': lambda event: self.output_logger.log(
                f"{event['rider']}: "
                + (f"{self.show_name({'source': event['target']})} " if event.get('target') is not None else f"{self.show_name(event)} ")
                + (f"rolls {event['roll'].result()} vs DC {event['dc']} and " if event.get('roll') is not None else '')
                + f"{event.get('message', '')}."),
            'save_auto_success': lambda event: self.output_logger.log(f"{self.show_name(event)} fails a {event['save_type']} saving throw ({event['roll'].result()} vs DC {event['dc']}) but uses {str(event['feature']).replace('_', ' ').title()} to succeed instead."),
            'regeneration': lambda event: self.output_logger.log(f"{self.show_name(event)} regenerates {event['value']} hit points."),
            'regeneration_blocked': lambda event: self.output_logger.log(f"{self.show_name(event)} cannot regenerate this turn ({str(event['reason']).replace('_', ' ')})."),
            'misty_escape': lambda event: self.output_logger.log(f"{self.show_name(event)} drops to 0 hit points and dissolves into a cloud of mist, escaping toward its resting place."),
            'misty_escape_failed': lambda event: self.output_logger.log(f"{self.show_name(event)} cannot turn to mist ({str(event['reason']).replace('_', ' ')}) and is destroyed!"),
            'misty_escape_recovered': lambda event: self.output_logger.log(f"{self.show_name(event)} regains 1 hit point in its resting place."),
            'polymorph': lambda event: self.output_logger.log(f"{self.show_name(event)} is transformed into a {str(event.get('form')).replace('_', ' ')}."),
            'polymorph_end': lambda event: self.output_logger.log(
                f"{self.show_name(event)} reverts to their normal form"
                + (" as the beast form drops to 0 hit points." if event.get('reason') == 'dropped_to_zero' else ".")),
            'polymorph_unaffected': lambda event: self.output_logger.log(f"Polymorph has no effect on {self.show_target_name(event)} ({str(event.get('reason')).replace('_', ' ')})."),
            'wild_shape_revert': lambda event: self.output_logger.log(f"{self.show_name(event)} reverts from Wild Shape to their normal form."),
            'additional_damage': lambda event: self.output_logger.log(f"{self.show_target_name(event)} takes {event['value']} additional {event['damage_type']} damage from {self.show_name(event)}'s {self.attack_label(event['attack_name'])}."),
            'undead_fortitude': lambda event: self.output_logger.log(
                f"{self.show_name(event)} {'clings to unlife and stays at 1 HP' if event.get('success') else 'fails to cling to unlife'} "
                f"(Undead Fortitude, CON save {event['roll']} vs DC {event['dc']})."),
            'save_assist': lambda event: self.output_logger.log(
                f"{self.show_name(event)} uses {str(event.get('feature') or 'a reaction').replace('_', ' ').title()} to add +{event.get('bonus')} to {self.show_target_name(event)}'s {event.get('save_type')} saving throw ({event['roll'].result()} vs DC {event.get('dc')})."),
            'rest_items': lambda event: self.output_logger.log(
                f"{self.show_name(event)} prepares {', '.join(str(i).replace('_', ' ') for i in event.get('items') or [])}."),
            'craft_item': lambda event: self.output_logger.log(
                f"{self.show_name(event)} creates {str(event.get('item')).replace('_', ' ')}" + (f" using a level {event['slot_level']} spell slot." if event.get('slot_level') else ".")),
            'no_healing': lambda event: self.output_logger.log(f"{self.show_target_name(event)} can't regain hit points until {self.show_name(event)}'s next turn."),
            'thrown_item_hit': lambda event: self.output_logger.log(
                f"{self.show_name(event)} throws {event.get('item_label', 'a flask')} at {self.show_target_name(event)} and hits"
                + (f" with attack roll {event['attack_roll']} = {event['attack_roll'].result()}." if event.get('attack_roll') is not None else ".")),
            'thrown_item_miss': lambda event: self.output_logger.log(
                f"{self.show_name(event)} throws {event.get('item_label', 'a flask')} at {self.show_target_name(event)} and misses"
                + (f" with attack roll {event['attack_roll']} = {event['attack_roll'].result()}." if event.get('attack_roll') is not None else ".")),
            'burning': lambda event: self.output_logger.log(f"{self.show_target_name(event)} catches fire ({event.get('damage')} {event.get('damage_type')} damage at the start of each of its turns)."),
            'burning_damage': lambda event: self.output_logger.log(f"{self.show_name(event)} burns for {event['roll']} = {event['value']} {event.get('damage_type', 'fire')} damage."),
            'burning_extinguished': lambda event: self.output_logger.log(
                f"{self.show_name(event)} puts out the flames on {self.show_target_name(event)}."
                if event.get('source') is not event.get('target')
                else f"{self.show_name(event)} puts out the flames."),
            'extinguish_failed': lambda event: self.output_logger.log(
                f"{self.show_name(event)} fails to put out the flames on {self.show_target_name(event)} "
                f"(Dexterity check {event['roll']} = {event['roll'].result()} vs DC {event['dc']})."),
            'life_drain': lambda event: self.output_logger.log(f"{self.show_name(event)} drains {event['value']} life from {self.show_target_name(event)}: its hit point maximum is reduced and {self.show_name(event)} regains that many hit points."),
            'grappled_on_hit': lambda event: self.output_logger.log(f"{self.show_name(event)} grapples {self.show_target_name(event)} (escape DC {event['escape_dc']}) instead of dealing {event['damage_type']} damage."),
            'charmed': lambda event: self.output_logger.log(f"{self.show_target_name(event)} is charmed by {self.show_name(event)}."),
            'charm_ended': lambda event: self.output_logger.log(f"{self.show_target_name(event)} is no longer charmed by {self.show_name(event)}."),
            'frightened': lambda event: self.output_logger.log(f"{self.show_target_name(event)} is frightened of {self.show_name(event)}."),
            'fear_ended': lambda event: self.output_logger.log(f"{self.show_target_name(event)} is no longer frightened of {self.show_name(event)}."),
            'attack_option_armed': lambda event: self.output_logger.log(f"{self.show_name(event)} readies {event.get('option')} for their next weapon attack."),
            'attack_option_hit': lambda event: self.output_logger.log(
                f"{self.show_name(event)} uses {event.get('option')} on {self.show_target_name(event)}"
                + (f": DC {event.get('dc')} save, rolled {event['roll'].result()} ({'success' if event.get('success') else 'failure'})" if event.get('roll') is not None else '')
                + (f" — {str(event.get('outcome')).replace('_', ' ')}." if event.get('outcome') else '.')),
            'sacred_weapon': lambda event: self.output_logger.log(f"{self.show_name(event)} channels divinity into their weapon: +{event.get('bonus')} to attack rolls and it glows with holy light."),
            'abjure_foes': lambda event: self.output_logger.log(
                f"{self.show_name(event)} uses Abjure Foes but no foes are affected." if event.get('target') is None
                else f"{self.show_target_name(event)} {'resists' if event.get('success') else 'fails to resist'} {self.show_name(event)}'s Abjure Foes (DC {event.get('dc')}, rolled {event['roll'].result() if event.get('roll') is not None else '-'})."),
            'generic_failed_save': lambda event: self.output_logger.log(f"[{event['effect_description']}]: {self.show_name(event)} failed a {event['save_type']} saving throw against DC {event['dc']} with {event['roll']} = {event['roll'].result()}. {event['outcome']}"),
            'generic_success_save': lambda event: self.output_logger.log(f"[{event['effect_description']}]: {self.show_name(event)} succeeded on a {event['save_type']} saving throw against DC {event['dc']} with {event['roll']} = {event['roll'].result()}. {event.get('outcome')}"),
            'drop_concentration': lambda event: self.output_logger.log(f"{self.show_name(event)} drops concentration."),
            'concentration_check': concentration_check,
            'second_wind': lambda event: self.output_logger.log(f"{self.show_name(event)} uses second wind to recover {event['value']}={event['value'].result()} hit points."),    
            'disengage': lambda event: self.output_logger.log(f"{self.show_name(event)} disengages."),
            'disarm': lambda event: self.output_logger.log(f"{self.show_name(event)} disarms {self.show_target_name(event)} of {event.get('item')}."),
            'uncanny_dodge': lambda event: self.output_logger.log(f"{self.show_name(event)} uses Uncanny Dodge."),
            'arcane_ward_absorb': lambda event: self.output_logger.log(
                f"{self.show_name(event)}'s Arcane Ward absorbs {event.get('damage')} damage ({event.get('remaining')} left)."),
            'turn_status': turn_status,
            'dodge': lambda event: self.output_logger.log(f"{self.show_name(event)} dodges."),
            'died': died,
            'summon_called': lambda event: self.output_logger.log(
                f"{self.show_name(event)} uses {event.get('summon_label', 'a summon')}, calling "
                f"{event.get('count')} {event.get('npc_label')}"
                + (f" (arriving in {event['arrival_rounds']} rounds)." if event.get('arrival_rounds') else ".")),
            'summons_arrived': lambda event: self.output_logger.log(
                f"{event.get('count')} {event.get('npc_label')} answer the call of {self.show_name(event)}."),
            'summons_dismissed': lambda event: self.output_logger.log(
                f"{event.get('count')} creature(s) summoned by {self.show_name(event)} depart"
                + (f" ({event['reason']})." if event.get('reason') else ".")),
            'animated_remains_restored': lambda event: self.output_logger.log(
                f"{self.show_name(event)} collapses, leaving the body of {self.show_target_name(event)}."),
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
            'blind_miss': blind_miss,
            'mirror_image_duplicate': mirror_image_duplicate,
            'hide': hide,
            'pickpocket': pickpocket,
            'pickpocket_failed': pickpocket_failed,
            'ice_knife': ice_knife,
            'flavor': lambda event: self.output_logger.log(self.t(f"event.flavor.{event['text']}", **event)),
            'lucky_reroll': lambda event: self.output_logger.log(f"{self.show_name(event)} uses luck to reroll from {event['old_roll']} to {event['roll']}"),
            'luck_point': lambda event: self.output_logger.log(
                f"{self.show_name(event)} spends a luck point "
                + (f"to roll {str(event.get('roll_kind') or 'the roll').replace('_', ' ')} with advantage: {event['old_roll']} -> {event['roll']} = {event['roll'].result()} vs {event.get('dc')}"
                   if event.get('mode') == 'advantage' else
                   f"to give {self.show_target_name(event)}'s attack disadvantage: {event['old_roll']} -> {event['roll']} = {event['roll'].result()} vs AC {event.get('dc')}")
                + f" ({event.get('remaining')} left)."),
            'grapple_immune': lambda event: self.output_logger.log(f"For some reason, {self.show_target_name(event)} is immune to grapple."),
            'room_service_buzz': lambda event: self.output_logger.log(
                event.get('message')
                or f"{self.show_name(event)} rang the room-service buzzer ({event.get('room_label', 'guest room')})."
            ),
            'object_interaction': object_interaction,
            'grapple_success': lambda event: self.output_logger.log(f"{self.show_name(event)} grapples {self.show_target_name(event)}"),
            'move': lambda event: self.output_logger.log(
                f"{self.show_name(event)} is dragged to {event['position']} by {getattr(event['dragged_by'], 'name', event['dragged_by'])}"
                if event.get('dragged_by') is not None else
                f"{'[legendary action] ' if event.get('as_legendary_action') else ''}{self.show_name(event)} moved to {event['position']} {event['move_cost'] * 5} feet"),
            'grapple_failure': lambda event: self.output_logger.log(f"{self.show_name(event)} failed to grapple {self.show_target_name(event)}"),
            'drop_grapple': lambda event: self.output_logger.log(
                f"{self.show_name(event)} drops grapple on {self.show_target_name(event)}"
                + (f" ({event['reason']})" if event.get('reason') else "")),
            'initiative': lambda event: self.output_logger.log(f"{self.show_name(event)} rolled initiative {event['roll']} value {event['value']}"),
            'start_of_turn': start_of_turn,
            'detect_magic': lambda event: self.output_logger.log(
                f"{self.show_name(event)} senses magic within {event.get('range_ft', 30)} feet."
            ),
            'silvery_barbs_reroll': lambda event: self.output_logger.log(
                f"{self.show_name(event)} casts {event.get('spell_label', 'Silvery Barbs')} on "
                f"{self.decorate_name(event['target'])}: forces a reroll "
                f"({event.get('old_roll')} → {event.get('new_roll')}"
                f"{', using the lower result' if event.get('replaced') else ', keeping the lower original result'})."
            ),
            'counterspell': lambda event: self.output_logger.log(
                f"{self.show_name(event)} casts {event.get('spell_label', 'Counterspell')} at "
                f"{self.show_target_name(event)}"
                + (f" with a level {event['cast_level']} slot (target spell level {event['target_spell_level']})"
                   if event.get('resolution') == 'auto_at_or_above' and event.get('cast_level') is not None else "")
                + (f", spellcasting check {event['roll']} = {event['roll'].result()} vs DC {event['dc']}"
                   if event.get('resolution') == 'ability_check' and event.get('roll') is not None else "")
                + (": it succeeds." if event.get('success') else ": it fails.")
            ),
            'wrath_of_the_storm': lambda event: self.output_logger.log(
                f"{self.show_name(event)} uses Wrath of the Storm on {self.show_target_name(event)}: "
                f"Dexterity save {event.get('save_roll')} vs DC {event.get('save_dc')} "
                f"{'succeeds' if event.get('save_success') else 'fails'}, "
                f"{event.get('damage')} {event.get('damage_type')} damage."
            ),
            'giant_ancestry': lambda event: self.output_logger.log(
                f"{self.show_name(event)} uses {event.get('label', 'Giant Ancestry')} on {self.show_target_name(event)}"
                + {
                    'frosts_chill': ", slowing it by 10 feet.",
                    'hills_tumble': ", knocking it prone.",
                }.get(event.get('feature'), ".")
            ),
            'stones_endurance': lambda event: self.output_logger.log(
                f"{self.show_name(event)} uses Stone's Endurance ({event['roll']} = {event['roll'].result()}), "
                f"reducing the damage by {event.get('reduced')}."
            ),
            'storms_thunder': lambda event: self.output_logger.log(
                f"{self.show_name(event)} answers with Storm's Thunder, dealing {event.get('damage')} "
                f"thunder damage to {self.show_target_name(event)}."
            ),
            'clouds_jaunt': lambda event: self.output_logger.log(
                f"{self.show_name(event)} uses Cloud's Jaunt and teleports to {event.get('position')}."
            ),
            'large_form': lambda event: self.output_logger.log(f"{self.show_name(event)} grows to Large size (Large Form)."),
            'large_form_end': lambda event: self.output_logger.log(f"{self.show_name(event)} returns to normal size."),
            'dispel_magic': lambda event: self.output_logger.log(
                f"{self.show_name(event)} casts Dispel Magic on {self.show_target_name(event)}"
                + (f" with a level {event['cast_level']} slot" if event.get('cast_level') else "")
                + (": " + "; ".join(
                    f"{o['label']} (level {o['level']}) "
                    + ("ends" if o['ended'] else "holds")
                    + (f" (check {o['roll']} = {o['roll'].result()} vs DC {o['dc']})" if o.get('roll') is not None else "")
                    for o in event['outcomes']) + "."
                   if event.get('outcomes') else ": no spells to dispel.")
            ),
            'spell_countered': lambda event: self.output_logger.log(
                f"{self.show_name(event)} counters {self.decorate_name(event['target'])}'s "
                f"{event.get('spell_label', 'spell')}! The spell fails and has no effect."
            ),
            'silvery_barbs_advantage': lambda event: self.output_logger.log(
                f"{self.show_name(event)} grants advantage on the next roll to "
                f"{self.show_target_name(event)} ({event.get('spell_label', 'Silvery Barbs')})."
            ),
            'spell_buf': lambda event: self.output_logger.log(f"{self.show_name(event)} cast {_spell_label(event['spell'])} on {self.show_target_name(event)}"),
            'spell_debuff': lambda event: self.output_logger.log(
                f"{self.show_name(event)} cast {event['spell'].label() if hasattr(event.get('spell'), 'label') else (event['spell'].name if hasattr(event.get('spell'), 'name') else event.get('spell'))} on {self.show_target_name(event)}"
            ),
            'spell_heal': lambda event: self.output_logger.log(f"{self.show_name(event)} cast {event['spell']['name']} on {self.show_target_name(event)} and healed for {event['heal_roll']}={event['heal_roll'].result()} hit points."),
            'save_success': lambda event: self.output_logger.log(f"{self.show_name(event)} succeeded on a {event['save_type']} saving throw against DC {event['dc']} with {event['roll']}={event['roll'].result()}"),
            'save_fail': lambda event: self.output_logger.log(f"{self.show_name(event)} failed on a {event['save_type']} saving throw against DC {event['dc']} with {event['roll']}={event['roll'].result()}"),
            'start_of_combat': start_of_combat,
            'use_item': handle_use_item,
            'interact': interact,
            'negative_heal': lambda event: self.output_logger.log(f"An effect is preventing {self.show_name(event)} from receiving the full amount of healing. {event['previous']} -> {event['new']}"),
            'condition_spell_end': lambda event: self.output_logger.log(
                f"{self.show_target_name(event)} is no longer affected by {_spell_label(event.get('spell'))}"
                + {'saved': ' (saved).', 'damaged': ' (took damage).'}.get(event.get('reason'), '.')
            ),
            'effect_ended': lambda event: self.output_logger.log(
                f"{self.show_target_name(event)} is no longer {str(event.get('effect_name', 'affected')).replace('_', ' ')}."
            ),
            'off_plane': lambda event: self.output_logger.log(
                f"{self.show_target_name(event)} vanishes from this plane"
                f" ({str(event.get('reason') or 'away').replace('_', ' ')})."
            ),
            'returned_to_plane': lambda event: self.output_logger.log(
                f"{self.show_target_name(event)} reappears."
            ),
            'blink_roll': lambda event: self.output_logger.log(
                f"{self.show_name(event)} rolls {event['roll']}={event['roll'].result()} for Blink"
                + (" and blinks out to the Ethereal Plane." if event.get('vanished') else " and stays.")
            ),
            'detect_creatures': lambda event: self.output_logger.log(
                f"{self.show_name(event)} ({_spell_label(event.get('spell'))}) senses "
                + (", ".join(f"{f['name']} ({'/'.join(f.get('types') or []) or 'creature'})"
                             for f in event.get('found') or []) or "nothing")
                + " nearby."
            ),
            'contact_other_plane': lambda event: self.output_logger.log(
                f"{self.show_name(event)} contacts an otherworldly entity"
                + (f" and may ask up to {event.get('questions', 5)} questions." if event.get('success')
                   else " and the contact overwhelms their mind!")
            ),
            'hazard_save': lambda event: self.output_logger.log(
                f"{event.get('label', 'Hazard')}: {self.show_target_name(event)} "
                + (f"rolls {event['save_roll']}={event['save_roll'].result()} "
                   if event.get('save_roll') is not None else "")
                + f"on a DC {event.get('dc')} {event.get('save', '')} save"
                + (" (success)" if event.get('saved') else " (failure)")
                + f" and takes {event.get('damage')} {event.get('damage_type', '')} damage."
            ),
            'mechanism_rotated': lambda event: self.output_logger.log(
                f"{self.show_name(event)} turns {event.get('label', 'the mechanism')} to face "
                f"{event.get('facing')}"
                + (f" (combined Strength {event['combined_strength']})."
                   if event.get('combined_strength') else
                   f" (Strength check {event['roll']}={event['roll'].result()})."
                   if event.get('roll') is not None else ".")
            ),
            'mechanism_rotate_failed': lambda event: self.output_logger.log(
                f"{self.show_name(event)} strains but cannot turn {event.get('label', 'the mechanism')}"
                + (f" (Strength check {event['roll']}={event['roll'].result()} vs DC {event.get('dc')})."
                   if event.get('roll') is not None else ".")
            ),
            'escape': lambda event: self.output_logger.log(
                f"{self.show_name(event)} escapes the battle"
                + (f" using {event['method']}." if event.get('method') else ".")
            ),
            'death_burst': lambda event: self.output_logger.log(
                f"{self.show_name(event)} bursts as it dies! {self.show_target_name(event)} takes "
                f"{event.get('damage')} {event.get('damage_type', '')} damage"
                + (" (saved for half)." if event.get('saved') else ".")
            ),
            'recharge': lambda event: self.output_logger.log(
                f"{self.show_name(event)} rolls {event['roll']}={event['roll'].result()} to recharge "
                f"{event.get('ability')}" + (" — it's ready again." if event.get('recharged') else ".")
            ),
            'npc_area_ability': lambda event: self.output_logger.log(
                f"{self.show_name(event)} uses {event.get('ability')}!"
            ),
            'npc_area_immune': lambda event: self.output_logger.log(
                f"{self.show_target_name(event)} is immune to {event.get('ability')}."
            ),
            'exhaustion': lambda event: self.output_logger.log(
                f"{self.show_target_name(event)} gains a level of exhaustion (now {event.get('level')})."
            ),
            'misty_step': lambda event: self.output_logger.log(
                f"{self.show_name(event)} teleports to {tuple(event.get('position') or ())}."
            ),
            'sending': lambda event: self.output_logger.log(
                f"{self.show_name(event)} sends a telepathic message to {self.show_target_name(event)}"
                + (f": \"{event['message']}\"" if event.get('message') else ".")
            ),
            'plant_growth': lambda event: self.output_logger.log(
                f"{self.show_name(event)} makes the plants in the area grow thick and overgrown."
            ),
            'dismiss_effect': lambda event: self.output_logger.log(f"{self.show_name(event)}: {_spell_label(event['effect'])} effect has been dismissed."),
            'resummon_familiar': lambda event: self.output_logger.log(f"{self.show_name(event)} summons {event['familiar'].name}"),
            'dismiss_familiar': lambda event: self.output_logger.log(f"{self.show_name(event)} dismisses {event['familiar'].name}"),
            'find_familiar': lambda event: self.output_logger.log(f"{self.show_name(event)} creates a familiar {event['familiar'].name}"),
            'bardic_inspiration': lambda event: self.output_logger.log(
                f"{self.show_name(event)} inspires {self.show_target_name(event)} with a {event.get('die', '1d6')} Bardic Inspiration die."
            ),
            'bardic_inspiration_used': lambda event: self.output_logger.log(
                f"{self.show_name(event)} uses Bardic Inspiration ({event.get('die', '1d6')}) and adds {event.get('bonus')} (rolled {event.get('roll')})."
            ),
            'inspiration_granted': lambda event: self.output_logger.log(
                f"{self.show_name(event)} gains {event.get('label', 'Inspiration')}."
            ),
            'inspiration_used': lambda event: self.output_logger.log(
                f"{self.show_name(event)} spends {event.get('label', 'Inspiration')}."
            ),
            'look': look,
            'message': lambda event: self.output_logger.log(f"{self.show_name(event)}: {event['message']}"),
            'narration': self._handle_narration_event,
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
            ),
            'color_spray': lambda event: self.output_logger.log(
                f"{self.show_name(event)} casts Color Spray and affects "
                f"{', '.join(self.decorate_name(t) for t in (event.get('targets') or [])) if event.get('targets') else 'no creatures'} "
                f"(pool {event.get('pool_roll')} = {event.get('pool_total')}, remaining {event.get('remaining')})."
            ),
            'witch_bolt': lambda event: self.output_logger.log(
                f"{self.show_name(event)} latches Witch Bolt onto {self.show_target_name(event)}."
            ),
            'witch_bolt_sustain': lambda event: self.output_logger.log(
                f"{self.show_name(event)} channels Witch Bolt into {self.show_target_name(event)} for {event.get('damage_roll')}={event.get('damage_roll').result()} lightning damage."
            ),
            'grease': lambda event: self.output_logger.log(
                f"{self.show_name(event)} casts Grease at {event.get('target')}, coating {len(event.get('squares') or [])} squares in slippery terrain."
            ),
            'grease_save': lambda event: self.output_logger.log(
                f"{self.show_target_name(event)} "
                f"{'keeps footing' if event.get('success') else 'slips prone'} "
                f"in Grease ({event.get('roll')}={event.get('roll').result()} vs DC {event.get('dc')}, {event.get('reason')})."
            ),
            'stinking_cloud': lambda event: self.output_logger.log(
                f"{self.show_name(event)} conjures a Stinking Cloud at {event.get('target')}."
            ),
            'stinking_cloud_save': lambda event: self.output_logger.log(
                f"{self.show_target_name(event)} "
                f"{'resists the nauseating gas' if event.get('success') else 'retches and reels, losing their action'} "
                f"in Stinking Cloud ({event.get('roll')}={event.get('roll').result()} vs DC {event.get('dc')})."
            ),
            'spirit_guardians': lambda event: self.output_logger.log(
                f"{self.show_name(event)} casts Spirit Guardians: {event.get('damage_type', 'radiant')} spirits "
                f"circle within 15 ft, slowing and harming enemies."
            ),
            'sleet_storm': lambda event: self.output_logger.log(
                f"{self.show_name(event)} casts Sleet Storm at {event.get('target')}: freezing sleet blankets "
                f"{len(event.get('squares') or [])} squares (heavily obscured, icy difficult terrain)."
            ),
            'sleet_storm_save': lambda event: self.output_logger.log(
                f"{self.show_target_name(event)} "
                f"{'keeps footing' if event.get('success') else 'slips and falls prone'} "
                f"in the Sleet Storm ({event.get('roll')}={event.get('roll').result()} vs DC {event.get('dc')})."
            ),
            'weapon_hit_spell_cast': lambda event: self.output_logger.log(
                f"{self.show_name(event)} casts {event.get('spell')} (level {event.get('slot_level')}) "
                f"as the blow lands on {self.decorate_name(event.get('target'))}."
            ),
            'ensnaring_strike': lambda event: self.output_logger.log(
                f"{self.decorate_name(event.get('target'))} "
                + ("tears through the grasping vines" if event.get('success')
                   else "is restrained by thorny vines")
                + f" {_roll_vs_dc(event)}."
            ),
            'break_free': lambda event: self.output_logger.log(
                (f"{self.show_name(event)} struggles against {event.get('restraint')}"
                 if event.get('source') is event.get('target')
                 else f"{self.show_name(event)} tries to free {self.decorate_name(event.get('target'))} "
                      f"from {event.get('restraint')}")
                + f": {'free!' if event.get('success') else 'still held'} {_roll_vs_dc(event)}."
            ),
            'spike_growth': lambda event: self.output_logger.log(
                f"{self.show_name(event)} casts Spike Growth: hidden thorns cover "
                f"{len(event.get('squares') or [])} squares (difficult terrain, 2d4 piercing per 5 ft moved)."
            ),
            'spike_growth_damage': lambda event: self.output_logger.log(
                f"{self.decorate_name(event.get('target'))} is torn by Spike Growth thorns."
            ),
            'silence': lambda event: self.output_logger.log(
                f"{self.show_name(event)} casts Silence: a 20-ft sphere of absolute quiet covers "
                f"{len(event.get('squares') or [])} squares (no speech, no verbal spells, immune to thunder)."
            ),
            'magic_weapon': lambda event: self.output_logger.log(
                f"{self.show_name(event)} casts Magic Weapon on "
                f"{self.decorate_name(event.get('target'))}'s {str(event.get('weapon')).replace('_', ' ')} "
                f"(+{event.get('bonus')} to attack and damage)."
                if event.get('weapon') else
                f"{self.show_name(event)} casts Magic Weapon, but {self.decorate_name(event.get('target'))} "
                f"holds no nonmagical weapon."
            ),
            'pass_without_trace': lambda event: self.output_logger.log(
                f"{self.show_name(event)} casts Pass without Trace; "
                f"{', '.join(event.get('members') or []) or 'the caster'} gain +10 to Stealth."
            ),
            'disguise_self': lambda event: self.output_logger.log(
                f"{self.show_name(event)} casts Disguise Self and now looks like {event.get('description')}."
            ),
            'disguise_check': lambda event: self.output_logger.log(
                f"{self.show_name(event)} studies {self.decorate_name(event.get('target'))} and "
                f"{'sees through the disguise' if event.get('success') else 'is fooled by the disguise'} "
                f"{_roll_vs_dc(event)}."
            ),
            'rope_trick': lambda event: self.output_logger.log(
                f"{self.show_name(event)} casts Rope Trick; "
                f"{', '.join(event.get('members') or []) or 'the caster'} climb into the hidden space."
            ),
            'fear': lambda event: self.output_logger.log(
                f"{self.show_name(event)} casts Fear: "
                + ("; ".join(
                    f"{self.decorate_name(s.get('target'))} "
                    f"{'resists' if s.get('success') else 'is terrified'} "
                    f"{_roll_vs_dc(dict(s, dc=event.get('dc')))}"
                    for s in (event.get('saves') or [])) or "no creatures in the cone")
                + "."
            ),
            'fear_save': lambda event: self.output_logger.log(
                f"{self.decorate_name(event.get('target'))}, out of sight of its tormentor, "
                f"{'shakes off the fear' if event.get('success') else 'remains terrified'} {_roll_vs_dc(event)}."
            ),
            'attack_surge': lambda event: self.output_logger.log(
                f"{self.show_name(event)} draws on {event.get('spell')}: the next weapon attack has advantage "
                f"and the wind quickens their stride."
            ),
            'push_creature': lambda event: self.output_logger.log(
                f"{self.show_name(event)} casts {event.get('spell') or 'a gust'} at "
                f"{self.decorate_name(event.get('target'))}: "
                + ("too large to be moved" if event.get('too_large')
                   else ("it holds its ground" if event.get('success') else "it is pushed back"))
                + (f" {_roll_vs_dc(event)}" if not event.get('too_large') else "")
                + "."
            ),
            'call_lightning': lambda event: self.output_logger.log(
                f"{self.show_name(event)} casts Call Lightning"
                f"{' and takes command of the storm' if event.get('stormy') else ''}; "
                f"a bolt strikes {event.get('target')}."
            ),
            'call_lightning_bolt': lambda event: self.output_logger.log(
                f"{self.show_name(event)} calls another lightning bolt down at {event.get('target')}."
            ),
            'daylight': lambda event: self.output_logger.log(
                f"{self.show_name(event)} casts Daylight"
                + (f", making {self.show_target_name(event)} shine like the sun"
                   if event.get('target') is not None
                   else f", flooding the area around {event.get('position')} with daylight")
                + (f" and dispelling {event['dispelled']} magical darkness" if event.get('dispelled') else '')
                + "."
            ),
            'remove_curse': lambda event: self.output_logger.log(
                f"{self.show_name(event)} casts Remove Curse on {self.show_target_name(event)}"
                + (f", ending {', '.join(str(e) for e in event['ended'])}" if event.get('ended') else '')
                + (f" and breaking the hold of {', '.join(event['items'])}" if event.get('items') else '')
                + ("." if (event.get('ended') or event.get('items') or event.get('status_cleared'))
                   else ", but no curse was found.")
            ),
            'aura_of_vitality': lambda event: self.output_logger.log(
                f"{self.show_name(event)} casts Aura of Vitality; healing energy radiates around them."
            ),
            'aura_of_vitality_pulse': lambda event: self.output_logger.log(
                f"{self.show_name(event)} channels the Aura of Vitality into {self.show_target_name(event)}."
            ),
            'faerie_fire': lambda event: self.output_logger.log(
                f"{self.show_name(event)} casts Faerie Fire"
                + (f"; {self.decorate_name(event['targets'])} glow with outlining light."
                   if event.get('targets') else "; every creature in the area shrugs off the light.")
            ),
            'targeting_ward': lambda event: self.output_logger.log(
                f"{self.show_name(event)} tests {self.decorate_name(event['target'])}'s {event.get('label') or 'ward'} "
                f"({event.get('save_type', 'wisdom')} save {event.get('roll')}="
                f"{event['roll'].result() if event.get('roll') is not None else '?'} vs DC {event.get('dc')})"
                + (f" and loses the {'spell' if event.get('kind') == 'spell' else 'attack'}."
                   if event.get('blocked') else " and pushes through.")
            ),
            'sanctuary_end': lambda event: self.output_logger.log(
                f"{self.show_name(event)}'s Sanctuary ends."
            ),
            'lesser_restoration': lambda event: self.output_logger.log(
                f"{self.show_name(event)} casts Lesser Restoration on {self.show_target_name(event)}"
                + (f", ending {str(event['ended']).replace('_', ' ')}." if event.get('ended')
                   else ", but there is nothing to cure.")
            ),
            'ray_of_sickness': lambda event: self.output_logger.log(
                f"{self.show_target_name(event)} "
                + ("is poisoned by the Ray of Sickness" if event.get('poisoned')
                   else "fights off the Ray of Sickness's poison")
                + (f" ({event['roll']}={event['roll'].result()} vs DC {event.get('dc')})."
                   if event.get('roll') is not None else ".")
            ),
            'melfs_acid_arrow': lambda event: self.output_logger.log(
                f"Acid clings to {self.show_target_name(event)} and will burn again at the end of their next turn."
            ),
            'flaming_sphere': lambda event: self.output_logger.log(
                f"{self.show_name(event)} conjures a Flaming Sphere at {event.get('target')}."
            ),
            'flaming_sphere_move': lambda event: self.output_logger.log(
                f"{self.show_name(event)} rolls the Flaming Sphere to {event.get('target')}"
                + (f", ramming {self.decorate_name(event['ram'])}." if event.get('ram') is not None else ".")
            ),
            'dancing_weapon_move': lambda event: self.output_logger.log(
                f"{self.show_name(event)} "
                + ("tosses" if event.get('toss') else "sends")
                + f" the {event.get('item_name') or 'dancing weapon'} flying to {event.get('to')}"
                + (f" to strike {self.decorate_name(event['target'])}" if event.get('target') is not None else "")
                + (f" (attack {event.get('attack_number')} of {event.get('max_attacks')})."
                   if event.get('attack_number') else ".")
            ),
            'dancing_weapon_return': lambda event: self.output_logger.log(
                f"The {event.get('item_name') or 'dancing weapon'} "
                + {
                    'returned': f"flies back into {self.show_name(event)}'s hand.",
                    'caught': f"is plucked from the air by {self.show_name(event)}.",
                    'no_free_hand': f"returns but {self.show_name(event)} has no free hand; it drops at their feet.",
                    'out_of_range': f"stops hovering and falls, too far from {self.show_name(event)}.",
                }.get(event.get('outcome'), f"stops dancing for {self.show_name(event)}.")
            ),
            'attunement': lambda event: self.output_logger.log(
                f"{self.show_name(event)} " + {
                    'attuned': f"is now attuned to {event.get('item_label')}.",
                    'ended': f"ends attunement to {event.get('item_label')}.",
                    'pending': (f"will attune to {event.get('item_label')} during the next rest."
                                if event.get('mode') == 'attune'
                                else f"will end attunement to {event.get('item_label')} during the next rest."),
                    'failed': f"fails to {'attune to' if event.get('mode') != 'end' else 'end attunement to'} "
                              f"{event.get('item_label')}: {event.get('reason')}",
                    'lost': f"loses attunement to {event.get('item_label')}"
                            + (' (left behind for 24 hours).' if event.get('reason') == 'separated' else '.'),
                }.get(event.get('outcome'), f"attunement to {event.get('item_label')} changed.")
            ),
            'item_regain_hp': lambda event: self.output_logger.log(
                f"{self.show_name(event)} regains {event.get('value')} HP from "
                f"{str(event.get('item') or 'an item').replace('_', ' ').title()}."
            ),
            'flaming_sphere_save': lambda event: self.output_logger.log(
                f"{self.show_target_name(event)} "
                f"{'dodges most of the flames' if event.get('success') else 'is engulfed by the flames'} "
                f"of the Flaming Sphere ({event.get('roll')}={event.get('roll').result()} vs DC {event.get('dc')})."
            ),
            'feather_fall': lambda event: self.output_logger.log(
                f"{self.show_name(event)} casts Feather Fall; {self.decorate_name(event.get('targets') or [event['target']])} "
                f"will drift gently down."
            ),
            'prestidigitation': lambda event: self.output_logger.log(
                f"{self.show_name(event)} performs a bit of Prestidigitation ({event.get('trick') or 'sensory'} trick)"
                + (f" at {event.get('target')}." if event.get('target') else ".")
            ),
            'mending': lambda event: self.output_logger.log(
                f"{self.show_name(event)} casts Mending"
                + (f", repairing the {event['object_name']}." if event.get('object_name')
                   else f" and knits a small break back together at {event.get('target')}.")
            ),
            'identify': lambda event: self.output_logger.log(
                f"{self.show_name(event)} casts Identify on {self.show_target_name(event)}: "
                + (f"magic items: {', '.join(event['items'])}" if event.get('items') else "no magic items")
                + (f"; affected by {', '.join(event['spells'])}." if event.get('spells') else "; no active spells.")
            ),
            'gaseous_form': lambda event: self.output_logger.log(
                f"{self.show_name(event)} casts Gaseous Form; {self.show_target_name(event)} "
                f"{'become' if event.get('source') is event.get('target') else 'becomes'} a drifting cloud of mist."
            ),
            'revived': lambda event: self.output_logger.log(
                f"{self.show_name(event)} brings {self.show_target_name(event)} back to life "
                f"with {event.get('hp', 1)} hit point."
                if event.get('source') is not event.get('target')
                else f"{self.show_target_name(event)} returns to life with {event.get('hp', 1)} hit point."
            ),
            'rage_start': lambda event: self.output_logger.log(
                f"{self.show_name(event)} flies into a rage! ({event.get('rounds', 10)} rounds remaining)"
            ),
            'rage_end': lambda event: self.output_logger.log(
                f"{self.show_name(event)}'s rage ends" + (f" ({event['reason']})" if event.get('reason') else "")
            ),
            'reckless_attack': lambda event: self.output_logger.log(
                f"{self.show_name(event)} attacks recklessly, granting and gaining advantage on melee attacks until their next turn."
            ),
            'darkness': lambda event: self.output_logger.log(
                f"{self.show_name(event)} casts Darkness, filling a 15-foot sphere at {event.get('target')} with magical darkness."
            ),
            'tiny_hut': lambda event: self.output_logger.log(
                f"{self.show_name(event)} raises Leomund's Tiny Hut — an immobile dome of force."
            ),
            'tiny_hut_failed': lambda event: self.output_logger.log(
                f"{self.show_name(event)} tried to cast Leomund's Tiny Hut, but the spell fails"
                f" ({event.get('reason', 'invalid area')})."
            ),
            'tiny_hut_ended': lambda event: self.output_logger.log(
                f"Leomund's Tiny Hut collapses as {self.show_name(event)} leaves the dome."
            ),
            'tiny_hut_lighting': lambda event: self.output_logger.log(
                f"{self.show_name(event)} commands the hut interior to become {event.get('mode', 'lit')}."
            ),
            'message_spell': lambda event: self.output_logger.log(
                f"{self.show_name(event)} casts Message on {self.show_target_name(event)}."
            ),
            'message_spell_failed': lambda event: self.output_logger.log(
                f"{self.show_name(event)} tried to cast Message, but the spell fails"
                f" ({event.get('reason', 'blocked')})."
            ),
            'ready_action_declared': lambda event: self.output_logger.log(
                f"{self.show_name(event)} readies an action: "
                f"{event.get('description') or (event.get('trigger') or {}).get('description') or 'a reaction'}"
                f" (trigger: {(event.get('trigger') or {}).get('event', '?')})"
            ),
            'ready_action_fired': lambda event: self.output_logger.log(
                f"{self.show_name(event)}'s readied action triggers"
                f" ({event.get('trigger_event', '?')}): "
                f"{event.get('description') or (event.get('state') or {}).get('description', '')}"
            ),
            'ready_action_fizzled': lambda event: self.output_logger.log(
                f"{self.show_name(event)}'s readied action fizzles"
                f" (trigger: {event.get('trigger_event', '?')})"
                + (f" \u2014 {event['reason']}" if event.get('reason') else "")
            ),
            'ready_action_error': lambda event: self.output_logger.log(
                f"{self.show_name(event)}'s readied action errored: {event.get('error', 'unknown')}"
            ),
            'weapon_mastery': self._handle_weapon_mastery,
        }

        for event, handler in event_handlers.items():
            self.register_event_listener(event, handler)

    def _handle_weapon_mastery(self, event):
        mastery = str(event.get("mastery") or "").lower()
        labels = {
            "push": "Push",
            "topple": "Topple",
            "sap": "Sap",
            "vex": "Vex",
            "slow": "Slow",
            "graze": "Graze",
            "cleave": "Cleave",
            "nick": "Nick",
        }
        label = labels.get(mastery, mastery.title() or "Weapon Mastery")
        source = self.show_name(event)
        target = self.show_target_name(event) if event.get("target") is not None else "the target"
        if mastery == "push":
            dest = event.get("destination")
            extra = f" to {dest}" if dest else ""
            self.output_logger.log(f"{source} uses Weapon Mastery ({label}) and pushes {target}{extra}.")
        elif mastery == "topple":
            self.output_logger.log(f"{source} uses Weapon Mastery ({label}): {target} is knocked prone.")
        elif mastery == "sap":
            self.output_logger.log(
                f"{source} uses Weapon Mastery ({label}): {target} has disadvantage on its next attack."
            )
        elif mastery == "vex":
            self.output_logger.log(
                f"{source} uses Weapon Mastery ({label}): advantage on their next attack against {target}."
            )
        elif mastery == "slow":
            self.output_logger.log(
                f"{source} uses Weapon Mastery ({label}): {target}'s speed is reduced by 10 feet."
            )
        elif mastery == "graze":
            dmg = event.get("damage")
            dmg_bit = f" for {dmg} damage" if dmg else ""
            self.output_logger.log(f"{source} uses Weapon Mastery ({label}) and grazes {target}{dmg_bit}.")
        else:
            self.output_logger.log(f"{source} uses Weapon Mastery ({label}) on {target}.")

    def show_name(self, event):
        return self.decorate_name(event['source'])

    def _handle_narration_event(self, event):
        narration = event.get('narration') or {}
        entry = narration.get('on_enter') or {}
        text = entry.get('text')
        if not text:
            return
        title = entry.get('title')
        prefix = f"[Narration] {title}: " if title else "[Narration] "
        self.output_logger.log(f"{prefix}{text}")

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
        if entity is None:
            return "nothing"
        if isinstance(entity, (tuple, list)):
            if len(entity) == 2 and all(isinstance(c, (int, float)) and not isinstance(c, bool) for c in entity):
                return f"the square at ({int(entity[0])}, {int(entity[1])})"
            decorated_names = [self.decorate_name(e) for e in entity]
            if not decorated_names:
                return ""
            elif len(decorated_names) == 1:
                return decorated_names[0]
            else:
                return ", ".join(decorated_names[:-1]) + " and " + decorated_names[-1]
        label = getattr(entity, 'label', None)
        if callable(label):
            return label()
        return str(entity)

    def attack_label(self, name):
        """Readable attack name: translates ``spell.*`` keys and turns raw
        stat-block ids (``unarmed_strike2``) into ``Unarmed Strike``."""
        if not name:
            return ''
        name = str(name)
        try:
            translated = self.t(name)
        except Exception:
            translated = name
        if translated and translated != name:
            return translated
        base = name.split('.', 1)[1] if name.startswith('spell.') else name
        if '_' in base or name.startswith('spell.'):
            base = re.sub(r'\d+$', '', base).replace('_', ' ').strip().title()
        return base

    def t(self, token, **options):
        return i18n.t(token, **options)