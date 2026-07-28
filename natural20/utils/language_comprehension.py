"""Shared rules for whether a listener understands a spoken language."""

from __future__ import annotations

from typing import Any, Optional

from natural20.utils.animal_communication import has_animal_communication

BEAST_DIALECT_TO_BASE_LANGUAGE = {
    'sheep': 'beast',
}


def normalize_language(language: Optional[str]) -> str:
    normalized = str(language or 'common').strip().lower()
    if normalized in {'animal', 'animals', 'beasts', 'beast_speech'}:
        return 'beast'
    return normalized


def _language_set_for_entity(entity: Any, *, understood: bool = False) -> set[str]:
    if understood:
        getter = getattr(entity, 'languages_understood', None)
        if not callable(getter):
            getter = getattr(entity, 'languages', None)
    else:
        getter = getattr(entity, 'languages', None)
    try:
        languages = getter() or [] if callable(getter) else []
    except Exception:
        languages = []
    return {str(item).strip().lower() for item in languages if item}


def _listener_language_set(listener: Any) -> set[str]:
    return _language_set_for_entity(listener, understood=True)


def _entity_is_beast(entity: Any) -> bool:
    props = getattr(entity, 'properties', None)
    if not isinstance(props, dict):
        return False
    race = props.get('race', []) or []
    if isinstance(race, str):
        race = [race]
    return 'beast' in {str(item).strip().lower() for item in race if item}


def speaker_reaches_beast_via_animal_communication(
    source: Any,
    listener: Any,
    language: Optional[str],
    session: Any = None,
) -> bool:
    """Speak with Animals lets the caster's speech reach beasts."""
    if source is None or listener is None or not _entity_is_beast(listener):
        return False

    session_obj = session
    if session_obj is None:
        session_obj = getattr(source, 'session', None) or getattr(listener, 'session', None)
    if session_obj is None or not has_animal_communication(session_obj, entity=source):
        return False

    normalized_language = normalize_language(language)
    speaker_languages = _language_set_for_entity(source, understood=False)
    return normalized_language in speaker_languages


def comprehends_speech(
    listener: Any,
    language: Optional[str],
    *,
    source: Any = None,
    session: Any = None,
) -> bool:
    """Return True when *listener* can understand speech in *language* from *source*."""
    if understands_language(listener, language, session=session):
        return True
    if source is None:
        return False
    return speaker_reaches_beast_via_animal_communication(source, listener, language, session=session)


def understands_language_for_languages(
    listener_languages: Any,
    language: Optional[str],
) -> bool:
    """Return True when any language in *listener_languages* comprehends *language*."""
    normalized_language = normalize_language(language)
    normalized_languages = {
        str(item).strip().lower()
        for item in (listener_languages or [])
        if item
    }

    base_language = BEAST_DIALECT_TO_BASE_LANGUAGE.get(normalized_language)
    if base_language and base_language in normalized_languages:
        return True

    return normalized_language in normalized_languages


def understands_language(listener: Any, language: Optional[str], session: Any = None) -> bool:
    """Return True when *listener* can comprehend speech in *language*."""
    if listener is None:
        return False

    normalized_language = normalize_language(language)
    normalized_languages = _listener_language_set(listener)

    session_obj = session
    if session_obj is None:
        session_obj = getattr(listener, 'session', None)

    base_language = BEAST_DIALECT_TO_BASE_LANGUAGE.get(normalized_language)

    if session_obj is not None and has_animal_communication(session_obj, entity=listener):
        if normalized_language == 'beast' or base_language == 'beast':
            return True

    if base_language and base_language in normalized_languages:
        return True

    return normalized_language in normalized_languages
