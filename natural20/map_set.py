"""Named map sets: POV worlds that partition a campaign's maps.

Maps in the same set remain teleporter-linked. Maps in different sets never
reference each other. Campaigns without ``map_sets:`` get a single implicit
set id ``root`` containing every map.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

ROOT_MAP_SET_ID = 'root'
_SET_ID_RE = re.compile(r'^[a-z0-9][a-z0-9_\-]*$')


def _map_name(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    name = getattr(value, 'name', None)
    return str(name) if name else None


def slug_map_set_id(raw: str) -> str:
    text = str(raw or '').strip().lower().replace(' ', '_')
    text = re.sub(r'[^a-z0-9_\-]+', '', text)
    return text


def is_valid_map_set_id(set_id: str) -> bool:
    return bool(set_id) and bool(_SET_ID_RE.match(str(set_id)))


def map_set_membership(game_file: dict[str, Any] | None, map_names: Iterable[str]) -> dict[str, str]:
    """Return ``map_name -> set_id`` using the same rules as :class:`MapSetRegistry`.

    Used by the campaign validator without loading live ``Map`` objects.
    Unlisted maps fall back to ``root``. If a map is listed in two sets, the
    first listing wins (the validator reports the duplicate separately).
    """
    known = [str(name) for name in map_names]
    membership: dict[str, str] = {}
    cfg = (game_file or {}).get('map_sets') or {}
    if not isinstance(cfg, dict) or not cfg:
        return {name: ROOT_MAP_SET_ID for name in known}

    for set_id, set_cfg in cfg.items():
        if not isinstance(set_id, str) or not set_id:
            continue
        maps_list = []
        if isinstance(set_cfg, dict):
            maps_list = set_cfg.get('maps') or []
        elif isinstance(set_cfg, list):
            maps_list = set_cfg
        if not isinstance(maps_list, list):
            continue
        for name in maps_list:
            if not isinstance(name, str) or not name:
                continue
            if name not in membership:
                membership[name] = set_id

    for name in known:
        membership.setdefault(name, ROOT_MAP_SET_ID)
    return membership


def same_map_set_ids(membership: dict[str, str], a: Any, b: Any) -> bool:
    name_a = _map_name(a)
    name_b = _map_name(b)
    if not name_a or not name_b:
        return False
    return membership.get(name_a, ROOT_MAP_SET_ID) == membership.get(name_b, ROOT_MAP_SET_ID)


@dataclass
class MapSet:
    id: str
    label: str
    maps: list[str] = field(default_factory=list)

    def to_config(self) -> dict[str, Any]:
        return {
            'label': self.label,
            'maps': list(self.maps),
        }


class MapSetRegistry:
    """Session-level registry of map sets and map-name membership."""

    def __init__(self) -> None:
        self._sets: dict[str, MapSet] = {}
        self._map_to_set: dict[str, str] = {}

    def register(self, map_set: MapSet) -> None:
        self._sets[map_set.id] = map_set
        for name in map_set.maps:
            self._map_to_set[name] = map_set.id

    def get(self, set_id: str) -> Optional[MapSet]:
        return self._sets.get(set_id)

    def all_sets(self) -> list[MapSet]:
        sets = list(self._sets.values())
        sets.sort(key=lambda item: (0 if item.id == ROOT_MAP_SET_ID else 1, item.id))
        return sets

    def set_for_map(self, map_name: Any) -> str:
        name = _map_name(map_name)
        if not name:
            return ROOT_MAP_SET_ID
        return self._map_to_set.get(name, ROOT_MAP_SET_ID)

    def maps_in_set(self, set_id: str) -> list[str]:
        map_set = self._sets.get(set_id)
        if map_set is None:
            if set_id == ROOT_MAP_SET_ID:
                return [name for name, sid in self._map_to_set.items() if sid == ROOT_MAP_SET_ID]
            return []
        return list(map_set.maps)

    def same_map_set(self, a: Any, b: Any) -> bool:
        name_a = _map_name(a)
        name_b = _map_name(b)
        if not name_a or not name_b:
            return False
        return self.set_for_map(name_a) == self.set_for_map(name_b)

    def has_explicit_config(self) -> bool:
        if ROOT_MAP_SET_ID not in self._sets:
            return bool(self._sets)
        if len(self._sets) > 1:
            return True
        return True

    def ensure_set(self, set_id: str, label: Optional[str] = None) -> MapSet:
        existing = self._sets.get(set_id)
        if existing is not None:
            if label:
                existing.label = label
            return existing
        if not is_valid_map_set_id(set_id):
            raise ValueError(f'Invalid map set id: {set_id!r}')
        map_set = MapSet(set_id, label or set_id.replace('_', ' ').title(), [])
        self.register(map_set)
        return map_set

    def assign_map(self, map_name: str, set_id: str) -> None:
        if not map_name:
            raise ValueError('map_name is required')
        self.ensure_set(set_id)
        old_id = self._map_to_set.get(map_name)
        if old_id == set_id:
            if map_name not in self._sets[set_id].maps:
                self._sets[set_id].maps.append(map_name)
            return
        if old_id and old_id in self._sets:
            try:
                self._sets[old_id].maps.remove(map_name)
            except ValueError:
                pass
        self._map_to_set[map_name] = set_id
        if map_name not in self._sets[set_id].maps:
            self._sets[set_id].maps.append(map_name)

    def remove_map(self, map_name: str) -> None:
        old_id = self._map_to_set.pop(map_name, None)
        if old_id and old_id in self._sets:
            try:
                self._sets[old_id].maps.remove(map_name)
            except ValueError:
                pass

    def to_game_config(self) -> dict[str, Any]:
        return {item.id: item.to_config() for item in self.all_sets()}

    @classmethod
    def from_game_config(cls, game_file: dict[str, Any] | None, maps: dict[str, Any] | None) -> MapSetRegistry:
        registry = cls()
        known = list((maps or {}).keys())
        cfg = (game_file or {}).get('map_sets') or {}
        if not isinstance(cfg, dict) or not cfg:
            registry.register(MapSet(ROOT_MAP_SET_ID, 'Root', list(known)))
            return registry

        assigned: set[str] = set()
        for set_id, set_cfg in cfg.items():
            if not isinstance(set_id, str) or not set_id:
                continue
            label = set_id.replace('_', ' ').title()
            maps_list: list[str] = []
            if isinstance(set_cfg, dict):
                label = str(set_cfg.get('label') or label)
                raw_maps = set_cfg.get('maps') or []
                if isinstance(raw_maps, list):
                    maps_list = [str(name) for name in raw_maps if name]
            elif isinstance(set_cfg, list):
                maps_list = [str(name) for name in set_cfg if name]
            unique_maps = []
            for name in maps_list:
                if name in assigned:
                    continue
                assigned.add(name)
                unique_maps.append(name)
            registry.register(MapSet(set_id, label, unique_maps))

        unlisted = [name for name in known if name not in assigned]
        if ROOT_MAP_SET_ID not in registry._sets:
            registry.register(MapSet(ROOT_MAP_SET_ID, 'Root', unlisted))
        else:
            for name in unlisted:
                registry.assign_map(name, ROOT_MAP_SET_ID)
        return registry


def persist_map_sets_to_game_yml(session) -> dict[str, Any]:
    """Write ``map_sets`` (and keep ``maps``) to campaign ``game.yml``."""
    import yaml

    root_path = getattr(session, 'root_path', None) or '.'
    path = os.path.join(root_path, 'game.yml')
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as handle:
            props = yaml.safe_load(handle) or {}
    else:
        props = {}
    if not isinstance(props, dict):
        props = {}

    maps_dict = props.get('maps')
    session_props = getattr(session, 'game_properties', None) or {}
    if isinstance(session_props, dict) and isinstance(session_props.get('maps'), dict):
        maps_dict = session_props.get('maps')
    if not isinstance(maps_dict, dict):
        maps_dict = {}
        for name, map_obj in (getattr(session, 'maps', {}) or {}).items():
            maps_dict[name] = f'maps/{name}'
    props['maps'] = maps_dict

    registry = getattr(session, 'map_sets', None)
    if registry is not None:
        props['map_sets'] = registry.to_game_config()
    starting = getattr(session, 'active_map_set', None)
    if starting:
        props.setdefault('starting_map_set', starting)

    with open(path, 'w', encoding='utf-8') as handle:
        yaml.safe_dump(props, handle, sort_keys=False)

    session.game_properties = props
    return props


def unique_npc_uid_for_type(session, npc_type, overrides=None):
    """Return the authored unique ``entity_uid`` for ``npc_type``, or ``None``."""
    from natural20.npc import authored_unique_entity_uid
    from natural20.yaml_loader import load_campaign_resource_path

    if hasattr(session, '_canonical_npc_type') and isinstance(npc_type, str):
        npc_type = session._canonical_npc_type(npc_type)
    try:
        details = load_campaign_resource_path(session.root_path, f'npcs/{npc_type}.yml')
    except FileNotFoundError:
        details = {}
    extra = dict(overrides or {})
    return authored_unique_entity_uid(details, extra)


def _map_size_xy(battle_map):
    size = getattr(battle_map, 'size', None) or [0, 0]
    width = int(size[0]) if len(size) > 0 else 0
    height = int(size[1]) if len(size) > 1 else width
    return width, height


def spawn_or_move_npc(session, npc_type, target_map, x, y, group='b', rand_life=True,
                      overrides=None):
    """Create a generic NPC, or move/instance a unique NPC on the target map set.

    Unique NPCs already present on the destination map set are moved with
    :func:`place_entity_instance` instead of creating a second token.
    Unique NPCs that exist only on another set are instanced onto this set
    without removing the other-set token.
    """
    x, y = int(x), int(y)
    width, height = _map_size_xy(target_map)
    if x < 0 or y < 0 or x >= width or y >= height:
        raise ValueError('Position is outside map bounds')

    occupant = None
    try:
        occupant = target_map.entity_at(x, y)
    except Exception:
        occupant = None

    uid = unique_npc_uid_for_type(session, npc_type, overrides)
    existing = session.entity_by_uid(uid) if uid else None
    set_id = session.map_set_for(getattr(target_map, 'name', None))
    current = session.map_for_entity(existing, map_set=set_id) if existing else None

    if existing is not None and uid:
        if occupant is not None and occupant is not existing:
            raise ValueError('Position is occupied')
        from_map = getattr(current, 'name', None) if current is not None else None
        place_entity_instance(session, existing, target_map, x, y, group=group)
        moved = current is not None and current is not target_map
        same_map_move = current is target_map
        return {
            'entity_uid': str(getattr(existing, 'entity_uid', uid)),
            'npc_type': str(npc_type),
            'map': getattr(target_map, 'name', None),
            'position': [x, y],
            'unique': True,
            'moved': bool(moved or same_map_move),
            'from_map': from_map,
        }

    if occupant is not None:
        raise ValueError('Position is occupied')

    opt = {'rand_life': bool(rand_life)}
    if overrides:
        opt['overrides'] = dict(overrides)
    npc = session.npc(npc_type, opt)
    target_map.add(npc, x, y, group=group)
    return {
        'entity_uid': npc.entity_uid,
        'npc_type': str(npc_type),
        'map': getattr(target_map, 'name', None),
        'position': [x, y],
        'unique': bool(uid),
        'moved': False,
        'from_map': None,
    }


def place_entity_instance(session, entity, target_map, x: int, y: int, group=None):
    """Place ``entity`` on ``target_map`` without touching other map sets.

    Within the destination set the token is still unique: it is removed from
    any other map in that set, then added (or moved) on ``target_map``.
    """
    if entity is None or target_map is None:
        return None
    set_id = session.map_set_for(getattr(target_map, 'name', None))
    current = session.map_for_entity(entity, map_set=set_id)
    resolved_group = group
    if resolved_group is None:
        resolved_group = getattr(entity, 'group', None) or 'a'

    if current is target_map:
        try:
            pos = current.position_of(entity)
        except Exception:
            pos = None
        if pos is not None and list(pos) == [int(x), int(y)]:
            return entity
        if entity in getattr(current, 'entities', {}):
            current.remove(entity)
        target_map.add(entity, int(x), int(y), group=resolved_group)
        return entity

    if current is not None and entity in getattr(current, 'entities', {}):
        try:
            current.remove(entity)
        except Exception:
            pass
    target_map.add(entity, int(x), int(y), group=resolved_group)
    return entity


def iter_party_members(session) -> list:
    """PCs plus in-party sidekicks (unique by UID)."""
    from natural20.sidekick import iter_party_members as _iter_party
    return _iter_party(session)


def iter_player_characters(session) -> list:
    from natural20.player_character import PlayerCharacter

    seen: set[str] = set()
    players = []
    for battle_map in (getattr(session, 'maps', {}) or {}).values():
        try:
            entities = list(battle_map.entities)
        except Exception:
            continue
        for entity in entities:
            if not isinstance(entity, PlayerCharacter):
                continue
            uid = str(getattr(entity, 'entity_uid', '') or '')
            if not uid or uid in seen:
                continue
            seen.add(uid)
            players.append(entity)
    return players


def _spawn_positions(target_map) -> list[tuple[int, int]]:
    slots = getattr(target_map, 'player_spawn_points', None) or []
    positions = []
    for slot in slots:
        if isinstance(slot, (list, tuple)) and len(slot) >= 2:
            positions.append((int(slot[0]), int(slot[1])))
            continue
        if isinstance(slot, dict):
            pos = slot.get('position') or slot.get('pos')
            if isinstance(pos, (list, tuple)) and len(pos) >= 2:
                positions.append((int(pos[0]), int(pos[1])))
    return positions


def _nearest_placeable_to_spawns(target_map, entity, anchors: list[tuple[int, int]]) -> tuple[int, int]:
    """BFS from spawn/anchor squares to the nearest placeable cell."""
    from collections import deque

    width, height = _map_size_xy(target_map)
    seeds = [ (int(x), int(y)) for x, y in (anchors or []) if 0 <= int(x) < width and 0 <= int(y) < height ]
    if not seeds:
        seeds = [(0, 0)]
    visited: set[tuple[int, int]] = set()
    queue: deque[tuple[int, int]] = deque(seeds)
    for seed in seeds:
        visited.add(seed)
    while queue:
        x, y = queue.popleft()
        try:
            if target_map.placeable(entity, x, y, squeeze=False):
                return x, y
        except Exception:
            pass
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            nx, ny = x + dx, y + dy
            if nx < 0 or ny < 0 or nx >= width or ny >= height:
                continue
            if (nx, ny) in visited:
                continue
            visited.add((nx, ny))
            queue.append((nx, ny))
    return seeds[0]


def _next_placeable(target_map, entity, x: int, y: int) -> tuple[int, int]:
    try:
        if target_map.placeable(entity, int(x), int(y), squeeze=False):
            return int(x), int(y)
    except Exception:
        pass
    finder = getattr(target_map, 'find_empty_placeable_position', None)
    if finder:
        try:
            found = finder(entity, int(x), int(y))
            if found:
                fx, fy = int(found[0]), int(found[1])
                try:
                    if target_map.placeable(entity, fx, fy, squeeze=False):
                        return fx, fy
                except Exception:
                    pass
        except Exception:
            pass
    return _nearest_placeable_to_spawns(target_map, entity, [(int(x), int(y))])


def place_party_on_map(session, map_name: str, x: Optional[int] = None, y: Optional[int] = None,
                       players: Optional[list] = None, include_companions: bool = True,
                       include_sidekicks: bool = True, only_if_absent: bool = False) -> list[dict[str, Any]]:
    """Create/update PC (and companion/sidekick) instances on ``map_name``.

    Does not activate the map set. Returns a list of placement dicts.
    When ``only_if_absent`` is True, entities that already have a token on the
    destination map set are left where they are.
    """
    target_map = (getattr(session, 'maps', {}) or {}).get(map_name)
    if target_map is None:
        raise ValueError(f'Unknown map: {map_name}')

    party = list(players) if players is not None else iter_party_members(session)
    if include_sidekicks and players is not None:
        seen = {str(getattr(ent, 'entity_uid', '') or '') for ent in party}
        try:
            from natural20.sidekick import iter_in_party_sidekicks
            for extra in iter_in_party_sidekicks(session):
                uid = str(getattr(extra, 'entity_uid', '') or '')
                if uid and uid not in seen:
                    seen.add(uid)
                    party.append(extra)
        except Exception:
            pass

    placed: list[dict[str, Any]] = []
    dest_set = session.map_set_for(map_name) if hasattr(session, 'map_set_for') else None
    spawn_anchors = _spawn_positions(target_map)
    origin_x, origin_y = x, y
    if origin_x is None or origin_y is None:
        if spawn_anchors:
            origin_x, origin_y = spawn_anchors[0]
        else:
            origin_x, origin_y = 0, 0

    for index, entity in enumerate(party):
        uid = str(getattr(entity, 'entity_uid', '') or '')
        if only_if_absent and dest_set is not None:
            existing_map = session.map_for_entity(entity, map_set=dest_set)
            if existing_map is not None:
                try:
                    pos = existing_map.position_of(entity)
                except Exception:
                    pos = None
                placed.append({
                    'entity_uid': uid,
                    'map': getattr(existing_map, 'name', map_name),
                    'position': list(pos) if pos is not None else None,
                    'already_present': True,
                })
                continue

        slot = None
        allocate = getattr(target_map, 'allocate_player_spawn_point', None)
        if allocate and (x is None or y is None):
            try:
                slot = allocate(uid)
            except Exception:
                slot = None
        if slot:
            pos = slot.get('position') or slot.get('pos') or [origin_x, origin_y]
            px, py = int(pos[0]), int(pos[1])
            try:
                if not target_map.placeable(entity, px, py, squeeze=False):
                    px, py = _nearest_placeable_to_spawns(target_map, entity, spawn_anchors or [(px, py)])
            except Exception:
                px, py = _nearest_placeable_to_spawns(target_map, entity, spawn_anchors or [(px, py)])
        else:
            anchors = spawn_anchors or [(int(origin_x), int(origin_y))]
            if x is not None and y is not None:
                anchors = [(int(origin_x) + index, int(origin_y))] + list(anchors)
            px, py = _nearest_placeable_to_spawns(target_map, entity, anchors)

        place_entity_instance(session, entity, target_map, px, py, group=getattr(entity, 'group', None) or 'a')
        placed.append({
            'entity_uid': uid,
            'map': map_name,
            'position': [px, py],
            'already_present': False,
        })
        if include_companions:
            try:
                from natural20.companion import sync_companions_for_entity
                sync_companions_for_entity(
                    session,
                    getattr(session, 'game_properties', None),
                    entity,
                    target_map=target_map,
                )
            except Exception:
                pass
    return placed


def assignment_blockers(session, map_name: str, new_set_id: str) -> list[str]:
    """Return human-readable reasons ``map_name`` cannot move to ``new_set_id``."""
    errors: list[str] = []
    maps = getattr(session, 'maps', {}) or {}
    if map_name not in maps:
        return [f'Unknown map: {map_name}']

    stack = None
    stack_for = getattr(session, 'stack_for_map', None)
    if callable(stack_for):
        stack = stack_for(map_name)
    if stack is not None:
        stack_maps = list(stack.maps_in_stack()) if hasattr(stack, 'maps_in_stack') else []
        for other in stack_maps:
            if other == map_name:
                continue
            if session.map_set_for(other) != new_set_id and other in maps:
                errors.append(
                    f"Map '{map_name}' is in stack '{getattr(stack, 'id', stack)}' with "
                    f"'{other}', which would split the stack across map sets"
                )
                break

    current_set = session.map_set_for(map_name)
    if current_set == new_set_id:
        return errors

    def _target_of(obj) -> Optional[str]:
        return getattr(obj, 'target_map', None) or None

    def _is_party_link(obj) -> bool:
        try:
            from natural20.item_library.teleporter import is_party_travel_object
            return is_party_travel_object(obj)
        except Exception:
            return False

    battle_map = maps[map_name]
    for obj in list(getattr(battle_map, 'interactable_objects', {}).keys()):
        if _is_party_link(obj):
            continue
        target = _target_of(obj)
        if not target:
            continue
        if session.map_set_for(target) != new_set_id and session.map_set_for(target) == current_set:
            errors.append(
                f"Map '{map_name}' has a {type(obj).__name__} targeting '{target}' "
                f"which would become a cross-set reference"
            )
            break

    for other_name, other_map in maps.items():
        if other_name == map_name:
            continue
        if session.map_set_for(other_name) != current_set:
            continue
        for obj in list(getattr(other_map, 'interactable_objects', {}).keys()):
            if _is_party_link(obj):
                continue
            if _target_of(obj) == map_name:
                errors.append(
                    f"Map '{other_name}' has a {type(obj).__name__} targeting '{map_name}' "
                    f"which would become a cross-set reference"
                )
                break
    return errors
