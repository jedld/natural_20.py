"""Stinking Cloud — 20-ft radius heavily obscured gas; CON save or lose action."""
from __future__ import annotations

from natural20.environment_zones import register_persistent_zone
from natural20.spell.extensions.persistent_zone import PersistentAoEZone
from natural20.spell.hold_person_spell import HoldPersonSpell
from natural20.spell.objects.stinking_cloud_gas import StinkingCloudGas
from natural20.spell.spell import Spell


def _map_wind_mph(battle_map) -> float:
    try:
        return float((getattr(battle_map, 'properties', None) or {}).get('map', {}).get('wind_mph', 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _wind_duration_rounds(battle_map) -> int:
    wind = _map_wind_mph(battle_map)
    if wind >= 20:
        return 1
    if wind >= 10:
        return 4
    return 10


class StinkingCloudEffect:
    """Concentration hook: removes the cloud when dismissed."""

    def __init__(self, source, zone, battle_map):
        self.source = source
        self.zone = zone
        self.battle_map = battle_map

    @property
    def id(self):
        return 'stinking_cloud'

    def __str__(self):
        return 'stinking_cloud'

    def dismiss(self, entity, effect, opts=None):
        if self.zone is not None:
            self.zone.dismiss()


class StinkingCloudZone(PersistentAoEZone):
    __slots__ = ('source', 'dc', '_tile_objects', '_square_set')

    def __init__(self, source, battle, battle_map, squares, spell, *, duration_rounds=10):
        super().__init__(
            owner=source,
            battle=battle,
            map=battle_map,
            squares=squares,
            name='stinking_cloud',
            shape='radius',
            duration_rounds=duration_rounds,
            concentration=True,
            spell=spell,
        )
        self.source = source
        self.dc = source.spell_save_dc(
            HoldPersonSpell._caster_spell_ability(source, spell_action=None)
        )
        self._tile_objects = []
        self._square_set = {tuple(s) for s in squares}

    def contains(self, pos):
        return tuple(pos) in self._square_set

    def _completely_within(self, entity) -> bool:
        if self.map is None:
            return False
        squares = self.map.entity_squares(entity)
        if not squares:
            return False
        return all(tuple(sq) in self._square_set for sq in squares)

    def _auto_succeeds_save(self, entity) -> bool:
        if hasattr(entity, 'needs_to_breathe') and not entity.needs_to_breathe():
            return True
        if hasattr(entity, 'immune_to_condition') and entity.immune_to_condition('poisoned'):
            return True
        immunities = getattr(entity, 'damage_immunities', None) or []
        if 'poison' in immunities:
            return True
        condition_immunities = getattr(entity, 'condition_immunities', None) or []
        if 'poisoned' in condition_immunities:
            return True
        return False

    def apply_save(self, entity, *, reason='turn_start'):
        if entity is None or entity.dead() or not self._completely_within(entity):
            return
        if self._auto_succeeds_save(entity):
            return

        roll = entity.save_throw('constitution', self.battle, {'is_magical': True})
        success = roll.result() >= self.dc
        lost_action = False

        if not success and self.battle is not None:
            state = self.battle.entity_state_for(entity)
            state['action'] = 0
            lost_action = True

        self.source.session.event_manager.received_event({
            'event': 'stinking_cloud_save',
            'source': self.source,
            'target': entity,
            'roll': roll,
            'dc': self.dc,
            'save_type': 'constitution',
            'success': success,
            'reason': reason,
            'lost_action': lost_action,
        })

    def on_turn_start(self, entity):
        self.apply_save(entity, reason='turn_start')

    def on_dismiss(self):
        for tile in list(self._tile_objects):
            try:
                if tile in self.map.interactable_objects or tile in self.map.entities:
                    self.map.remove(tile)
            except Exception:
                pass
        self._tile_objects.clear()


class StinkingCloudSpell(Spell):
    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [{
                'type': 'select_empty_space',
                'num': 1,
                'range': self.properties.get('range', 90),
            }],
            'next': set_target,
        }

    def _cloud_squares(self, battle_map, center):
        radius_ft = int(self.properties.get('radius', 20))
        return battle_map.squares_in_radius(tuple(center), radius_ft, require_los=False)

    def resolve(self, entity, battle, spell_action, battle_map):
        center = spell_action.target
        squares = self._cloud_squares(battle_map, center)
        if not squares:
            return [{
                'type': 'spell_miss',
                'source': entity,
                'target': entity,
                'attack_name': 'stinking_cloud',
                'message': 'invalid_area',
                'spell': self.properties,
            }]
        return [{
            'type': 'stinking_cloud',
            'source': entity,
            'target': list(center),
            'squares': [list(s) for s in squares],
            'effect': self,
            'spell': self.properties,
            'map': battle_map,
            'duration_rounds': _wind_duration_rounds(battle_map),
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'stinking_cloud':
            return None

        if battle and session is None:
            session = battle.session
        source = item.get('source')
        if session is None and source is not None:
            session = getattr(source, 'session', None)
        if session is None:
            return None

        battle_map = item.get('map') or (battle.map_for(source) if battle else None)
        if battle_map is None:
            return None

        squares = [tuple(s) for s in item.get('squares', [])]
        effect = item.get('effect')
        duration_rounds = int(item.get('duration_rounds', 10))

        source.remove_effect('stinking_cloud')

        zone = StinkingCloudZone(
            source,
            battle,
            battle_map,
            squares,
            effect,
            duration_rounds=duration_rounds,
        )
        for pos in squares:
            tile = StinkingCloudGas(session, battle_map, source, zone)
            battle_map.place_object(tile, pos[0], pos[1])
            zone._tile_objects.append(tile)

        register_persistent_zone(zone, battle)

        dismiss_effect = StinkingCloudEffect(source, zone, battle_map)
        source.add_casted_effect({
            'target': zone,
            'effect': dismiss_effect,
            'expiration': session.game_time + int(item.get('spell', {}).get('duration_seconds', 60)),
        })
        source.register_effect(
            'stinking_cloud',
            StinkingCloudSpell,
            effect=dismiss_effect,
            source=source,
            duration=int(item.get('spell', {}).get('duration_seconds', 60)),
        )
        if battle is not None and hasattr(battle, 'start_concentration'):
            battle.start_concentration(source, dismiss_effect)
        else:
            source.concentration_on(dismiss_effect)

        session.event_manager.received_event({
            'event': 'stinking_cloud',
            'source': source,
            'target': item.get('target'),
            'squares': item.get('squares', []),
            'spell': effect,
        })
        return zone
