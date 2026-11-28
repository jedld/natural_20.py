"""Generic pocket-dimension (extradimensional space) system.

A *pocket dimension* is a small, dynamically generated map that exists only
while a spell/item effect lasts. The system provides:

``PocketDimensionZone``
    A :class:`~natural20.spell.extensions.persistent_zone.PersistentAoEZone`
    subclass that owns the space's lifetime. It ticks in both combat
    (``Battle.active_zones``) and exploration (``Map.environment_zones``),
    self-expires at ``expiration_time``, and ejects every member plus removes
    the pocket map when it is dismissed. Because the zone's squares hold the
    *entrance square on the outer map*, it is a Dispel Magic target for free:
    clicking the entrance square hits ``zones_at`` / ``zone_for_target``
    (the entrance object also carries a ``.zone`` back-reference).

``PocketEntranceObject``
    An interactable map object placed on both sides of the doorway: the outer
    entrance (e.g. the Rope Trick rope) offers ``climb_in`` (and the SRD
    "pull the rope up" hide), and the inner entrance offers ``climb_out`` plus
    pulling/dropping the rope. Entering/exiting removes the entity from one
    map and places it on the other (the same primitive teleporters use), so
    attacks, spells and line of sight never cross the boundary — the maps are
    simply different maps.

``create_pocket_dimension(...)``
    Builds the in-memory map, registers it with the session (same map set as
    the entry map so POV/teleport lookups keep working), places both entrance
    objects, and registers the zone for ticking.

SRD examples that map onto this system: Rope Trick (reworked here), Portable
Hole, Bag of Holding interiors, Demiplane, Mordenkainen's Magnificent
Mansion — add a new YAML ``pocket_dimension`` block to any spell/item and call
``create_pocket_dimension`` from its apply/use hook.

Save/load: the zone rides the existing ``!persistent_zone`` tag; the entrance
objects use a dedicated ``!pocket_entrance`` tag. ``relink_persistent_zones``
calls ``zone.relink(session, map_list)`` so the zone re-finds its outer map by
name and purges members that strayed out while the game was saved.
"""

from __future__ import annotations

import uuid
from collections import deque
from typing import Iterable, List, Optional, Tuple

from natural20.item_library.object import Object
from natural20.spell.extensions.persistent_zone import PersistentAoEZone

SESSION_STATE_KEY = 'pocket_dimensions'


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _session_for(owner, battle=None, zone_map=None):
    for holder in (owner, battle, zone_map):
        session = getattr(holder, 'session', None)
        if session is not None:
            return session
    return None


def _event(session, payload) -> None:
    event_manager = getattr(session, 'event_manager', None)
    if event_manager is not None:
        try:
            event_manager.received_event(payload)
        except Exception:
            pass


def _grid_position(pos) -> Optional[Tuple[int, int]]:
    try:
        return (int(pos[0]), int(pos[1]))
    except (TypeError, ValueError, IndexError):
        return None


def _free_square_near(battle_map, x: int, y: int, entity, taken=None) -> Tuple[int, int]:
    """Nearest square to (x, y) where ``entity`` can be placed, skipping ``taken``."""
    taken = set(taken or ())
    target = (int(x), int(y))
    width, height = (battle_map.size or [0, 0])[:2]

    def placeable(sq):
        sx, sy = sq
        if not (0 <= sx < width and 0 <= sy < height):
            return False
        if sq in taken:
            return False
        try:
            if battle_map.entity_at(sx, sy) is not None:
                return False
        except Exception:
            pass
        try:
            if not battle_map.placeable(entity, sx, sy, squeeze=False):
                return False
        except Exception:
            try:
                if not battle_map.placeable(entity, sx, sy):
                    return False
            except Exception:
                return False
        return True

    if placeable(target):
        return target
    seen = {target}
    queue = deque([target])
    while queue:
        cx, cy = queue.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            nx, ny = cx + dx, cy + dy
            if (nx, ny) in seen:
                continue
            seen.add((nx, ny))
            if placeable((nx, ny)):
                return (nx, ny)
            queue.append((nx, ny))
    return target


def _map_named(map_list, name) -> Optional[object]:
    for m in (map_list or []):
        if getattr(m, 'name', None) == name:
            return m
    return None


def pocket_map_properties(*, side_squares: int, feet_per_grid: int = 5,
                          label: str = 'Pocket Dimension',
                          narration: str = '',
                          illumination: float = 0.8) -> dict:
    """ASCII properties for a simple all-floor pocket map."""
    side = max(3, int(side_squares))
    rows = ['.' * side for _ in range(side)]
    return {
        'name': label,
        'description': narration or label,
        'grid_size': int(feet_per_grid),
        'pocket_dimension': True,
        'map': {'base': rows, 'illumination': illumination},
        'legend': {},
        'triggers': {},
    }


def maze_map_properties(*, cells_x: int = 8, cells_y: int = 8,
                        feet_per_grid: int = 5,
                        label: str = 'The Labyrinth',
                        narration: str = '',
                        illumination: float = 0.3,
                        seed=None):
    """ASCII properties for a procedurally generated labyrinth.

    Recursive-backtracker maze over ``cells_x`` x ``cells_y`` cells; walls are
    ``#`` (auto-loaded as stone walls by ``Map._setup_objects``) and corridors
    are ``.``. Returns ``(properties, entrance_xy, warden_xy)`` where the
    entrance is the maze entry cell and ``warden_xy`` is the corridor cell
    farthest from it (BFS) — where the Maze spell parks its minotaur.
    """
    import random
    from collections import deque

    rng = random.Random(seed)
    cells_x = max(2, int(cells_x))
    cells_y = max(2, int(cells_y))
    width, height = 2 * cells_x + 1, 2 * cells_y + 1
    grid = [['#'] * width for _ in range(height)]

    stack = [(0, 0)]
    grid[1][1] = '.'
    while stack:
        cx, cy = stack[-1]
        options = []
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < cells_x and 0 <= ny < cells_y and \
                    grid[2 * ny + 1][2 * nx + 1] == '#':
                options.append((dx, dy, nx, ny))
        if not options:
            stack.pop()
            continue
        dx, dy, nx, ny = rng.choice(options)
        grid[2 * cy + 1 + dy][2 * cx + 1 + dx] = '.'
        grid[2 * ny + 1][2 * nx + 1] = '.'
        stack.append((nx, ny))

    # BFS from the entrance cell: the farthest cell hosts the warden.
    seen = {(0, 0): 0}
    queue = deque([(0, 0)])
    farthest = (0, 0)
    while queue:
        x, y = queue.popleft()
        if seen[(x, y)] > seen[farthest]:
            farthest = (x, y)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < cells_x and 0 <= ny < cells_y and \
                    grid[2 * ny + 1][2 * nx + 1] == '.' and (nx, ny) not in seen:
                seen[(nx, ny)] = seen[(x, y)] + 1
                queue.append((nx, ny))

    # Upscale x2: corridors become 2 squares wide so Large creatures (the
    # maze's minotaur) can move and stand in them.
    factor = 2
    uw, uh = width * factor, height * factor
    big = [['#'] * uw for _ in range(uh)]
    for y in range(height):
        for x in range(width):
            if grid[y][x] == '.':
                for dy in range(factor):
                    for dx in range(factor):
                        big[y * factor + dy][x * factor + dx] = '.'
    rows = [''.join(row) for row in big]
    entrance = (1 * factor, 1 * factor)
    warden = (farthest[0] * 2 + 1, farthest[1] * 2 + 1)
    props = {
        'name': label,
        'description': narration or label,
        'grid_size': int(feet_per_grid),
        'pocket_dimension': True,
        'map': {'base': rows, 'illumination': illumination},
        'legend': {},
        'triggers': {},
    }
    return props, entrance, warden


# ---------------------------------------------------------------------------
# zone
# ---------------------------------------------------------------------------

class PocketDimensionZone(PersistentAoEZone):
    """Lifetime + membership record for one extradimensional space.

    ``map``/``squares`` track the *entrance* on the outer map (so Dispel
    Magic's square-click machinery finds it); the interior is the separate
    ``pocket_map_name`` map.
    """

    __slots__ = (
        'pocket_map_name', 'outer_map_name', 'anchor_uid', 'inner_anchor_uid',
        'member_uids', 'capacity', 'rope_stowed', 'pocket_label',
        'entrance_square', 'dismiss_reason', 'return_square', 'climbable',
        'inner_spawn',
    )

    def __init__(self, owner, battle, outer_map, entrance_square, *,
                 pocket_map, capacity: int = 8, spell=None,
                 name: str = 'pocket_dimension', label: str = 'Pocket Dimension'):
        entrance_square = _grid_position(entrance_square) or (0, 0)
        super().__init__(
            owner=owner,
            battle=battle,
            map=outer_map,
            squares=[entrance_square],
            name=name,
            shape='point',
            concentration=False,
            spell=spell,
        )
        self.entrance_square = list(entrance_square)
        self.pocket_map_name = getattr(pocket_map, 'name', None)
        self.outer_map_name = getattr(outer_map, 'name', None)
        self.anchor_uid = None
        self.inner_anchor_uid = None
        self.member_uids = ''
        self.capacity = int(capacity or 8)
        self.rope_stowed = False
        self.pocket_label = label
        self.dismiss_reason = 'ended'
        # Optional: eject back onto this exact outer square (Maze).
        self.return_square = None
        # False when the doorway cannot be walked back through at will
        # (the Maze spell: escape needs the spell's own action check).
        self.climbable = True
        # Where creatures appear inside the pocket (maze entrance cell);
        # defaults to the map center.
        self.inner_spawn = None

    # --- queries -----------------------------------------------------------

    def contains(self, pos) -> bool:
        pos = _grid_position(pos)
        return pos is not None and pos == tuple(self.entrance_square)

    @property
    def session(self):
        return _session_for(self.owner, self.battle, self.map)

    def pocket_map(self):
        session = self.session
        if session is None:
            return None
        return (getattr(session, 'maps', None) or {}).get(self.pocket_map_name)

    def entrance(self):
        return self._find_anchor(self.map, self.anchor_uid)

    def inner_entrance(self):
        return self._find_anchor(self.pocket_map(), self.inner_anchor_uid)

    @staticmethod
    def _find_anchor(battle_map, uid):
        if battle_map is None or not uid:
            return None
        for column in getattr(battle_map, 'objects', []) or []:
            for cell in column or []:
                for obj in cell or []:
                    if getattr(obj, 'entity_uid', None) == uid:
                        return obj
        return None

    def members(self) -> list:
        session = self.session
        out = []
        for uid in [u for u in str(self.member_uids or '').split(',') if u]:
            member = session.entity_by_uid(uid) if session is not None else None
            if member is not None:
                out.append(member)
        return out

    def member_uid_list(self) -> List[str]:
        return [u for u in str(self.member_uids or '').split(',') if u]

    def has_member(self, entity) -> bool:
        uid = getattr(entity, 'entity_uid', None)
        return bool(uid) and uid in self.member_uid_list()

    def occupant_count(self) -> int:
        return len(self.member_uid_list())

    def is_full(self, entity=None) -> bool:
        if entity is not None and self.has_member(entity):
            return False
        return self.occupant_count() >= self.capacity

    def add_member(self, entity) -> None:
        uid = getattr(entity, 'entity_uid', None)
        if not uid:
            return
        uids = self.member_uid_list()
        if uid not in uids:
            uids.append(uid)
            self.member_uids = ','.join(uids)

    def remove_member(self, entity) -> None:
        uid = getattr(entity, 'entity_uid', None)
        uids = [u for u in self.member_uid_list() if u != uid]
        self.member_uids = ','.join(uids)

    # --- movement ----------------------------------------------------------

    def enter(self, entity, battle=None, *, emit: bool = True):
        """Move ``entity`` from the outer map into the pocket map."""
        pocket = self.pocket_map()
        if pocket is None or entity is None or self.expired():
            return None
        session = self.session
        from natural20.map_set import place_entity_instance
        if getattr(self, 'inner_spawn', None):
            center = tuple(_grid_position(self.inner_spawn) or
                           (pocket.size[0] // 2, pocket.size[1] // 2))
        else:
            center = (pocket.size[0] // 2, pocket.size[1] // 2)
        x, y = _free_square_near(pocket, center[0], center[1], entity)
        place_entity_instance(session, entity, pocket, x, y,
                              group=getattr(entity, 'group', None) or 'a')
        self.add_member(entity)
        if emit:
            _event(session, {
                'event': 'pocket_dimension_travel',
                'source': entity,
                'target': entity,
                'direction': 'in',
                'direction_label': f"climbs into {self.pocket_label}",
                'map': self.pocket_map_name,
                'zone_id': self.id,
            })
        return (x, y)

    def exit(self, entity, battle=None, *, emit: bool = True):
        """Move ``entity`` back to the outer map, next to the entrance."""
        if entity is None:
            return None
        pocket = self.pocket_map()
        outer = self.map
        session = self.session
        if outer is None:
            return None
        from natural20.map_set import place_entity_instance
        if pocket is not None and entity in getattr(pocket, 'entities', {}):
            pocket.remove(entity)
        ex, ey = tuple(self.entrance_square)
        taken = set()
        for other in self.members():
            if other is entity:
                continue
            try:
                taken.add(tuple(outer.position_of(other)))
            except Exception:
                continue
        x, y = _free_square_near(outer, ex, ey, entity, taken=taken)
        place_entity_instance(session, entity, outer, x, y,
                              group=getattr(entity, 'group', None) or 'a')
        self.remove_member(entity)
        if emit:
            _event(session, {
                'event': 'pocket_dimension_travel',
                'source': entity,
                'target': entity,
                'direction': 'out',
                'direction_label': f"climbs back down from {self.pocket_label}",
                'map': self.outer_map_name,
                'zone_id': self.id,
            })
        return (x, y)

    # --- rope (optional hide) ----------------------------------------------

    def set_rope_stowed(self, stowed: bool) -> None:
        self.rope_stowed = bool(stowed)
        entrance = self.entrance()
        if entrance is not None:
            entrance.is_concealed = self.rope_stowed
            entrance.invalidate_token_cache()
        _event(self.session, {
            'event': 'pocket_dimension_rope',
            'source': self.owner,
            'target': entrance,
            'stowed': self.rope_stowed,
            'zone_id': self.id,
        })

    # --- teardown ----------------------------------------------------------

    def eject_members(self, reason: str = 'ended') -> list:
        """Drop everyone inside back onto the outer map near the entrance."""
        outer = self.map
        if outer is None:
            self.member_uids = ''
            return []
        placed = []
        taken = set()
        if getattr(self, 'return_square', None):
            # Maze-style spaces expel the creature back into the exact square
            # it vanished from ("reappears in the space it left").
            ex0, ey0 = _grid_position(self.return_square) or tuple(self.entrance_square)
        else:
            ex0, ey0 = tuple(self.entrance_square)
        for member in self.members():
            if outer is not None and member in getattr(outer, 'entities', {}):
                continue
            pocket = self.pocket_map()
            if pocket is not None and member in getattr(pocket, 'entities', {}):
                pocket.remove(member)
            ex, ey = (ex0, ey0)
            x, y = _free_square_near(outer, ex, ey, member, taken=taken)
            taken.add((x, y))
            outer.add(member, x, y, group=getattr(member, 'group', None) or 'a')
            placed.append((member, (x, y)))
        self.member_uids = ''
        return placed

    def clear_member_effects(self) -> None:
        """Drop owner-side spell effects (untargetable + restrictions) from members."""
        spell = self.spell
        targets = list(self.members())
        if self.owner is not None and self.owner not in targets:
            targets.append(self.owner)
        for member in targets:
            try:
                member.targettable = True
            except Exception:
                pass
            if spell is None:
                continue
            for key in list(getattr(member, 'effects', None) or {}):
                descriptors = member.effects.get(key) or []
                kept = [d for d in descriptors if d.get('effect') is not spell]
                if kept:
                    member.effects[key] = kept
                else:
                    member.effects.pop(key, None)
            casted = getattr(member, 'casted_effects', None)
            if isinstance(casted, list):
                member.casted_effects = [
                    d for d in casted
                    if not (isinstance(d, dict) and d.get('effect') is spell)
                ]

    def on_dismiss(self):
        session = self.session
        outer = self.map
        # 1. clean member effects while everyone is still registered, then
        # 2. eject everyone next to the entrance,
        # 3. remove the entrance objects and the pocket map itself.
        self.clear_member_effects()
        placed = self.eject_members(reason=getattr(self, 'dismiss_reason', 'ended'))

        # Anything still inside that never joined as a member is part of the
        # space itself (e.g. the Maze spell's minotaur): it vanishes when the
        # demiplane collapses.
        pocket = self.pocket_map()
        vanished = []
        if pocket is not None:
            for entity in list((getattr(pocket, 'entities', None) or {}).keys()):
                try:
                    pocket.remove(entity)
                except Exception:
                    pass
                if session is not None:
                    try:
                        session.entity_registry.unregister(entity)
                    except Exception:
                        pass
                vanished.append(entity)

        # Anyone from a running battle who just left the battlefield
        # (escaped/ejected member, vanished warden) drops out of combat too,
        # so the battle can end normally when nothing opposed remains.
        battle = getattr(self, 'battle', None)
        if battle is not None:
            for entity in [p for p, _ in placed] + vanished:
                try:
                    if entity in battle.entities:
                        battle.remove(entity)
                except Exception:
                    pass

        for battle_map, uid in ((outer, self.anchor_uid),
                                (self.pocket_map(), self.inner_anchor_uid)):
            anchor = self._find_anchor(battle_map, uid)
            if anchor is not None:
                try:
                    battle_map.remove(anchor)
                except Exception:
                    pass

        pocket = self.pocket_map()
        if session is not None and pocket is not None:
            try:
                session.unregister_map(self.pocket_map_name)
            except Exception:
                pass
        state = getattr(session, 'session_state', None)
        if isinstance(state, dict):
            (state.get(SESSION_STATE_KEY) or {}).pop(self.id, None)

        _event(session, {
            'event': 'pocket_dimension_closed',
            'source': self.owner,
            'target': outer,
            'map': self.pocket_map_name,
            'outer_map': self.outer_map_name,
            'zone_id': self.id,
            'label': self.pocket_label,
            'reason': getattr(self, 'dismiss_reason', 'ended'),
        })

    def dismiss(self, reason: str = 'ended'):
        self.dismiss_reason = reason
        return super().dismiss()

    # --- save/load ---------------------------------------------------------

    def relink(self, session, map_list) -> None:
        """Re-find the outer map by name (or via its outside entrance object)
        and prune members that are no longer inside the pocket."""
        outer = _map_named(map_list, self.outer_map_name) if self.outer_map_name else None
        if outer is None:
            for m in map_list:
                found = False
                for col in getattr(m, 'objects', []) or []:
                    for cell in col or []:
                        for o in cell or []:
                            if getattr(o, 'zone', None) is self and not getattr(o, 'inside', True):
                                found = True
                                break
                        if found:
                            break
                    if found:
                        break
                if found:
                    outer = m
                    break
        if outer is not None:
            self.map = outer
        pocket = _map_named(map_list, self.pocket_map_name)
        if pocket is None:
            self.member_uids = ''
            return
        live = []
        for uid in self.member_uid_list():
            entity = session.entity_by_uid(uid) if session is not None else None
            if entity is not None and entity in getattr(pocket, 'entities', {}):
                live.append(uid)
        self.member_uids = ','.join(live)

    def has_member_on_pocket(self, entity) -> bool:
        pocket = self.pocket_map()
        return pocket is not None and entity in getattr(pocket, 'entities', {})

    def to_dict(self):
        data = super().to_dict()
        data.update({
            'pocket_map_name': self.pocket_map_name,
            'outer_map_name': self.outer_map_name,
            'entrance_square': list(self.entrance_square),
            'anchor_uid': self.anchor_uid,
            'inner_anchor_uid': self.inner_anchor_uid,
            'member_uids': self.member_uids,
            'capacity': self.capacity,
            'rope_stowed': self.rope_stowed,
            'pocket_label': self.pocket_label,
            'return_square': (list(self.return_square)
                              if self.return_square else None),
            'inner_spawn': (list(self.inner_spawn)
                            if getattr(self, 'inner_spawn', None) else None),
        })
        return data


# ---------------------------------------------------------------------------
# entrance objects
# ---------------------------------------------------------------------------

CLIMB_IN = 'climb_in'
CLIMB_OUT = 'climb_out'
PULL_ROPE = 'pull_rope'
DROP_ROPE = 'drop_rope'

_ENTRANCE_ACTIONS = {CLIMB_IN, CLIMB_OUT, PULL_ROPE, DROP_ROPE}


class PocketEntranceObject(Object):
    """Doorway anchor on one side of a pocket dimension.

    Outside instances show the entrance token (e.g. the hanging Rope Trick
    rope) and offer ``climb_in``. Inside instances offer ``climb_out`` and
    the SRD pull/drop-the-rope toggle. Also doubles as the Dispel Magic
    anchor: ``zone_for_target`` follows its ``.zone`` attribute, and the
    zone's squares cover this object's square.
    """

    def __init__(self, session, battle_map, zone: PocketDimensionZone, *,
                 inside: bool, token_image: str = 'rope_trick.png',
                 label: str = 'Extradimensional entrance'):
        self.zone = zone
        self.inside = bool(inside)
        self._token_image = token_image
        self._token_image_override = False
        uid = f"pocket_entrance:{zone.id}:{'in' if inside else 'out'}"
        super().__init__(
            session,
            battle_map,
            {
                'name': label,
                'label': label,
                'description': ('The rope leading down out of the hidden space.'
                                if inside else
                                'A rope hanging perpendicular to the ground, '
                                'with an invisible doorway at its top.'),
                'entity_uid': uid,
                'type': 'pocket_entrance',
                'pocket_entrance': True,
                'passable': True,
                'placeable': True,
                'opaque': False,
                'targettable': False,
                'token_image': token_image,
                'buttons': [
                    {'action': CLIMB_IN, 'label': 'Climb In', 'image': 'interact_use'},
                    {'action': CLIMB_OUT, 'label': 'Climb Out', 'image': 'interact_use'},
                    {'action': PULL_ROPE, 'label': 'Pull Rope Up', 'image': 'interact_use'},
                    {'action': DROP_ROPE, 'label': 'Lower Rope', 'image': 'interact_use'},
                ],
            },
        )
        if zone.anchor_uid is None and not inside:
            zone.anchor_uid = self.entity_uid
        if zone.inner_anchor_uid is None and inside:
            zone.inner_anchor_uid = self.entity_uid

    # --- visibility ---------------------------------------------------------

    def concealed(self) -> bool:
        if self.inside:
            return False
        return bool(self.zone is not None and self.zone.rope_stowed)

    def token_image(self):
        if self.concealed():
            return None
        if self.zone is not None and self.zone.expired():
            return None
        if not self._token_image:
            return None
        return f"objects/{self._token_image}"

    def invalidate_token_cache(self):
        return None

    def allow_targeting(self):
        return False

    def label(self):
        return self.properties.get('label') or 'Extradimensional entrance'

    # --- interactions --------------------------------------------------------

    def _refused(self, entity, reason, message):
        _event(getattr(self, 'session', None), {
            'event': 'pocket_dimension_failed',
            'source': entity,
            'target': self,
            'reason': reason,
            'message': message,
        })
        return False

    def _near_enough(self, entity) -> bool:
        battle_map = getattr(self, 'map', None)
        if battle_map is None or entity is None:
            return True
        try:
            ox, oy = battle_map.position_of(self)
            ex, ey = battle_map.position_of(entity)
        except Exception:
            return True  # cross-map or unresolvable: let the quick-interact gate decide
        return max(abs(ox - ex), abs(oy - ey)) <= 1

    def available_interactions(self, entity, battle=None, admin=False):
        zone = self.zone
        interactions = {}
        if zone is None or zone.expired():
            return interactions
        if not getattr(zone, 'climbable', True):
            return interactions
        if not self.inside:
            disabled = False
            reason = None
            if zone.rope_stowed:
                disabled, reason = True, 'The rope has been pulled up into the space.'
            elif zone.is_full(entity):
                disabled, reason = True, 'The hidden space is already full.'
            interactions[CLIMB_IN] = ({'disabled': True, 'disabled_text': reason}
                                      if disabled else {'prompt': 'Climb into the hidden space'})
        else:
            interactions[CLIMB_OUT] = {'prompt': 'Climb back down to the ground'}
            if zone.rope_stowed:
                interactions[DROP_ROPE] = {'prompt': 'Let the rope back down'}
            else:
                interactions[PULL_ROPE] = {'prompt': 'Pull the rope up into the space'}
        return interactions

    def resolve(self, entity, action, other_params, opts=None):
        if opts is None:
            opts = {}
        if action in _ENTRANCE_ACTIONS:
            return {
                'action': action,
                'source': entity,
                'target': self,
                'battle': opts.get('battle'),
                'zone_id': getattr(self.zone, 'id', None),
            }
        return super().resolve(entity, action, other_params, opts)

    def use(self, entity, result, session=None):
        action = result.get('action') if isinstance(result, dict) else result
        zone = self.zone
        if zone is None or zone.expired():
            return False
        session = session or getattr(self, 'session', None)
        if action == CLIMB_IN:
            if zone.rope_stowed:
                return self._refused(entity, 'rope_stowed',
                                     'The rope has been pulled up; there is nothing to climb.')
            if zone.is_full(entity):
                return self._refused(entity, 'full',
                                     'The hidden space is already full.')
            if not self._near_enough(entity):
                return self._refused(entity, 'too_far',
                                     'You must stand at the rope to climb it.')
            zone.enter(entity, result.get('battle') if isinstance(result, dict) else None)
            return True
        if action == CLIMB_OUT:
            zone.exit(entity)
            return True
        if action in (PULL_ROPE, DROP_ROPE):
            zone.set_rope_stowed(action == PULL_ROPE)
            return True
        return super().use(entity, result, session)

    # --- save/load ------------------------------------------------------------

    def to_dict(self):
        return {
            'session': self.session,
            'entity_uid': self.entity_uid,
            'inside': self.inside,
            'zone': self.zone,
            'token_image': self._token_image,
            'properties': dict(self.properties or {}),
        }

    @classmethod
    def from_dict(cls, data):
        obj = cls.__new__(cls)
        properties = dict(data.get('properties') or {})
        properties['entity_uid'] = data.get('entity_uid') or properties.get('entity_uid')
        obj.inside = bool(data.get('inside'))
        obj.zone = data.get('zone')
        obj._token_image = data.get('token_image') or properties.get('token_image') or 'rope_trick.png'
        obj._token_image_override = False
        Object.__init__(obj, data.get('session'), None, properties)
        return obj


# ---------------------------------------------------------------------------
# factory / lifecycle
# ---------------------------------------------------------------------------

def create_pocket_dimension(session, owner, battle, outer_map, entrance_square, *,
                            name: str = 'pocket_dimension',
                            label: str = 'Pocket Dimension',
                            capacity: int = 8,
                            duration_seconds: int = 3600,
                            size_ft: int = 30,
                            illumination: float = 0.8,
                            token_image: str = 'rope_trick.png',
                            narration: str = '',
                            map_properties: Optional[dict] = None,
                            climbable: bool = True,
                            inner_entrance_pos=None,
                            spell=None) -> PocketDimensionZone:
    """Create + register the pocket map, the zone and both entrance objects.

    The pocket map is registered in the *same map set* as ``outer_map`` so
    ``session.map_for_entity`` POV lookups keep working for creatures inside.

    ``map_properties`` overrides the generated open-room grid (the Maze spell
    passes a procedural labyrinth). ``token_image=None`` hides the doorway
    tokens; ``climbable=False`` removes the walk-through verbs (escape is an
    action of the spell that made the space).
    """
    from natural20.map import Map

    entrance_square = _grid_position(entrance_square) or (0, 0)
    feet_per_grid = getattr(outer_map, 'feet_per_grid', 5) or 5
    side = max(3, int(round(int(size_ft) / feet_per_grid)))

    short = uuid.uuid4().hex[:8]
    map_name = f"pocket_{name}_{short}"
    props = map_properties or pocket_map_properties(
        side_squares=side, feet_per_grid=feet_per_grid,
        label=label, narration=narration, illumination=illumination)
    props = dict(props)
    props.setdefault('name', label)
    props['name'] = map_name
    props['pocket_dimension'] = True
    pocket_map = session.register_map(
        map_name,
        Map(session, None, name=map_name, properties=props),
        map_set=session.map_set_for(getattr(outer_map, 'name', None)),
    )

    zone = PocketDimensionZone(
        owner=owner,
        battle=battle,
        outer_map=outer_map,
        entrance_square=entrance_square,
        pocket_map=pocket_map,
        capacity=capacity,
        spell=spell,
        name=name,
        label=label,
    )
    zone.climbable = bool(climbable)
    if duration_seconds:
        zone.expiration_time = getattr(session, 'game_time', 0) + int(duration_seconds)

    outer_entrance = PocketEntranceObject(session, outer_map, zone,
                                          inside=False, token_image=token_image,
                                          label=label)
    outer_map.place_object(outer_entrance, *entrance_square)
    inner_xy = _grid_position(inner_entrance_pos) or (pocket_map.size[0] // 2,
                                                      pocket_map.size[1] // 2)
    inner_entrance = PocketEntranceObject(session, pocket_map, zone,
                                          inside=True, token_image=token_image,
                                          label=label)
    pocket_map.place_object(inner_entrance, *inner_xy)
    zone.inner_spawn = list(inner_xy)

    from natural20.environment_zones import register_persistent_zone
    register_persistent_zone(zone, battle)

    state = getattr(session, 'session_state', None)
    if not isinstance(state, dict):
        session.session_state = {}
        state = session.session_state
    state.setdefault(SESSION_STATE_KEY, {})[zone.id] = {
        'map': map_name,
        'outer_map': getattr(outer_map, 'name', None),
        'owner_uid': getattr(owner, 'entity_uid', None),
        'spell': getattr(spell, 'name', None) or name,
    }
    return zone


def iter_pocket_zones(battle=None, session=None):
    """Every live ``PocketDimensionZone`` from map ticking and battle ticking."""
    seen = set()
    maps = {}
    if session is not None:
        maps = getattr(session, 'maps', None) or {}
    elif battle is not None:
        maps = {getattr(m, 'name', str(i)): m for i, m in enumerate(getattr(battle, 'maps', None) or [])}
    zones = []
    for battle_map in maps.values():
        zones.extend(getattr(battle_map, 'environment_zones', None) or [])
    if battle is not None:
        zones.extend(getattr(battle, 'active_zones', None) or [])
    for zone in zones:
        if (isinstance(zone, PocketDimensionZone)
                and not getattr(zone, '_dismissed', False)
                and id(zone) not in seen):
            seen.add(id(zone))
            yield zone


def find_pocket_zone(session, *, zone_id=None, map_name=None, battle=None):
    for zone in iter_pocket_zones(battle=battle, session=session):
        if zone_id is not None and str(zone.id) == str(zone_id):
            return zone
        if map_name is not None and zone.pocket_map_name == map_name:
            return zone
    return None
