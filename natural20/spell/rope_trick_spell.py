"""Rope Trick — 2nd-level transmutation (SRD, 1 hour).

Simplified model: the rope and its extradimensional space are not placed on
the map. Instead the caster and up to ``max_creatures - 1`` (7) allies within
30 feet "climb in": while the spell lasts they can't be targeted
(``targettable = False``) and can't attack or cast spells out of the space
(``action_restriction`` → ``attack``, ``spell``). The spell is out-of-combat
only (YAML ``requires: [out_of_combat]``) and is meant for safe rests and
hiding from patrols; it ends after the duration or when the DM removes the
effect. Pulling the rope up, the visible entrance and creatures dropping out
when it ends are narrative.
"""
from __future__ import annotations

from natural20.spell.spell import Spell
from natural20.utils.auras import _friendly as friendly


class RopeTrickSpell(Spell):
    def __init__(self, session, source, spell_name, details):
        super().__init__(session, source, spell_name, details)
        self.member_uids = ''

    def __str__(self):
        return 'rope_trick'

    def build_map(self, orig_action):
        action = orig_action.clone()
        action.target = self.source
        return action

    def members_for(self, entity, battle=None):
        members = [entity]
        session = getattr(entity, 'session', None)
        battle_map = None
        if battle is not None:
            battle_map = battle.map_for(entity)
        elif session is not None and hasattr(session, 'map_for'):
            battle_map = session.map_for(entity)
        if battle_map is None:
            return members
        limit = int(self.properties.get('max_creatures', 8) or 8)
        reach = int(self.properties.get('gather_radius', 30) or 30) / battle_map.feet_per_grid
        nearby = []
        for other in list(battle_map.entities.keys()):
            if other is entity or getattr(other, 'object', lambda: False)():
                continue
            if not hasattr(other, 'register_effect') or other.dead():
                continue
            if not friendly(entity, other, battle):
                continue
            try:
                distance = battle_map.distance(entity, other)
            except Exception:
                continue
            if distance <= reach:
                nearby.append((distance, other))
        nearby.sort(key=lambda pair: pair[0])
        members.extend(other for _, other in nearby[:max(0, limit - 1)])
        return members

    def resolve(self, entity, battle, spell_action, battle_map):
        members = self.members_for(entity, battle)
        self.member_uids = ','.join(m.entity_uid for m in members)
        return [{
            'type': 'rope_trick',
            'source': entity,
            'target': entity,
            'members': members,
            'effect': self,
            'spell': self.properties,
        }]

    @staticmethod
    def action_restriction(entity, opts=None):
        return list((opts or {}).get('value') or []) + ['attack', 'spell']

    @staticmethod
    def rope_trick(entity, opts=None):
        return True

    def members(self):
        session = getattr(self.source, 'session', None) or self.session
        out = []
        for uid in [u for u in str(self.member_uids or '').split(',') if u]:
            member = session.entity_by_uid(uid) if session is not None else None
            if member is not None:
                out.append(member)
        return out

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'rope_trick':
            return None
        source, effect = item['source'], item['effect']
        session = session or (battle.session if battle is not None else source.session)
        duration = int(effect.properties.get('duration_seconds', 3600))
        members = item.get('members') or [source]
        for member in members:
            source.add_casted_effect({'target': member, 'effect': effect,
                                      'expiration': session.game_time + duration})
            for key in ('rope_trick', 'action_restriction'):
                member.register_effect(key, RopeTrickSpell, effect=effect, source=source, duration=duration)
            member.targettable = False
        session.event_manager.received_event({
            'event': 'rope_trick', 'source': source, 'target': source,
            'members': [m.label() if hasattr(m, 'label') else str(m) for m in members],
        })
        return source

    def restore_hooks(self):
        for member in self.members():
            if member.has_effect('rope_trick'):
                member.targettable = False

    def dismiss(self, entity, _descriptor=None, opts=None):
        for member in self.members():
            member.targettable = True
            if member is entity:
                continue
            for key in ('rope_trick', 'action_restriction'):
                effects = member.effects.get(key) or []
                kept = [f for f in effects if f.get('effect') is not self]
                if kept:
                    member.effects[key] = kept
                else:
                    member.effects.pop(key, None)
        if entity is not None and hasattr(entity, 'targettable'):
            entity.targettable = True
