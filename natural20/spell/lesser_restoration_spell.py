"""Lesser Restoration — 2nd-level abjuration (SRD), touch, instantaneous.

Ends one disease or one of these conditions on the touched creature:
blinded, deafened, paralyzed, or poisoned. Without an explicit choice the
spell picks the most debilitating one present (``CONDITION_PRIORITY``). A
caller may pick one with ``spell_action.opts['condition']`` (or
``spell_action.condition``); ``'disease'`` ends one disease status.
"""
from __future__ import annotations

from natural20.spell.spell import Spell

CONDITION_PRIORITY = ('paralyzed', 'blinded', 'poisoned', 'deafened')

# Effect types that impose each condition without (only) a status entry.
CONDITION_EFFECT_TYPES = {
    'paralyzed': ('hold_person', 'paralyzed'),
    'blinded': ('blinded_override', 'blinded'),
    'poisoned': ('poisoned',),
    'deafened': ('deafened',),
}


def _statuses(target):
    return getattr(target, 'statuses', None) or []


def _diseases(target):
    return [s for s in _statuses(target) if isinstance(s, str) and 'disease' in s.lower()]


def _has_condition(target, condition):
    if condition in _statuses(target):
        return True
    check = getattr(target, condition, None)
    if callable(check):
        try:
            return bool(check())
        except Exception:
            return False
    return False


def curable_conditions(target):
    found = [c for c in CONDITION_PRIORITY if _has_condition(target, c)]
    if _diseases(target):
        found.append('disease')
    return found


def _remove_status(target, status):
    statuses = getattr(target, 'statuses', None)
    if statuses is None:
        return
    if isinstance(statuses, set):
        statuses.discard(status)
    else:
        while status in statuses:
            statuses.remove(status)


def end_condition(target, condition):
    """End ``condition`` on ``target``; returns the name of what was ended."""
    if condition == 'disease':
        diseases = _diseases(target)
        if not diseases:
            return None
        _remove_status(target, diseases[0])
        return diseases[0]
    for effect_type in CONDITION_EFFECT_TYPES.get(condition, ()):
        for descriptor in list((getattr(target, 'effects', None) or {}).get(effect_type, [])):
            effect = descriptor.get('effect')
            if effect is not None and not isinstance(effect, str):
                target.remove_effect(effect)
    _remove_status(target, condition)
    return condition


class LesserRestorationSpell(Spell):
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

    @staticmethod
    def requested_condition(spell_action):
        chosen = getattr(spell_action, 'condition', None)
        if not chosen:
            chosen = (getattr(spell_action, 'opts', None) or {}).get('condition')
        return str(chosen).lower() if chosen else None

    def resolve(self, entity, battle, spell_action, battle_map):
        target = spell_action.target
        if isinstance(target, (list, tuple)):
            target = target[0] if target else entity
        present = curable_conditions(target)
        requested = self.requested_condition(spell_action)
        if requested:
            condition = requested if requested in present else None
        else:
            condition = present[0] if present else None
        return [{
            'type': 'lesser_restoration',
            'source': entity,
            'target': target,
            'condition': condition,
            'effect': self,
            'spell': self.properties,
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'lesser_restoration':
            return None
        target = item['target']
        if session is None:
            session = battle.session if battle is not None else item['source'].session
        ended = end_condition(target, item['condition']) if item.get('condition') else None
        item['ended'] = ended
        session.event_manager.received_event({
            'event': 'lesser_restoration',
            'source': item['source'],
            'target': target,
            'ended': ended,
        })
        return target
