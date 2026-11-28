"""Teleportation destination registry + PHB Teleport outcome table.

Every creature that can cast ``teleport`` keeps a personal database of
destinations in ``entity.properties['teleport_destinations']`` (a plain list
of dicts, so it serializes with the entity for save/load and survives as
authored YAML on NPCs/characters). A destination is either:

``kind: 'coords'``
    a fixed ``map`` + ``x``/``y`` square on a campaign map, or
``kind: 'anchor'``
    a *person or object* (``entity_uid``); the arrival point is wherever that
    entity stands when the spell is cast (SRD "linked object", scrying a
    familiar person, a party rally beacon, ...).

``familiarity`` decides the d100 outcome table and is set by the DM (VTT DM
Console -> Teleport panel, MCP ``dm.teleport_destination``) or authored:

    permanent_circle  linked_object  very_familiar
    seen_casually     viewed_once    false

The same module is the engine-level API for game events and AI agents:
``upsert_destination`` / ``remove_destination`` / ``list_destinations`` take
any entity and store plain-data dicts, so a story trigger ("the party maps
the ruin" -> add a ``viewed_once`` destination) is one call.

Similar Area / Off Target results need somewhere to actually land on a
grid VTT. Destinations may declare ``similar_maps`` / ``off_target_map``, and
map YAMLs may declare top-level ``area_themes: [laboratory, tavern]`` so the
closest thematically-similar map can be chosen. With nothing authored, the
outcome still happens but lands on a random free square of the destination
map, and the narrative distance is logged.
"""

from __future__ import annotations

import random
import re
import uuid
from collections import deque
from typing import List, Optional, Tuple

DESTINATIONS_KEY = 'teleport_destinations'

# PHB Teleportation Outcome table (d100). Ranges are inclusive.
OUTCOME_MISHAP = 'mishap'
OUTCOME_SIMILAR = 'similar_area'
OUTCOME_OFF_TARGET = 'off_target'
OUTCOME_ON_TARGET = 'on_target'

FAMILIARITY_PERMANENT_CIRCLE = 'permanent_circle'
FAMILIARITY_LINKED_OBJECT = 'linked_object'
FAMILIARITY_VERY_FAMILIAR = 'very_familiar'
FAMILIARITY_SEEN_CASUALLY = 'seen_casually'
FAMILIARITY_VIEWED_ONCE = 'viewed_once'
FAMILIARITY_FALSE = 'false'

FAMILIARITY_LEVELS = (
    FAMILIARITY_PERMANENT_CIRCLE,
    FAMILIARITY_LINKED_OBJECT,
    FAMILIARITY_VERY_FAMILIAR,
    FAMILIARITY_SEEN_CASUALLY,
    FAMILIARITY_VIEWED_ONCE,
    FAMILIARITY_FALSE,
)

FAMILIARITY_LABELS = {
    FAMILIARITY_PERMANENT_CIRCLE: 'Permanent circle',
    FAMILIARITY_LINKED_OBJECT: 'Linked object',
    FAMILIARITY_VERY_FAMILIAR: 'Very familiar',
    FAMILIARITY_SEEN_CASUALLY: 'Seen casually',
    FAMILIARITY_VIEWED_ONCE: 'Viewed once or described',
    FAMILIARITY_FALSE: 'False destination',
}

# familiarity -> ordered [(outcome, high), ...] for a 1d100 roll.
# permanent circle / linked object: always on target; false: mishap or
# similar area (it does not exist, so it can never be "on target").
_OUTCOME_TABLE = {
    FAMILIARITY_PERMANENT_CIRCLE: [(OUTCOME_ON_TARGET, 100)],
    FAMILIARITY_LINKED_OBJECT: [(OUTCOME_ON_TARGET, 100)],
    FAMILIARITY_VERY_FAMILIAR: [
        (OUTCOME_MISHAP, 5), (OUTCOME_SIMILAR, 13),
        (OUTCOME_OFF_TARGET, 24), (OUTCOME_ON_TARGET, 100),
    ],
    FAMILIARITY_SEEN_CASUALLY: [
        (OUTCOME_MISHAP, 33), (OUTCOME_SIMILAR, 43),
        (OUTCOME_OFF_TARGET, 53), (OUTCOME_ON_TARGET, 100),
    ],
    FAMILIARITY_VIEWED_ONCE: [
        (OUTCOME_MISHAP, 43), (OUTCOME_SIMILAR, 53),
        (OUTCOME_OFF_TARGET, 73), (OUTCOME_ON_TARGET, 100),
    ],
    FAMILIARITY_FALSE: [(OUTCOME_MISHAP, 50), (OUTCOME_SIMILAR, 100)],
}


def roll_outcome(familiarity: str, roll: int) -> str:
    """Map a 1..100 roll to a teleport outcome for ``familiarity``."""
    table = _OUTCOME_TABLE.get(normalize_familiarity(familiarity),
                               _OUTCOME_TABLE[FAMILIARITY_VIEWED_ONCE])
    roll = max(1, min(100, int(roll)))
    low = 1
    for outcome, high in table:
        if low <= roll <= high:
            return outcome
        low = high + 1
    return table[-1][0]


def normalize_familiarity(value) -> str:
    key = re.sub(r'[^a-z0-9]+', '_', str(value or '').strip().lower())
    aliases = {
        'permanent': FAMILIARITY_PERMANENT_CIRCLE,
        'circle': FAMILIARITY_PERMANENT_CIRCLE,
        'permanent_circle': FAMILIARITY_PERMANENT_CIRCLE,
        'object': FAMILIARITY_LINKED_OBJECT,
        'linked_object': FAMILIARITY_LINKED_OBJECT,
        'very_familiar': FAMILIARITY_VERY_FAMILIAR,
        'seen_casually': FAMILIARITY_SEEN_CASUALLY,
        'seen': FAMILIARITY_SEEN_CASUALLY,
        'viewed_once': FAMILIARITY_VIEWED_ONCE,
        'viewed_once_or_described': FAMILIARITY_VIEWED_ONCE,
        'described': FAMILIARITY_VIEWED_ONCE,
        'false': FAMILIARITY_FALSE,
        'false_destination': FAMILIARITY_FALSE,
    }
    return aliases.get(key, FAMILIARITY_VIEWED_ONCE)


# ---------------------------------------------------------------------------
# personal destination registry
# ---------------------------------------------------------------------------

def _slugify(name: str) -> str:
    slug = re.sub(r'[^a-z0-9]+', '-', str(name or '').strip().lower()).strip('-')
    return slug or 'destination'


def list_destinations(entity) -> List[dict]:
    """The entity's known destinations (live list from ``properties``)."""
    if entity is None:
        return []
    props = getattr(entity, 'properties', None)
    if props is None:
        return []
    entries = props.get(DESTINATIONS_KEY)
    if not isinstance(entries, list):
        return []
    return [e for e in entries if isinstance(e, dict)]


def find_destination(entity, dest_id: str) -> Optional[dict]:
    for entry in list_destinations(entity):
        if entry.get('id') == dest_id or entry.get('name') == dest_id:
            return entry
    return None


def upsert_destination(entity, destination: dict) -> dict:
    """Add or update a destination by ``id``/``name`` (engine-side API used
    by the DM UI, MCP tools and game events). Stores plain data only."""
    props = getattr(entity, 'properties', None)
    if props is None:
        raise ValueError('entity has no properties to store destinations in')
    entry = normalize_destination(destination)
    existing = list_destinations(entity)
    for idx, old in enumerate(existing):
        if old.get('id') == entry['id'] or (
                old.get('name') and old.get('name') == entry.get('name')):
            merged = dict(old)
            merged.update(entry)
            merged['id'] = old.get('id') or entry['id']
            props[DESTINATIONS_KEY] = [
                merged if item is old else item for item in existing
            ]
            return merged
    props[DESTINATIONS_KEY] = existing + [entry]
    return entry


def remove_destination(entity, dest_id: str) -> bool:
    props = getattr(entity, 'properties', None)
    if props is None:
        return False
    existing = list_destinations(entity)
    remaining = [e for e in existing
                 if e.get('id') != dest_id and e.get('name') != dest_id]
    if len(remaining) == len(existing):
        return False
    props[DESTINATIONS_KEY] = remaining
    return True


def set_familiarity(entity, dest_id: str, familiarity: str) -> Optional[dict]:
    entry = find_destination(entity, dest_id)
    if entry is None:
        return None
    entry['familiarity'] = normalize_familiarity(familiarity)
    return entry


def normalize_destination(raw: dict) -> dict:
    """Validate/normalize one authored or UI-supplied destination dict."""
    if not isinstance(raw, dict):
        raise ValueError('destination must be a mapping')
    name = str(raw.get('name') or '').strip()
    if not name:
        raise ValueError('destination requires a name')
    kind = str(raw.get('kind') or ('anchor' if raw.get('entity_uid') else 'coords'))
    if kind not in ('coords', 'anchor'):
        raise ValueError(f'unknown destination kind: {kind}')
    entry = {
        'id': str(raw.get('id') or _slugify(name)),
        'name': name,
        'kind': kind,
        'familiarity': normalize_familiarity(raw.get('familiarity')),
    }
    if kind == 'coords':
        x, y = raw.get('x'), raw.get('y')
        if x is None or y is None:
            raise ValueError('coords destination requires x and y')
        entry['map'] = str(raw.get('map') or '')
        entry['x'] = int(x)
        entry['y'] = int(y)
    else:
        entry['entity_uid'] = str(raw.get('entity_uid') or '')
        if not entry['entity_uid']:
            raise ValueError('anchor destination requires entity_uid')
    for key in ('similar_maps', 'off_target_map', 'notes', 'added_by'):
        value = raw.get(key)
        if value:
            entry[key] = value
    return entry


# ---------------------------------------------------------------------------
# resolution and arrival placement
# ---------------------------------------------------------------------------

def resolve_destination(session, entity, destination, battle=None):
    """Resolve ``destination`` to ``(map, x, y)`` at cast time.

    ``coords`` look the map up on the session; ``anchor`` follows the anchor
    entity's *current* map/position. Returns ``None`` when the destination
    no longer resolves (a removed map, a destroyed anchor) — the caller then
    treats it like a false destination.
    """
    if session is None or not isinstance(destination, dict):
        return None
    kind = destination.get('kind', 'coords')
    if kind == 'anchor':
        anchor_uid = str(destination.get('entity_uid') or '')
        anchor = session.entity_by_uid(anchor_uid) if anchor_uid else None
        if anchor is None:
            return None
        target_map = None
        if battle is not None:
            try:
                target_map = battle.map_for(anchor)
            except Exception:
                target_map = None
        if target_map is None:
            target_map = session.map_for(anchor)
        if target_map is None:
            return None
        try:
            x, y = target_map.position_of(anchor)
        except Exception:
            return None
        return (target_map, int(x), int(y))
    map_name = str(destination.get('map') or '')
    target_map = _map_by_name(session, map_name)
    if target_map is None:
        return None
    try:
        return (target_map, int(destination.get('x')), int(destination.get('y')))
    except (TypeError, ValueError):
        return None


def _map_by_name(session, map_name) -> Optional[object]:
    if not map_name:
        return None
    maps = getattr(session, 'maps', None)
    if isinstance(maps, dict):
        found = maps.get(str(map_name))
        if found is not None:
            return found
    getter = getattr(session, 'get_map', None)
    if callable(getter):
        try:
            return getter(str(map_name))
        except Exception:
            return None
    return None


def _iter_session_maps(session) -> List[object]:
    maps = getattr(session, 'maps', None)
    if isinstance(maps, dict):
        return [m for m in maps.values() if m is not None]
    return []


def map_area_themes(battle_map) -> List[str]:
    props = getattr(battle_map, 'properties', None) or {}
    themes = props.get('area_themes') or props.get('area_theme') or []
    if isinstance(themes, str):
        themes = [themes]
    return [str(t).strip().lower() for t in themes if str(t).strip()]


def destination_theme_tags(session, destination) -> List[str]:
    """Themes used for the Similar Area result: the destination's own map
    themes (or the anchor entity's map themes)."""
    resolved = resolve_destination(session, None, destination)
    tags = set()
    if resolved is not None:
        tags.update(map_area_themes(resolved[0]))
    for name in (destination.get('similar_maps') or []):
        battle_map = _map_by_name(session, name)
        if battle_map is not None:
            tags.update(map_area_themes(battle_map))
    return sorted(tags)


def pick_similar_area(session, destination, origin_map, rng=None) -> Optional[Tuple[object, int, int]]:
    """Landing spot for a Similar Area result: the closest map that shares an
    ``area_themes`` tag with the destination, arriving at its base spawn.
    Falls back to an explicit ``similar_maps`` entry, then to a random spot
    on the destination map itself."""
    rng = rng or random
    explicit = [
        _map_by_name(session, name)
        for name in (destination.get('similar_maps') or [])
    ]
    tags = set(destination_theme_tags(session, destination))
    dest_map = None
    if resolved_dest := resolve_destination(session, None, destination):
        dest_map = resolved_dest[0]

    candidates = []
    for battle_map in _iter_session_maps(session):
        if origin_map is not None and battle_map is origin_map:
            continue
        if dest_map is not None and battle_map is dest_map:
            continue  # the destination map itself is not a "similar area"
        name = getattr(battle_map, 'name', None)
        if explicit and name in [getattr(m, 'name', None) for m in explicit if m]:
            candidates.append((0, battle_map))
        elif tags and tags & set(map_area_themes(battle_map)):
            candidates.append((1, battle_map))
    if candidates:
        candidates.sort(key=lambda pair: (pair[0], str(getattr(pair[1], 'name', ''))))
        battle_map = candidates[0][1]
        return (battle_map, *_base_spawn(battle_map, rng))
    return None


def pick_off_target(session, destination, origin_map, rng=None) -> Optional[Tuple[object, int, int]]:
    """Landing spot for an Off Target result: a random free square on the
    destination's declared ``off_target_map`` (the road/wilderness map the DM
    set up), else a random free square on the destination map itself."""
    rng = rng or random
    battle_map = _map_by_name(session, destination.get('off_target_map') or '')
    if battle_map is None:
        resolved = resolve_destination(session, None, destination)
        battle_map = resolved[0] if resolved else None
    if battle_map is None:
        return None
    return (battle_map, *_random_free_square(battle_map, rng))


def _base_spawn(battle_map, rng) -> Tuple[int, int]:
    base = (getattr(battle_map, 'properties', None) or {}).get('map', {}).get('base')
    if isinstance(base, list) and base:
        rows = [r for r in base if isinstance(r, list) and r]
        if rows:
            row = rng.choice(rows)
            try:
                return (int(row[0]), int(row[1]))
            except (TypeError, ValueError, IndexError):
                pass
    return _random_free_square(battle_map, rng)


def _random_free_square(battle_map, rng) -> Tuple[int, int]:
    width, height = (getattr(battle_map, 'size', None) or [0, 0])[:2]
    width, height = int(width), int(height)
    if width <= 0 or height <= 0:
        return (0, 0)
    for _ in range(50):
        x, y = rng.randrange(width), rng.randrange(height)
        try:
            if battle_map.entity_at(x, y) is None and battle_map.placeable(None, x, y):
                return (x, y)
        except Exception:
            return (x, y)
    return (width // 2, height // 2)


def free_square_near(battle_map, x: int, y: int, entity=None, taken=None) -> Tuple[int, int]:
    """Nearest square to (x, y) where ``entity`` fits (anchor landings and
    crowding push the party around the intended arrival square)."""
    taken = set(tuple(t) for t in (taken or ()))
    target = (int(x), int(y))

    def placeable(sq):
        if sq in taken:
            return False
        try:
            if entity is not None and not battle_map.placeable(entity, sq[0], sq[1]):
                return False
        except Exception:
            try:
                if battle_map.entity_at(sq[0], sq[1]) is not None:
                    return False
            except Exception:
                pass
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
    return target


def describe_roll(roll: int, outcome: str) -> str:
    return f"rolled {roll} — {outcome.replace('_', ' ')}"


def new_destination_id(name: str) -> str:
    return f"{_slugify(name)}-{uuid.uuid4().hex[:6]}"


# ---------------------------------------------------------------------------
# event / trigger API (map YAML triggers, on_enter objects, story beats)
# ---------------------------------------------------------------------------
#
# Authored event blocks grant/revoke destinations as game events, e.g. a
# scrying pool map object (``teleport_destinations:`` on the object YAML,
# fired on ``on_enter``) or a map ``triggers:`` entry of type
# ``teleport_destinations``::
#
#   teleport_destinations:
#     - op: add                 # add | remove | set_familiarity
#       target: self            # self | party | all_characters | uid:<uid>
#       once: true              # per entity (on_enter pads)
#       destination:
#         name: Sunken Temple
#         map: temple
#         x: 8
#         y: 8
#         familiarity: viewed once or described
#         notes: glimpsed in the scrying pool
#
def _op_targets(session, source, target_spec):
    spec = str(target_spec or 'self').strip().lower()
    if spec in ('', 'self', 'source', 'entity'):
        return [source] if source is not None else []
    if spec in ('party', 'party_members'):
        try:
            from natural20.map_set import iter_party_members
            return list(iter_party_members(session))
        except Exception:
            return []
    if spec in ('all_characters', 'all_pcs', 'pcs'):
        from natural20.player_character import PlayerCharacter
        seen, out = set(), []
        for battle_map in (getattr(session, 'maps', None) or {}).values():
            for entity in list(getattr(battle_map, 'entities', {}) or {}):
                uid = getattr(entity, 'entity_uid', None)
                if (isinstance(entity, PlayerCharacter) and uid not in seen):
                    seen.add(uid)
                    out.append(entity)
        return out
    if spec.startswith('uid:'):
        entity = session.entity_by_uid(spec[4:])
        return [entity] if entity is not None else []
    entity = session.entity_by_uid(spec)
    return [entity] if entity is not None else []


def apply_destination_ops(session, ops, source=None, battle=None):
    """Apply authored/runtime destination changes as a game event.

    Returns ``(applied_lines, errors)`` — human-readable strings for the DM
    log. Emits a ``teleport_destinations`` event when anything changed.
    """
    if session is None or ops is None:
        return [], ['no session']
    if isinstance(ops, dict):
        ops = [ops]
    applied, errors = [], []
    for op_cfg in ops:
        if not isinstance(op_cfg, dict):
            continue
        op = str(op_cfg.get('op') or 'add').strip().lower()
        destination = op_cfg.get('destination') or op_cfg
        targets = _op_targets(session, source, op_cfg.get('target'))
        if not targets:
            errors.append(f"teleport destination op '{op}': no matching target "
                          f"{op_cfg.get('target')!r}")
            continue
        for entity in targets:
            if entity is None:
                continue
            # once-gate lives in properties (persisted by save/load, unlike
            # player-character attributes)
            state_flags = getattr(entity, 'properties', None)
            already = None
            if op_cfg.get('once') and isinstance(state_flags, dict):
                seen = state_flags.setdefault('_teleport_dest_granted', [])
                key = str(destination.get('name') or destination.get('id') or '')
                already = key in seen
            try:
                if op == 'add':
                    entry = upsert_destination(entity, destination)
                    if already:
                        continue
                    if op_cfg.get('once') and isinstance(state_flags, dict):
                        state_flags.setdefault('_teleport_dest_granted', []).append(
                            str(entry.get('name') or entry.get('id') or ''))
                    label = FAMILIARITY_LABELS.get(entry.get('familiarity'), '')
                    applied.append(
                        f"{getattr(entity, 'name', entity)} learns a teleport "
                        f"destination: {entry.get('name')} ({label})")
                elif op == 'remove':
                    key = str(destination.get('id') or destination.get('name') or '')
                    if remove_destination(entity, key):
                        applied.append(
                            f"{getattr(entity, 'name', entity)} forgets the teleport "
                            f"destination {key}")
                elif op == 'set_familiarity':
                    key = str(destination.get('id') or destination.get('name') or '')
                    entry = set_familiarity(entity, key, destination.get('familiarity'))
                    if entry is not None:
                        applied.append(
                            f"{getattr(entity, 'name', entity)} now knows {key} as "
                            f"{FAMILIARITY_LABELS.get(entry['familiarity'], '')}")
                    else:
                        errors.append(f"unknown destination {key!r}")
                else:
                    errors.append(f"unknown teleport destination op {op!r}")
            except ValueError as exc:
                errors.append(str(exc))
    if applied and getattr(session, 'event_manager', None) is not None:
        try:
            session.event_manager.received_event({
                'event': 'teleport_destinations',
                'source': source,
                'lines': applied,
            })
        except Exception:
            pass
    return applied, errors
