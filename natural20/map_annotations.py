"""Map landmarks — named points, rects, polygons, and object refs for NPC/LLM context."""

from __future__ import annotations

import copy
import re
from typing import Any, Iterable, Optional, Sequence, Tuple

Point = Tuple[int, int]
Bounds = dict[str, int]

_VALID_KINDS = frozenset({'point', 'area', 'polygon', 'object_ref', 'stack_opening', 'floor_mask'})
_SLUG_RE = re.compile(r'^[a-z][a-z0-9_\-]{0,63}$')


def _as_int_pair(value: Any) -> Optional[Point]:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    try:
        return int(value[0]), int(value[1])
    except (TypeError, ValueError):
        return None


def normalize_annotation_id(raw: str) -> str:
    slug = str(raw or '').strip().lower().replace(' ', '_')
    slug = re.sub(r'[^a-z0-9_\-]+', '_', slug).strip('_')
    return slug


def validate_annotation_id(annotation_id: str) -> bool:
    return bool(annotation_id and _SLUG_RE.match(annotation_id))


def normalize_annotation(raw: dict[str, Any], *, index: int = 0) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError('annotation must be a mapping')

    annotation_id = normalize_annotation_id(raw.get('id') or raw.get('name') or f'landmark_{index + 1}')
    if not validate_annotation_id(annotation_id):
        raise ValueError(f'Invalid annotation id: {annotation_id!r}')

    kind = str(raw.get('kind') or 'point').strip().lower()
    if kind not in _VALID_KINDS:
        raise ValueError(f'Unsupported annotation kind: {kind}')

    label = str(raw.get('label') or annotation_id).strip() or annotation_id
    description = str(raw.get('description') or raw.get('text') or '').strip()

    normalized: dict[str, Any] = {
        'id': annotation_id,
        'label': label,
        'kind': kind,
    }
    if description:
        normalized['description'] = description

    if raw.get('magical') is not None:
        normalized['magical'] = bool(raw.get('magical'))
    magic_school = raw.get('magic_school') or raw.get('school')
    if magic_school:
        normalized['magic_school'] = str(magic_school).strip().lower()
    aura_strength = raw.get('aura_strength') or raw.get('strength')
    if aura_strength:
        normalized['aura_strength'] = str(aura_strength).strip().lower()

    if kind == 'point':
        pos = _as_int_pair(raw.get('pos') or raw.get('position'))
        if pos is None:
            raise ValueError(f'point annotation {annotation_id} requires pos: [x, y]')
        normalized['pos'] = [pos[0], pos[1]]
    elif kind == 'area':
        bounds = raw.get('bounds') or {}
        if not isinstance(bounds, dict):
            raise ValueError(f'area annotation {annotation_id} requires bounds mapping')
        try:
            x1, y1 = int(bounds['x1']), int(bounds['y1'])
            x2, y2 = int(bounds['x2']), int(bounds['y2'])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f'area annotation {annotation_id} requires bounds x1,y1,x2,y2') from exc
        normalized['bounds'] = {
            'x1': min(x1, x2),
            'y1': min(y1, y2),
            'x2': max(x1, x2),
            'y2': max(y1, y2),
        }
    elif kind == 'polygon':
        points: list[list[int]] = []
        for entry in raw.get('points') or []:
            pair = _as_int_pair(entry)
            if pair is None:
                continue
            points.append([pair[0], pair[1]])
        if len(points) < 3:
            raise ValueError(f'polygon annotation {annotation_id} requires at least 3 points')
        normalized['points'] = points
    elif kind == 'object_ref':
        entity_uid = str(raw.get('entity_uid') or raw.get('object_uid') or '').strip()
        if not entity_uid:
            raise ValueError(f'object_ref annotation {annotation_id} requires entity_uid')
        normalized['entity_uid'] = entity_uid
    elif kind == 'stack_opening':
        stack_ref = str(raw.get('stack') or raw.get('stack_id') or '').strip()
        if stack_ref:
            normalized['stack'] = stack_ref
        shape = str(raw.get('shape') or 'point').strip().lower()
        normalized['shape'] = shape
        if shape == 'area' or raw.get('bounds'):
            bounds = raw.get('bounds') or {}
            if isinstance(bounds, dict):
                try:
                    normalized['bounds'] = {
                        'x1': int(bounds['x1']),
                        'y1': int(bounds['y1']),
                        'x2': int(bounds['x2']),
                        'y2': int(bounds['y2']),
                    }
                except (KeyError, TypeError, ValueError):
                    pass
        pos = _as_int_pair(raw.get('pos') or raw.get('position'))
        if pos is not None:
            normalized['pos'] = [pos[0], pos[1]]
        if raw.get('fall_damage'):
            normalized['fall_damage'] = str(raw.get('fall_damage'))
    elif kind == 'floor_mask':
        stack_ref = str(raw.get('stack') or raw.get('stack_id') or '').strip()
        if stack_ref:
            normalized['stack'] = stack_ref
        if raw.get('blocks_sight'):
            normalized['blocks_sight'] = str(raw.get('blocks_sight'))
        if raw.get('allows_sight'):
            normalized['allows_sight'] = str(raw.get('allows_sight'))
        shape = str(raw.get('shape') or 'area').strip().lower()
        if shape == 'polygon' and raw.get('points'):
            points: list[list[int]] = []
            for entry in raw.get('points') or []:
                pair = _as_int_pair(entry)
                if pair is not None:
                    points.append([pair[0], pair[1]])
            if len(points) >= 3:
                normalized['points'] = points
                normalized['shape'] = 'polygon'
        elif raw.get('bounds'):
            bounds = raw.get('bounds') or {}
            if isinstance(bounds, dict):
                try:
                    normalized['bounds'] = {
                        'x1': int(bounds['x1']),
                        'y1': int(bounds['y1']),
                        'x2': int(bounds['x2']),
                        'y2': int(bounds['y2']),
                    }
                except (KeyError, TypeError, ValueError):
                    pass

    return normalized


def list_map_annotations(map_properties: dict[str, Any] | None) -> list[dict[str, Any]]:
    raw = (map_properties or {}).get('map_annotations') or []
    if not isinstance(raw, list):
        return []
    items: list[dict[str, Any]] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            continue
        try:
            items.append(normalize_annotation(entry, index=index))
        except ValueError:
            continue
    return items


def annotation_by_id(map_properties: dict[str, Any] | None, annotation_id: str) -> Optional[dict[str, Any]]:
    needle = normalize_annotation_id(annotation_id)
    if not needle:
        return None
    for item in list_map_annotations(map_properties):
        if item.get('id') == needle:
            return item
    return None


def point_in_bounds(x: int, y: int, bounds: Bounds) -> bool:
    return (
        bounds.get('x1', 0) <= x <= bounds.get('x2', 0)
        and bounds.get('y1', 0) <= y <= bounds.get('y2', 0)
    )


def point_in_polygon(x: int, y: int, points: Sequence[Sequence[int]]) -> bool:
    """Ray-casting point-in-polygon test on grid coordinates."""
    vertices = [_as_int_pair(p) for p in points]
    vertices = [v for v in vertices if v is not None]
    if len(vertices) < 3:
        return False

    inside = False
    j = len(vertices) - 1
    for i, (xi, yi) in enumerate(vertices):
        xj, yj = vertices[j]
        intersects = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / float(yj - yi + 1e-9) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def annotation_contains_point(annotation: dict[str, Any], x: int, y: int) -> bool:
    kind = annotation.get('kind')
    if kind == 'point' or kind == 'stack_opening':
        pos = _as_int_pair(annotation.get('pos'))
        if pos is not None and pos == (int(x), int(y)):
            return True
        if kind == 'stack_opening' and annotation.get('bounds'):
            return point_in_bounds(int(x), int(y), annotation.get('bounds') or {})
        return False
    if kind == 'floor_mask':
        if annotation.get('points'):
            return point_in_polygon(int(x), int(y), annotation.get('points') or [])
        if annotation.get('bounds'):
            return point_in_bounds(int(x), int(y), annotation.get('bounds') or {})
        return False
    if kind == 'area':
        return point_in_bounds(int(x), int(y), annotation.get('bounds') or {})
    if kind == 'polygon':
        return point_in_polygon(int(x), int(y), annotation.get('points') or [])
    return False


def annotation_centroid(annotation: dict[str, Any]) -> Optional[Point]:
    kind = annotation.get('kind')
    if kind == 'point':
        return _as_int_pair(annotation.get('pos'))
    if kind == 'area':
        bounds = annotation.get('bounds') or {}
        try:
            return (
                int((int(bounds['x1']) + int(bounds['x2'])) / 2),
                int((int(bounds['y1']) + int(bounds['y2'])) / 2),
            )
        except (KeyError, TypeError, ValueError):
            return None
    if kind == 'polygon':
        points = annotation.get('points') or []
        if not points:
            return None
        xs = [int(p[0]) for p in points]
        ys = [int(p[1]) for p in points]
        return int(sum(xs) / len(xs)), int(sum(ys) / len(ys))
    return None


def annotation_anchor_square(annotation: dict[str, Any], battle_map=None) -> Optional[Point]:
    """Return a grid square NPCs should path toward for this landmark."""
    kind = annotation.get('kind')
    if kind == 'object_ref' and battle_map is not None:
        uid = annotation.get('entity_uid')
        if not uid:
            return None
        obj = battle_map.object_by_uid(uid) or battle_map.entity_by_uid(uid)
        if obj is None:
            return None
        try:
            return tuple(battle_map.entity_or_object_pos(obj))
        except Exception:
            return None
    return annotation_centroid(annotation)


def annotations_at_position(map_properties: dict[str, Any] | None, x: int, y: int) -> list[dict[str, Any]]:
    return [
        item
        for item in list_map_annotations(map_properties)
        if annotation_contains_point(item, int(x), int(y))
    ]


def format_annotation_for_llm(annotation: dict[str, Any], *, include_description: bool = True) -> str:
    label = annotation.get('label') or annotation.get('id')
    parts = [f"{label} (@{annotation.get('id')})"]
    if include_description and annotation.get('description'):
        parts.append(str(annotation['description']))
    kind = annotation.get('kind')
    if kind == 'point':
        pos = annotation.get('pos')
        if pos:
            parts.append(f"grid {pos[0]},{pos[1]}")
    elif kind == 'area':
        bounds = annotation.get('bounds') or {}
        parts.append(
            f"area ({bounds.get('x1')},{bounds.get('y1')})-({bounds.get('x2')},{bounds.get('y2')})"
        )
    elif kind == 'polygon':
        pts = annotation.get('points') or []
        parts.append(f"polygon ({len(pts)} vertices)")
    elif kind == 'object_ref':
        parts.append(f"object {annotation.get('entity_uid')}")
    return ' — '.join(parts)


def format_annotations_block(annotations: Iterable[dict[str, Any]]) -> str:
    lines = [format_annotation_for_llm(item) for item in annotations]
    return '\n'.join(f"- {line}" for line in lines if line)


def upsert_map_annotation(
    data: dict[str, Any],
    annotation: dict[str, Any],
) -> dict[str, Any]:
    payload = copy.deepcopy(data)
    normalized = normalize_annotation(annotation, index=0)
    entries = payload.setdefault('map_annotations', [])
    if not isinstance(entries, list):
        entries = []
        payload['map_annotations'] = entries

    replaced = False
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        existing_id = normalize_annotation_id(entry.get('id') or entry.get('name') or '')
        if existing_id == normalized['id']:
            entries[index] = normalized
            replaced = True
            break
    if not replaced:
        entries.append(normalized)
    return payload


def annotation_label_anchor(annotation: dict[str, Any]) -> Optional[Point]:
    """Grid square where the edit UI label is anchored (drag origin)."""
    kind = annotation.get('kind')
    if kind == 'point':
        return _as_int_pair(annotation.get('pos'))
    if kind == 'area':
        bounds = annotation.get('bounds') or {}
        try:
            return int(bounds['x1']), int(bounds['y1'])
        except (KeyError, TypeError, ValueError):
            return None
    if kind == 'polygon':
        points = annotation.get('points') or []
        if not points:
            return None
        return _as_int_pair(points[0])
    return None


def translate_annotation(annotation: dict[str, Any], dx: int, dy: int) -> dict[str, Any]:
    """Return a copy of the annotation shifted by (dx, dy) grid squares."""
    if dx == 0 and dy == 0:
        return copy.deepcopy(annotation)

    moved = copy.deepcopy(annotation)
    kind = moved.get('kind')
    if kind == 'point':
        pos = _as_int_pair(moved.get('pos'))
        if pos is None:
            raise ValueError('point annotation missing pos')
        moved['pos'] = [pos[0] + dx, pos[1] + dy]
    elif kind == 'area':
        bounds = moved.get('bounds') or {}
        moved['bounds'] = {
            'x1': int(bounds['x1']) + dx,
            'y1': int(bounds['y1']) + dy,
            'x2': int(bounds['x2']) + dx,
            'y2': int(bounds['y2']) + dy,
        }
    elif kind == 'polygon':
        points = moved.get('points') or []
        moved['points'] = [[int(p[0]) + dx, int(p[1]) + dy] for p in points]
    elif kind == 'object_ref':
        raise ValueError('object_ref landmarks cannot be moved; move the referenced object instead')
    else:
        raise ValueError(f'Unsupported annotation kind for move: {kind}')
    return moved


def delete_map_annotation(data: dict[str, Any], annotation_id: str) -> dict[str, Any]:
    payload = copy.deepcopy(data)
    needle = normalize_annotation_id(annotation_id)
    entries = payload.get('map_annotations') or []
    if not isinstance(entries, list):
        entries = []
    payload['map_annotations'] = [
        entry
        for entry in entries
        if isinstance(entry, dict)
        and normalize_annotation_id(entry.get('id') or entry.get('name') or '') != needle
    ]
    return payload
