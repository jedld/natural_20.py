from typing import Any, Dict, List, Optional

from natural20.utils.conversation import entity_label

STATE_KEY = 'animal_communication'
DEFAULT_DURATION_SECONDS = 8 * 60 * 60


def _clone_state(session) -> Dict[str, Any]:
    raw_state = session.load_state(STATE_KEY) or {}
    state = dict(raw_state) if isinstance(raw_state, dict) else {}
    by_entity = state.get('by_entity') if isinstance(state.get('by_entity'), dict) else {}
    state['by_entity'] = {str(uid): int(until) for uid, until in by_entity.items() if str(uid)}
    state['global_until'] = int(state.get('global_until') or 0)
    return state


def _save_state(session, state: Dict[str, Any]) -> None:
    session.save_state(STATE_KEY, state)


def grant_animal_communication(session, entity=None, duration_seconds: int = DEFAULT_DURATION_SECONDS) -> int:
    state = _clone_state(session)
    now = int(getattr(session, 'game_time', 0) or 0)
    expiration = now + int(duration_seconds)

    if entity is None:
        state['global_until'] = max(int(state.get('global_until') or 0), expiration)
    else:
        uid = str(getattr(entity, 'entity_uid', '') or '')
        if uid:
            state['by_entity'][uid] = max(int(state['by_entity'].get(uid) or 0), expiration)

    _save_state(session, state)
    return expiration


def animal_communication_expires_at(session, entity=None) -> int:
    state = _clone_state(session)
    global_until = int(state.get('global_until') or 0)

    if entity is None:
        return global_until

    uid = str(getattr(entity, 'entity_uid', '') or '')
    entity_until = int(state.get('by_entity', {}).get(uid) or 0) if uid else 0
    return max(global_until, entity_until)


def has_animal_communication(session, entity=None, now: Optional[int] = None) -> bool:
    if now is None:
        now = int(getattr(session, 'game_time', 0) or 0)
    return animal_communication_expires_at(session, entity=entity) > int(now)


def _entity_speaks_beast_language(entity) -> bool:
    try:
        spoken = getattr(entity, 'languages', lambda: [])() or []
    except Exception:
        spoken = []
    normalized = {str(item).strip().lower() for item in spoken if item}
    return bool(normalized & {'beast', 'sheep', 'animals'})


def animal_communication_status_text(session, entity=None) -> str:
    if entity is None:
        return 'unknown'
    if has_animal_communication(session, entity=entity):
        expiration = animal_communication_expires_at(session, entity=entity)
        return f'active until game time {expiration}'
    return 'inactive'


def animal_communication_guidance_lines(
    session,
    observer,
    speaker=None,
    *,
    nearby_entities=None,
) -> List[str]:
    """Prompt lines so beast-speaking NPCs know who can understand them."""
    if observer is None or not _entity_speaks_beast_language(observer):
        return []

    lines: List[str] = []
    seen_uids = set()

    def _append_for(target, role: str):
        uid = str(getattr(target, 'entity_uid', '') or '')
        if not uid or uid in seen_uids:
            return
        seen_uids.add(uid)
        status = animal_communication_status_text(session, target)
        label = entity_label(target)
        if status == 'inactive':
            lines.append(
                f"- Speak with Animals on {label} ({role}): inactive — they cannot understand "
                f"your beast/sheep speech yet; offer a comprehension aid (e.g. scroll) before "
                f"lengthy dialogue."
            )
        else:
            lines.append(
                f"- Speak with Animals on {label} ({role}): {status} — they can understand "
                f"your beast/sheep speech."
            )

    if speaker is not None:
        _append_for(speaker, 'current speaker')

    for target in nearby_entities or []:
        if target is speaker:
            continue
        _append_for(target, 'nearby')

    if not lines:
        return []

    return [
        'Speak with Animals awareness (trust this; do not guess):',
        *lines,
    ]


def animal_communication_activation_note(listener) -> str:
    """System note for beast-speaking NPCs when a listener gains comprehension."""
    label = entity_label(listener) if listener is not None else 'The listener'
    return (
        f"{label} read a Speak with Animals scroll and can understand your "
        "beast/sheep speech now. Continue in [in sheep] with clear dialogue; "
        "do not offer the scroll again or explain how it works."
    )
