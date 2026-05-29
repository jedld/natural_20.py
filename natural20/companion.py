"""Non-hostile companions that follow the party across maps."""


def companion_defs(game_properties):
    if not game_properties:
        return []
    raw = game_properties.get('companions') or []
    return raw if isinstance(raw, list) else []


def quest_allows_companion(session, companion_cfg):
    require = companion_cfg.get('require_session')
    if not require:
        return True
    if session is None:
        return False
    state = getattr(session, 'session_state', {}) or {}
    for key, expected in require.items():
        if state.get(key) != expected:
            return False
    return True


def sync_companion_to_map(session, game_properties, companion_uid, target_map, anchor_pos, offset=None):
    """Place companion on target_map adjacent to anchor_pos if not already there."""
    if session is None or target_map is None or anchor_pos is None:
        return None

    companion = session.entity_by_uid(companion_uid)
    if companion is None:
        return None

    try:
        current_map = session.map_for(companion)
    except Exception:
        current_map = None

    if current_map is target_map and companion in getattr(target_map, 'entities', {}):
        return companion

    if current_map is not None and companion in getattr(current_map, 'entities', {}):
        try:
            current_map.remove(companion)
        except Exception:
            pass

    ox, oy = offset or [1, 0]
    candidates = [
        (anchor_pos[0] + ox, anchor_pos[1] + oy),
        (anchor_pos[0] - ox, anchor_pos[1] + oy),
        (anchor_pos[0] + ox, anchor_pos[1] - oy),
        (anchor_pos[0], anchor_pos[1] + 1),
        (anchor_pos[0], anchor_pos[1] - 1),
        anchor_pos,
    ]
    for pos in candidates:
        try:
            if target_map.placeable(companion, pos[0], pos[1], squeeze=False):
                target_map.add(companion, pos[0], pos[1], group=companion.properties.get('group', 'd'))
                return companion
        except Exception:
            continue
    return None


def sync_companions_for_entity(session, game_properties, anchor_entity, target_map=None):
    if anchor_entity is None:
        return
    if target_map is None:
        try:
            target_map = session.map_for(anchor_entity)
        except Exception:
            return
    if target_map is None:
        return

    try:
        anchor_pos = target_map.position_of(anchor_entity)
    except Exception:
        anchor_pos = None
    if anchor_pos is None:
        return

    for cfg in companion_defs(game_properties):
        if not quest_allows_companion(session, cfg):
            continue
        uid = cfg.get('entity_uid')
        if not uid:
            continue
        sync_companion_to_map(
            session,
            game_properties,
            uid,
            target_map,
            anchor_pos,
            offset=cfg.get('spawn_offset'),
        )


def sync_companions_on_map_switch(session, game_properties, username, target_map_name):
    """After a player switches maps, pull configured companions to the same map."""
    if session is None:
        return
    target_map = session.maps.get(target_map_name) if isinstance(target_map_name, str) else target_map_name
    if target_map is None:
        return

    from natural20.player_character import PlayerCharacter
    for ent in list(getattr(target_map, 'entities', {}).keys()):
        if isinstance(ent, PlayerCharacter):
            sync_companions_for_entity(session, game_properties, ent, target_map=target_map)
