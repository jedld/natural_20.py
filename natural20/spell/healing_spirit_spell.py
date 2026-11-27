"""Healing Spirit (Xanathar's Guide) — concentration spirit that mends allies.

A 5-foot-cube spirit appears in range and lasts while you concentrate (up to
1 hour). A creature that enters the spirit's space for the first time on a
turn, or starts its turn there, regains hit points (1d6; the spell YAML may
scale the dice). Undead and constructs gain nothing. Moving the spirit with a
bonus action is DM-narrated in the VTT (recast to reposition).
"""
from __future__ import annotations

import uuid

from natural20.die_roll import DieRoll
from natural20.environment_zones import register_persistent_zone
from natural20.spell.extensions.persistent_zone import PersistentAoEZone
from natural20.spell.objects.zone_tile import ZoneTile
from natural20.spell.spell import Spell


def _cannot_be_healed(entity):
    if entity is None:
        return True
    types = set()
    try:
        from natural20.spell.condition_spells import _creature_types
        types = {str(t).lower() for t in (_creature_types(entity) or [])}
    except Exception:
        pass
    race = getattr(entity, 'race', None)
    if callable(race):
        try:
            race = race()
        except Exception:
            race = None
    if isinstance(race, (list, tuple, set)):
        types |= {str(r).lower() for r in race}
    return bool(types & {'undead', 'construct'})


class HealingSpiritTile(ZoneTile):
    """One square of the mending spirit's area."""

    def __init__(self, session, battle_map, source, zone):
        self.source = source
        self.zone = zone
        self._uid = f"healing_spirit_tile:{uuid.uuid4()}"
        super().__init__(
            session,
            battle_map,
            {
                'name': 'Healing Spirit',
                'description': 'A gentle shape wreathed in soothing green light.',
                'entity_uid': self._uid,
                'type': 'healing_spirit_tile',
                'movement_cost': 1,
                'passable': True,
                'placeable': True,
                'opaque': False,
                'targettable': False,
                'healing_spirit': True,
            },
        )


class HealingSpiritEffect:
    """Concentration hook: removes the spirit when dismissed."""

    def __init__(self, source, zone):
        self.source = source
        self.zone = zone

    @property
    def id(self):
        return 'healing_spirit'

    def __str__(self):
        return 'healing_spirit'

    def dismiss(self, entity, effect, opts=None):
        if self.zone is not None:
            self.zone.dismiss()


class HealingSpiritZone(PersistentAoEZone):
    __slots__ = ('source', 'heal_dice', '_tile_objects', '_square_set', '_healed_turn')

    def __init__(self, source, battle, battle_map, squares, spell, *,
                 heal_dice='1d6', duration_rounds=100):
        super().__init__(
            owner=source,
            battle=battle,
            map=battle_map,
            squares=squares,
            name='healing_spirit',
            shape='radius',
            duration_rounds=duration_rounds,
            concentration=True,
            spell=spell,
        )
        self.source = source
        self.heal_dice = heal_dice
        self._tile_objects = []
        self._square_set = {tuple(s) for s in squares}
        self._healed_turn = {}

    def contains(self, pos):
        return tuple(pos) in self._square_set

    def in_area(self, entity):
        pos = self.map.position_of(entity) if self.map is not None else None
        return pos is not None and self.contains(pos)

    def _turn_key(self):
        battle = self.battle
        if battle is None:
            return None
        return (battle.current_round(), getattr(battle, 'current_turn_index', 0))

    def heal(self, entity):
        if entity is None or entity.dead() or _cannot_be_healed(entity):
            return None
        if not hasattr(entity, 'heal'):
            return None
        key = self._turn_key()
        uid = getattr(entity, 'entity_uid', id(entity))
        if key is not None and self._healed_turn.get(uid) == key:
            return None
        self._healed_turn[uid] = key
        roll = DieRoll.roll(str(self.heal_dice or '1d6'), battle=self.battle,
                            entity=self.source,
                            description='dice_roll.spells.healing_spirit')
        amount = roll.result()
        if amount > 0:
            entity.heal(amount)
        self.source.session.event_manager.received_event({
            'event': 'healing_spirit', 'source': self.source, 'target': entity,
            'amount': amount,
        })
        return amount

    def on_turn_start(self, entity):
        if self.in_area(entity):
            return self.heal(entity)
        return None

    def on_movement_step(self, entity, from_pos, to_pos):
        if from_pos is None or to_pos is None or tuple(from_pos) == tuple(to_pos):
            return None
        if self.contains(to_pos):
            return self.heal(entity)
        return None

    def on_dismiss(self):
        for tile in list(self._tile_objects):
            try:
                if tile in self.map.interactable_objects or tile in self.map.entities:
                    self.map.remove(tile)
            except Exception:
                pass
        self._tile_objects.clear()


class HealingSpiritSpell(Spell):

    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [{'type': 'select_empty_space', 'num': 1,
                       'range': self.properties.get('range', 60),
                       'require_los': True}],
            'next': set_target,
        }

    def resolve(self, entity, battle, spell_action, battle_map):
        point = spell_action.target
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            return [{'type': 'spell_miss', 'source': entity, 'target': entity,
                     'attack_name': 'Healing Spirit', 'message': 'no_target',
                     'spell': self.properties}]
        return [{
            'type': 'healing_spirit',
            'source': entity,
            'target': [int(point[0]), int(point[1])],
            'squares': [[int(point[0]), int(point[1])]],
            'effect': self,
            'spell': self.properties,
            'map': battle_map,
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'healing_spirit':
            return None
        source = item['source']
        if session is None:
            session = battle.session if battle is not None else source.session
        battle_map = item.get('map') or (battle.map_for(source) if battle else None)
        if battle_map is None:
            return None
        spell = item.get('spell') or {}
        duration = int(spell.get('duration_seconds', 3600))
        squares = [tuple(s) for s in item.get('squares', [])]

        source.remove_effect('healing_spirit')
        zone = HealingSpiritZone(source, battle, battle_map, squares,
                                 item.get('effect'),
                                 heal_dice=spell.get('heal_dice', '1d6'),
                                 duration_rounds=max(1, duration // 6))
        for pos in squares:
            tile = HealingSpiritTile(session, battle_map, source, zone)
            battle_map.place_object(tile, pos[0], pos[1])
            zone._tile_objects.append(tile)
        register_persistent_zone(zone, battle)

        effect = HealingSpiritEffect(source, zone)
        source.add_casted_effect({
            'target': zone,
            'effect': effect,
            'expiration': session.game_time + duration,
        })
        source.register_effect('healing_spirit', HealingSpiritSpell, effect=effect,
                               source=source, duration=duration)
        if battle is not None and hasattr(battle, 'start_concentration'):
            battle.start_concentration(source, effect)
        else:
            source.concentration_on(effect)

        session.event_manager.received_event({
            'event': 'healing_spirit',
            'source': source,
            'target': item.get('target'),
            'spell': item.get('effect'),
        })
        return zone
