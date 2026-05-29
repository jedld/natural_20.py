"""Effect filter helpers and event listeners extracted from app.py.

Provides narration overlay, control override, turn skipped, and battle-end
narration handlers.  Event listener registration is deferred behind
``register_effect_listeners()`` so the module can be imported without
side-effects.
"""

import logging

from .runtime_state import (
    get_socketio,
    get_current_game,
    get_game_session,
    get_controllers,
    get_output_logger,
    get_event_manager,
    get_level,
    get_active_effects,
    get_active_effects_map,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure helpers (no global state)
# ---------------------------------------------------------------------------

def _humanize_condition(condition_id):
    if not condition_id:
        return 'control override'
    return str(condition_id).replace('_', ' ')


def _entity_brief(entity):
    if entity is None:
        return None
    return {
        'uid': getattr(entity, 'entity_uid', None),
        'name': getattr(entity, 'label', lambda: getattr(entity, 'name', 'Unknown'))()
            if callable(getattr(entity, 'label', None)) else getattr(entity, 'name', 'Unknown'),
    }


def _entity_position(entity):
    """Return ``[x, y]`` for ``entity`` on whichever map it currently lives on."""
    try:
        game = get_current_game()
        if not game or entity is None:
            return None
        for m in (getattr(game, 'maps', {}) or {}).values():
            try:
                if entity in m.entities:
                    return list(m.entities[entity])
            except Exception:
                continue
    except Exception:
        return None
    return None


def _users_controlling(entity):
    """Usernames whose ``WebController`` is bound to ``entity`` (plus DMs)."""
    game = get_current_game()
    if not game or entity is None:
        return set()
    users = set()
    try:
        ctrl = (game.web_controllers or {}).get(entity)
        if ctrl is not None and hasattr(ctrl, 'get_users'):
            for u in ctrl.get_users() or []:
                if u:
                    users.add(u)
    except Exception:
        pass
    # Always include any DM-role user so they see the override too.
    try:
        for username in (game.username_to_sid or {}).keys():
            if username and username.lower().startswith('dm'):
                users.add(username)
    except Exception:
        pass
    return users


def _emit_to_users(payload, usernames):
    """Send a socket ``message`` payload to the SIDs of every named user.

    Falls back to a global broadcast when no usernames resolve to known SIDs
    so the notification is never silently dropped.
    """
    socketio = get_socketio()
    game = get_current_game()
    sent = False
    if game and usernames:
        sid_map = getattr(game, 'username_to_sid', {}) or {}
        for username in usernames:
            for sid in sid_map.get(username, []) or []:
                socketio.emit('message', payload, to=sid)
                sent = True
    if not sent:
        socketio.emit('message', payload)


# ---------------------------------------------------------------------------
# Event listener callbacks
# ---------------------------------------------------------------------------

def _emit_narration_overlay(event, record_narration_fn):
    """Emit a narration overlay and persist it to PC journals."""
    narration = event.get('narration') or {}
    entry = narration.get('on_enter') or {}
    if not entry.get('text'):
        return
    map_name = event.get('map_name')
    if not map_name:
        source = event.get('source')
        if source is not None:
            try:
                resolved_map = get_game_session().map_for(source)
                if resolved_map is not None:
                    map_name = resolved_map.name
            except Exception:
                map_name = None
    socketio = get_socketio()
    socketio.emit('message', {
        'type': 'narration',
        'message': narration,
        'map_name': map_name,
    })
    # Persist the narration into every present PC's journal so players have
    # an after-the-fact record they can search through their character
    # sheet. Targets default to "all PCs on the relevant map".
    target_uids = event.get('target_entities')
    source = event.get('source')
    source_uid = getattr(source, 'entity_uid', None) if source is not None else None
    try:
        record_narration_fn(
            narration,
            map_name=map_name,
            target_uids=target_uids,
            source=source_uid,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug(f"Failed to record narration in journals: {exc}")


def _emit_control_override_change(event, action):
    """Notify manual users when a loss-of-control effect starts/ends."""
    target = event.get('target')
    source = event.get('source')
    condition = event.get('condition') or 'control_override'
    target_brief = _entity_brief(target)
    source_brief = _entity_brief(source)
    target_name = (target_brief or {}).get('name') or 'Someone'
    source_name = (source_brief or {}).get('name') if source_brief else None
    pretty_condition = _humanize_condition(condition)

    if action == 'added':
        if source_name and source_name != target_name:
            log_msg = f"{target_name} is now {pretty_condition} (from {source_name})."
        else:
            log_msg = f"{target_name} is now {pretty_condition}."
        toast_text = f"{target_name}: {pretty_condition}"
    else:
        log_msg = f"{target_name} is no longer {pretty_condition}."
        toast_text = f"{target_name}: {pretty_condition} ended"

    try:
        output_logger = get_output_logger()
        output_logger.log(log_msg, visibility='public')
    except Exception:
        pass

    payload = {
        'type': 'control_override',
        'action': action,
        'target': target_brief,
        'source': source_brief,
        'condition': condition,
        'condition_label': pretty_condition,
        'message': log_msg,
        'toast': toast_text,
        'position': _entity_position(target),
    }
    _emit_to_users(payload, _users_controlling(target))


def _on_control_override_added(event):
    _emit_control_override_change(event, 'added')


def _on_control_override_removed(event):
    _emit_control_override_change(event, 'removed')


def _on_turn_skipped(event):
    target = event.get('target')
    target_brief = _entity_brief(target)
    target_name = (target_brief or {}).get('name') or 'Someone'
    statuses = event.get('statuses') or []
    reason = event.get('reason') or 'incapacitated'
    pretty_reason = _humanize_condition(reason)
    if statuses:
        pretty_statuses = ', '.join(_humanize_condition(s) for s in statuses)
        log_msg = f"{target_name}'s turn is skipped ({pretty_reason}: {pretty_statuses})."
    else:
        log_msg = f"{target_name}'s turn is skipped ({pretty_reason})."

    try:
        output_logger = get_output_logger()
        output_logger.log(log_msg, visibility='public')
    except Exception:
        pass

    payload = {
        'type': 'turn_skipped',
        'target': target_brief,
        'reason': reason,
        'reason_label': pretty_reason,
        'statuses': list(statuses),
        'message': log_msg,
        'toast': f"{target_name}: turn skipped ({pretty_reason})",
        'position': _entity_position(target),
    }
    _emit_to_users(payload, _users_controlling(target))


def _select_outcome_narration(battle, outcome):
    """Look up campaign narration for the given outcome ('tpk' | 'victory').

    Returns a narration dict shaped like the standard narration overlay
    payload, or ``None`` if the campaign has not declared one for this
    outcome/map combination.
    """
    try:
        properties = getattr(get_game_session(), 'game_properties', None) or {}
    except Exception:
        properties = {}
    key = 'tpk_narration' if outcome == 'tpk' else 'victory_narration'
    section = properties.get(key) or {}
    if not isinstance(section, dict):
        return None, None

    map_name = None
    try:
        battle_map = get_current_game().get_current_battle_map()
        if battle_map is not None:
            map_name = getattr(battle_map, 'name', None)
    except Exception:
        map_name = None

    by_map = section.get('by_map') or {}
    entry = None
    if map_name and isinstance(by_map, dict):
        entry = by_map.get(map_name)
    if not entry:
        entry = section.get('default')
    if not entry or not isinstance(entry, dict):
        return None, map_name
    text = entry.get('text')
    if not text:
        return None, map_name
    payload = {
        'on_enter': {
            'title': entry.get('title'),
            'text': text,
            'once': False,
            'tpk': outcome == 'tpk',
            'outcome': outcome,
        }
    }
    return payload, map_name


def _on_battle_end_narrate(game_manager, session, record_narration_fn):
    """Emit a campaign-appropriate narration overlay when a battle ends."""
    battle = game_manager.get_current_battle()
    if battle is None:
        return False
    try:
        outcome = 'tpk' if battle.tpk() else 'victory'
    except Exception:
        return False
    narration, map_name = _select_outcome_narration(battle, outcome)
    if not narration:
        return False
    try:
        socketio = get_socketio()
        socketio.emit('message', {
            'type': 'narration',
            'message': narration,
            'map_name': map_name,
        })
    except Exception as exc:  # pragma: no cover - socket emit best-effort
        logger.warning(f"Failed to emit battle-end narration: {exc}")
        return False
    try:
        record_narration_fn(narration, map_name=map_name)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug(f"Failed to record battle-end narration: {exc}")
    return True


# ---------------------------------------------------------------------------
# Client effect sync (SocketIO connect / request_effects)
# ---------------------------------------------------------------------------

def emit_active_effects_for_client(emit_fn):
    """Emit current visual-effect payloads to one client via ``emit_fn(name, payload)``."""
    from flask import session

    from .special_effects import (
        filter_effect_payloads,
        map_default_effect_payloads,
        point_fire_effect_payload,
    )

    try:
        game_key = (
            getattr(get_current_game().game_session, 'root_path', None)
            or getattr(get_game_session(), 'root_path', None)
            or get_level()
        )

        cur_map = None
        try:
            username = session.get('username')
            if username:
                cur_map = get_current_game().get_map_for_user(username)
            else:
                try:
                    cur_map = get_current_game().get_map_for_user(None)
                except Exception:
                    cur_map = get_current_game().get_current_battle_map()
        except Exception:
            cur_map = None

        effects = filter_effect_payloads(get_active_effects().get(game_key, {}).values())
        if effects:
            for payload in effects:
                emit_fn('effect:set', payload)
        else:
            try:
                cur_name = getattr(cur_map, 'name', None)
                map_overrides = filter_effect_payloads(
                    get_active_effects_map().get(game_key, {}).get(cur_name, {}).values()
                )
                if map_overrides:
                    for payload in map_overrides:
                        emit_fn('effect:set', payload)
                else:
                    for payload in map_default_effect_payloads(cur_map):
                        emit_fn('effect:set', payload)
            except Exception:
                pass

        try:
            emit_fn('effect:set', point_fire_effect_payload(cur_map))
        except Exception:
            pass
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Registration entry point
# ---------------------------------------------------------------------------

def register_effect_listeners(record_narration_fn):
    """Register all effect-related event listeners on the global event_manager.

    Args:
        record_narration_fn: Callable for ``_record_narration_for_pcs`` passed
            in from ``app.py`` to avoid a circular import.  Signature::

                def record_narration_fn(narration, map_name=None, target_uids=None, source=None)
    """
    event_manager = get_event_manager()

    # Wrap _emit_narration_overlay to inject the record function
    def _emit_narration_overlay_wrapped(event):
        _emit_narration_overlay(event, record_narration_fn)

    event_manager.register_event_listener('narration', _emit_narration_overlay_wrapped)
    event_manager.register_event_listener('control_override_added', _on_control_override_added)
    event_manager.register_event_listener('control_override_removed', _on_control_override_removed)
    event_manager.register_event_listener('turn_skipped', _on_turn_skipped)

    # Battle-end narration is registered on current_game, not event_manager
    def _on_battle_end_narrate_wrapped(game_manager, session):
        return _on_battle_end_narrate(game_manager, session, record_narration_fn)

    try:
        current_game = get_current_game()
        current_game.register_event_handler('on_battle_end', _on_battle_end_narrate_wrapped)
    except Exception:
        pass  # current_game may not be initialized yet during early imports
