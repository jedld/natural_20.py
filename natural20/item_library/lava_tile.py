"""Lava tiles — damaging terrain hazards placed from a map legend.

A ``lava`` object (see ``templates/items/objects.yml``) turns a square of the
map into a molten hazard with generic, reusable rules:

- **Difficult terrain** for creatures that are not flying over it
  (``movement_cost: 2``; the flying exemption is engine-generic —
  ``natural20/utils/movement.py`` and the path planners skip the extra cost
  for flying creatures).
- **Enter damage** — a creature that moves into the lava takes the
  configured fire damage (default ``2d8``), fired per path square by the
  zone dispatchers (``Battle.trigger_movement_step`` in combat and
  ``natural20.environment_zones.trigger_environment_movement_step`` out of
  combat, both driven from ``MoveAction.apply``).
- **Start-of-turn damage** — a creature that starts its turn in the lava
  takes the same damage (``Battle.trigger_event('start_of_turn')`` walks
  ``battle.active_zones`` for the current turn's target).
- **Environment damage** — out of combat, each 6-second world-time tick
  (``natural20.environment_zones.tick_environment_zones``) deals the
  damage to every creature standing in the lava, matching the round-based
  cadence combat uses.

A contiguous patch of lava squares is grouped into one shared
``LavaZone`` (a ``PersistentAoEZone``): map load merges squares that touch
the same tile (8-neighbour), battle start promotes the zones onto
``battle.active_zones`` and battle end demotes them back, and save/load
restores them through the generic ``!persistent_zone`` / ``!zone_tile``
machinery in ``natural20/utils/serialization.py``.

Pushes and teleports do not fire the enter damage (``Map.move_to`` does not
dispatch zone steps); a pushed creature still burns at the start of its
next turn and whenever it moves.
"""
from __future__ import annotations

import uuid

from natural20.die_roll import DieRoll
from natural20.environment_zones import register_persistent_zone
from natural20.spell.extensions.persistent_zone import PersistentAoEZone
from natural20.spell.objects.zone_tile import ZoneTile

DEFAULT_ENTER_DIE = '2d8'
DEFAULT_START_TURN_DIE = '2d8'


def _roll_damage(die_str):
    """Roll the configured damage die, falling back to the default on typos."""
    try:
        return DieRoll.roll(str(die_str or DEFAULT_ENTER_DIE))
    except Exception:
        return DieRoll.roll(DEFAULT_ENTER_DIE)


class LavaHazardMixin:
    """Shared hazard configuration + damage application.

    Mixed into the tile and the zone so both answer ``enter_damage_die()``
    / ``start_turn_damage_die()`` / ``fire_immunity_required()`` — the web
    hazard context (``natural20/utils/hazard_context.py``) reads exactly
    those from zone objects.
    """

    def enter_damage_die(self):
        props = getattr(self, 'properties', None) or {}
        return str(props.get('enter_damage_die')
                   or props.get('damage_die') or DEFAULT_ENTER_DIE)

    def start_turn_damage_die(self):
        props = getattr(self, 'properties', None) or {}
        return str(props.get('start_turn_damage_die')
                   or props.get('damage_die') or DEFAULT_START_TURN_DIE)

    def fire_immunity_required(self):
        """When true (default), creatures immune to fire take no lava damage."""
        props = getattr(self, 'properties', None) or {}
        return bool(props.get('fire_immunity_required', True))

    def environmental_hazard(self):
        """Mark this zone as an always-hostile terrain hazard (no owner)."""
        return True

    def label(self):
        props = getattr(self, 'properties', None) or {}
        return str(props.get('name') or 'lava')

    def _damage_type(self):
        props = getattr(self, 'properties', None) or {}
        return str(props.get('damage_type') or 'fire')

    def _immune(self, entity):
        if entity is None:
            return True
        try:
            if entity.dead():
                return True
        except Exception:
            return True
        if self.fire_immunity_required():
            try:
                if entity.immune_to('fire'):
                    return True
            except Exception:
                pass
        return False

    def apply_lava_damage(self, entity, battle, die_str, reason):
        """Roll and deal lava fire damage to ``entity``. Returns the roll."""
        if self._immune(entity):
            return None
        roll = _roll_damage(die_str)
        dmg = roll.result() if hasattr(roll, 'result') else int(roll)
        session = (getattr(battle, 'session', None)
                   or getattr(self, 'session', None)
                   or getattr(entity, 'session', None))
        if session is not None and getattr(session, 'event_manager', None):
            session.event_manager.received_event({
                'event': 'console',
                'source': self,
                'target': entity,
                'message': (
                    f"{entity} is caught in {self.label()} and takes "
                    f"{dmg} fire damage ({die_str})."
                ),
            })
        entity.take_damage(dmg, battle=battle, damage_type=self._damage_type(),
                           session=session)
        return roll

    def _entity_in_zone(self, entity):
        if self.map is None or entity is None:
            return False
        try:
            pos = self.map.position_of(entity)
        except Exception:
            return False
        return pos is not None and self.contains(pos)

    # --- zone hooks ----------------------------------------------------

    def on_movement_step(self, entity, from_pos, to_pos):
        """Damage when a creature *enters* the lava (crossing its edge),
        not when it shuffles inside it. Flying creatures hover unharmed."""
        if from_pos is None or to_pos is None:
            return None
        if tuple(from_pos) == tuple(to_pos):
            return None
        if entity is None:
            return None
        try:
            if getattr(entity, 'object', lambda: False)():
                return None
            if entity.is_flying():
                return None
        except Exception:
            pass
        if not self.contains(to_pos):
            return None
        if self.contains(from_pos):
            return None
        battle = getattr(self, 'battle', None)
        return self.apply_lava_damage(entity, battle, self.enter_damage_die(),
                                      'enter')

    # NOTE: no ``on_enter`` here on purpose. The zone dispatchers
    # (``Battle.trigger_movement_step`` / the environment twin) call BOTH
    # ``on_movement_step`` and ``on_enter`` for a fresh entry, so an
    # ``on_enter`` on the zone would burn twice per move. ``on_movement_step``
    # is the single enter-damage authority; forced movement (pushes) burns via
    # the tile's ``on_enter`` guard below, and standing in lava burns at the
    # turn start / environment tick.

    def on_turn_start(self, entity):
        """Start-of-turn damage for creatures standing in the lava."""
        if entity is None:
            return None
        if not self._entity_in_zone(entity):
            return None
        try:
            if getattr(entity, 'object', lambda: False)():
                return None
            if entity.is_flying():
                return None
        except Exception:
            pass
        battle = getattr(self, 'battle', None)
        return self.apply_lava_damage(entity, battle,
                                      self.start_turn_damage_die(),
                                      'turn_start')


class LavaZone(LavaHazardMixin, PersistentAoEZone):
    """A connected set of lava squares ticking as one environment zone.

    The zone anchors on the map directly (``map_name``), not on a creature:
    the relinker prefers the map holding its tiles, and with ``owner=None``
    it never expires on its own.
    """

    __slots__ = ("map_name", "properties", "_square_set", "_tile_objects")

    def __init__(self, battle_map, squares, properties=None, battle=None):
        super().__init__(
            owner=None,
            battle=battle,
            map=battle_map,
            squares=squares,
            name='lava',
            shape='irregular',
            duration_rounds=None,
            concentration=False,
            spell=None,
        )
        self.properties = dict(properties or {})
        self.map_name = getattr(battle_map, 'name', None)
        self._square_set = {tuple(s) for s in squares}
        self._tile_objects = []

    def contains(self, pos):
        square_set = getattr(self, '_square_set', None)
        if not square_set:
            square_set = self._square_set = {tuple(s) for s in self.squares}
        return tuple(pos) in square_set

    def relink(self, session, map_list):
        """Anchor on the map by name after save/load (the generic relinker
        can't follow the ``None`` owner)."""
        if self.map is None and map_list:
            for m in map_list:
                if getattr(m, 'name', None) == self.map_name:
                    self.map = m
                    break
        # Rebuild the lookup set from the durable squares list (the raw
        # saved set can come back with non-tuple keys).
        self._square_set = {tuple(s) for s in self.squares}

    def expired(self):
        # Environmental hazards never expire on their own; only tile removal
        # (map editing) takes them out.
        return bool(self._dismissed)

    def on_dismiss(self):
        for tile in list(self._tile_objects):
            try:
                if tile in self.map.interactable_objects or tile in self.map.entities:
                    self.map.remove(tile)
            except Exception:
                pass
        self._tile_objects.clear()


class LavaTile(LavaHazardMixin, ZoneTile):
    """One square of a lava hazard.

    Construction matches the two live paths:
      * ``Map.place_object`` → ``LavaTile(session, map, properties)``
        (legend ``type: lava`` + ``item_class: LavaTile``), and
      * ``ZoneTile.from_dict`` → ``__new__`` + ``Object.__init__`` on load.

    The zone is the single damage authority: ``MoveAction.apply`` and
    ``tick_environment_zones`` dispatch through the zone, not the tile, so
    a walking creature is never charged twice for one move.
    """

    def __init__(self, session, battle_map, properties=None, source=None,
                 zone=None):
        props = dict(properties or {})
        props.setdefault('name', 'Lava')
        props.setdefault('type', 'lava')
        props.setdefault('movement_cost', 2)
        props.setdefault('passable', True)
        props.setdefault('placeable', True)
        props.setdefault('targettable', False)
        props.setdefault('damage_type', 'fire')
        props.setdefault('lava', True)
        props.setdefault('enter_damage_die', DEFAULT_ENTER_DIE)
        props.setdefault('start_turn_damage_die', DEFAULT_START_TURN_DIE)
        self._uid = f"lava_tile:{uuid.uuid4()}"
        props.setdefault('entity_uid', self._uid)
        super().__init__(session, battle_map, props)
        self.source = source
        self.zone = zone

    def token_image(self):
        return None

    def allow_targeting(self):
        return False

    def jump_required(self):
        return False

    def concealed(self):
        return False

    def on_enter(self, entity, map_obj, battle, from_pos=None, to_pos=None):
        """Burn creatures pushed or teleported into this square.

        Voluntary movement is skipped when the move is running through
        ``MoveAction.apply`` (it sets ``_lava_move_step_dispatch`` on the map
        around its per-step zone dispatch), which already charges the step —
        otherwise the same move would burn twice.
        """
        if map_obj is not None and getattr(map_obj, '_lava_move_step_dispatch', False):
            return
        if entity is None:
            return
        try:
            if getattr(entity, 'object', lambda: False)():
                return
            if entity.is_flying():
                return
        except Exception:
            pass
        zone = self.zone
        if zone is None:
            return
        if from_pos is not None and zone.contains(tuple(from_pos)):
            return
        zone.apply_lava_damage(entity, getattr(zone, 'battle', None),
                               zone.enter_damage_die(), 'push')


def _same_hazard(a, b):
    """True when two lava tiles share hazard configuration."""
    if a is None or b is None:
        return False
    pa, pb = (a.properties or {}), (b.properties or {})
    return (
        str(pa.get('enter_damage_die') or pa.get('damage_die') or '') ==
        str(pb.get('enter_damage_die') or pb.get('damage_die') or '')
        and str(pa.get('start_turn_damage_die') or pa.get('damage_die') or '') ==
        str(pb.get('start_turn_damage_die') or pb.get('damage_die') or '')
        and bool(pa.get('fire_immunity_required', True)) ==
        bool(pb.get('fire_immunity_required', True))
    )


def build_lava_zones(battle_map, tiles_by_pos, battle=None):
    """Merge adjacent lava tiles into shared zones and register them.

    ``tiles_by_pos`` maps ``(x, y)`` to the placed ``LavaTile``. 8-neighbour
    merging turns a contiguous pool into a single ticking zone while
    separate pools stay separate.
    """
    if not tiles_by_pos:
        return []

    pending = dict(tiles_by_pos)
    zones = []
    while pending:
        seed_pos, seed_tile = next(iter(pending.items()))
        group = {seed_pos: seed_tile}
        del pending[seed_pos]
        frontier = [seed_pos]
        while frontier:
            (x, y) = frontier.pop()
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    npos = (x + dx, y + dy)
                    tile = pending.get(npos)
                    if tile is not None and _same_hazard(seed_tile, tile):
                        group[npos] = tile
                        del pending[npos]
                        frontier.append(npos)
        zone = LavaZone(battle_map, list(group.keys()),
                        seed_tile.properties, battle=battle)
        for tile in group.values():
            tile.zone = zone
            zone._tile_objects.append(tile)
        register_persistent_zone(zone, battle)
        zones.append(zone)
    return zones
