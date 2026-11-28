"""Rope Trick — 2nd-level transmutation (SRD, 1 hour).

Full model on the pocket-dimension system (``natural20.utils.pocket_dimension``):
casting raises a rope at the caster's square (a visible entrance object on the
map, and the Dispel Magic anchor for the whole space) and opens an invisible
doorway at its top into a dynamically generated pocket-dimension map. The
caster and up to ``max_creatures - 1`` allies within ``gather_radius`` feet
climb in automatically. While inside, creatures live on the pocket map:
attacks and spells from outside can't reach them (different maps), and they
also carry the ``rope_trick`` marker plus ``action_restriction`` (attack,
spell) so nothing leaks out through the doorway. Anyone inside can climb back
out through the inner entrance, and can pull the rope up so the entrance
disappears from view outside.

The space lasts ``duration_seconds`` of game time (zone ticking expires it),
ends on Dispel Magic (click the rope square — the zone's square — or the rope
object, which carries a ``.zone`` link), or when the caster dismisses it.
When it ends everyone inside drops out next to the rope, the pocket map is
unregistered, and the rope vanishes.
"""
from __future__ import annotations

from natural20.spell.spell import Spell
from natural20.utils.auras import _friendly as friendly


class RopeTrickSpell(Spell):
    def __init__(self, session, source, spell_name, details):
        super().__init__(session, source, spell_name, details)
        self.member_uids = ''
        self.zone_id = ''
        self.pocket_map_name = ''

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
        try:
            square = list(battle_map.position_of(entity))
        except Exception:
            square = None
        return [{
            'type': 'rope_trick',
            'source': entity,
            'target': entity,
            'members': members,
            'effect': self,
            'spell': self.properties,
            'square': square,
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

    # --- pocket dimension plumbing ------------------------------------------

    def zone(self, battle=None):
        """The live ``PocketDimensionZone`` for this cast, if any."""
        from natural20.utils.pocket_dimension import PocketDimensionZone, find_pocket_zone
        for entry in list(getattr(self.source, 'casted_effects', None) or []):
            if isinstance(entry, dict) and entry.get('effect') is self:
                target = entry.get('target')
                if isinstance(target, PocketDimensionZone) and not getattr(target, '_dismissed', False):
                    return target
        session = getattr(self.source, 'session', None) or self.session
        if session is None:
            return None
        return find_pocket_zone(
            session,
            zone_id=getattr(self, 'zone_id', '') or None,
            map_name=getattr(self, 'pocket_map_name', '') or None,
            battle=battle,
        )

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'rope_trick':
            return None
        from natural20.utils.pocket_dimension import create_pocket_dimension

        source, effect = item['source'], item['effect']
        session = session or (battle.session if battle is not None else source.session)
        battle_map = battle.map_for(source) if battle is not None else session.map_for(source)
        if battle_map is None:
            return None
        square = item.get('square')
        if not square:
            square = list(battle_map.position_of(source))

        props = effect.properties or {}
        duration = int(props.get('duration_seconds', 3600) or 3600)
        members = item.get('members') or [source]

        zone = create_pocket_dimension(
            session, source, battle, battle_map, square,
            name='rope_trick',
            label=props.get('pocket_label') or 'The Rope Trick space',
            capacity=int(props.get('max_creatures', 8) or 8),
            duration_seconds=duration,
            size_ft=int(props.get('pocket_size_ft', 30) or 30),
            illumination=float(props.get('pocket_illumination', 0.9) or 0.9),
            token_image=props.get('entrance_token') or 'rope_trick.png',
            narration=props.get('pocket_narration') or '',
            spell=effect,
        )
        effect.zone_id = zone.id
        effect.pocket_map_name = zone.pocket_map_name

        for member in members:
            source.add_casted_effect({'target': member, 'effect': effect,
                                      'expiration': session.game_time + duration})
            for key in ('rope_trick', 'action_restriction'):
                member.register_effect(key, RopeTrickSpell, effect=effect, source=source, duration=duration)
            member.targettable = False
            zone.enter(member, battle, emit=False)

        # Owner-side entry that targets the zone itself: Dispel Magic's
        # end_spell_zone routes through the caster's dismiss hook.
        source.add_casted_effect({'target': zone, 'effect': effect,
                                  'expiration': session.game_time + duration})

        session.event_manager.received_event({
            'event': 'rope_trick', 'source': source, 'target': source,
            'members': [m.label() if hasattr(m, 'label') else str(m) for m in members],
            'map': zone.pocket_map_name,
            'zone_id': zone.id,
        })
        return source

    def restore_hooks(self):
        for member in self.members():
            if member.has_effect('rope_trick'):
                member.targettable = False

    def dismiss(self, entity, _descriptor=None, opts=None):
        zone = self.zone()
        if zone is not None and not getattr(zone, '_dismissed', False):
            # Zone teardown ejects everyone next to the rope and clears the
            # member-side effects (targettable, restrictions).
            zone.dismiss('dismissed')
            if entity is not None and hasattr(entity, 'targettable') and entity.has_effect('rope_trick'):
                entity.targettable = True
            return
        # Zone already gone (expired mid-save, legacy effect): plain cleanup.
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
