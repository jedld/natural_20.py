"""Wall of Thorns (SRD) — persistent thorn wall that blocks line of sight.

SRD shape: a wall up to 60 ft long, 10 ft high and 5 ft thick, or a circle
20 ft in diameter (the wall is the ring of squares around the point). Both
are approximated on the 5 ft grid; the shape is chosen with a
``select_choice`` step and anchored with ``select_square``.

Rules implemented:
- The wall squares are opaque (they block line of sight) and very hard to
  move through (SRD: 1 ft of movement through the wall costs 4 ft, so each
  square costs 4 squares of movement).
- When the wall appears, each creature in its area makes a Dexterity saving
  throw, taking 7d8 piercing damage, or half as much on a success.
- The first time a creature enters the wall on a turn, or ends its turn
  there, it makes a Dexterity saving throw, taking 7d8 slashing damage on a
  failed save, or half as much on a successful one.
- Casting with a slot above 6th adds 1d8 to both damage dice per slot level
  above 6th.

Rendering: tiles carry a ``wall_of_thorns`` marker flag picked up by the 2D
renderer (``wall_of_thorns_marker``) and the 3D map state classifier
(``wall_of_thorns_tile`` -> the ``thorns`` fixture kind).
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

SHAPES = ('wall', 'wall_ns', 'circle')


def wall_of_thorns_squares(battle_map, center, shape, *,
                           wall_length_ft=60, circle_diameter_ft=20):
    """Grid squares of the wall shape anchored at ``center``.

    ``wall`` / ``wall_ns``: a straight wall ``wall_length_ft`` long, centered
    on the point, running east-west / north-south. ``circle``: the ring of
    squares forming a circle of ``circle_diameter_ft`` diameter centered on
    the point (5 ft thick).
    """
    cx, cy = int(center[0]), int(center[1])
    w, h = battle_map.size
    squares = []

    def add(x, y):
        if 0 <= x < w and 0 <= y < h and (x, y) not in squares:
            squares.append((x, y))

    if shape == 'circle':
        # 20 ft diameter on a 5 ft grid -> a 4x4 ring (outer 20 ft, inner
        # 10 ft hole), centered on the clicked square.
        side = max(2, int(circle_diameter_ft) // battle_map.feet_per_grid)
        lo = -(side // 2)
        hi = side // 2 - 1
        for dx in range(lo, hi + 1):
            for dy in range(lo, hi + 1):
                if dx in (lo, hi) or dy in (lo, hi):
                    add(cx + dx, cy + dy)
    else:
        # Straight wall centered on the point (east-west or north-south).
        length = max(1, int(wall_length_ft) // battle_map.feet_per_grid)
        lo = -(length // 2)
        hi = length - length // 2 - 1
        for i in range(lo, hi + 1):
            if shape == 'wall_ns':
                add(cx, cy + i)
            else:
                add(cx + i, cy)
    return squares


class WallOfThornsTile(ZoneTile):
    """One square of the thorn wall: opaque, costly to move through."""

    def __init__(self, session, battle_map, source, zone, movement_cost=4):
        self.source = source
        self.zone = zone
        self._uid = f"wall_of_thorns_tile:{uuid.uuid4()}"
        super().__init__(
            session,
            battle_map,
            {
                'name': 'Wall of Thorns',
                'description': 'A tangle of tough, needle-bristling brush. '
                               'It blocks line of sight and is hard to move through.',
                'entity_uid': self._uid,
                'type': 'wall_of_thorns_tile',
                'movement_cost': int(movement_cost or 4),
                'passable': True,
                'placeable': True,
                'opaque': True,  # SRD: the wall blocks line of sight
                'see_own_square': True,  # ... but the wall itself is visible
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
    __slots__ = ('source', 'appearance_dice', 'enter_dice', 'save', 'save_dc',
                 '_tile_objects', '_square_set', '_entered_turn', '_ended_turn')

    def __init__(self, source, battle, battle_map, squares, spell, *,
                 appearance_dice='7d8', enter_dice='7d8', save='dexterity',
                 save_dc=13, duration_rounds=100):
        super().__init__(
            owner=source,
            battle=battle,
            map=battle_map,
            squares=squares,
            name='wall_of_thorns',
            shape='custom',
            duration_rounds=duration_rounds,
            concentration=True,
            spell=spell,
        )
        self.source = source
        self.appearance_dice = appearance_dice
        self.enter_dice = enter_dice
        self.save = save
        self.save_dc = int(save_dc or 13)
        self._tile_objects = []
        self._square_set = {tuple(s) for s in squares}
        self._entered_turn = {}
        self._ended_turn = {}

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

    def _save_for_half(self, entity, dice, damage_type, attack_name):
        if entity is None or entity.dead() or not hasattr(entity, 'take_damage'):
            return None
        if getattr(entity, 'object', lambda: False)():
            return None
        roll = DieRoll.roll(str(dice or '7d8'), battle=self.battle,
                            entity=self.source,
                            description=f'dice_roll.spells.{attack_name}')
        caster_spell = self.spell  # the casting Spell instance (SaveForHalfMixin)
        items = caster_spell.resolve_save_for_half(
            [entity], ability=self.save, dc=self.save_dc, damage_roll=roll,
            attack_name=attack_name, damage_type=damage_type,
            battle=self.battle,
        )
        for item in items:
            damage_event(item, self.battle)
        return items

    def _apply_entry_damage(self, entity):
        """First entry on a turn (SRD: slashing, Dex save for half)."""
        key = self._turn_key()
        uid = getattr(entity, 'entity_uid', id(entity))
        if key is not None and self._entered_turn.get(uid) == key:
            return None
        self._entered_turn[uid] = key
        return self._save_for_half(entity, self.enter_dice, 'slashing',
                                   'wall_of_thorns')

    def _apply_end_of_turn_damage(self, entity):
        """Ending a turn inside the wall (once per turn)."""
        key = self._turn_key()
        uid = getattr(entity, 'entity_uid', id(entity))
        if key is not None and self._ended_turn.get(uid) == key:
            return None
        self._ended_turn[uid] = key
        return self._save_for_half(entity, self.enter_dice, 'slashing',
                                   'wall_of_thorns')

    def apply_appearance_damage(self, entities):
        """Creatures in the area when the wall appears take piercing damage."""
        results = []
        for entity in entities:
            items = self._save_for_half(entity, self.appearance_dice, 'piercing',
                                        'wall_of_thorns_appears')
            if items:
                results.extend(items)
        return results

    def on_enter(self, entity):
        if self.in_area(entity):
            self._apply_entry_damage(entity)
        return None

    def on_turn_end(self, entity):
        if self.in_area(entity):
            self._apply_end_of_turn_damage(entity)
        return None

    def on_dismiss(self):
        for tile in list(self._tile_objects):
            try:
                if tile in self.map.interactable_objects or tile in self.map.entities:
                    self.map.remove(tile)
            except Exception:
                pass
        self._tile_objects.clear()


class WallOfThornsSpell(SaveForHalfMixin, Spell):
    def clone(self):
        # Carry the chosen shape through the build-chain clones
        # (select_choice stores it on the spell instance).
        spell = super().clone()
        if hasattr(self, 'shape'):
            spell.shape = self.shape
        return spell

    def _shape(self):
        return getattr(self, 'shape', 'wall')

    def _scaled_dice(self, base_dice, spell_action):
        """SRD: both damage dice gain +1d8 per slot level above 6th."""
        base_level = int(self.properties.get('level', 6) or 6)
        try:
            cast_level = int(getattr(spell_action, 'at_level', None)
                             or base_level)
        except (TypeError, ValueError):
            cast_level = base_level
        extra = max(0, cast_level - base_level)
        if not extra:
            return str(base_dice)
        try:
            count, sides = str(base_dice).lower().split('d')
            return f"{int(count) + extra}d{sides}"
        except (ValueError, AttributeError):
            return str(base_dice)

    def build_map(self, orig_action):
        def choose_shape(choice):
            shape = str(choice).lower()
            if shape not in SHAPES:
                raise ValueError(f'Invalid Wall of Thorns shape: {choice}')

            action = orig_action.clone()
            action.spell_action.shape = shape

            def set_center(center):
                targeted = action.clone()
                targeted.target = center
                return targeted

            return {
                'param': [{
                    'type': 'select_square',
                    'num': 1,
                    'range': self.properties.get('range', 120),
                    'centered': True,
                    'width': (self.properties.get('wall_length', 60)
                              if shape == 'wall' else
                              self.properties.get('circle_diameter', 20)
                              if shape == 'circle' else 5),
                    'height': (5 if shape == 'wall' else
                               self.properties.get('circle_diameter', 20)
                               if shape == 'circle'
                               else self.properties.get('wall_length', 60)),
                }],
                'next': set_center,
            }

        return {
            'param': [{
                'type': 'select_choice',
                'num': 1,
                'choices': [
                    ['Wall (up to 60 ft long, east-west)', 'wall'],
                    ['Wall (up to 60 ft long, north-south)', 'wall_ns'],
                    ['Circle (20 ft diameter)', 'circle'],
                ],
            }],
            'next': choose_shape,
        }

    def resolve(self, entity, battle, spell_action, battle_map):
        center = spell_action.target
        if not isinstance(center, (list, tuple)):
            center = battle_map.entity_or_object_pos(center)
        center = (int(center[0]), int(center[1]))
        shape = getattr(getattr(spell_action, 'spell_action', None), 'shape',
                        None) or self._shape()
        appearance_dice = self._scaled_dice(
            self.properties.get('appearance_damage', '7d8'), spell_action)
        enter_dice = self._scaled_dice(
            self.properties.get('enter_damage', '7d8'), spell_action)
        squares = wall_of_thorns_squares(
            battle_map, center, shape,
            wall_length_ft=int(self.properties.get('wall_length', 60) or 60),
            circle_diameter_ft=int(self.properties.get('circle_diameter', 20) or 20),
        )
        ability = HoldPersonSpell._caster_spell_ability(entity, spell_action)
        save_dc = entity.spell_save_dc(ability) if hasattr(entity, 'spell_save_dc') else 13
        return [{
            'type': 'wall_of_thorns',
            'source': entity,
            'target': list(center),
            'shape': shape,
            'squares': [list(s) for s in squares],
            'effect': self,
            'spell': self.properties,
            'save_dc': save_dc,
            'appearance_dice': appearance_dice,
            'enter_dice': enter_dice,
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
        appearance_dice = item.get('appearance_dice') or spell.get('appearance_damage', '7d8')
        enter_dice = item.get('enter_dice') or spell.get('enter_damage', '7d8')

        source.remove_effect('wall_of_thorns')
        zone = WallOfThornsZone(
            source, battle, battle_map, squares, item.get('effect'),
            appearance_dice=appearance_dice,
            enter_dice=enter_dice,
            save=spell.get('save', 'dexterity'),
            save_dc=item.get('save_dc', 13),
            duration_rounds=max(1, duration // 6))
        for pos in squares:
            tile = WallOfThornsTile(session, battle_map, source, zone,
                                    movement_cost=spell.get('movement_cost', 4))
            battle_map.place_object(tile, pos[0], pos[1])
            zone._tile_objects.append(tile)
        register_persistent_zone(zone, battle)

        # Creatures in the area when the wall appears take the piercing
        # appearance damage (Dex save for half).
        occupants = [entity for entity in list(getattr(battle_map, 'entities', []) or [])
                     if zone.in_area(entity)]
        zone.apply_appearance_damage(occupants)

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
            'shape': item.get('shape', 'wall'),
            'squares': item.get('squares', []),
            'spell': item.get('effect'),
        })
        return zone
