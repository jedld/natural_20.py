"""Spike Growth — 20-ft-radius patch of thorns (SRD, concentration 10 minutes).

The area is difficult terrain. A creature takes ``damage_per_step`` (2d4)
piercing damage for every 5 feet it moves into or within the area
(``PersistentAoEZone.on_movement_step``, fired per path square by
``MoveAction.apply``). Forced movement and out-of-combat walking do not
trigger the thorns (the engine only broadcasts voluntary combat movement).
"""
from __future__ import annotations

from natural20.die_roll import DieRoll
from natural20.environment_zones import register_persistent_zone
from natural20.spell.extensions.persistent_zone import PersistentAoEZone
from natural20.spell.objects.spike_growth_tile import SpikeGrowthTile
from natural20.spell.spell import Spell
from natural20.utils.attack_util import damage_event


class SpikeGrowthEffect:
    """Concentration hook: removes the thorns when dismissed."""

    def __init__(self, source, zone):
        self.source = source
        self.zone = zone

    @property
    def id(self):
        return 'spike_growth'

    def __str__(self):
        return 'spike_growth'

    def dismiss(self, entity, effect, opts=None):
        if self.zone is not None:
            self.zone.dismiss()


class SpikeGrowthZone(PersistentAoEZone):
    __slots__ = ('source', 'damage_dice', '_tile_objects', '_square_set')

    def __init__(self, source, battle, battle_map, squares, spell, *, damage_dice='2d4',
                 duration_rounds=100):
        super().__init__(
            owner=source,
            battle=battle,
            map=battle_map,
            squares=squares,
            name='spike_growth',
            shape='radius',
            duration_rounds=duration_rounds,
            concentration=True,
            spell=spell,
        )
        self.source = source
        self.damage_dice = damage_dice
        self._tile_objects = []
        self._square_set = {tuple(s) for s in squares}

    def contains(self, pos):
        square_set = getattr(self, '_square_set', None)
        if not square_set:
            square_set = self._square_set = {tuple(s) for s in self.squares}
        return tuple(pos) in square_set

    def on_movement_step(self, entity, from_pos, to_pos):
        if from_pos is None or to_pos is None or tuple(from_pos) == tuple(to_pos):
            return None
        if not self.contains(to_pos):
            return None
        if entity is None or entity.dead() or not hasattr(entity, 'take_damage'):
            return None
        if getattr(entity, 'object', lambda: False)():
            return None
        roll = DieRoll.roll(str(self.damage_dice or '2d4'), battle=self.battle, entity=self.source,
                            description='dice_roll.spells.spike_growth')
        self.source.session.event_manager.received_event({
            'event': 'spike_growth_damage', 'source': self.source, 'target': entity,
            'position': list(to_pos),
        })
        damage_event({
            'source': self.source,
            'target': entity,
            'attack_name': 'Spike Growth',
            'damage_type': 'piercing',
            'damage_roll': roll,
            'damage': roll,
            'spell': getattr(self.spell, 'properties', None) or {'name': 'Spike Growth'},
        }, self.battle)
        return roll

    def on_dismiss(self):
        for tile in list(self._tile_objects):
            try:
                if tile in self.map.interactable_objects or tile in self.map.entities:
                    self.map.remove(tile)
            except Exception:
                pass
        self._tile_objects.clear()


class SpikeGrowthSpell(Spell):
    @staticmethod
    def spike_growth(entity, opt=None):
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
                'range': self.properties.get('range', 150),
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
            'type': 'spike_growth',
            'source': entity,
            'target': [int(center[0]), int(center[1])],
            'squares': [list(s) for s in squares],
            'effect': self,
            'spell': self.properties,
            'map': battle_map,
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'spike_growth':
            return None
        source = item['source']
        if session is None:
            session = battle.session if battle is not None else source.session
        battle_map = item.get('map') or (battle.map_for(source) if battle else None)
        if battle_map is None:
            return None
        spell = item.get('spell') or {}
        duration = int(spell.get('duration_seconds', 600))
        squares = [tuple(s) for s in item.get('squares', [])]

        source.remove_effect('spike_growth')
        zone = SpikeGrowthZone(source, battle, battle_map, squares, item.get('effect'),
                               damage_dice=spell.get('damage_per_step', '2d4'),
                               duration_rounds=max(1, duration // 6))
        for pos in squares:
            tile = SpikeGrowthTile(session, battle_map, source, zone)
            battle_map.place_object(tile, pos[0], pos[1])
            zone._tile_objects.append(tile)
        register_persistent_zone(zone, battle)

        effect = SpikeGrowthEffect(source, zone)
        source.add_casted_effect({
            'target': zone,
            'effect': effect,
            'expiration': session.game_time + duration,
        })
        source.register_effect('spike_growth', SpikeGrowthSpell, effect=effect, source=source,
                               duration=duration)
        if battle is not None and hasattr(battle, 'start_concentration'):
            battle.start_concentration(source, effect)
        else:
            source.concentration_on(effect)

        session.event_manager.received_event({
            'event': 'spike_growth',
            'source': source,
            'target': item.get('target'),
            'squares': item.get('squares', []),
            'spell': item.get('effect'),
        })
        return zone
