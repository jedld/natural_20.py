"""Create Bonfire (Xanathar's Guide) — bonus-action flame cube.

A 5-foot cube of magical flame appears in range; it is not fuel-dependent and
lasts while you concentrate (up to 1 minute). As a bonus action on your turn,
each creature in the bonfire's space makes a Dexterity saving throw or takes
2d8 fire damage (3d8 at 5th level, 4d8 at 11th, 5d8 at 17th). The engine
fires that strike automatically at the start of the caster's turn and
consumes the caster's bonus action when one is available.
"""
from __future__ import annotations

import uuid

from natural20.die_roll import DieRoll
from natural20.environment_zones import register_persistent_zone
from natural20.spell.extensions.persistent_zone import PersistentAoEZone
from natural20.spell.objects.zone_tile import ZoneTile
from natural20.spell.spell import Spell
from natural20.utils.attack_util import damage_event


class BonfireTile(ZoneTile):
    """One square of magical flame."""

    def __init__(self, session, battle_map, source, zone):
        self.source = source
        self.zone = zone
        self._uid = f"bonfire_tile:{uuid.uuid4()}"
        super().__init__(
            session,
            battle_map,
            {
                'name': 'Bonfire',
                'description': 'Flame hangs in the air, unattached to any fuel.',
                'entity_uid': self._uid,
                'type': 'bonfire_tile',
                'movement_cost': 1,
                'passable': True,
                'placeable': True,
                'opaque': False,
                'targettable': False,
                'bonfire': True,
            },
        )


class CreateBonfireEffect:
    """Concentration hook: removes the flames when dismissed."""

    def __init__(self, source, zone):
        self.source = source
        self.zone = zone

    @property
    def id(self):
        return 'create_bonfire'

    def __str__(self):
        return 'create_bonfire'

    def dismiss(self, entity, effect, opts=None):
        if self.zone is not None:
            self.zone.dismiss()


class CreateBonfireZone(PersistentAoEZone):
    __slots__ = ('source', 'damage_dice', 'save', '_tile_objects', '_square_set')

    def __init__(self, source, battle, battle_map, squares, spell, *,
                 damage_dice='2d8', save='dexterity', duration_rounds=10):
        super().__init__(
            owner=source,
            battle=battle,
            map=battle_map,
            squares=squares,
            name='create_bonfire',
            shape='radius',
            duration_rounds=duration_rounds,
            concentration=True,
            spell=spell,
        )
        self.source = source
        self.damage_dice = damage_dice
        self.save = save
        self._tile_objects = []
        self._square_set = {tuple(s) for s in squares}

    def contains(self, pos):
        return tuple(pos) in self._square_set

    def occupants(self):
        found = []
        for pos in self._square_set:
            entity = self.map.thing_at(pos[0], pos[1]) if hasattr(self.map, 'thing_at') else None
            if entity is not None and not getattr(entity, 'object', lambda: False)() \
                    and entity not in found:
                found.append(entity)
        return found

    def _dc(self):
        spell = self.spell if isinstance(self.spell, dict) else \
            getattr(self.spell, 'properties', None) or {}
        return int(spell.get('save_dc') or 13)

    def strike(self, battle=None):
        """Dex save or take fire damage for every creature in the flames."""
        dc = self._dc()
        results = []
        for entity in self.occupants():
            if entity is self.source or entity.dead() or not hasattr(entity, 'take_damage'):
                continue
            if not getattr(battle or self.battle, 'opposing', lambda _a, _b: True)(
                    self.source, entity):
                continue
            roll = DieRoll.roll(str(self.damage_dice or '2d8'), battle=self.battle,
                                entity=self.source,
                                description='dice_roll.spells.create_bonfire')
            save = entity.save_throw(self.save, self.battle,
                                     {"is_magical": True, "dc": dc}) \
                if hasattr(entity, 'save_throw') else None
            if save is not None and save >= dc:
                continue
            damage_event({
                'source': self.source,
                'target': entity,
                'attack_name': 'Create Bonfire',
                'damage_type': 'fire',
                'damage_roll': roll,
                'damage': roll,
                'spell': getattr(self.spell, 'properties', None) or {'name': 'Create Bonfire'},
            }, self.battle)
            results.append(entity)
        return results

    def on_turn_start(self, entity):
        if entity is self.source:
            battle = self.battle
            if battle is not None:
                try:
                    if (battle.entity_state_for(entity) or {}).get('bonus_action', 0) < 1:
                        return None
                    battle.consume(entity, 'bonus_action')
                except Exception:
                    pass
            self.strike(battle)
        return None

    def on_dismiss(self):
        for tile in list(self._tile_objects):
            try:
                if tile in self.map.interactable_objects or tile in self.map.entities:
                    self.map.remove(tile)
            except Exception:
                pass
        self._tile_objects.clear()


class CreateBonfireSpell(Spell):

    def _damage_dice(self, entity):
        level = getattr(entity, 'cantrip_level', lambda: 1)()
        dice = 2
        for step in (5, 11, 17):
            if level >= step:
                dice += 1
        return f'{dice}d8'

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
                     'attack_name': 'Create Bonfire', 'message': 'no_target',
                     'spell': self.properties}]
        from natural20.spell.hold_person_spell import HoldPersonSpell
        ability = HoldPersonSpell._caster_spell_ability(entity, spell_action)
        return [{
            'type': 'create_bonfire',
            'source': entity,
            'target': [int(point[0]), int(point[1])],
            'squares': [[int(point[0]), int(point[1])]],
            'effect': self,
            'spell': self.properties,
            'damage_dice': self._damage_dice(entity),
            'save_dc': entity.spell_save_dc(ability) if hasattr(entity, 'spell_save_dc') else 13,
            'map': battle_map,
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'create_bonfire':
            return None
        source = item['source']
        if session is None:
            session = battle.session if battle is not None else source.session
        battle_map = item.get('map') or (battle.map_for(source) if battle else None)
        if battle_map is None:
            return None
        spell = item.get('spell') or {}
        duration = int(spell.get('duration_seconds', 60))
        squares = [tuple(s) for s in item.get('squares', [])]

        source.remove_effect('create_bonfire')
        zone = CreateBonfireZone(
            source, battle, battle_map, squares, item.get('effect'),
            damage_dice=item.get('damage_dice', '2d8'),
            save=spell.get('save', 'dexterity'),
            duration_rounds=max(1, duration // 6))
        # Stash the computed save DC on the spell properties view the zone reads.
        zone_props = getattr(item.get('effect'), 'properties', None)
        if isinstance(zone_props, dict):
            zone_props['save_dc'] = item.get('save_dc', 13)
        for pos in squares:
            tile = BonfireTile(session, battle_map, source, zone)
            battle_map.place_object(tile, pos[0], pos[1])
            zone._tile_objects.append(tile)
        register_persistent_zone(zone, battle)

        effect = CreateBonfireEffect(source, zone)
        source.add_casted_effect({
            'target': zone,
            'effect': effect,
            'expiration': session.game_time + duration,
        })
        source.register_effect('create_bonfire', CreateBonfireSpell, effect=effect,
                               source=source, duration=duration)
        if battle is not None and hasattr(battle, 'start_concentration'):
            battle.start_concentration(source, effect)
        else:
            source.concentration_on(effect)

        session.event_manager.received_event({
            'event': 'create_bonfire',
            'source': source,
            'target': item.get('target'),
            'spell': item.get('effect'),
        })
        return zone
