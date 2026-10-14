"""Pass without Trace — 2nd-level abjuration (SRD, concentration 1 hour).

A 30-ft aura of shadow and quiet: the caster and the allies chosen at cast
time (every ally within ``radius`` feet) gain ``skill_bonus`` (+10) to
Stealth checks while they stay within that distance of the caster
(generic ``skill_check_bonus`` effect, read by ``Entity`` skill checks).

Simplifications: allies who arrive after the cast are not added, and the
"can't be tracked except by magic" clause is narrative only.
"""
from __future__ import annotations

from natural20.spell.spell import Spell
from natural20.utils.auras import _friendly as friendly


class PassWithoutTraceSpell(Spell):
    def __init__(self, session, source, spell_name, details):
        super().__init__(session, source, spell_name, details)
        self.member_uids = ''

    def __str__(self):
        return 'pass_without_trace'

    def radius(self):
        return int(self.properties.get('radius', 30) or 30)

    def build_map(self, orig_action):
        action = orig_action.clone()
        action.target = self.source
        return action

    def _members(self, entity, battle):
        members = [entity]
        battle_map = battle.map_for(entity) if battle is not None else None
        if battle_map is None:
            session = getattr(entity, 'session', None)
            battle_map = session.map_for(entity) if session is not None and hasattr(session, 'map_for') else None
        if battle_map is None:
            return members
        reach = self.radius() / battle_map.feet_per_grid
        for other in list(battle_map.entities.keys()):
            if other is entity or getattr(other, 'object', lambda: False)():
                continue
            if not hasattr(other, 'register_effect') or other.dead():
                continue
            if not friendly(entity, other, battle):
                continue
            try:
                if battle_map.distance(entity, other) <= reach:
                    members.append(other)
            except Exception:
                continue
        return members

    def resolve(self, entity, battle, spell_action, battle_map):
        members = self._members(entity, battle)
        self.member_uids = ','.join(m.entity_uid for m in members)
        return [{
            'type': 'pass_without_trace',
            'source': entity,
            'target': entity,
            'members': members,
            'effect': self,
            'spell': self.properties,
        }]

    def within_aura(self, entity):
        caster = self.source
        if entity is caster:
            return True
        session = getattr(caster, 'session', None)
        if session is None or not hasattr(session, 'map_for'):
            return False
        caster_map = session.map_for(caster)
        if caster_map is None or caster_map is not session.map_for(entity):
            return False
        try:
            return caster_map.distance(caster, entity) <= self.radius() / caster_map.feet_per_grid
        except Exception:
            return False

    @staticmethod
    def skill_check_bonus(entity, opts=None):
        opts = opts or {}
        value = int(opts.get('value') or 0)
        effect = opts.get('effect')
        if str(opts.get('skill') or '') != 'stealth' or effect is None:
            return value
        if not effect.within_aura(entity):
            return value
        return value + int(effect.properties.get('skill_bonus', 10) or 10)

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'pass_without_trace':
            return None
        source = item['source']
        effect = item['effect']
        session = session or (battle.session if battle is not None else source.session)
        duration = int(effect.properties.get('duration_seconds', 3600))
        if effect.properties.get('concentration', True):
            if battle is not None and hasattr(battle, 'start_concentration'):
                battle.start_concentration(source, effect)
            else:
                source.concentration_on(effect)
        for member in item.get('members') or [source]:
            source.add_casted_effect({'target': member, 'effect': effect,
                                      'expiration': session.game_time + duration})
            member.register_effect('skill_check_bonus', PassWithoutTraceSpell, effect=effect,
                                   source=source, duration=duration)
        session.event_manager.received_event({
            'event': 'pass_without_trace', 'source': source, 'target': source,
            'members': [m.label() if hasattr(m, 'label') else str(m) for m in item.get('members') or []],
        })
        return source

    def dismiss(self, entity, _descriptor=None, opts=None):
        session = getattr(self.source, 'session', None)
        if session is None:
            return
        for uid in [u for u in str(self.member_uids or '').split(',') if u]:
            member = session.entity_by_uid(uid)
            if member is None or member is entity:
                continue
            effects = member.effects.get('skill_check_bonus') or []
            member.effects['skill_check_bonus'] = [f for f in effects if f.get('effect') is not self]
            if not member.effects['skill_check_bonus']:
                del member.effects['skill_check_bonus']
