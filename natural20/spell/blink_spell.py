"""Blink — 3rd-level transmutation (SRD, 1 minute, no concentration).

At the end of each of the caster's turns a die decides whether they vanish to
the Ethereal Plane (2014: d20 ≥ 11; 2024: d6 4–6; YAML ``blink.die`` /
``blink.success_min``). While away the caster can't be targeted or caught in
areas (``natural20/utils/off_plane.py``); they return at the start of their
next turn into their square or the nearest open one. Choosing a specific
return square within 10 ft is left to a later move.
"""
from __future__ import annotations

from natural20.die_roll import DieRoll
from natural20.spell.spell import Spell
from natural20.utils.off_plane import off_plane, return_to_plane, send_off_plane

EFFECT_KEY = 'blink'


class BlinkEffect:
    def __init__(self, source, spell_properties, duration):
        self.source = source
        self.spell_properties = dict(spell_properties or {})
        self.duration = int(duration)
        self.ended = False

    @property
    def id(self):
        return 'blink'

    def __str__(self):
        return 'blink'

    def _rule(self):
        rule = self.spell_properties.get('blink') or {}
        return str(rule.get('die', 'd20')), int(rule.get('success_min', 11))

    def register_hooks(self):
        self.source.register_event_hook('end_of_turn', self, method_name='on_end_of_turn',
                                        effect=self, source=self.source, duration=self.duration)
        self.source.register_event_hook('start_of_turn', self, method_name='on_start_of_turn',
                                        effect=self, source=self.source, duration=self.duration)

    def restore_hooks(self):
        if not self.ended:
            self.register_hooks()

    def on_end_of_turn(self, entity, opt=None):
        if self.ended or entity.dead():
            return
        battle = (opt or {}).get('battle')
        die, success_min = self._rule()
        roll = DieRoll.roll(f"1{die}", entity=entity, battle=battle, description='dice_roll.spells.blink')
        vanished = roll.result() >= success_min
        entity.session.event_manager.received_event({
            'event': 'blink_roll', 'source': entity, 'target': entity, 'roll': roll, 'vanished': vanished,
        })
        if vanished:
            send_off_plane(entity, 'ethereal', source=entity)

    def on_start_of_turn(self, entity, opt=None):
        if off_plane(entity):
            return_to_plane(entity, (opt or {}).get('battle'))

    def dismiss(self, entity, _descriptor=None, opts=None):
        self.ended = True
        for key, hooks in list(entity.entity_event_hooks.items()):
            entity.entity_event_hooks[key] = [h for h in hooks if h.get('effect') is not self]
        if off_plane(entity):
            return_to_plane(entity)


class BlinkSpell(Spell):
    def build_map(self, orig_action):
        action = orig_action.clone()
        action.target = self.source
        return action

    def resolve(self, entity, battle, spell_action, battle_map):
        return [{'type': 'blink', 'source': entity, 'target': entity, 'spell': self.properties, 'effect': self}]

    @staticmethod
    def blink(entity, opts=None):
        return True

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'blink':
            return None
        source = item['source']
        session = session or (battle.session if battle is not None else source.session)
        duration = int((item.get('spell') or {}).get('duration_seconds', 60))
        source.remove_effect(EFFECT_KEY)
        effect = BlinkEffect(source, item.get('spell'), duration)
        source.add_casted_effect({'target': source, 'effect': effect,
                                  'expiration': session.game_time + duration})
        source.register_effect(EFFECT_KEY, BlinkSpell, effect=effect, source=source, duration=duration)
        effect.register_hooks()
        session.event_manager.received_event({'event': 'spell_buf', 'source': source, 'target': source,
                                              'spell': item.get('spell')})
        return source
