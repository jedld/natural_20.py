"""Sleet Storm — 40-ft-radius cylinder of freezing rain and sleet.

The area is heavily obscured and difficult terrain. A creature that enters
the area for the first time on a turn, or starts its turn there, makes a
Dexterity save or falls prone. A creature that starts its turn there while
concentrating makes a Constitution save against the caster's spell DC or
loses concentration.
"""
from __future__ import annotations

from natural20.environment_zones import register_persistent_zone
from natural20.spell.extensions.persistent_zone import PersistentAoEZone
from natural20.spell.hold_person_spell import HoldPersonSpell
from natural20.spell.objects.sleet_storm_tile import SleetStormTile
from natural20.spell.spell import Spell


class SleetStormEffect:
    """Concentration hook: removes the storm when dismissed."""

    def __init__(self, source, zone):
        self.source = source
        self.zone = zone

    @property
    def id(self):
        return 'sleet_storm'

    def __str__(self):
        return 'sleet_storm'

    def dismiss(self, entity, effect, opts=None):
        if self.zone is not None:
            self.zone.dismiss()


class SleetStormZone(PersistentAoEZone):
    __slots__ = ('source', 'dc', '_tile_objects', '_square_set', '_saved')

    def __init__(self, source, battle, battle_map, squares, spell, *, dc, duration_rounds=10):
        super().__init__(
            owner=source,
            battle=battle,
            map=battle_map,
            squares=squares,
            name='sleet_storm',
            shape='radius',
            duration_rounds=duration_rounds,
            concentration=True,
            spell=spell,
        )
        self.source = source
        self.dc = dc
        self._tile_objects = []
        self._square_set = {tuple(s) for s in squares}
        self._saved = {}

    def contains(self, pos):
        return tuple(pos) in self._square_set

    def _turn_key(self):
        if self.battle is not None:
            return (self.battle.current_round(), getattr(self.battle, 'current_turn_index', 0))
        return getattr(getattr(self.source, 'session', None), 'game_time', 0)

    def slip_save(self, entity, reason='turn_start'):
        if entity is None or entity.dead():
            return None
        uid = getattr(entity, 'entity_uid', id(entity))
        key = self._turn_key()
        if self._saved.get(uid) == key:
            return None
        self._saved[uid] = key

        roll = entity.save_throw('dexterity', self.battle, {'is_magical': True, 'dc': self.dc})
        success = roll.result() >= self.dc
        became_prone = False
        if not success and not entity.prone():
            entity.do_prone()
            became_prone = True
        self.source.session.event_manager.received_event({
            'event': 'sleet_storm_save',
            'source': self.source,
            'target': entity,
            'roll': roll,
            'dc': self.dc,
            'save_type': 'dexterity',
            'success': success,
            'reason': reason,
            'became_prone': became_prone,
        })
        return success

    def concentration_save(self, entity):
        concentration = getattr(entity, 'concentration', None)
        if entity is None or entity.dead() or concentration is None:
            return None
        roll = entity.save_throw('constitution', self.battle,
                                 {'is_magical': True, 'dc': self.dc, 'concentration': concentration})
        success = roll.result() >= self.dc
        self.source.session.event_manager.received_event({
            'source': entity,
            'event': 'concentration_check',
            'result': 'success' if success else 'failure',
            'effect': concentration,
            'roll': roll,
            'dc': self.dc,
        })
        if not success:
            entity.dismiss_effect(concentration)
        return success

    def on_turn_start(self, entity):
        self.slip_save(entity, reason='turn_start')
        self.concentration_save(entity)

    def on_enter(self, entity):
        self.slip_save(entity, reason='enter')

    def on_dismiss(self):
        for tile in list(self._tile_objects):
            try:
                if tile in self.map.interactable_objects or tile in self.map.entities:
                    self.map.remove(tile)
            except Exception:
                pass
        self._tile_objects.clear()


class SleetStormSpell(Spell):
    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [{
                'type': 'select_radius',
                'num': 1,
                'range': self.properties.get('range', 150),
                'radius': self.properties.get('radius', 40),
            }],
            'next': set_target,
        }

    def resolve(self, entity, battle, spell_action, battle_map):
        center = spell_action.target
        squares = battle_map.squares_in_radius(
            (int(center[0]), int(center[1])), int(self.properties.get('radius', 40)), require_los=False)
        return [{
            'type': 'sleet_storm',
            'source': entity,
            'target': [int(center[0]), int(center[1])],
            'squares': [list(s) for s in squares],
            'effect': self,
            'spell': self.properties,
            'map': battle_map,
            'dc': entity.spell_save_dc(HoldPersonSpell._caster_spell_ability(entity, spell_action)),
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'sleet_storm':
            return None
        source = item['source']
        if session is None:
            session = battle.session if battle is not None else source.session
        battle_map = item.get('map') or (battle.map_for(source) if battle else None)
        if battle_map is None:
            return None
        duration = int((item.get('spell') or {}).get('duration_seconds', 60))
        squares = [tuple(s) for s in item.get('squares', [])]

        source.remove_effect('sleet_storm')
        zone = SleetStormZone(source, battle, battle_map, squares, item.get('effect'),
                              dc=item['dc'], duration_rounds=max(1, duration // 6))
        for pos in squares:
            tile = SleetStormTile(session, battle_map, source, zone)
            battle_map.place_object(tile, pos[0], pos[1])
            zone._tile_objects.append(tile)
        register_persistent_zone(zone, battle)

        effect = SleetStormEffect(source, zone)
        source.add_casted_effect({
            'target': zone,
            'effect': effect,
            'expiration': session.game_time + duration,
        })
        source.register_effect('sleet_storm', SleetStormSpell, effect=effect, source=source,
                               duration=duration)
        if battle is not None and hasattr(battle, 'start_concentration'):
            battle.start_concentration(source, effect)
        else:
            source.concentration_on(effect)

        session.event_manager.received_event({
            'event': 'sleet_storm',
            'source': source,
            'target': item.get('target'),
            'squares': item.get('squares', []),
            'spell': item.get('effect'),
        })
        return zone
