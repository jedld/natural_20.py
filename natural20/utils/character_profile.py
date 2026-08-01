"""D&D 5e player character profile fields (personality, characteristics, alignment).

Supports YAML storage aligned with D&D Beyond import/export, DMG/PHB random tables,
and LLM context for controller-owned PCs. NPC perception continues to use
``outward_appearance`` via ``natural20.utils.outward_appearance``.
"""

from __future__ import annotations

import random
import re
from pathlib import Path
from typing import Any, Dict, Mapping, MutableMapping, Optional, Sequence

import yaml

# Top-level YAML keys (D&D Beyond compatible where noted).
PROFILE_TEXT_FIELDS = (
    'alignment',
    'gender',
    'faith',
    'age',
    'hair',
    'eyes',
    'skin',
    'height',
    'weight',
    'size',
    'personality_traits',
    'ideals',
    'bonds',
    'flaws',
    'backstory',
    'outward_appearance',
)

PERSONALITY_FIELDS = ('personality_traits', 'ideals', 'bonds', 'flaws')
PHYSICAL_FIELDS = ('eyes', 'hair', 'skin', 'age', 'height', 'weight', 'faith')
SIZE_CATEGORIES = ('tiny', 'small', 'medium', 'large', 'huge')

ALIGNMENT_OPTIONS = (
    'lawful_good',
    'neutral_good',
    'chaotic_good',
    'lawful_neutral',
    'true_neutral',
    'chaotic_neutral',
    'lawful_evil',
    'neutral_evil',
    'chaotic_evil',
)

_TABLES_CACHE: Optional[Dict[str, Any]] = None


def _templates_root() -> Path:
    here = Path(__file__).resolve().parent.parent.parent
    return here / 'templates'


def load_profile_tables(*, templates_root: Optional[Path] = None) -> Dict[str, Any]:
    global _TABLES_CACHE
    if _TABLES_CACHE is not None and templates_root is None:
        return _TABLES_CACHE
    root = templates_root or _templates_root()
    path = root / 'character_profile_tables.yml'
    if not path.is_file():
        return {}
    with open(path, 'r', encoding='utf-8') as fh:
        data = yaml.safe_load(fh) or {}
    if templates_root is None:
        _TABLES_CACHE = data
    return data


def _clean_text(value: Any) -> str:
    if value is None:
        return ''
    return str(value).strip()


def _nested_characteristics(props: Mapping[str, Any]) -> Dict[str, str]:
    nested = props.get('characteristics')
    if not isinstance(nested, dict):
        return {}
    return {k: _clean_text(v) for k, v in nested.items() if _clean_text(v)}


def extract_profile(props: Optional[Mapping[str, Any]]) -> Dict[str, str]:
    """Read normalized profile fields from entity properties or PC YAML dict."""
    props = props or {}
    nested = _nested_characteristics(props)
    profile: Dict[str, str] = {}
    for key in PROFILE_TEXT_FIELDS:
        if key in props and _clean_text(props.get(key)):
            profile[key] = _clean_text(props.get(key))
        elif key in nested and _clean_text(nested.get(key)):
            profile[key] = _clean_text(nested.get(key))
    return profile


def merge_profile_into_mapping(
    target: MutableMapping[str, Any],
    profile: Mapping[str, Any],
    *,
    clear_empty: bool = True,
) -> None:
    """Apply profile fields onto a PC YAML dict or entity properties mapping."""
    for key in PROFILE_TEXT_FIELDS:
        value = _clean_text(profile.get(key))
        if value:
            target[key] = value
        elif clear_empty and key in target:
            target.pop(key, None)
    # Drop legacy nested block when using flat storage.
    if clear_empty and 'characteristics' in target:
        target.pop('characteristics', None)


def profile_from_form(form: Mapping[str, Any]) -> Dict[str, str]:
    """Parse profile fields from a Flask ``request.form``-like mapping."""
    profile: Dict[str, str] = {}
    for key in PROFILE_TEXT_FIELDS:
        if key not in form:
            continue
        value = _clean_text(form.get(key))
        if value:
            profile[key] = value
    return profile


def default_size_for_race(race_def: Optional[Mapping[str, Any]]) -> str:
    if not race_def:
        return 'medium'
    size = _clean_text(race_def.get('size')).lower()
    return size if size in SIZE_CATEGORIES else 'medium'


def resolve_size(
    props: Optional[Mapping[str, Any]],
    race_def: Optional[Mapping[str, Any]] = None,
) -> str:
    props = props or {}
    override = _clean_text(props.get('size')).lower()
    if override in SIZE_CATEGORIES:
        return override
    nested = _nested_characteristics(props)
    nested_size = _clean_text(nested.get('size')).lower()
    if nested_size in SIZE_CATEGORIES:
        return nested_size
    return default_size_for_race(race_def)


def _roll_dice(expr: str, rng: random.Random) -> int:
    expr = str(expr or '').strip().lower()
    match = re.fullmatch(r'(\d+)d(\d+)', expr)
    if not match:
        return 0
    count, sides = int(match.group(1)), int(match.group(2))
    return sum(rng.randint(1, sides) for _ in range(count))


def _format_height(inches: int) -> str:
    feet, inch = divmod(max(0, int(inches)), 12)
    return f"{feet}'{inch}\""


def _random_physical(
    tables: Mapping[str, Any],
    *,
    size: str,
    rng: random.Random,
) -> Dict[str, str]:
    physical = tables.get('physical') or {}
    size_bases = (tables.get('size_bases') or {}).get(size) or (tables.get('size_bases') or {}).get('medium') or {}
    height_base = int(size_bases.get('height_base_in') or 56)
    height_bonus = _roll_dice(str(size_bases.get('height_dice') or '2d10'), rng)
    height_in = height_base + height_bonus
    weight_base = int(size_bases.get('weight_base_lb') or 110)
    weight_bonus = _roll_dice(str(size_bases.get('weight_dice') or '2d4'), rng)
    weight_lb = weight_base + weight_bonus * max(1, height_bonus // 4 or 1)

    def pick(key: str) -> str:
        options = physical.get(key) or []
        if not options:
            return ''
        return str(rng.choice(list(options)))

    age_roll = rng.randint(15, 60) if size in ('small', 'medium') else rng.randint(20, 200)
    return {
        'eyes': pick('eyes'),
        'hair': pick('hair'),
        'skin': pick('skin'),
        'faith': pick('faith'),
        'gender': pick('genders'),
        'height': _format_height(height_in),
        'weight': f'{weight_lb} lb',
        'age': str(age_roll),
    }


def _background_tables(tables: Mapping[str, Any], background: str) -> Dict[str, Sequence[str]]:
    backgrounds = tables.get('backgrounds') or {}
    bg = backgrounds.get(background) or {}
    default = tables.get('default') or {}
    merged: Dict[str, Sequence[str]] = {}
    for key in PERSONALITY_FIELDS:
        options = bg.get(key) or default.get(key) or []
        merged[key] = list(options)
    return merged


def randomize_profile(
    *,
    background: str = '',
    race_def: Optional[Mapping[str, Any]] = None,
    size: Optional[str] = None,
    include_personality: bool = True,
    include_physical: bool = True,
    include_alignment: bool = True,
    rng: Optional[random.Random] = None,
    templates_root: Optional[Path] = None,
) -> Dict[str, str]:
    """Roll PHB/DMG-style profile fields for character creation."""
    rng = rng or random.Random()
    tables = load_profile_tables(templates_root=templates_root)
    resolved_size = (size or default_size_for_race(race_def)).lower()
    if resolved_size not in SIZE_CATEGORIES:
        resolved_size = 'medium'

    profile: Dict[str, str] = {'size': resolved_size}
    if include_physical:
        profile.update(_random_physical(tables, size=resolved_size, rng=rng))
    if include_personality:
        bg_tables = _background_tables(tables, background)
        for key in PERSONALITY_FIELDS:
            options = bg_tables.get(key) or []
            if options:
                profile[key] = str(rng.choice(list(options)))
    if include_alignment:
        profile['alignment'] = str(rng.choice(ALIGNMENT_OPTIONS))
    return profile


def format_profile_for_llm(profile: Mapping[str, str], *, max_field_chars: int = 400) -> str:
    """Compact multi-line summary for LLM combat / conversation prompts."""
    if not profile:
        return ''

    def clip(text: str) -> str:
        text = _clean_text(text)
        if len(text) <= max_field_chars:
            return text
        return text[: max_field_chars - 3].rsplit(' ', 1)[0] + '...'

    labels = {
        'alignment': 'Alignment',
        'gender': 'Gender',
        'faith': 'Faith',
        'age': 'Age',
        'hair': 'Hair',
        'eyes': 'Eyes',
        'skin': 'Skin',
        'height': 'Height',
        'weight': 'Weight',
        'size': 'Size',
        'personality_traits': 'Personality traits',
        'ideals': 'Ideals',
        'bonds': 'Bonds',
        'flaws': 'Flaws',
        'backstory': 'Backstory',
    }
    lines = []
    for key, label in labels.items():
        value = clip(profile.get(key, ''))
        if value:
            lines.append(f'{label}: {value}')
    return '\n'.join(lines)


def profile_for_entity(entity, *, race_def: Optional[Mapping[str, Any]] = None) -> Dict[str, str]:
    """Full authored profile for an in-game entity (LLM controller context)."""
    props = getattr(entity, 'properties', None) or {}
    profile = extract_profile(props)
    if 'size' not in profile:
        try:
            size_val = entity.size() if hasattr(entity, 'size') and callable(entity.size) else None
        except Exception:
            size_val = None
        if size_val:
            profile['size'] = _clean_text(size_val)
        else:
            profile['size'] = resolve_size(props, race_def)
    return profile


def llm_character_context(entity, *, race_def: Optional[Mapping[str, Any]] = None, max_chars: int = 900) -> str:
    """Personality/backstory summary for LLM-controlled entities."""
    profile = profile_for_entity(entity, race_def=race_def)
    summary = format_profile_for_llm(profile)
    if not summary:
        return ''
    if len(summary) > max_chars:
        return summary[: max_chars - 3].rsplit('\n', 1)[0] + '...'
    return summary


def sync_profile_keys() -> Sequence[str]:
    """Property keys to mirror from PC YAML onto live entity instances."""
    return PROFILE_TEXT_FIELDS
