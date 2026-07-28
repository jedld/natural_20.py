"""Helpers for resolving NPC-only object annotations."""

from __future__ import annotations

from typing import Any, List, Optional

from natural20.utils.conversation import entity_label, mention_handle_for


def _annotation_text(annotation: dict) -> str:
    return str(
        annotation.get('text')
        or annotation.get('note')
        or annotation.get('annotation')
        or ''
    ).strip()


def visible_annotations_for(
    observer,
    subject,
    *,
    perception: Optional[int] = None,
) -> List[dict]:
    if observer is None or subject is None:
        return []
    if not hasattr(subject, 'has_annotations') or not subject.has_annotations():
        return []
    try:
        rows, _ = subject.list_annotations(observer, perception=perception)
    except Exception:
        return []
    return rows or []


def format_annotations_for_subject(observer, subject) -> str:
    rows = visible_annotations_for(observer, subject)
    if not rows:
        return ''
    parts = []
    for row in rows:
        text = _annotation_text(row)
        if text:
            parts.append(text)
    return '; '.join(parts)


def format_annotation_summary(
    observer,
    subjects: List[Any],
    *,
    range_ft: Optional[float] = None,
    battle_map=None,
) -> str:
    if observer is None or not subjects:
        return '[ANNOTATIONS] No annotations are apparent from here.'

    lines = ['[ANNOTATIONS]']
    found = False
    for subject in subjects:
        if battle_map is not None and range_ft is not None:
            try:
                distance = battle_map.distance(observer, subject) * battle_map.feet_per_grid
                if distance > range_ft:
                    continue
                if not battle_map.can_see(observer, subject):
                    continue
            except Exception:
                continue

        rows = visible_annotations_for(observer, subject)
        if not rows:
            continue

        found = True
        handle = mention_handle_for(subject)
        label = entity_label(subject)
        texts = [_annotation_text(row) for row in rows if _annotation_text(row)]
        if texts:
            lines.append(f'- @{handle} ({label}): ' + ' | '.join(texts))

    if not found:
        lines.append('- none visible to you within range')
    return '\n'.join(lines)
