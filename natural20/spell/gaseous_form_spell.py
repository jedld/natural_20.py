"""Gaseous Form — 3rd-level transmutation (SRD), concentration up to 1 hour.

A willing creature touched becomes a misty cloud. While transformed its only
movement is a 10-foot flying speed, it resists nonmagical bludgeoning,
piercing and slashing damage, and it has advantage on Strength, Dexterity
and Constitution saves. It can't attack, cast spells, talk or manipulate
objects (``natural20.utils.action_restrictions``).
"""
from __future__ import annotations

import uuid

from natural20.spell.spell import Spell

GASEOUS_RESISTANCES = ('non-magical bludgeoning', 'non-magical piercing', 'non-magical slashing')
GASEOUS_SAVES = ('strength', 'dexterity', 'constitution')
GASEOUS_SPEED = 10
EFFECT_TYPES = ('gaseous_form', 'fly_speed', 'speed_override', 'resistance_override',
                'save_advantage_modifier', 'action_restriction')


class GaseousFormEffect:
    def __init__(self, source, target, added_status=True, granted_flight=False):
        self.source = source
        self.target = target
        self.added_status = bool(added_status)
        self.granted_flight = bool(granted_flight)
        self.uid = f"gaseous_form:{uuid.uuid4().hex[:10]}"
        self.ended = False

    @property
    def id(self):
        return self.uid

    def __str__(self):
        return 'gaseous_form'

    def label(self):
        return 'Gaseous Form'

    @staticmethod
    def gaseous_form(entity, opt=None):
        return True

    @staticmethod
    def fly_speed(entity, opt=None):
        return GASEOUS_SPEED

    @staticmethod
    def speed_override(entity, opt=None):
        return GASEOUS_SPEED

    @staticmethod
    def resistance_override(entity, opt=None):
        value = list((opt or {}).get('value') or [])
        for res in GASEOUS_RESISTANCES:
            if res not in value:
                value.append(res)
        return value

    @staticmethod
    def save_advantage_modifier(entity, opt=None):
        opt = opt or {}
        adv, dis = opt.get('value') or [[], []]
        adv, dis = list(adv or []), list(dis or [])
        if str(opt.get('save_type') or opt.get('ability') or '').lower() in GASEOUS_SAVES:
            adv.append('gaseous_form')
        return [adv, dis]

    @staticmethod
    def action_restriction(entity, opt=None):
        return list((opt or {}).get('value') or []) + ['attack', 'spell', 'speak', 'interact']

    def apply_to(self, target, duration):
        for effect_type in EFFECT_TYPES:
            target.register_effect(effect_type, GaseousFormEffect, effect=self,
                                   source=self.source, duration=duration)

    def dismiss(self, entity, _descriptor=None, opts=None):
        if self.ended:
            return
        self.ended = True
        target = self.target
        source = self.source
        if source is not None and getattr(source, 'concentration', None) is self:
            source.drop_concentration()
        if target is None or isinstance(target, str):
            return
        if target is not entity and hasattr(target, 'remove_effect'):
            target.remove_effect(self)
        if self.added_status and 'gaseous_form' in (getattr(target, 'statuses', None) or []):
            target.statuses.remove('gaseous_form')
        if self.granted_flight and hasattr(target, 'fly_speed') and not target.fly_speed():
            target._granted_flight = False
            target.land()


class GaseousFormSpell(Spell):
    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [{
                'type': 'select_target',
                'num': 1,
                'range': self.properties.get('range', 5),
                'target_types': ['allies', 'self'],
            }],
            'next': set_target,
        }

    def resolve(self, entity, battle, spell_action, battle_map):
        target = spell_action.target
        if isinstance(target, (list, tuple)):
            target = target[0] if target else entity
        return [{
            'type': 'gaseous_form',
            'source': entity,
            'target': target or entity,
            'effect': self,
            'spell': self.properties,
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'gaseous_form':
            return None
        source, target = item['source'], item['target']
        if session is None:
            session = battle.session if battle is not None else source.session
        duration = int((item.get('spell') or {}).get('duration_seconds', 3600))
        added = 'gaseous_form' not in target.statuses
        if added:
            target.statuses.append('gaseous_form')
        granted = not (target.properties.get('speed_fly') or 0)
        effect = GaseousFormEffect(source, target, added_status=added, granted_flight=granted)
        effect.apply_to(target, duration)
        source.add_casted_effect({'target': target, 'effect': effect,
                                  'expiration': session.game_time + duration})
        if granted:
            target._granted_flight = True
        if hasattr(target, 'fly'):
            target.fly()
        if battle is not None and hasattr(battle, 'start_concentration'):
            battle.start_concentration(source, effect)
        else:
            source.concentration_on(effect)
        session.event_manager.received_event({
            'event': 'gaseous_form',
            'source': source,
            'target': target,
        })
        return target
