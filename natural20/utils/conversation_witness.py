"""Witnessed in-world actions for NPC conversation context (generic, map-aware)."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Set

from natural20.utils.conversation import audible_entities, entity_label


def _entity_uid(entity) -> Optional[str]:
    if entity is None:
        return None
    uid = getattr(entity, 'entity_uid', None)
    return str(uid) if uid else None


def witness_entity_uids(
    session,
    *,
    source=None,
    target=None,
    extra_entities: Optional[Iterable] = None,
    distance_ft: int = 30,
    volume: str = 'normal',
) -> List[str]:
    """Entity UIDs that could plausibly witness an action between source and target."""
    uids: Set[str] = set()
    for entity in (source, target):
        uid = _entity_uid(entity)
        if uid:
            uids.add(uid)
    for entity in extra_entities or []:
        uid = _entity_uid(entity)
        if uid:
            uids.add(uid)

    battle_map = None
    if source is not None and session is not None:
        try:
            battle_map = session.map_for_entity(source)
        except Exception:
            battle_map = None

    if battle_map is not None and source is not None:
        try:
            for entry in audible_entities(source, battle_map, distance_ft=distance_ft, mode=volume):
                listener = entry.get('entity')
                uid = _entity_uid(listener)
                if uid:
                    uids.add(uid)
        except Exception:
            pass

    return sorted(uids)


def log_witnessed_action(
    output_logger,
    session,
    message: str,
    *,
    source=None,
    target=None,
    extra_entities: Optional[Iterable] = None,
    distance_ft: int = 30,
    volume: str = 'normal',
) -> None:
    """Append a console line visible to nearby entities (for NPC conversation memory)."""
    if output_logger is None or not hasattr(output_logger, 'log'):
        return
    text = str(message or '').strip()
    if not text:
        return
    entity_uids = witness_entity_uids(
        session,
        source=source,
        target=target,
        extra_entities=extra_entities,
        distance_ft=distance_ft,
        volume=volume,
    )
    if not entity_uids:
        return
    output_logger.log(
        text,
        visibility={'kind': 'entities', 'entity_uids': entity_uids},
    )


def witnessed_action_lines(
    output_logger,
    observer,
    *,
    limit: int = 10,
) -> List[str]:
    """Recent log lines the observer entity was scoped to see."""
    if output_logger is None or observer is None:
        return []
    if not hasattr(output_logger, 'get_visible_entries_for_entity'):
        return []
    try:
        entries = output_logger.get_visible_entries_for_entity(observer)
    except Exception:
        return []
    lines: List[str] = []
    for entry in entries[-max(1, int(limit)):]:
        message = str((entry or {}).get('message') or '').strip()
        if message:
            lines.append(message)
    return lines


def format_witnessed_actions_summary(
    lines: List[str],
    *,
    heading: str = 'Recent events you witnessed nearby (authoritative):',
) -> str:
    cleaned = [str(line).strip() for line in (lines or []) if str(line).strip()]
    if not cleaned:
        return ''
    body = '\n'.join(f"- {line}" for line in cleaned)
    return f"\n{heading}\n{body}\n"


def format_actor_target_message(actor, target, verb: str, detail: str = '') -> str:
    actor_name = entity_label(actor) if actor is not None else 'Someone'
    target_name = entity_label(target) if target is not None else 'someone'
    text = f"{actor_name} {verb} {target_name}"
    if detail:
        text = f"{text} {detail}".strip()
    return text
