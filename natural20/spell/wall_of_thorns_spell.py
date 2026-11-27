"""Wall of Thorns (SRD) — persistent thicket zone, reuse of the Spike Growth machinery.

The area is difficult terrain (tiles with ``movement_cost: 2``). A creature
takes ``damage_per_step`` (1d10) piercing damage for every 5 feet it moves into
or within the area, and 7d8 piercing (Dex save half) when it enters the area
for the first time on a turn or starts its turn there (once per round).
"""
from __future__ import annotations

import uuid

from natural20.die_roll import DieRoll
from natural20.environment_zones import register_persistent_zone
from natural20.spell.extensions.persistent_zone import PersistentAoEZone
from natural20.spell.extensions.save_for_half import SaveForHalfMixin
from natural20.spell.hold_person_spell import HoldPersonSpell
from natural20.spell.objects.zone_tile import ZoneTile
from natural20.spell.spell import Spell
from natural20.utils.attack_util import damage_event


class WallOfThornsTile(ZoneTile):
    """Difficult-terrain square of the thorn wall."""

    def __init__(self, session, battle_map, source, zone):
        self.source = source
        self.zone = zone
        self._uid = f"wall_of_thorns_tile:{uuid.uuid4()}"
        super().__init__(
            session,
            battle_map,
            {
                'name': 'Wall of Thorns',
                'description': 'A tangle of tough, needle-bristling brush.',
                'entity_uid': self._uid,
                'type': 'wall_of_thorns_tile',
                'movement_cost': 2,
                'passable': True,
                'placeable': True,
                'opaque': False,
                'targettable': False,
                'wall_of_thorns': True,
            },
        )


class WallOfThornsEffect:
    """Concentration hook: removes the thicket when dismissed."""

    def __init__(self, source, zone):
        self.source = source
        self.zone = zone

    @property
    def id(self):
        return 'wall_of_thorns'

    def __str__(self):
        return 'wall_of_thorns'

    def dismiss(self, entity, effect, opts=None):
        if self.zone is not None:
            self.zone.dismiss()


class WallOfThornsZone(PersistentAoEZone):
    __slots__ = ('source', 'damage_dice', 'enter_dice', 'save', 'save_dc',
                 '_tile_objects', '_square_set', '_hit_this_turn')

    def __init__(self, source, battle, battle_map, squares, spell, *,
                 damage_dice='1d10', enter_dice='7d8', save='dexterity',
                 save_dc=13, duration_rounds=100):
        super().__init__(
            owner=source,
            battle=battle,
            map=battle_map,
            squares=squares,
            name='wall_of_thorns',
            shape='radius',
            duration_rounds=duration_rounds,
            concentration=True,
            spell=spell,
        )
        self.source = source
        self.damage_dice = damage_dice
        self.enter_dice = enter_dice
        self.save = save
        self.save_dc = int(save_dc or 13)
        self._tile_objects = []
        self._square_set = {tuple(s) for s in squares}
        self._hit_this_turn = {}

    def contains(self, pos):
        return tuple(pos) in self._square_set

    def in_area(self, entity):
        battle_map = self.map
        if battle_map is None or entity is None:
            return False
        pos = battle_map.position_of(entity)
        return pos is not None and self.contains(pos)

    def _turn_key(self):
        battle = self.battle
        if battle is None:
            return None
        return (battle.current_round(), getattr(battle, 'current_turn_index', 0))

    def _apply_enter_damage(self, entity):
        if entity is None or entity.dead() or not hasattr(entity, 'take_damage'):
            return None
        if getattr(entity, 'object', lambda: False)():
            return None
        key = self._turn_key()
        uid = getattr(entity, 'entity_uid', id(entity))
        if key is not None and self._hit_this_turn.get(uid) == key:
            return None
        self._hit_this_turn[uid] = key
        roll = DieRoll.roll(str(self.enter_dice or '7d8'), battle=self.battle,
                            entity=self.source,
                            description='dice_roll.spells.wall_of_thorns')
        caster_spell = self.spell  # the casting Spell instance (SaveForHalfMixin)
        items = caster_spell.resolve_save_for_half(
            [entity], ability=self.save, dc=self.save_dc, damage_roll=roll,
            attack_name='wall_of_thorns', damage_type='piercing',
            battle=self.battle,
        )
        for item in items:
            damage_event(item, self.battle)
        return items

    def on_turn_start(self, entity):
        if self.in_area(entity):
            self._apply_enter_damage(entity)
        return None

    def on_enter(self, entity):
        if self.in_area(entity):
            self._apply_enter_damage(entity)
        return None

    def on_movement_step(self, entity, from_pos, to_pos):
        if from_pos is None or to_pos is None or tuple(from_pos) == tuple(to_pos):
            return None
        if not self.contains(to_pos):
            return None
        if entity is None or entity.dead() or not hasattr(entity, 'take_damage'):
            return None
        if getattr(entity, 'object', lambda: False)():
            return None
        roll = DieRoll.roll(str(self.damage_dice or '1d10'), battle=self.battle,
                            entity=self.source,
                            description='dice_roll.spells.wall_of_thorns_step')
        damage_event({
            'source': self.source,
            'target': entity,
            'attack_name': 'Wall of Thorns',
            'damage_type': 'piercing',
            'damage_roll': roll,
            'damage': roll,
            'spell': getattr(self.spell, 'properties', None) or {'name': 'Wall of Thorns'},
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


class WallOfThornsSpell(SaveForHalfMixin, Spell):
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
            (int(center[0]), int(center[1])),
            int(self.properties.get('radius', 20)), require_los=False)
        ability = HoldPersonSpell._caster_spell_ability(entity, spell_action)
        save_dc = entity.spell_save_dc(ability) if hasattr(entity, 'spell_save_dc') else 13
        return [{
            'type': 'wall_of_thorns',
            'source': entity,
            'target': [int(center[0]), int(center[1])],
            'squares': [list(s) for s in squares],
            'effect': self,
            'spell': self.properties,
            'save_dc': save_dc,
            'map': battle_map,
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'wall_of_thorns':
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

        source.remove_effect('wall_of_thorns')
        zone = WallOfThornsZone(
            source, battle, battle_map, squares, item.get('effect'),
            damage_dice=spell.get('damage_per_step', '1d10'),
            enter_dice=spell.get('enter_damage', '7d8'),
            save=spell.get('save', 'dexterity'),
            save_dc=item.get('save_dc', 13),
            duration_rounds=max(1, duration // 6))
        for pos in squares:
            tile = WallOfThornsTile(session, battle_map, source, zone)
            battle_map.place_object(tile, pos[0], pos[1])
            zone._tile_objects.append(tile)
        register_persistent_zone(zone, battle)

        # Creatures standing in the area when it appears take the entry damage.
        for entity in list(getattr(battle_map, 'entities', []) or []):
            if zone.in_area(entity):
                zone._apply_enter_damage(entity)

        effect = WallOfThornsEffect(source, zone)
        source.add_casted_effect({
            'target': zone,
            'effect': effect,
            'expiration': session.game_time + duration,
        })
        source.register_effect('wall_of_thorns', WallOfThornsSpell, effect=effect,
                               source=source, duration=duration)
        if battle is not None and hasattr(battle, 'start_concentration'):
            battle.start_concentration(source, effect)
        else:
            source.concentration_on(effect)

        session.event_manager.received_event({
            'event': 'wall_of_thorns',
            'source': source,
            'target': item.get('target'),
            'squares': item.get('squares', []),
            'spell': item.get('effect'),
        })
        return zone
