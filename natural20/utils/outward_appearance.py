"""Resolve how an entity looks to outside observers (conversation, observe, sheets)."""

from __future__ import annotations

import re
from typing import Any, List, Optional


def explicit_outward_appearance(properties: Optional[dict]) -> str:
    """Return a YAML-authored outward appearance string, if any."""
    props = properties or {}
    return str(props.get('outward_appearance') or props.get('appearance') or '').strip()


def _format_race(entity) -> str:
    race = None
    try:
        if hasattr(entity, 'race') and callable(entity.race):
            race = entity.race()
    except Exception:
        race = None
    if not race:
        race = (getattr(entity, 'properties', None) or {}).get('race')

    if isinstance(race, list):
        parts = [str(item).replace('_', ' ').strip() for item in race if str(item).strip()]
        specific = [part for part in parts if part.lower() != 'humanoid']
        return ' '.join(specific or parts)
    if isinstance(race, str) and race.strip():
        return race.replace('_', ' ').strip()
    return ''


def _format_class_descriptor(entity) -> str:
    try:
        if hasattr(entity, 'class_descriptor') and callable(entity.class_descriptor):
            descriptor = entity.class_descriptor()
            if isinstance(descriptor, str) and descriptor.strip():
                return descriptor.replace('_', ' ').strip()
    except Exception:
        pass

    try:
        class_levels = entity.class_and_level() if hasattr(entity, 'class_and_level') else []
    except Exception:
        class_levels = []

    labels: List[str] = []
    for klass, level in class_levels or []:
        if not isinstance(klass, str):
            continue
        klass_name = klass.replace('_', ' ').strip()
        if not klass_name:
            continue
        if level:
            labels.append(f"level {level} {klass_name}")
        else:
            labels.append(klass_name)
    return ', '.join(labels)


def _item_display_label(item: dict) -> str:
    return (item.get('label') or item.get('name') or 'item').strip()


def _visible_equipment_phrase(entity, session=None) -> str:
    if not hasattr(entity, 'equipped_items'):
        return ''
    try:
        equipped = list(entity.equipped_items() or [])
    except Exception:
        return ''

    armor_labels: List[str] = []
    weapon_labels: List[str] = []
    for item in equipped:
        label = _item_display_label(item)
        item_type = str(item.get('type') or item.get('subtype') or '').lower()
        if 'armor' in item_type or item_type == 'shield':
            armor_labels.append(label)
        elif 'weapon' in item_type:
            weapon_labels.append(label)

    parts: List[str] = []
    if armor_labels:
        parts.append('wearing ' + ', '.join(armor_labels[:2]))
    if weapon_labels:
        parts.append('carrying ' + ', '.join(weapon_labels[:2]))
    return '; '.join(parts)


def _notes_appearance(entity, observer=None) -> str:
    if not hasattr(entity, 'has_notes') or not entity.has_notes():
        return ''
    try:
        notes, _ = entity.list_notes(
            entity=observer,
            entity_pov=[observer] if observer is not None else None,
        )
    except Exception:
        return ''
    visible = []
    for note in notes or []:
        text = str((note or {}).get('note') or '').strip()
        if text and text != '???':
            visible.append(text)
    return '; '.join(visible[:2])


def _object_appearance(entity) -> str:
    props = getattr(entity, 'properties', {}) or {}
    explicit = explicit_outward_appearance(props)
    if explicit:
        return explicit
    description = ''
    try:
        description_fn = getattr(entity, 'description', None)
        description = (description_fn() if callable(description_fn) else description_fn) or ''
    except Exception:
        description = ''
    description = str(description).strip()
    if description:
        if len(description) > 320:
            description = description[:317].rstrip() + '...'
        return description
    label = props.get('label') or props.get('name') or props.get('kind')
    if label:
        return f"Looks like {str(label).lower()}."
    return ''


def derive_outward_appearance(entity, session=None, observer=None) -> str:
    """Build a best-effort outward appearance from race, class, gear, and kind."""
    props = getattr(entity, 'properties', {}) or {}

    try:
        if callable(getattr(entity, 'object', None)) and entity.object():
            return _object_appearance(entity) or 'No distinguishing features are obvious from here.'
    except Exception:
        pass

    chunks: List[str] = []
    size = props.get('size')
    if size:
        chunks.append(str(size).replace('_', ' '))

    race = _format_race(entity)
    if race:
        chunks.append(race)

    subrace = props.get('subrace')
    if subrace:
        chunks.append(str(subrace).replace('_', ' '))

    class_part = _format_class_descriptor(entity)
    if class_part:
        chunks.append(class_part)

    gear = _visible_equipment_phrase(entity, session=session)
    if chunks:
        base = ' '.join(chunks)
        if gear:
            return f"A {base}, {gear}."
        return f"A {base}."

    kind = props.get('kind') or props.get('sub_type')
    if kind:
        phrase = f"A {str(kind).replace('_', ' ')}"
        if gear:
            return f"{phrase}, {gear}."
        return f"{phrase}."

    if gear:
        return f"Someone {gear}."

    return ''


def resolve_outward_appearance(
    entity,
    session=None,
    observer=None,
    *,
    include_notes: bool = True,
) -> str:
    """Return the outward appearance an observer would plausibly notice."""
    props = getattr(entity, 'properties', {}) or {}
    explicit = explicit_outward_appearance(props)
    if explicit:
        return explicit

    if include_notes:
        note_text = _notes_appearance(entity, observer=observer)
        if note_text:
            return note_text

    derived = derive_outward_appearance(entity, session=session, observer=observer)
    if derived:
        return derived

    label = ''
    try:
        label_fn = getattr(entity, 'label', None)
        label = (label_fn() if callable(label_fn) else label_fn) or ''
    except Exception:
        label = ''
    label = str(label).strip()
    if label:
        return f"Looks like {label.lower()}."

    return 'No distinguishing features are obvious from here.'


def normalize_outward_appearance_value(value: Any) -> str:
    return re.sub(r'\s+', ' ', str(value or '').strip())


def conversation_self_appearance(entity, session=None) -> str:
    """Appearance text injected into NPC conversation prompts for self-knowledge."""
    return resolve_outward_appearance(
        entity,
        session=session,
        observer=entity,
        include_notes=False,
    )
