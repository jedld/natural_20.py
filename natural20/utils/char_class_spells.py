"""Helpers for character-builder spell lists vs engine implementation."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Set


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

    availability: Dict[str, bool] = {}
    for slug in sorted(collect_spell_list_slugs(classes)):
        try:
            meta = session.load_spell(slug)
            availability[slug] = bool(spell_is_implemented(slug, meta))
        except Exception:
            availability[slug] = False
    return availability


def missing_spell_yaml_slugs(session, classes: Dict[str, Any]) -> Iterable[str]:
    slugs = collect_spell_list_slugs(classes)
    for slug in sorted(slugs):
        try:
            session.load_spell(slug)
        except Exception:
            yield slug
