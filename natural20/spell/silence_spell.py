"""Silence — 20-ft-radius sphere of magical silence (SRD, concentration 10 minutes, ritual).

Every square of the sphere gets a ``SilenceTile`` (``silenced: true``), so
the generic silence checks in ``natural20/utils/silence.py`` apply:

* creatures inside can't speak or hear (``combat_comms``; treated as Deafened
  for speech and callouts — the Deafened status itself is not applied),
* creatures inside can't cast spells with a verbal component
  (``spell_requirements.environment_issue`` → ``silenced``),
* creatures inside are immune to thunder damage (``SilenceWard``, an
  ``immunity_override`` effect that checks the creature's square each time).
"""
from __future__ import annotations

from natural20.environment_zones import register_persistent_zone
from natural20.spell.extensions.persistent_zone import PersistentAoEZone
from natural20.spell.objects.silence_tile import SilenceTile
from natural20.spell.spell import Spell
from natural20.utils.silence import entity_in_silenced_area

WARD_KEY = 'immunity_override'


class SilenceWard:
    """Thunder immunity for whoever stands in a silenced square right now."""

    @property
    def id(self):
        return 'silence_ward'

    def __str__(self):
        return 'silence_ward'

    @staticmethod
    def immunity_override(entity, opts=None):
        value = list((opts or {}).get('value') or [])
        if entity_in_silenced_area(entity) and 'thunder' not in value:
            value.append('thunder')
        return value

    def dismiss(self, entity, effect, opts=None):
        return None


def has_silence_ward(entity) -> bool:
    return any(isinstance(f.get('effect'), SilenceWard)
               for f in (getattr(entity, 'effects', {}) or {}).get(WARD_KEY, []))


def ensure_silence_ward(entity):
    if entity is None or not hasattr(entity, 'register_effect') or has_silence_ward(entity):
        return
    ward = SilenceWard()
    entity.register_effect(WARD_KEY, ward, effect=ward)


def drop_silence_ward(entity):
    effects = getattr(entity, 'effects', None)
    if not effects or WARD_KEY not in effects:
        return
    if entity_in_silenced_area(entity):
        return
    effects[WARD_KEY] = [f for f in effects[WARD_KEY] if not isinstance(f.get('effect'), SilenceWard)]
    if not effects[WARD_KEY]:
        del effects[WARD_KEY]


class SilenceEffect:
    """Concentration hook on the caster: removes the sphere when dismissed.

    Registered under ``silence_zone`` (never ``silence``, which
    ``entity_in_magical_silence`` treats as "this creature is silenced")."""

    def __init__(self, source, zone):
        self.source = source
        self.zone = zone

    @property
    def id(self):
        return 'silence_zone'

    def __str__(self):
        return 'silence'

    def dismiss(self, entity, effect, opts=None):
        if self.zone is not None:
            self.zone.dismiss()


class SilenceZone(PersistentAoEZone):
    __slots__ = ('source', '_tile_objects', '_square_set', 'warded_uids')

    def __init__(self, source, battle, battle_map, squares, spell, *, duration_rounds=100):
        super().__init__(
            owner=source,
            battle=battle,
            map=battle_map,
            squares=squares,
            name='silence',
            shape='radius',
            duration_rounds=duration_rounds,
            concentration=True,
            spell=spell,
        )
        self.source = source
        self._tile_objects = []
        self._square_set = {tuple(s) for s in squares}
        self.warded_uids = []

    def contains(self, pos):
        square_set = getattr(self, '_square_set', None)
        if not square_set:
            square_set = self._square_set = {tuple(s) for s in self.squares}
        return tuple(pos) in square_set

    def _ward(self, entity):
        if entity is None or getattr(entity, 'object', lambda: False)():
            return
        ensure_silence_ward(entity)
        uid = getattr(entity, 'entity_uid', None)
        if uid and uid not in self.warded_uids:
            self.warded_uids.append(uid)

    def sync_occupants(self):
        for entity in self.occupants():
            self._ward(entity)

    def on_movement_step(self, entity, from_pos, to_pos):
        if to_pos is not None and self.contains(to_pos):
            self._ward(entity)

    def on_turn_start(self, entity):
        self._ward(entity)

    def on_enter(self, entity):
        self._ward(entity)

    def on_dismiss(self):
        for tile in list(self._tile_objects):
            try:
                if tile in self.map.interactable_objects or tile in self.map.entities:
                    self.map.remove(tile)
            except Exception:
                pass
        self._tile_objects.clear()
        session = getattr(self.source, 'session', None)
        for uid in list(self.warded_uids or []):
            entity = session.entity_by_uid(uid) if session is not None else None
            if entity is not None:
                drop_silence_ward(entity)
        self.warded_uids = []


class SilenceSpell(Spell):
    @staticmethod
    def silence_zone(entity, opt=None):
        return True

    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [{
                'type': 'select_radius',
                'num': 1,
                'range': self.properties.get('range', 120),
                'radius': self.properties.get('radius', 20),
            }],
            'next': set_target,
        }

    def resolve(self, entity, battle, spell_action, battle_map):
        center = spell_action.target
        if not isinstance(center, (list, tuple)):
            center = battle_map.entity_or_object_pos(center)
        squares = battle_map.squares_in_radius(
            (int(center[0]), int(center[1])), int(self.properties.get('radius', 20)), require_los=False)
        return [{
            'type': 'silence',
            'source': entity,
            'target': [int(center[0]), int(center[1])],
            'squares': [list(s) for s in squares],
            'effect': self,
            'spell': self.properties,
            'map': battle_map,
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'silence':
            return None
        source = item['source']
        if session is None:
            session = battle.session if battle is not None else source.session
        battle_map = item.get('map') or (battle.map_for(source) if battle else None)
        if battle_map is None:
            return None
        duration = int((item.get('spell') or {}).get('duration_seconds', 600))
        squares = [tuple(s) for s in item.get('squares', [])]

        source.remove_effect('silence_zone')
        zone = SilenceZone(source, battle, battle_map, squares, item.get('effect'),
                           duration_rounds=max(1, duration // 6))
        for pos in squares:
            tile = SilenceTile(session, battle_map, source, zone)
            battle_map.place_object(tile, pos[0], pos[1])
            zone._tile_objects.append(tile)
        register_persistent_zone(zone, battle)
        zone.sync_occupants()

        effect = SilenceEffect(source, zone)
        source.add_casted_effect({
            'target': zone,
            'effect': effect,
            'expiration': session.game_time + duration,
        })
        source.register_effect('silence_zone', SilenceSpell, effect=effect, source=source,
                               duration=duration)
        if battle is not None and hasattr(battle, 'start_concentration'):
            battle.start_concentration(source, effect)
        else:
            source.concentration_on(effect)

        session.event_manager.received_event({
            'event': 'silence',
            'source': source,
            'target': item.get('target'),
            'squares': item.get('squares', []),
            'spell': item.get('effect'),
        })
        return zone
