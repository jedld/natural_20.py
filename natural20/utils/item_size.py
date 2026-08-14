"""Creature/item size categories for container limits and corpse carrying."""

from __future__ import annotations

from typing import Any, Optional

SIZE_ORDER = ('tiny', 'small', 'medium', 'large', 'huge', 'gargantuan')

# Typical unladen body weight by size category (lbs). Used when YAML has no weight.
DEFAULT_CREATURE_WEIGHT_LBS = {
    'tiny': 8.0,
    'small': 40.0,
    'medium': 180.0,
    'large': 800.0,
    'huge': 2500.0,
    'gargantuan': 20000.0,
}

_WEAPON_TYPES = {'weapon', 'melee_attack', 'ranged_attack'}
_BULKY_TYPES = {'weapon', 'armor', 'shield', 'melee_attack', 'ranged_attack'}


def normalize_size(value: Any, default: str = 'tiny') -> str:
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in SIZE_ORDER:
        return text
    return default


def size_rank(value: Any, default: str = 'tiny') -> int:
    size = normalize_size(value, default=default)
    try:
        return SIZE_ORDER.index(size)
    except ValueError:
        return SIZE_ORDER.index(default)


def size_allows(item_size: Any, max_item_size: Any) -> bool:
    """True when *item_size* is at most *max_item_size*."""
    if max_item_size is None:
        return True
    return size_rank(item_size) <= size_rank(max_item_size, default='small')


def default_item_size(definition: Optional[dict]) -> str:
    if not definition:
        return 'tiny'
    explicit = definition.get('size')
    if explicit:
        return normalize_size(explicit)
    typ = str(definition.get('type') or '').lower()
    subtype = str(definition.get('subtype') or '').lower()
    if typ in _BULKY_TYPES or subtype in _WEAPON_TYPES:
        return 'small'
    return 'tiny'


def default_container_max_item_size(definition: Optional[dict]) -> str:
    """Largest size a YAML container item will accept.

    Backpacks and similar mundane packs default to **small** (medium or larger
    bodies/items do not fit). Extradimensional bags default to **large**.
    """
    if not definition:
        return 'small'
    explicit = definition.get('max_item_size', definition.get('capacity_size'))
    if explicit:
        return normalize_size(explicit, default='small')
    if definition.get('extradimensional') or definition.get('extradimensional_space'):
        return 'large'
    return 'small'


def resolve_item_size(item_name: Any, session=None, entry: Optional[dict] = None, definition: Optional[dict] = None) -> str:
    if isinstance(entry, dict) and entry.get('size'):
        return normalize_size(entry.get('size'))
    if definition is None and session is not None and item_name:
        try:
            definition = session.load_thing(item_name) or {}
        except Exception:
            definition = {}
    if isinstance(definition, dict) and definition.get('size'):
        return normalize_size(definition.get('size'))
    return default_item_size(definition if isinstance(definition, dict) else None)


def creature_body_weight_lbs(entity) -> float:
    """Unladen body weight for a creature (inventory counted separately)."""
    props = getattr(entity, 'properties', None) or {}
    raw = props.get('weight', props.get('weight_lbs'))
    if raw is not None:
        try:
            return max(0.0, float(raw))
        except (TypeError, ValueError):
            pass
    size = 'medium'
    size_fn = getattr(entity, 'size', None)
    if callable(size_fn):
        try:
            size = normalize_size(size_fn(), default='medium')
        except Exception:
            size = normalize_size(props.get('size'), default='medium')
    else:
        size = normalize_size(props.get('size'), default='medium')
    return float(DEFAULT_CREATURE_WEIGHT_LBS.get(size, 180.0))
