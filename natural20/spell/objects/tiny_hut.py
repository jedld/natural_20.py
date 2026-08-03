"""Leomund's Tiny Hut — immobile force dome map objects."""
from __future__ import annotations

import uuid
from typing import Iterable, List, Optional, Set, Tuple

from natural20.item_library.object import Object
from natural20.spell.extensions.persistent_zone import PersistentAoEZone

HUT_RADIUS_FT = 10
MAX_CREATURES = 10  # caster + nine Medium or smaller creatures


def hut_interior_squares(battle_map, center: Tuple[int, int], radius_ft: int = HUT_RADIUS_FT):
    return battle_map.squares_in_radius(tuple(center), radius_ft, require_los=False)


def hut_shell_squares(battle_map, center: Tuple[int, int], radius_ft: int = HUT_RADIUS_FT):
    interior = set(hut_interior_squares(battle_map, center, radius_ft))
    if not interior:
        return []
    radius_squares = max(0, int(radius_ft) // battle_map.feet_per_grid)
    cx, cy = center
    shell = []
    for x, y in interior:
        if max(abs(x - cx), abs(y - cy)) == radius_squares:
            shell.append((x, y))
    return sorted(shell)


def creatures_in_squares(battle_map, squares: Iterable[Tuple[int, int]]):
    interior = {tuple(s) for s in squares}
    seen = []
    for entity, pos in battle_map.entities.items():
        if tuple(pos) in interior and entity not in seen:
            seen.append(entity)
    return seen


def objects_in_squares(battle_map, squares: Iterable[Tuple[int, int]]):
    seen = []
    for x, y in squares:
        for obj in battle_map.objects_at(x, y):
            if obj not in seen:
                seen.append(obj)
    return seen


def hut_cast_violation(battle_map, center: Tuple[int, int], radius_ft: int = HUT_RADIUS_FT):
    """Return a failure reason string, or None when the hut can be raised."""
    interior = hut_interior_squares(battle_map, center, radius_ft)
    creatures = creatures_in_squares(battle_map, interior)
    if len(creatures) > MAX_CREATURES:
        return 'too_many_creatures'
    for creature in creatures:
        if creature.size_identifier() > 2:  # larger than Medium
            return 'creature_too_large'
    return None


def iter_tiny_hut_domes(battle_map):
    for obj in list(getattr(battle_map, 'interactable_objects', {}).keys()):
        if isinstance(obj, TinyHutDome):
            yield obj


def force_dome_blocks_outside_vision(battle_map, pos1, pos2) -> bool:
    for dome in iter_tiny_hut_domes(battle_map):
        if dome.blocks_outside_vision(pos1, pos2):
            return True
    return False


def force_dome_blocks_spell(battle_map, pos1, pos2) -> bool:
    for dome in iter_tiny_hut_domes(battle_map):
        if dome.blocks_spell_effect(pos1, pos2):
            return True
    return False


def force_dome_blocks_movement(battle_map, entity, from_pos, to_pos) -> bool:
    """Block crossing the dome boundary unless the mover was inside at cast time."""
    if from_pos is None or to_pos is None:
        return False
    from_pos = tuple(from_pos)
    to_pos = tuple(to_pos)
    if from_pos == to_pos:
        return False
    uid = getattr(entity, 'entity_uid', None)
    for dome in iter_tiny_hut_domes(battle_map):
        inside_from = dome.contains(from_pos)
        inside_to = dome.contains(to_pos)
        if inside_from == inside_to:
            continue
        if uid and uid in dome.allowed_creature_uids:
            continue
        if uid and uid == getattr(dome.owner, 'entity_uid', None):
            continue
        return True
    return False


class TinyHutDome(Object):
    """Anchor object for an active Tiny Hut dome."""

    def __init__(
        self,
        session,
        battle_map,
        owner,
        center: Tuple[int, int],
        *,
        radius_ft: int = HUT_RADIUS_FT,
        duration_seconds: int = 8 * 60 * 60,
        allowed_creature_uids: Optional[Set[str]] = None,
        allowed_object_uids: Optional[Set[str]] = None,
        dome_color: str = 'sapphire',
    ):
        self.owner = owner
        self.center = tuple(center)
        self.radius_ft = radius_ft
        self.interior_squares = {tuple(s) for s in hut_interior_squares(battle_map, self.center, radius_ft)}
        self.shell_squares = {tuple(s) for s in hut_shell_squares(battle_map, self.center, radius_ft)}
        self.allowed_creature_uids = set(allowed_creature_uids or [])
        self.allowed_object_uids = set(allowed_object_uids or [])
        self.interior_lighting = 'default'
        self.dome_color = dome_color
        self.expiration_time = session.game_time + int(duration_seconds)
        self.zone = None
        self._barriers: List[TinyHutBarrier] = []
        super().__init__(
            session,
            battle_map,
            {
                'name': "Leomund's Tiny Hut",
                'description': 'An immobile dome of magical force.',
                'entity_uid': f"tiny_hut_dome:{uuid.uuid4().hex[:12]}",
                'type': 'tiny_hut_dome',
                'tiny_hut_dome': True,
                'passable': True,
                'placeable': True,
                'opaque': False,
                'targettable': False,
                'dome_color': dome_color,
                'radius_ft': radius_ft,
            },
        )

    def contains(self, pos: Tuple[int, int]) -> bool:
        return tuple(pos) in self.interior_squares

    def blocks_line(self, pos1, pos2) -> bool:
        return self.contains(pos1) != self.contains(pos2)

    def blocks_outside_vision(self, pos1, pos2) -> bool:
        return not self.contains(pos1) and self.contains(pos2)

    def blocks_spell_effect(self, pos1, pos2) -> bool:
        return self.blocks_line(pos1, pos2)

    def interior_light_value(self) -> Optional[float]:
        if self.interior_lighting == 'dark':
            return 0.0
        if self.interior_lighting == 'dim':
            return 0.5
        return None

    def set_interior_lighting(self, mode: str):
        if mode in ('default', 'dim', 'dark'):
            self.interior_lighting = mode

    def passable_for_origin(self, origin) -> bool:
        if origin is None:
            return False
        ox, oy = int(origin[0]), int(origin[1])
        if self.contains((ox, oy)):
            return True
        for entity in self.map.entities_at(ox, oy):
            uid = getattr(entity, 'entity_uid', None)
            if uid and uid in self.allowed_creature_uids:
                return True
        for obj in self.map.objects_at(ox, oy):
            uid = getattr(obj, 'entity_uid', None)
            if uid and uid in self.allowed_object_uids:
                return True
        return False

    def place_barriers(self):
        """Movement blocking is enforced in ``Map.passable`` (force dome hooks)."""
        return

    def remove_barriers(self):
        self._barriers.clear()

    def token_image(self):
        return None

    def label(self):
        return "Leomund's Tiny Hut"


class TinyHutBarrier(Object):
    """Force shell segment — blocks outsiders, allows interior occupants."""

    def __init__(self, session, battle_map, dome: TinyHutDome, position: Tuple[int, int]):
        self.dome = dome
        self._position = tuple(position)
        super().__init__(
            session,
            battle_map,
            {
                'name': "Tiny Hut barrier",
                'description': 'An immobile dome of magical force.',
                'entity_uid': f"tiny_hut_barrier:{uuid.uuid4().hex[:10]}",
                'type': 'tiny_hut_barrier',
                'tiny_hut_barrier': True,
                'passable': False,
                'placeable': False,
                'opaque': False,
                'targettable': False,
                'dome_color': dome.dome_color,
                'interior_lighting': dome.interior_lighting,
            },
        )

    def passable(self, origin=None):
        return self.dome.passable_for_origin(origin)

    def opaque(self, origin=None):
        return False

    def allow_targeting(self):
        return False

    def token_image(self):
        return None


class TinyHutZone(PersistentAoEZone):
    """Tracks hut lifetime and ends the spell when the caster leaves."""

    __slots__ = ('dome', 'caster_uid', 'battle_map')

    def __init__(self, caster, battle, battle_map, dome: TinyHutDome, spell, duration_seconds: int):
        super().__init__(
            owner=caster,
            battle=battle,
            map=battle_map,
            squares=dome.interior_squares,
            name='tiny_hut',
            shape='radius',
            duration_rounds=None,
            concentration=False,
            spell=spell,
        )
        self.dome = dome
        self.caster_uid = getattr(caster, 'entity_uid', None)
        self.battle_map = battle_map
        self.expiration_time = dome.expiration_time
        dome.zone = self

    def contains(self, pos):
        return self.dome.contains(pos)

    def on_movement_step(self, entity, _from_pos, to_pos):
        if to_pos is None:
            return
        if getattr(entity, 'entity_uid', None) != self.caster_uid:
            return
        if not self.contains(tuple(to_pos)):
            self.dismiss()

    def on_dismiss(self):
        try:
            self.owner.remove_effect('tiny_hut')
        except Exception:
            pass
        self.dome.remove_barriers()
        try:
            if self.dome in self.battle_map.interactable_objects:
                self.battle_map.remove(self.dome)
        except Exception:
            pass
        if self.battle and self.owner:
            self.owner.session.event_manager.received_event({
                'event': 'tiny_hut_ended',
                'source': self.owner,
                'target': self.dome.center,
            })


class TinyHutEffect:
    """Registered on the caster for save/load dismissal hooks."""

    def __init__(self, dome: TinyHutDome, zone: TinyHutZone):
        self.dome = dome
        self.zone = zone

    @property
    def id(self):
        return 'tiny_hut'

    def __str__(self):
        return 'tiny_hut'

    def dismiss(self, entity, effect, opts=None):
        if self.zone and not self.zone.expired():
            self.zone.dismiss()
