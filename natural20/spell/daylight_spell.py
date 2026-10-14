"""Daylight — 3rd-level evocation (SRD), 1 hour, not concentration.

A 60-foot-radius sphere of bright light (plus dim light for another 60 feet)
spreads from a point the caster chooses within 60 feet, or from an object the
caster holds so the light moves with it. Magical darkness created by a spell
of level 3 or lower that overlaps the sphere is dispelled.

Two casting modes (``select_choice`` first):

* ``point`` — places a ``DaylightSource`` map object at an empty square (read
  by the static light builder like any light-emitting entity).
* ``held`` — the caster carries the light: a ``light_override`` effect on the
  caster (bright 60 / dim 60), the same mechanism as the Light cantrip.

``DaylightEffect`` sits in the caster's ``casted_effects`` with a 1-hour
expiration; dismissing it removes the map object or the light override.
"""
from __future__ import annotations

import uuid

from natural20.spell.objects.daylight import DaylightSource
from natural20.spell.objects.darkness import Darkness
from natural20.spell.spell import Spell


class DaylightEffect:
    """Marker for one active Daylight (point object or carried light)."""

    def __init__(self, source, target=None, light_object=None, battle_map=None):
        self.source = source
        self.target = target
        self.light_object = light_object
        self.battle_map = battle_map
        # Unique per cast: Entity.remove_effect drops every casted effect sharing an id.
        self.instance_id = f"daylight:{uuid.uuid4().hex[:12]}"

    @property
    def id(self):
        return self.instance_id

    def __str__(self):
        return 'daylight'

    def label(self):
        return 'Daylight'

    def relink_maps(self, maps):
        """Save/load hook: restore the map handle dropped by serialization."""
        anchor = self.light_object if self.light_object is not None else self.target
        for battle_map in maps:
            if anchor is not None and anchor in getattr(battle_map, 'entities', {}):
                self.battle_map = battle_map
                return

    def _map_for(self, entity):
        battle_map = getattr(self, 'battle_map', None)
        if battle_map is not None:
            return battle_map
        session = getattr(self.source, 'session', None) or getattr(entity, 'session', None)
        if session is None or entity is None:
            return None
        try:
            return session.map_for(entity)
        except Exception:
            return None

    def dismiss(self, entity, effect, opts=None):
        light_object = self.light_object
        if light_object is not None and not isinstance(light_object, str):
            battle_map = self._map_for(light_object)
            if battle_map is not None and light_object in battle_map.entities:
                battle_map.remove(light_object)
                battle_map.invalidate_dynamic_lights()
        target = self.target
        if target is not None and not isinstance(target, str):
            target.effects = {
                key: [f for f in value if f.get('effect') is not self]
                for key, value in (getattr(target, 'effects', None) or {}).items()
            }
            battle_map = self._map_for(target)
            if battle_map is not None:
                battle_map.invalidate_dynamic_lights()


def darkness_dispelled_by(battle_map, center, radius_feet, max_level=3):
    """``Darkness`` objects on ``battle_map`` whose sphere overlaps a sphere of
    ``radius_feet`` at ``center`` and that came from a spell of ``max_level``
    or lower."""
    if battle_map is None or center is None:
        return []
    feet = battle_map.feet_per_grid or 5
    found = []
    for entity in list(battle_map.entities.keys()):
        if not isinstance(entity, Darkness):
            continue
        level = entity.spell_level if entity.spell_level is not None else 2
        if level > max_level:
            continue
        pos = battle_map.entity_or_object_pos(entity)
        if pos is None:
            continue
        reach = (int(radius_feet) + int(entity.radius_feet)) / feet
        if max(abs(pos[0] - center[0]), abs(pos[1] - center[1])) <= reach:
            found.append(entity)
    return found


def dispel_darkness_object(battle_map, darkness):
    """End the Darkness spell behind ``darkness`` (drops its caster's concentration)."""
    owner = darkness.owner
    for entry in list(getattr(owner, 'casted_effects', None) or []):
        effect = entry.get('effect')
        if getattr(effect, 'darkness', None) is darkness:
            owner.dismiss_effect(effect)
            break
    if darkness in battle_map.entities:
        battle_map.remove(darkness)
    battle_map.invalidate_dynamic_lights()


class DaylightSpell(Spell):
    BRIGHT_FEET = 60
    DIM_FEET = 60
    DURATION_SECONDS = 3600

    def _radius(self):
        return int(self.properties.get('radius', self.BRIGHT_FEET))

    def build_map(self, orig_action):
        def choose_mode(choice):
            if str(choice) == 'held':
                action = orig_action.clone()
                action.target = orig_action.source
                return action

            def set_point(target):
                action = orig_action.clone()
                action.target = target
                return action

            return {
                'param': [{
                    'type': 'select_empty_space',
                    'num': 1,
                    'range': self.properties.get('range', 60),
                }],
                'next': set_point,
            }

        return {
            'param': [{
                'type': 'select_choice',
                'choices': [['A point within range', 'point'],
                            ['An object you hold (light moves with you)', 'held']],
                'num': 1,
            }],
            'next': choose_mode,
        }

    def validate(self, battle_map, target=None, battle=None):
        self.clear_validation_errors()
        self.errors = []
        target = target if target is not None else self.target
        if target is None:
            self.errors.append('Invalid target')
            return False
        if isinstance(target, (list, tuple)):
            max_range = self.properties.get('range', 60)
            if battle_map is not None and battle_map.distance_to_square(self.source, *target) \
                    * battle_map.feet_per_grid > max_range:
                self.errors.append('Target is out of range')
        elif target is not self.source:
            self.errors.append('Daylight can only be carried by the caster')
        return len(self.errors) == 0

    def resolve(self, entity, battle, spell_action, battle_map):
        target = spell_action.target
        if isinstance(target, (list, tuple)):
            center = [int(target[0]), int(target[1])]
            carrier = None
        else:
            carrier = target or entity
            center = battle_map.entity_or_object_pos(carrier) if battle_map is not None else None
        dispelled = darkness_dispelled_by(battle_map, center, self._radius())
        return [{
            'type': 'daylight',
            'source': entity,
            'target': carrier if carrier is not None else center,
            'position': center,
            'carrier': carrier,
            'map': battle_map,
            'level': getattr(spell_action, 'at_level', None) or self.properties.get('level', 3),
            'dispelled': dispelled,
            'effect': self,
            'spell': self.properties,
        }]

    @staticmethod
    def light_override(entity, opt=None):
        opt = opt or {}
        return {
            'bright': max(opt.get('bright', 0) or 0, DaylightSpell.BRIGHT_FEET),
            'dim': max(opt.get('dim', 0) or 0, DaylightSpell.DIM_FEET),
        }

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'daylight':
            return None
        if battle is not None and session is None:
            session = battle.session
        source = item['source']
        battle_map = item.get('map')
        carrier = item.get('carrier')
        duration = int((item.get('spell') or {}).get('duration_seconds', DaylightSpell.DURATION_SECONDS))

        for darkness in item.get('dispelled') or []:
            if battle_map is not None:
                dispel_darkness_object(battle_map, darkness)

        if carrier is not None:
            marker = DaylightEffect(source, target=carrier, battle_map=battle_map)
            carrier.register_effect('light_override', DaylightSpell, effect=marker,
                                    source=source, duration=duration)
        else:
            radius = int((item.get('spell') or {}).get('radius', DaylightSpell.BRIGHT_FEET))
            light = DaylightSource(session, source, radius_feet=radius, spell_level=item.get('level'))
            battle_map.place(item['position'], light)
            marker = DaylightEffect(source, light_object=light, battle_map=battle_map)

        source.add_casted_effect({
            'target': carrier if carrier is not None else item.get('position'),
            'effect': marker,
            'expiration': session.game_time + duration,
        })
        if battle_map is not None:
            battle_map.invalidate_dynamic_lights()

        session.event_manager.received_event({
            'event': 'daylight',
            'source': source,
            'target': carrier,
            'position': item.get('position'),
            'dispelled': len(item.get('dispelled') or []),
            'spell': marker,
        })
        return marker
