"""Leomund's Tiny Hut — immobile 10-ft force dome (8 hours, not concentration)."""
from __future__ import annotations

from natural20.environment_zones import register_persistent_zone
from natural20.spell.spell import Spell
from natural20.spell.objects.tiny_hut import (
    TinyHutDome,
    TinyHutEffect,
    TinyHutZone,
    creatures_in_squares,
    hut_cast_violation,
    hut_interior_squares,
    objects_in_squares,
    HUT_RADIUS_FT,
)
from natural20.utils.target_validation import add_validation_issue


class LeomundsTinyHutSpell(Spell):
    """Self-centered force dome that blocks outsiders and spell lines."""

    def build_map(self, orig_action):
        action = orig_action.clone()
        action.target = action.source
        return action

    def validate(self, battle_map, target=None, battle=None):
        super().validate(battle_map, target, battle=battle)
        if battle_map is None or self.source not in battle_map.entities:
            add_validation_issue(self, 'spell.tiny_hut.no_position')
            return

        center = battle_map.entities[self.source]
        reason = hut_cast_violation(battle_map, center, self.properties.get('radius', HUT_RADIUS_FT))
        if reason == 'too_many_creatures':
            add_validation_issue(self, 'spell.tiny_hut.too_many_creatures')
        elif reason == 'creature_too_large':
            add_validation_issue(self, 'spell.tiny_hut.creature_too_large')

    def resolve(self, entity, battle, spell_action, battle_map):
        center = battle_map.entities[entity]
        radius_ft = self.properties.get('radius', HUT_RADIUS_FT)
        reason = hut_cast_violation(battle_map, center, radius_ft)
        if reason:
            return [{
                'type': 'tiny_hut_failed',
                'source': entity,
                'target': center,
                'reason': reason,
                'spell': self.properties,
                'effect': self,
            }]

        interior = hut_interior_squares(battle_map, center, radius_ft)
        creatures = creatures_in_squares(battle_map, interior)
        objects = objects_in_squares(battle_map, interior)
        allowed_creature_uids = {getattr(c, 'entity_uid', '') for c in creatures if getattr(c, 'entity_uid', None)}
        owner_uid = getattr(entity, 'entity_uid', None)
        if owner_uid:
            allowed_creature_uids.add(owner_uid)
        allowed_object_uids = set()
        for obj in objects:
            uid = getattr(obj, 'entity_uid', None)
            if uid:
                allowed_object_uids.add(uid)

        return [{
            'type': 'tiny_hut',
            'source': entity,
            'target': center,
            'center': center,
            'radius_ft': radius_ft,
            'allowed_creature_uids': list(allowed_creature_uids),
            'allowed_object_uids': list(allowed_object_uids),
            'map': battle_map,
            'effect': self,
            'spell': self.properties,
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') == 'tiny_hut_failed':
            if session is None and battle:
                session = battle.session
            if session:
                session.event_manager.received_event({
                    'event': 'tiny_hut_failed',
                    'source': item.get('source'),
                    'target': item.get('target'),
                    'reason': item.get('reason'),
                    'spell': item.get('spell'),
                })
            return item.get('source')

        if item.get('type') != 'tiny_hut':
            return None

        if battle and session is None:
            session = battle.session
        if session is None:
            return None

        source = item['source']
        battle_map = item.get('map') or (battle.map_for(source) if battle else None)
        if battle_map is None:
            return None

        center = tuple(item['center'])
        radius_ft = item.get('radius_ft', HUT_RADIUS_FT)
        duration_seconds = (item.get('spell') or {}).get('duration_seconds', 8 * 60 * 60)

        for existing in list(battle_map.interactable_objects.keys()):
            if isinstance(existing, TinyHutDome) and existing.owner is source:
                if existing.zone:
                    existing.zone.dismiss()
                else:
                    existing.remove_barriers()
                    battle_map.remove(existing)

        dome = TinyHutDome(
            session,
            battle_map,
            source,
            center,
            radius_ft=radius_ft,
            duration_seconds=duration_seconds,
            allowed_creature_uids=set(item.get('allowed_creature_uids') or []),
            allowed_object_uids=set(item.get('allowed_object_uids') or []),
        )
        battle_map.place_object(dome, center[0], center[1])
        dome.place_barriers()

        zone = TinyHutZone(source, battle, battle_map, dome, item.get('effect'), duration_seconds)
        register_persistent_zone(zone, battle)

        effect = TinyHutEffect(dome, zone)
        source.add_casted_effect({
            'target': center,
            'effect': effect,
            'expiration': session.game_time + duration_seconds,
        })
        source.register_effect('tiny_hut', LeomundsTinyHutSpell, effect=effect, source=source,
                               duration=duration_seconds)

        session.event_manager.received_event({
            'event': 'tiny_hut',
            'spell': item.get('effect'),
            'source': source,
            'target': center,
            'squares': [list(s) for s in dome.interior_squares],
            'shell_squares': [list(s) for s in dome.shell_squares],
            'dome_color': dome.dome_color,
        })
        return source

    @staticmethod
    def set_interior_lighting(source, mode: str, session=None):
        """Command the hut interior to dim or darken (caster only)."""
        for effect_entry in getattr(source, 'current_effects', lambda: [])() or []:
            effect = effect_entry.get('effect')
            if isinstance(effect, TinyHutEffect):
                effect.dome.set_interior_lighting(mode)
                for barrier in effect.dome._barriers:
                    barrier.properties['interior_lighting'] = mode
                if session:
                    session.event_manager.received_event({
                        'event': 'tiny_hut_lighting',
                        'source': source,
                        'target': effect.dome.center,
                        'mode': mode,
                    })
                return True
        return False
