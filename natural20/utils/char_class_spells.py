"""Helpers for character-builder spell lists vs engine implementation."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Set

# Per-campaign cache so /character_builder does not rebuild this on every request.
_AVAILABILITY_CACHE: Dict[str, Dict[str, bool]] = {}


def collect_spell_list_slugs(classes: Dict[str, Any]) -> Set[str]:
    slugs: Set[str] = set()
    for class_def in (classes or {}).values():
        spell_list = (class_def or {}).get('spell_list') or {}
        for spells in spell_list.values():
            if isinstance(spells, list):
                slugs.update(spells)
    return slugs


def spell_availability_map(session, classes: Dict[str, Any]) -> Dict[str, bool]:
    """Map spell slug -> playable in combat (``spell_is_implemented``)."""
    from natural20.utils.spell_loader import spell_is_implemented

    cache_key = str(getattr(session, 'root_path', '') or id(session))
    cached = _AVAILABILITY_CACHE.get(cache_key)
    if cached is not None:
        return cached

    slugs = collect_spell_list_slugs(classes)
    if not slugs:
        _AVAILABILITY_CACHE[cache_key] = {}
        return {}

    try:
        all_spells = session.load_all_spells()
    except Exception:
        all_spells = {}

    availability: Dict[str, bool] = {}
    for slug in sorted(slugs):
        meta = all_spells.get(slug)
        if not meta:
            availability[slug] = False
            continue
        try:
            availability[slug] = bool(spell_is_implemented(slug, meta))
        except Exception:
            availability[slug] = False

    _AVAILABILITY_CACHE[cache_key] = availability
    return availability


def clear_spell_availability_cache(root_path: str | None = None) -> None:
    """Drop cached spell availability (tests or hot-reload)."""
    if root_path is None:
        _AVAILABILITY_CACHE.clear()
        return
    _AVAILABILITY_CACHE.pop(str(root_path), None)


def missing_spell_yaml_slugs(session, classes: Dict[str, Any]) -> Iterable[str]:
    slugs = collect_spell_list_slugs(classes)
    for slug in sorted(slugs):
        try:
            session.load_spell(slug)
        except Exception:
            yield slug
