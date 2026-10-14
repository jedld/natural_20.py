"""Beacon of Hope — 3rd-level abjuration (SRD), concentration up to 1 minute.

Any number of creatures of the caster's choice within 30 ft gain, while the
spell lasts:

* advantage on Wisdom saving throws (``save_advantage_modifier``),
* advantage on death saving throws (``death_save_advantage_modifier``),
* the maximum possible hit points from any healing (``max_healing``, honored
  by ``natural20.utils.healing.effective_heal_roll``).
"""
from __future__ import annotations

from natural20.spell.spell import Spell


class BeaconOfHopeSpell(Spell):
    DURATION_SECONDS = 60
    TARGET_EFFECTS = ('save_advantage_modifier', 'death_save_advantage_modifier', 'max_healing')
    MAX_TARGETS = 12

    def __init__(self, session, source, spell_name, details):
        super().__init__(session, source, spell_name, details)
        # Comma-separated UIDs so the target list survives save/load (the
        # Spell representer keeps scalar attributes only).
        self.target_uids = ''

    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [{
                'type': 'select_target',
                'num': int(self.properties.get('max_targets', self.MAX_TARGETS)),
                'min': 1,
                'range': self.properties.get('range', 30),
                'unique_targets': True,
                'auto_pick': 'all',
                'target_types': ['allies', 'self'],
            }],
            'next': set_target,
        }

    @staticmethod
    def _targets(target):
        if target is None:
            return []
        targets = target if isinstance(target, (list, tuple)) else [target]
        out = []
        for t in targets:
            if hasattr(t, 'register_effect') and t not in out:
                out.append(t)
        return out

    def resolve(self, entity, battle, spell_action, _battle_map):
        targets = self._targets(spell_action.target)
        self.target_uids = ','.join(str(t.entity_uid) for t in targets)
        return [{
            'source': entity,
            'target': target,
            'type': 'beacon_of_hope',
            'spell': self.properties,
            'effect': self,
        } for target in targets]

    @staticmethod
    def save_advantage_modifier(entity, opt=None):
        opt = opt or {}
        adv, dis = opt.get('value') or [[], []]
        adv = list(adv or [])
        if str(opt.get('save_type') or opt.get('ability') or '').lower() in ('wisdom', 'wis'):
            adv.append('beacon_of_hope')
        return [adv, list(dis or [])]

    @staticmethod
    def death_save_advantage_modifier(entity, opt=None):
        opt = opt or {}
        adv, dis = opt.get('value') or [[], []]
        return [list(adv or []) + ['beacon_of_hope'], list(dis or [])]

    @staticmethod
    def max_healing(entity, opt=None):
        return True

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'beacon_of_hope':
            return None
        if battle is not None and session is None:
            session = battle.session
        source = item['source']
        target = item['target']
        effect = item['effect']
        duration = BeaconOfHopeSpell.DURATION_SECONDS

        if source.current_concentration() is not effect:
            if battle is not None and hasattr(battle, 'start_concentration'):
                battle.start_concentration(source, effect)
            else:
                source.concentration_on(effect)

        source.add_casted_effect({
            'target': target,
            'effect': effect,
            'expiration': session.game_time + duration,
        })
        for effect_type in BeaconOfHopeSpell.TARGET_EFFECTS:
            target.register_effect(effect_type, BeaconOfHopeSpell, effect=effect,
                                   source=source, duration=duration)
        session.event_manager.received_event({
            'event': 'spell_buf',
            'spell': effect,
            'source': source,
            'target': target,
        })
        return target

    def dismiss(self, entity, _descriptor=None, opts=None):
        """Ending the spell on the caster clears every target, even after a
        reload (when ``action.target`` is gone)."""
        if entity is not self.source:
            return
        session = getattr(entity, 'session', None)
        for uid in [u for u in str(self.target_uids or '').split(',') if u]:
            target = session.entity_by_uid(uid) if session is not None else None
            if target is None or target is entity:
                continue
            target.effects = {
                key: [f for f in value if f.get('effect') is not self]
                for key, value in (getattr(target, 'effects', None) or {}).items()
            }
