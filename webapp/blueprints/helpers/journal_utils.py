"""Journal helpers shared by the character blueprint and battle/effects code."""

from flask import jsonify, session

from natural20.player_character import PlayerCharacter

from .auth_utils import user_role
from .runtime_state import get_current_game, get_socketio, get_logger
from .template_globals import entities_controlled_by


def _journal_owner_check(character):
    """Return (allowed, error_response). Players may only act on their own PCs."""
    if 'dm' in user_role():
        return True, None
    username = session.get('username')
    if not username:
        return False, (jsonify(error='Not authenticated'), 401)
    owned = entities_controlled_by(username)
    if character in owned:
        return True, None
    return False, (jsonify(error='Forbidden'), 403)


def _serialize_journal(character, query=None, kind=None, limit=None):
    if hasattr(character, 'search_journal'):
        return character.search_journal(query=query, kind=kind, limit=limit)
    return list(getattr(character, 'journal', None) or [])


def _persist_journal_change(character):
    """Best-effort autosave hook so journal mutations survive a crash."""
    logger = get_logger()
    try:
        save = getattr(get_current_game(), 'save_game_async', None)
        if callable(save):
            save()
    except Exception as exc:  # pragma: no cover - autosave is best-effort
        logger.debug(f"Journal autosave skipped: {exc}")


def _log_journal_entry_to_campaign_db(character, entry):
    db = getattr(get_current_game(), 'campaign_log_db', None)
    logger = get_logger()
    if db is None or not entry:
        return
    try:
        db.append_journal_entry(getattr(character, 'entity_uid', None), entry)
    except Exception as exc:
        logger.debug(f"Campaign journal log skipped: {exc}")


def _record_narration_for_pcs(narration, map_name=None, target_uids=None, source=None):
    """Append a narration entry to every relevant PC's journal."""
    if not isinstance(narration, dict):
        return
    entry = narration.get('on_enter') or {}
    text = entry.get('text')
    if not text:
        return
    title = entry.get('title')
    tags = []
    outcome = entry.get('outcome')
    if outcome:
        tags.append(outcome)
    if entry.get('tpk'):
        tags.append('tpk')

    current_game = get_current_game()
    socketio = get_socketio()
    logger = get_logger()

    candidates = []
    if target_uids:
        for uid in target_uids:
            ent = current_game.get_entity_by_uid(uid)
            if ent is not None:
                candidates.append(ent)
    else:
        seen = set()
        try:
            maps = list(current_game.maps.values()) if map_name is None else [
                m for m in current_game.maps.values() if getattr(m, 'name', None) == map_name
            ]
        except Exception:
            maps = []
        for battle_map in maps:
            for ent in getattr(battle_map, 'entities', []) or []:
                if isinstance(ent, PlayerCharacter) and ent.entity_uid not in seen:
                    seen.add(ent.entity_uid)
                    candidates.append(ent)

    affected_uids = []
    for pc in candidates:
        if not isinstance(pc, PlayerCharacter):
            continue
        if not hasattr(pc, 'add_journal_entry'):
            continue
        try:
            stored = pc.add_journal_entry(
                text,
                kind='narration',
                title=title,
                source=source,
                map_name=map_name,
                tags=tags,
            )
            if stored is not None:
                affected_uids.append(pc.entity_uid)
                _log_journal_entry_to_campaign_db(pc, stored)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug(f"Failed to record narration for {pc.entity_uid}: {exc}")

    if affected_uids:
        try:
            socketio.emit('message', {
                'type': 'journal_update',
                'entity_uids': affected_uids,
                'reason': 'narration',
            })
        except Exception:
            pass
