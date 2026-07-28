"""Detect Magic aura helpers — 5e schools, item/entity/annotation sources."""

from __future__ import annotations

import math
from typing import Any, Iterable, Optional

MAGIC_SCHOOLS = frozenset({
    'abjuration',
    'conjuration',
    'divination',
    'enchantment',
    'evocation',
    'illusion',
    'necromancy',
    'transmutation',
})

DEFAULT_SCHOOL = 'transmutation'
DETECT_MAGIC_RANGE_FT = 30
PRESENCE_LABEL = 'Magic sensed'

# Maximum cumulative thickness (feet) Detect Magic can penetrate per material.
DETECT_MAGIC_PENETRATION_FT = {
    'stone': 1.0,
    'metal': 1.0 / 12.0,
    'lead': 0.0,
    'wood': 3.0,
    'dirt': 3.0,
}


def normalize_magic_school(raw: Any) -> str:
    school = str(raw or DEFAULT_SCHOOL).strip().lower().replace(' ', '_')
    if school in MAGIC_SCHOOLS:
        return school
    return DEFAULT_SCHOOL


def _aura(label: str, school: str, *, strength: str = 'faint', source: str = 'unknown',
          revelation: str = 'aura') -> dict[str, str]:
    return {
        'label': str(label or school.title()),
        'school': normalize_magic_school(school),
        'strength': strength if strength in ('faint', 'strong') else 'faint',
        'source': source,
        'revelation': revelation if revelation in ('aura', 'presence') else 'aura',
    }


def _presence_only_aura(aura: dict[str, str]) -> dict[str, str]:
    return {
        'label': PRESENCE_LABEL,
        'school': 'unknown',
        'strength': aura.get('strength') or 'faint',
        'source': aura.get('source') or 'unknown',
        'revelation': 'presence',
    }


def _merge_auras(auras: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for aura in auras:
        if not isinstance(aura, dict):
            continue
        key = (
            str(aura.get('label') or ''),
            normalize_magic_school(aura.get('school')),
            str(aura.get('strength') or 'faint'),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append({
            'label': key[0] or key[1].title(),
            'school': key[1],
            'strength': key[2],
            'source': str(aura.get('source') or 'unknown'),
        })
    return merged


def item_definition_bears_magic(item_def: dict[str, Any] | None) -> bool:
    if not isinstance(item_def, dict):
        return False
    if item_def.get('magical'):
        return True
    if item_def.get('type') in ('scroll', 'potion', 'wand', 'rod', 'staff'):
        return True
    if item_def.get('item_class') in ('SpellScroll', 'HealingPotion', 'MagicSpellItem'):
        return True
    if item_def.get('spell'):
        return True
    return False


def item_definition_magic_school(session, item_def: dict[str, Any] | None, item_name: str = '') -> str:
    if not isinstance(item_def, dict):
        return DEFAULT_SCHOOL
    if item_def.get('magic_school'):
        return normalize_magic_school(item_def['magic_school'])
    spell_name = item_def.get('spell')
    if spell_name and session is not None:
        spell = session.load_spell(spell_name)
        if isinstance(spell, dict) and spell.get('school'):
            return normalize_magic_school(spell['school'])
    item_type = str(item_def.get('type') or '').lower()
    if item_type == 'potion':
        return 'conjuration'
    if item_type == 'scroll':
        return 'divination'
    return DEFAULT_SCHOOL


def item_definition_aura(session, item_name: str, item_def: dict[str, Any] | None) -> Optional[dict[str, str]]:
    if not item_definition_bears_magic(item_def):
        return None
    label = str(item_def.get('label') or item_def.get('name') or item_name).strip()
    strength = 'strong' if item_def.get('magical_strength') == 'strong' else 'faint'
    return _aura(label, item_definition_magic_school(session, item_def, item_name),
                 strength=strength, source='item')


def _entity_property_aura(entity) -> list[dict[str, str]]:
    props = getattr(entity, 'properties', None) or {}
    auras: list[dict[str, str]] = []
    raw = props.get('magical_aura')
    if isinstance(raw, dict):
        auras.append(_aura(
            raw.get('label') or getattr(entity, 'label', lambda: getattr(entity, 'name', 'Magic'))(),
            raw.get('school') or raw.get('magic_school') or DEFAULT_SCHOOL,
            strength=raw.get('strength') or 'faint',
            source='entity',
        ))
    elif props.get('magical') or props.get('magic_school'):
        label = props.get('aura_label') or getattr(entity, 'label', lambda: getattr(entity, 'name', 'Magic'))()
        auras.append(_aura(label, props.get('magic_school') or DEFAULT_SCHOOL,
                           strength=props.get('aura_strength') or 'faint', source='entity'))
    return auras


def _entity_inventory_auras(session, entity) -> list[dict[str, str]]:
    if session is None or entity is None:
        return []
    auras: list[dict[str, str]] = []
    inventory = getattr(entity, 'inventory', None) or {}
    for item_name, entry in inventory.items():
        qty = 0
        if isinstance(entry, dict):
            qty = int(entry.get('qty') or 0)
        if qty <= 0:
            continue
        item_def = session.load_thing(item_name)
        aura = item_definition_aura(session, str(item_name), item_def)
        if aura:
            auras.append(aura)
    if hasattr(entity, 'equipped_items'):
        for item in entity.equipped_items() or []:
            item_name = item.get('name')
            if not item_name:
                continue
            item_def = session.load_thing(item_name) or item
            aura = item_definition_aura(session, str(item_name), item_def)
            if aura:
                auras.append(aura)
    return auras


def _entity_active_spell_auras(session, entity) -> list[dict[str, str]]:
    if session is None or entity is None or not hasattr(entity, 'current_effects'):
        return []
    auras: list[dict[str, str]] = []
    for effect_entry in entity.current_effects() or []:
        effect = effect_entry.get('effect')
        if effect is None:
            continue
        props = getattr(effect, 'properties', None)
        if isinstance(props, dict) and props.get('school'):
            label = getattr(effect, 'name', None) or props.get('label') or props.get('name') or 'Active spell'
            auras.append(_aura(label, props['school'], strength='faint', source='spell_effect'))
    return auras


def entity_magical_auras(session, entity) -> list[dict[str, str]]:
    if entity is None:
        return []
    return _merge_auras(
        _entity_property_aura(entity)
        + _entity_inventory_auras(session, entity)
        + _entity_active_spell_auras(session, entity)
    )


def object_magical_auras(session, obj) -> list[dict[str, str]]:
    if obj is None:
        return []
    props = getattr(obj, 'properties', None) or {}
    auras: list[dict[str, str]] = []
    raw = props.get('magical_aura')
    if isinstance(raw, dict):
        auras.append(_aura(
            raw.get('label') or getattr(obj, 'label', lambda: getattr(obj, 'name', 'Object'))(),
            raw.get('school') or raw.get('magic_school') or DEFAULT_SCHOOL,
            strength=raw.get('strength') or 'faint',
            source='object',
        ))
    elif props.get('magical') or props.get('magic_school'):
        auras.append(_aura(
            props.get('aura_label') or getattr(obj, 'label', lambda: getattr(obj, 'name', 'Object'))(),
            props.get('magic_school') or DEFAULT_SCHOOL,
            strength=props.get('aura_strength') or 'faint',
            source='object',
        ))
    inventory = getattr(obj, 'inventory', None) or {}
    if session is not None and inventory:
        for item_name, entry in inventory.items():
            qty = int((entry or {}).get('qty') or 0) if isinstance(entry, dict) else 0
            if qty <= 0:
                continue
            item_def = session.load_thing(item_name)
            aura = item_definition_aura(session, str(item_name), item_def)
            if aura:
                auras.append(aura)
    return _merge_auras(auras)


def annotation_magical_auras(annotation: dict[str, Any]) -> list[dict[str, str]]:
    if not isinstance(annotation, dict):
        return []
    if not annotation.get('magical') and not annotation.get('magic_school'):
        return []
    return [_aura(
        annotation.get('label') or annotation.get('id') or 'Magical presence',
        annotation.get('magic_school') or annotation.get('school') or DEFAULT_SCHOOL,
        strength=annotation.get('aura_strength') or annotation.get('strength') or 'faint',
        source='annotation',
    )]


def list_campaign_magical_annotations(session, map_name: str) -> list[dict[str, Any]]:
    game_props = getattr(session, 'game_properties', None) or {}
    raw = game_props.get('magical_annotations') or {}
    if not isinstance(raw, dict):
        return []
    entries = raw.get(map_name) or []
    if not isinstance(entries, list):
        return []
    from natural20.map_annotations import normalize_annotation

    items: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        try:
            items.append(normalize_annotation(entry, index=index))
        except ValueError:
            continue
    return items


def resolve_map_annotation_key(session, battle_map) -> Optional[str]:
    if battle_map is None:
        return None
    if getattr(battle_map, 'name', None):
        return str(battle_map.name)
    if session is not None and hasattr(session, 'maps') and isinstance(session.maps, dict):
        for key, candidate in session.maps.items():
            if candidate is battle_map:
                return str(key)
    props = getattr(battle_map, 'properties', None) or {}
    return props.get('name')


def distance_ft(pos_a, pos_b, feet_per_grid: int = 5) -> float:
    dx = (int(pos_a[0]) - int(pos_b[0])) * feet_per_grid
    dy = (int(pos_a[1]) - int(pos_b[1])) * feet_per_grid
    return math.hypot(dx, dy)


def viewer_has_detect_magic(viewer) -> bool:
    return viewer is not None and hasattr(viewer, 'has_effect') and viewer.has_effect('detect_magic')


def _object_blocks_detect_magic(obj, origin=None) -> bool:
    """Whether an object on a path square blocks Detect Magic (direction-agnostic default)."""
    props = getattr(obj, 'properties', None) or {}
    if props.get('detect_magic_barrier'):
        return True

    class_name = obj.__class__.__name__
    item_type = str(props.get('type') or getattr(obj, 'type', '') or '').lower()

    if class_name in ('DoorObject', 'DoorObjectWall') or 'door' in item_type:
        try:
            return bool(obj.closed() and not obj.dead())
        except Exception:
            return bool(props.get('opaque'))

    if class_name in ('StoneWall', 'StoneWallDirectional') or props.get('wall'):
        try:
            return not obj.dead()
        except Exception:
            return True

    if props.get('opaque'):
        return True

    if origin is not None:
        try:
            return bool(obj.opaque(origin))
        except Exception:
            return False

    try:
        return bool(obj.opaque())
    except Exception:
        return False


def _barrier_layers_at_square(battle_map, x: int, y: int, origin=None) -> list[tuple[str, float]]:
    """Return (material, thickness_ft) layers on a grid square for Detect Magic."""
    layers: list[tuple[str, float]] = []
    feet_per_grid = float(getattr(battle_map, 'feet_per_grid', 5) or 5)

    if battle_map.base_map[x][y] == '#':
        layers.append(('stone', feet_per_grid))
        return layers

    for obj in battle_map.objects_at(x, y):
        props = getattr(obj, 'properties', None) or {}
        custom = props.get('detect_magic_barrier')
        if isinstance(custom, dict):
            material = str(custom.get('material') or 'stone').lower()
            thickness = float(custom.get('thickness_ft', 1.0))
            layers.append((material, thickness))
            continue

        if not _object_blocks_detect_magic(obj, origin=origin):
            continue

        item_type = str(props.get('type') or getattr(obj, 'type', '') or '').lower()
        name = str(props.get('name') or getattr(obj, 'name', '') or '').lower()
        class_name = obj.__class__.__name__

        if props.get('metallic') or 'iron' in name or 'metal' in name:
            layers.append(('metal', 1.0 / 12.0))
        elif 'lead' in name or props.get('material') == 'lead':
            layers.append(('lead', 0.01))
        elif 'stone_wall' in item_type or class_name in ('StoneWall', 'StoneWallDirectional'):
            layers.append(('stone', 1.0))
        elif 'dirt' in item_type or 'earth' in item_type:
            layers.append(('dirt', feet_per_grid))
        elif 'door' in item_type or class_name in ('DoorObject', 'DoorObjectWall'):
            layers.append(('wood', 2.0 / 12.0))
        elif props.get('wall'):
            layers.append(('stone', 1.0))
        elif props.get('opaque'):
            layers.append(('wood', 1.0 / 12.0))

    return layers


def detect_magic_path_blocked(battle_map, start: tuple[int, int], end: tuple[int, int]) -> bool:
    """True when cumulative barrier thickness along the path blocks Detect Magic."""
    if start == end:
        return False

    accumulated: dict[str, float] = {material: 0.0 for material in DETECT_MAGIC_PENETRATION_FT}
    squares = battle_map.squares_in_path(start[0], start[1], end[0], end[1], inclusive=False)
    prev = start
    for x, y in squares:
        if x < 0 or y < 0 or x >= battle_map.size[0] or y >= battle_map.size[1]:
            continue
        for material, thickness in _barrier_layers_at_square(battle_map, x, y, origin=prev):
            key = material if material in DETECT_MAGIC_PENETRATION_FT else 'stone'
            accumulated[key] = accumulated.get(key, 0.0) + thickness
            limit = DETECT_MAGIC_PENETRATION_FT[key]
            if limit <= 0 or accumulated[key] > limit + 1e-9:
                return True
        prev = (x, y)
    return False


def viewer_can_reveal_magic_at_square(battle_map, viewer, x: int, y: int) -> bool:
    """RAW: school/aura requires a visible creature or object on the square."""
    if not battle_map.can_see_square(viewer, (x, y)):
        return False
    entity = battle_map.entity_at(x, y)
    if entity is not None:
        try:
            return bool(battle_map.can_see(viewer, entity))
        except Exception:
            return False
    return True


def _viewer_senses_magic_at(battle_map, viewer, viewer_pos: tuple[int, int],
                            target: tuple[int, int], feet_per_grid: int) -> bool:
    if distance_ft(viewer_pos, target, feet_per_grid) > DETECT_MAGIC_RANGE_FT:
        return False
    return not detect_magic_path_blocked(battle_map, viewer_pos, target)


def _viewer_reveals_magic_at(battle_map, viewer, viewer_pos: tuple[int, int],
                             target: tuple[int, int], feet_per_grid: int) -> bool:
    if not _viewer_senses_magic_at(battle_map, viewer, viewer_pos, target, feet_per_grid):
        return False
    return viewer_can_reveal_magic_at_square(battle_map, viewer, target[0], target[1])


def collect_square_magical_auras(session, battle_map, x: int, y: int) -> list[dict[str, str]]:
    auras: list[dict[str, str]] = []
    map_key = resolve_map_annotation_key(session, battle_map)
    for annotation in battle_map.map_annotations_at(x, y):
        auras.extend(annotation_magical_auras(annotation))
    if map_key:
        for annotation in list_campaign_magical_annotations(session, map_key):
            from natural20.map_annotations import annotation_contains_point
            if annotation_contains_point(annotation, x, y):
                auras.extend(annotation_magical_auras(annotation))
    for obj in battle_map.objects_at(x, y):
        auras.extend(object_magical_auras(session, obj))
    entity = battle_map.entity_at(x, y)
    if entity is not None:
        auras.extend(entity_magical_auras(session, entity))
    return _merge_auras(auras)


def magical_auras_for_tile(session, battle_map, x: int, y: int, viewers) -> list[dict[str, str]]:
    active_viewers = [v for v in (viewers or []) if viewer_has_detect_magic(v)]
    if not active_viewers:
        return []

    raw_auras = collect_square_magical_auras(session, battle_map, x, y)
    if not raw_auras:
        return []

    feet_per_grid = getattr(battle_map, 'feet_per_grid', 5) or 5
    target = (int(x), int(y))
    can_sense = False
    can_reveal = False

    for viewer in active_viewers:
        for viewer_pos in battle_map.entity_squares(viewer):
            if _viewer_senses_magic_at(battle_map, viewer, viewer_pos, target, feet_per_grid):
                can_sense = True
            if _viewer_reveals_magic_at(battle_map, viewer, viewer_pos, target, feet_per_grid):
                can_reveal = True

    if not can_sense:
        return []

    if can_reveal:
        return [
            {**aura, 'revelation': 'aura'}
            for aura in raw_auras
        ]

    return [_presence_only_aura(aura) for aura in raw_auras]
