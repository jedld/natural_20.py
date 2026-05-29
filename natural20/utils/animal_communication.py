from typing import Any, Dict, Optional


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
