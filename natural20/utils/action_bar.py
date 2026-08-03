"""Helpers for grouping actions into action-bar tabs."""

from __future__ import annotations

import inspect
import json
import re
from typing import Any, Iterable, Sequence

# Action types surfaced on the default Common tab when no character override exists.
DEFAULT_COMMON_ACTION_TYPES = frozenset({
    'attack',
    'offhand_attack',
    'dash',
    'dash_bonus',
    'disengage',
    'disengage_bonus',
    'dodge',
    'help',
    'hide',
    'hide_bonus',
})

TAB_COMMON = 'common'
TAB_ACTIONS = 'actions'
TAB_SPELLS = 'spells'
TAB_ITEMS = 'items'
TAB_INTERACT = 'interact'
TAB_UTILITY = 'utility'

DEFAULT_TAB_ORDER = (
    TAB_COMMON,
    TAB_ACTIONS,
    TAB_SPELLS,
    TAB_ITEMS,
    TAB_INTERACT,
    TAB_UTILITY,
)


def _action_class_name(action: Any) -> str:
    return action.__class__.__name__


def action_favorite_key(action: Any) -> str:
    """Stable key used for YAML favorites and user pins."""
    cls_name = _action_class_name(action)
    if cls_name == 'SpellAction':
        spell = getattr(action, 'spell', None) or {}
        if isinstance(spell, dict):
            return str(spell.get('id') or spell.get('name') or getattr(action, 'spell_class', '') or 'spell')
        return str(getattr(action, 'spell_class', None) or 'spell')
    if cls_name == 'UseItemAction':
        item = getattr(action, 'target_item', None) or {}
        if isinstance(item, dict):
            return str(item.get('name') or item.get('image') or 'use_item')
        return 'use_item'
    if cls_name == 'AttackAction':
        using = getattr(action, 'using', None)
        if using:
            return f'attack:{using}'
        return 'attack'
    return str(getattr(action, 'action_type', cls_name) or cls_name)


def action_bar_tab_for(action: Any, *, common_types: Iterable[str] | None = None) -> str:
    """Return the tab id an action belongs to by default."""
    cls_name = _action_class_name(action)
    if cls_name == 'SpellAction':
        return TAB_SPELLS
    if cls_name == 'UseItemAction':
        return TAB_ITEMS
    if cls_name == 'InteractAction':
        return TAB_INTERACT
    action_type = str(getattr(action, 'action_type', '') or '')
    common = set(common_types or DEFAULT_COMMON_ACTION_TYPES)
    if cls_name == 'AttackAction' or action_type in common:
        return TAB_COMMON
    return TAB_ACTIONS


def is_favorite_action(action: Any, favorites: Sequence[str] | None) -> bool:
    if not favorites:
        return False
    fav_set = {str(item) for item in favorites}
    key = action_favorite_key(action)
    if key in fav_set:
        return True
    action_type = str(getattr(action, 'action_type', '') or '')
    return action_type in fav_set


def partition_standard_actions(
    actions: Sequence[Any],
    *,
    favorites: Sequence[str] | None = None,
    common_types: Iterable[str] | None = None,
) -> tuple[list[Any], list[Any]]:
    """Split standard (non-spell/item/interact) actions into common vs other tabs."""
    common: list[Any] = []
    other: list[Any] = []
    for action in actions:
        if is_favorite_action(action, favorites) or action_bar_tab_for(action, common_types=common_types) == TAB_COMMON:
            common.append(action)
        else:
            other.append(action)
    return common, other


def action_descriptor(action: Any) -> str:
    """Descriptor shared with the web UI for hotkeys and user pins."""
    cls_name = _action_class_name(action)
    opts = action.to_h() if hasattr(action, 'to_h') else {}
    label = ''
    if hasattr(action, 'label'):
        try:
            label = str(action.label() or '')
        except Exception:
            label = ''
    return f"action|{cls_name}|{json.dumps(opts, sort_keys=True, default=str)}|{label}"


def spell_descriptor(spell_name: str, at_level: int) -> str:
    opts = {'spell': spell_name, 'at_level': at_level}
    return f"action|SpellAction|{json.dumps(opts, sort_keys=True)}|{spell_name}"


def item_descriptor(item: dict[str, Any]) -> str:
    name = str(item.get('name') or item.get('image') or 'item')
    return f"action|UseItemAction|{json.dumps(item, sort_keys=True, default=str)}|{item.get('label', name)}"


def resolve_action_bar_config(entity: Any, game_config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Merge game-level and per-character action bar settings."""
    game_config = game_config or {}
    game_bar = game_config.get('action_bar') or {}
    char_bar = {}
    if hasattr(entity, 'properties') and isinstance(entity.properties, dict):
        char_bar = entity.properties.get('action_bar') or {}

    favorites = list(char_bar.get('favorites') or game_bar.get('favorites') or [])
    common_types = char_bar.get('common_action_types') or game_bar.get('common_action_types') or list(DEFAULT_COMMON_ACTION_TYPES)
    default_tab = char_bar.get('default_tab') or game_bar.get('default_tab') or TAB_COMMON
    tab_order = char_bar.get('tab_order') or game_bar.get('tab_order') or list(DEFAULT_TAB_ORDER)

    return {
        'favorites': favorites,
        'common_action_types': list(common_types),
        'default_tab': default_tab,
        'tab_order': list(tab_order),
    }


def entity_class_level_for_spells(entity: Any) -> list[tuple[str, int]]:
    if hasattr(entity, 'class_and_level'):
        rows = entity.class_and_level()
        if rows:
            return list(rows)
    spell_slots = getattr(entity, 'spell_slots', {}) or {}
    level = 1
    if hasattr(entity, 'level'):
        try:
            level = int(entity.level())
        except TypeError:
            level = int(entity.level)
    return [(klass, level) for klass in spell_slots.keys()]


def spell_level_label(level: int) -> str:
    if level <= 0:
        return 'Cantrips'
    labels = {
        1: '1st Level',
        2: '2nd Level',
        3: '3rd Level',
        4: '4th Level',
        5: '5th Level',
        6: '6th Level',
        7: '7th Level',
        8: '8th Level',
        9: '9th Level',
    }
    return labels.get(level, f'Level {level}')


def _spell_cast_classes(entity: Any, spell_details: dict[str, Any]) -> list[str]:
    classes = spell_details.get('spell_list_classes') or []
    result: list[str] = []
    spell_slots = getattr(entity, 'spell_slots', {}) or {}
    for class_name in classes:
        key = str(class_name).lower()
        if key in spell_slots:
            result.append(key)
    if not result and spell_slots:
        result = list(spell_slots.keys())
    return result


def available_upcast_levels(entity: Any, base_level: int, character_class: str) -> list[int]:
    if base_level <= 0:
        return [0]
    slots = getattr(entity, 'spell_slots', {}).get(character_class, {}) or {}
    if not slots:
        return [base_level]
    max_slot = max(slots.keys())
    return [lvl for lvl in range(base_level, max_slot + 1) if slots.get(lvl, 0) > 0]


def _explicit_yaml_upcast(spell_details: dict[str, Any]) -> bool | None:
    """Return declared upcast metadata when the spell YAML specifies it."""
    if 'upcast' in spell_details:
        return bool(spell_details['upcast'])
    if 'scales_with_slot' in spell_details:
        return bool(spell_details['scales_with_slot'])
    if spell_details.get('higher_level'):
        return True
    return None


def spell_class_scales_with_slot(spell_name: str, spell_details: dict[str, Any]) -> bool:
    """Detect slot scaling from the spell's Python implementation."""
    try:
        from natural20.spell.extensions.damage_scaling import DamageScalingMixin
        from natural20.utils.spell_loader import load_spell_class, resolve_spell_class_key

        cls = load_spell_class(resolve_spell_class_key(spell_name, spell_details))
    except Exception:
        return False

    explicit = getattr(cls, 'SCALES_WITH_SLOT', None)
    if explicit is not None:
        return bool(explicit)

    if issubclass(cls, DamageScalingMixin):
        per_slot = str(getattr(cls, 'PER_SLOT_DAMAGE', '') or '').strip().lower()
        if per_slot:
            return not bool(re.fullmatch(r'0d\d+', per_slot))
        if hasattr(cls, '_damage'):
            try:
                src = inspect.getsource(cls._damage)
            except (OSError, TypeError):
                src = ''
            for match in re.finditer(r'_scaled_damage_roll\([^)]+\)', src, re.DOTALL):
                dice_exprs = re.findall(r'["\'](\d*d\d+)["\']', match.group(0))
                if len(dice_exprs) >= 2 and not re.fullmatch(r'0d\d+', dice_exprs[1].lower()):
                    return True
        return False

    scaling_patterns = (
        r'additional_targets',
        r'max\(0,\s*(?:cast_level|at_level|int\(at_level)',
        r'rays\s*=',
        r'dice_count\s*=.*at_level',
        r'if\s+.*at_level\s*>\s*1',
        r'level\s*\+=\s*.*at_level',
        r'dmg_level\s*\+=',
        r'dice\s*=\s*2\s*\+\s*max',
    )
    for method_name in ('build_map', '_pool_roll', '_melee_bonus_dice', 'resolve'):
        method = getattr(cls, method_name, None)
        if method is None:
            continue
        try:
            src = inspect.getsource(method)
        except (OSError, TypeError):
            continue
        if any(re.search(pattern, src) for pattern in scaling_patterns):
            return True
    return False


def spell_scales_with_slot(spell_details: dict[str, Any], spell_name: str | None = None) -> bool:
    """True when casting in a higher slot materially changes the spell.

    Resolution order:
    1. Explicit YAML ``upcast`` / ``scales_with_slot`` / legacy ``higher_level``
    2. SRD description markers (``At Higher Levels``, etc.)
    3. Spell Python class introspection (fallback for missing metadata)
    """
    explicit = _explicit_yaml_upcast(spell_details)
    if explicit is not None:
        return explicit

    desc = str(spell_details.get('description') or '').lower()
    scaling_markers = (
        'at higher levels',
        'at higher levels:',
        'higher level slot',
        'each slot level above',
        'slot level above',
        'slot levels above',
    )
    if any(marker in desc for marker in scaling_markers):
        return True

    if spell_name:
        return spell_class_scales_with_slot(spell_name, spell_details)
    return False


def effective_cast_levels(
    entity: Any,
    base_level: int,
    character_class: str,
    *,
    scales_with_slot: bool,
) -> list[int]:
    """Slot levels worth offering for this spell right now."""
    available = available_upcast_levels(entity, base_level, character_class)
    if base_level <= 0:
        return [0] if 0 in available else available[:1]

    if scales_with_slot:
        return available

    slots = getattr(entity, 'spell_slots', {}).get(character_class, {}) or {}
    if slots.get(base_level, 0) > 0:
        return [base_level]

    higher = [lvl for lvl in available if lvl > base_level]
    if higher:
        return higher

    return available[:1] if available else [base_level]


def build_cast_options_for_spell(
    entity: Any,
    spell_details: dict[str, Any],
    *,
    spell_name: str | None = None,
) -> list[dict[str, Any]]:
    base_level = int(spell_details.get('level', 0))
    scales = spell_scales_with_slot(spell_details, spell_name)
    cast_options: list[dict[str, Any]] = []
    seen_levels: set[int] = set()

    for klass in _spell_cast_classes(entity, spell_details):
        for at_level in effective_cast_levels(
            entity, base_level, klass, scales_with_slot=scales,
        ):
            if at_level in seen_levels:
                continue
            seen_levels.add(at_level)
            cast_options.append({
                'at_level': at_level,
                'class': klass,
                'is_upcast': at_level > base_level,
                'label': spell_level_label(at_level) if at_level > 0 else 'Cantrip',
            })

    cast_options.sort(key=lambda row: row['at_level'])
    if not cast_options:
        cast_options = [{
            'at_level': base_level,
            'class': None,
            'is_upcast': False,
            'label': spell_level_label(base_level),
        }]
    return cast_options


def build_spell_tab_groups(entity: Any, castable_spells_by_level: dict[int, list[str]]) -> list[dict[str, Any]]:
    """Structured spell rows for the action bar Spells tab (with upcast options)."""
    if not castable_spells_by_level:
        return []

    class_levels = entity_class_level_for_spells(entity)
    groups: list[dict[str, Any]] = []

    for level in sorted(castable_spells_by_level.keys()):
        spell_names = castable_spells_by_level[level]
        if not spell_names:
            continue

        slot_rows: list[dict[str, Any]] = []
        if level > 0:
            for klass, _klass_level in class_levels:
                if not hasattr(entity, 'max_spell_slots'):
                    continue
                max_slots = entity.max_spell_slots(level, klass)
                if max_slots <= 0:
                    continue
                slot_rows.append({
                    'class': klass,
                    'class_label': str(klass).replace('_', ' ').title(),
                    'current': entity.spell_slots_count(level, klass),
                    'max': max_slots,
                })

        spell_entries: list[dict[str, Any]] = []
        for spell_name in spell_names:
            details = entity.session.load_spell(spell_name)
            base_level = int(details.get('level', level))
            cast_options = build_cast_options_for_spell(
                entity, details, spell_name=spell_name,
            )

            spell_entries.append({
                'name': spell_name,
                'base_level': base_level,
                'label': spell_name.replace('_', ' ').title(),
                'cast_options': cast_options,
                'scales_with_slot': spell_scales_with_slot(details, spell_name),
            })

        groups.append({
            'level': level,
            'label': spell_level_label(level),
            'slots': slot_rows,
            'spells': spell_entries,
        })

    return groups


def filter_spell_tab_groups(groups: Sequence[dict[str, Any]], favorites: Sequence[str] | None) -> list[dict[str, Any]]:
    if not favorites:
        return []
    fav_set = {str(item) for item in favorites}
    filtered: list[dict[str, Any]] = []
    for group in groups:
        spells = [spell for spell in group.get('spells', []) if spell.get('name') in fav_set]
        if not spells:
            continue
        copied = dict(group)
        copied['spells'] = [
            {
                **spell,
                # Favorites on the Common tab always use the default cast level.
                'cast_options': spell.get('cast_options', [])[:1],
            }
            for spell in spells
        ]
        filtered.append(copied)
    return filtered
