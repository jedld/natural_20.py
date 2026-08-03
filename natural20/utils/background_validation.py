"""Background validation and PC application helpers for character creation."""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, MutableMapping, Sequence


def _normalize_list(values: Iterable[Any] | None) -> list[str]:
    if not values:
        return []
    return [str(v).strip() for v in values if str(v or '').strip()]


def background_skill_choice_count(background_def: Mapping[str, Any] | None) -> int:
    if not background_def:
        return 0
    return int(background_def.get('skill_choice_count', 0) or 0)


def background_skills_pool(background_def: Mapping[str, Any] | None) -> list[str]:
    if not background_def:
        return []
    return _normalize_list(background_def.get('skills_pool'))


def validate_background_skill_selections(
    background_def: Mapping[str, Any] | None,
    selections: Sequence[str] | None,
) -> tuple[bool, str | None]:
    """Validate pick-N skill choices from a background skills pool."""
    selections = _normalize_list(selections)
    if not background_def:
        if selections:
            return False, 'Unexpected background skill choices'
        return True, None

    choice_count = background_skill_choice_count(background_def)
    fixed = _normalize_list(background_def.get('skill_proficiencies'))
    if choice_count <= 0:
        if selections:
            return False, 'Unexpected background skill choices'
        return True, None

    pool = set(background_skills_pool(background_def))
    if len(pool) < choice_count:
        return False, 'Not enough background skill options for this background.'
    if len(selections) != choice_count:
        plural = '' if choice_count == 1 else 's'
        return False, f'Choose {choice_count} background skill{plural}.'
    if not all(sel in pool for sel in selections):
        return False, 'Invalid background skill choices'
    if fixed and any(sel in fixed for sel in selections):
        return False, 'Background skill choices overlap fixed proficiencies'
    return True, None


def _combined_language_pool(background_def: Mapping[str, Any]) -> list[str]:
    standard = _normalize_list(background_def.get('languages_pool'))
    exotic = _normalize_list(background_def.get('exotic_languages_pool'))
    combined: list[str] = []
    seen: set[str] = set()
    for lang in standard + exotic:
        key = lang.lower()
        if key in seen:
            continue
        seen.add(key)
        combined.append(lang)
    return combined


def validate_background_language_selections(
    background_def: Mapping[str, Any] | None,
    selections: Sequence[str] | None,
    *,
    granted_languages: Sequence[str] | None = None,
) -> tuple[bool, str | None]:
    """Validate background language picks, including exotic-language minimums."""
    selections = _normalize_list(selections)
    granted = {str(g).lower() for g in (granted_languages or []) if str(g or '').strip()}

    if not background_def:
        if selections:
            return False, 'Unexpected background language choices'
        return True, None

    choice_count = int(background_def.get('language_choice_count', 0) or 0)
    if choice_count <= 0:
        if selections:
            return False, 'Unexpected background language choices'
        return True, None

    pool = _combined_language_pool(background_def)
    pool_set = {p.lower() for p in pool}
    available = [p for p in pool if p.lower() not in granted]
    if len(available) < choice_count:
        return False, 'Not enough background language options for this race/background combination.'
    if len(selections) != choice_count:
        plural = '' if choice_count == 1 else 's'
        return False, f'Choose {choice_count} background language{plural}.'
    if not all(sel.lower() in pool_set for sel in selections):
        return False, 'Invalid background language choices'

    exotic_min = int(background_def.get('exotic_language_min', 0) or 0)
    exotic_pool = {p.lower() for p in _normalize_list(background_def.get('exotic_languages_pool'))}
    if exotic_min > 0 and exotic_pool:
        exotic_selected = sum(1 for sel in selections if sel.lower() in exotic_pool)
        if exotic_selected < exotic_min:
            plural = '' if exotic_min == 1 else 's'
            return False, f'Choose at least {exotic_min} exotic language{plural}.'

    return True, None


_CURRENCY_RE = re.compile(r'^(\d+)_(gp|sp|cp|pp)$')


def parse_background_equipment_entry(entry: Any) -> dict[str, Any] | None:
    """Parse a background equipment YAML entry into an inventory row."""
    if entry is None:
        return None
    text = str(entry).strip()
    if not text:
        return None
    match = _CURRENCY_RE.match(text)
    if match:
        qty, unit = match.groups()
        item = {
            'gp': 'gold_piece',
            'sp': 'silver_piece',
            'cp': 'copper_piece',
            'pp': 'platinum_piece',
        }.get(unit, 'gold_piece')
        return {'item': item, 'qty': int(qty)}
    return {'item': text, 'qty': 1}


def apply_background_proficiencies(
    pc: MutableMapping[str, Any],
    background_def: Mapping[str, Any],
    *,
    skill_selections: Sequence[str] | None = None,
    language_selections: Sequence[str] | None = None,
) -> None:
    """Merge background skills, tools, and languages onto a PC dict."""
    for skill in _normalize_list(background_def.get('skill_proficiencies')):
        pc.setdefault('skills', [])
        if skill not in pc['skills']:
            pc['skills'].append(skill)
    for skill in _normalize_list(skill_selections):
        pc.setdefault('skills', [])
        if skill not in pc['skills']:
            pc['skills'].append(skill)
    for tool in _normalize_list(background_def.get('tool_proficiencies')):
        pc.setdefault('tool_proficiencies', [])
        if tool not in pc['tool_proficiencies']:
            pc['tool_proficiencies'].append(tool)
    for lang in _normalize_list(background_def.get('languages')):
        if lang.lower() == 'none':
            continue
        pc.setdefault('languages', [])
        if lang not in pc['languages']:
            pc['languages'].append(lang)
    for lang in _normalize_list(language_selections):
        pc.setdefault('languages', [])
        if lang not in pc['languages']:
            pc['languages'].append(lang)
    if pc.get('languages'):
        pc['languages'] = list(dict.fromkeys(pc['languages']))


def apply_background_starting_equipment(
    pc: MutableMapping[str, Any],
    background_def: Mapping[str, Any],
) -> None:
    """Append background equipment entries (items and currency) to inventory."""
    for entry in background_def.get('equipment') or []:
        row = parse_background_equipment_entry(entry)
        if row is None:
            continue
        pc.setdefault('inventory', []).append(row)
