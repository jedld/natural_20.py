import re

from natural20.utils.gibberish import gibberish


SPEECH_BASE_RANGES = {
    'whisper': 5,
    'normal': 30,
    'shout': 60,
}
SPEECH_MODE_ORDER = ['whisper', 'normal', 'shout']

MAX_HEARING_MODIFIER = 20
MIN_HEARING_MODIFIER = -10
MENTION_PATTERN = re.compile(r'(?<!\w)@([A-Za-z0-9][A-Za-z0-9_-]*)')
ACTION_TAG_PATTERN = re.compile(r'\[action:\s*([^\]]+)\]', re.IGNORECASE)
ASTERISK_ACTION_PATTERN = re.compile(r'\*([^*]+)\*')
SLASH_EMOTE_PATTERN = re.compile(r'^/(?:me|emote|action)\s+(.+)$', re.IGNORECASE | re.DOTALL)
MARKDOWN_BOLD_PATTERN = re.compile(r'\*\*([^*]+)\*\*')
MARKDOWN_EMPHASIS_PATTERN = re.compile(r'(?<!\*)\*([^*\n]+)\*(?!\*)')
UNDERSCORE_EMPHASIS_PATTERN = re.compile(r'(?<!_)_([^_\n]+)_(?!_)')
INLINE_CODE_PATTERN = re.compile(r'`([^`]+)`')
ACOUSTIC_WALL_PENALTY_FT = 30
ACOUSTIC_CLOSED_DOOR_PENALTY_FT = 20
ACOUSTIC_OPAQUE_OBJECT_PENALTY_FT = 10
ACOUSTIC_BLOCKED_LINE_PENALTY_FT = 45
ACOUSTIC_BLOCKED_LINE_SUPPLEMENT_FT = 15


def _safe_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_speech_mode(mode=None, distance_ft=None):
    if mode:
        mode = str(mode).strip().lower()
        if mode in SPEECH_BASE_RANGES:
            return mode

    distance_ft = _safe_int(distance_ft)
    if distance_ft is None:
        return 'normal'
    if distance_ft <= SPEECH_BASE_RANGES['whisper']:
        return 'whisper'
    if distance_ft >= SPEECH_BASE_RANGES['shout']:
        return 'shout'
    return 'normal'


def speech_distance_for(mode=None, distance_ft=None):
    explicit_distance = _safe_int(distance_ft)
    if explicit_distance is not None and explicit_distance >= 0:
        return explicit_distance
    return SPEECH_BASE_RANGES[normalize_speech_mode(mode=mode, distance_ft=distance_ft)]


def strip_spoken_address_prefix(text):
    """Remove leading 'Speaker to Target:' prefixes from NPC spoken lines."""
    raw = str(text or '').strip()
    if not raw:
        return raw
    match = re.match(
        r'^(?:.+?\s+to\s+[^:]+:)\s*(?P<body>.+)$',
        raw,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return raw
    body = (match.group('body') or '').strip()
    if not body:
        return raw
    if len(body) >= 2 and body[0] == body[-1] and body[0] in '"\'':
        body = body[1:-1].strip()
    return body or raw


def sanitize_spoken_text_for_tts(text):
    """Strip markdown-style emphasis markers so TTS reads the words, not punctuation."""
    raw = str(text or '').strip()
    if not raw:
        return raw

    working = raw
    working = MARKDOWN_BOLD_PATTERN.sub(r'\1', working)
    working = MARKDOWN_EMPHASIS_PATTERN.sub(r'\1', working)
    working = UNDERSCORE_EMPHASIS_PATTERN.sub(r'\1', working)
    working = INLINE_CODE_PATTERN.sub(r'\1', working)
    working = re.sub(r'\*+', '', working)
    return ' '.join(working.split())


def passive_perception_for(entity):
    if entity is None:
        return 10
    passive_perception = getattr(entity, 'passive_perception', None)
    try:
        if callable(passive_perception):
            return int(passive_perception() or 10)
        if passive_perception is not None:
            return int(passive_perception)
    except Exception:
        return 10
    return 10


def hearing_modifier_for(entity):
    passive_perception = passive_perception_for(entity)
    modifier = ((passive_perception - 10) // 5) * 5
    return max(MIN_HEARING_MODIFIER, min(MAX_HEARING_MODIFIER, modifier))


def effective_hearing_distance(listener, base_distance):
    return max(0, speech_distance_for(distance_ft=base_distance) + hearing_modifier_for(listener))


def parse_player_conversation_input(text):
    """Split player chat into spoken dialogue and non-verbal action descriptions."""
    raw = str(text or '').strip()
    if not raw:
        return {'spoken': '', 'actions': [], 'raw': ''}

    actions = []
    working = raw

    def _collect_action_tag(match):
        action = str(match.group(1) or '').strip()
        if action:
            actions.append(action)
        return ' '

    working = ACTION_TAG_PATTERN.sub(_collect_action_tag, working)

    def _collect_asterisk_action(match):
        action = str(match.group(1) or '').strip()
        if action:
            actions.append(action)
        return ' '

    working = ASTERISK_ACTION_PATTERN.sub(_collect_asterisk_action, working)

    slash_match = SLASH_EMOTE_PATTERN.match(working.strip())
    if slash_match:
        action = str(slash_match.group(1) or '').strip()
        if action:
            actions.append(action)
        working = ''

    spoken = ' '.join(working.split()).strip()
    return {'spoken': spoken, 'actions': actions, 'raw': raw}


def entity_label(entity):
    if entity is None:
        return ''
    label = getattr(entity, 'label', None)
    try:
        if callable(label):
            return str(label() or '')
    except Exception:
        pass
    return str(getattr(entity, 'name', '') or getattr(entity, 'entity_uid', '') or '')


def mention_handle_for(entity):
    label = entity_label(entity).strip().lower()
    if not label:
        label = str(getattr(entity, 'entity_uid', '') or '').strip().lower()
    handle = re.sub(r'[^a-z0-9]+', '-', label).strip('-')
    return handle or str(getattr(entity, 'entity_uid', '') or '').strip().lower()


def _word_aliases_for(entity):
    label = entity_label(entity)
    words = re.findall(r'[A-Za-z0-9]+', label.lower())
    role_words = set()
    for inner in re.findall(r'\(([^)]*)\)', label):
        role_words.update(re.findall(r'[A-Za-z0-9]+', inner.lower()))
    return {
        word for word in words
        if len(word) >= 3 and word not in role_words
    }


def _candidate_alias_map(entities):
    alias_map = {}
    word_counts = {}

    for entity in entities or []:
        if entity is None:
            continue
        aliases = {
            mention_handle_for(entity),
            str(getattr(entity, 'entity_uid', '') or '').strip().lower(),
        }
        for alias in aliases:
            if alias:
                alias_map.setdefault(alias, entity)
        for word in _word_aliases_for(entity):
            word_counts[word] = word_counts.get(word, 0) + 1

    for entity in entities or []:
        if entity is None:
            continue
        for word in _word_aliases_for(entity):
            if word_counts.get(word) == 1:
                alias_map.setdefault(word, entity)

    return alias_map


def resolve_mention_targets(message, entities):
    if not message:
        return []

    alias_map = _candidate_alias_map(entities)
    resolved = []
    seen = set()
    for token in MENTION_PATTERN.findall(message):
        entity = alias_map.get(token.strip().lower())
        entity_uid = getattr(entity, 'entity_uid', None)
        if entity is None or entity_uid in seen:
            continue
        seen.add(entity_uid)
        resolved.append(entity)
    return resolved


def resolve_named_targets(message, entities):
    if not message:
        return []

    alias_map = _candidate_alias_map(entities)
    resolved = []
    seen = set()
    for token in re.findall(r'(?<!@)\b([A-Za-z0-9][A-Za-z0-9_-]*)\b', message.lower()):
        entity = alias_map.get(token.strip().lower())
        entity_uid = getattr(entity, 'entity_uid', None)
        if entity is None or entity_uid in seen:
            continue
        seen.add(entity_uid)
        resolved.append(entity)
    return resolved


def unique_entities(entities):
    unique = []
    seen = set()
    for entity in entities or []:
        entity_uid = getattr(entity, 'entity_uid', None)
        if entity is None or entity_uid in seen:
            continue
        seen.add(entity_uid)
        unique.append(entity)
    return unique


def _map_position_for(entity, battle_map):
    try:
        position = battle_map.position_of(entity)
    except Exception:
        position = None
    if isinstance(position, (list, tuple)) and len(position) >= 2:
        return int(position[0]), int(position[1])
    return None


def _entity_map_for(entity, battle_map, battle=None):
    if battle is not None:
        mapped = battle.map_for(entity)
        if mapped is not None:
            return mapped
    if battle_map is not None:
        try:
            if entity in battle_map.entities:
                return battle_map
        except Exception:
            pass
    return battle_map


def _shared_stack(source_map, listener_map):
    if source_map is None or listener_map is None:
        return None
    stack = getattr(source_map, 'map_stack', None)
    if stack is None:
        return None
    if getattr(listener_map, 'map_stack', None) is not stack:
        return None
    return stack


def _door_penalty_at_entity(battle_map, entity) -> int:
    if battle_map is None or entity is None:
        return 0
    pos = _map_position_for(entity, battle_map)
    if pos is None:
        return 0
    penalty = 0
    try:
        objects = battle_map.objects_at(*pos)
    except Exception:
        objects = []
    for obj in objects or []:
        if _closed_door(obj):
            penalty += ACOUSTIC_CLOSED_DOOR_PENALTY_FT
    return penalty


def _stack_acoustic_profile(source, listener, source_map, listener_map, stack, battle):
    profile = {
        'penalty_ft': 0,
        'closed_doors': 0,
        'walls': 0,
        'opaque_objects': 0,
        'line_blocked': False,
        'summary': '',
    }
    if not battle.can_see(source, listener):
        profile['penalty_ft'] = ACOUSTIC_BLOCKED_LINE_PENALTY_FT
        profile['line_blocked'] = True
        profile['summary'] = 'blocked acoustic line'
        return profile

    for obj_map, ent in ((source_map, source), (listener_map, listener)):
        pos = _map_position_for(ent, obj_map)
        if pos is None:
            continue
        try:
            for obj in obj_map.objects_at(*pos) or []:
                if _closed_door(obj):
                    profile['closed_doors'] += 1
                    profile['penalty_ft'] += ACOUSTIC_CLOSED_DOOR_PENALTY_FT
        except Exception:
            pass

    parts = []
    if profile['closed_doors']:
        label = 'closed door' if profile['closed_doors'] == 1 else 'closed doors'
        parts.append(f"{profile['closed_doors']} {label}")
    profile['summary'] = ', '.join(parts)
    return profile


def _listeners_in_range(source, battle_map, search_distance_ft, *, battle=None, require_conversable=True):
    source_map = _entity_map_for(source, battle_map, battle=battle)
    stack = getattr(source_map, 'map_stack', None) if source_map else None
    listeners = []
    seen = set()

    if battle is not None and stack is not None and battle.maps:
        from natural20.map_stack_targeting import stack_entity_distance_ft

        for listener_map in battle.maps:
            if getattr(listener_map, 'map_stack', None) is not stack:
                continue
            for listener in list(listener_map.entities.keys()):
                if listener == source:
                    continue
                uid = getattr(listener, 'entity_uid', None) or id(listener)
                if uid in seen:
                    continue
                if require_conversable and not getattr(listener, 'conversable', lambda: True)():
                    continue
                try:
                    distance_ft = stack_entity_distance_ft(
                        stack, source, source_map, listener, listener_map,
                        feet_per_grid=source_map.feet_per_grid,
                    )
                except Exception:
                    continue
                if distance_ft <= search_distance_ft:
                    seen.add(uid)
                    listeners.append((listener, distance_ft))
        return listeners

    nearby = _entities_in_search_radius(
        source,
        battle_map,
        search_distance_ft,
        fallback_distances=[SPEECH_BASE_RANGES['shout']],
    )
    return [(listener, None) for listener in nearby]


def _closed_door(obj):
    kind_of_door = getattr(obj, 'kind_of_door', lambda: False)
    opened = getattr(obj, 'opened', lambda: False)
    dead = getattr(obj, 'dead', lambda: False)
    try:
        return bool(kind_of_door()) and not bool(opened()) and not bool(dead())
    except Exception:
        return False


def _wall_like_object(obj, origin=None):
    opaque = getattr(obj, 'opaque', None)
    if callable(opaque):
        try:
            return bool(opaque(origin))
        except Exception:
            pass
    wall_attr = getattr(obj, 'wall', None)
    if callable(wall_attr):
        try:
            if origin is not None:
                try:
                    return bool(wall_attr(origin))
                except TypeError:
                    pass
            return bool(wall_attr())
        except Exception:
            return False
    if wall_attr is not None:
        return bool(wall_attr)
    return False


# Simple dict-based cache for acoustic profiles keyed on positions.
# Key: (source_uid, listener_uid, source_pos, listener_pos, map_id)
# Positions in the key ensure automatic cache misses when entities move.
_acoustic_cache: dict = {}
_ACOUSTIC_CACHE_MAX_SIZE = 256


def _acoustic_line_blocked(battle_map, source_pos, listener_pos) -> bool:
    if battle_map is None or source_pos is None or listener_pos is None:
        return False
    try:
        result = battle_map.line_of_sight(
            source_pos[0],
            source_pos[1],
            listener_pos[0],
            listener_pos[1],
            inclusive=False,
        )
        return result is None
    except Exception:
        return False


def _passable_interactable_objects(battle_map, square):
    try:
        objects = battle_map.objects_at(*square) or []
    except Exception:
        return []
    fixtures = []
    for obj in objects:
        try:
            if obj.passable() and obj.interactable():
                fixtures.append(obj)
        except Exception:
            continue
    return fixtures


def _path_square_blocks_speech(battle_map, square, prev_square):
    """True when a square along the speech path should add wall-like acoustic penalty."""
    if _passable_interactable_objects(battle_map, square):
        # Speech carries over bar counters, tables, and similar service fixtures.
        return False
    try:
        objects = battle_map.objects_at(*square) or []
    except Exception:
        objects = []
    if any(_wall_like_object(obj, origin=prev_square) for obj in objects):
        return True
    # Fallback for terrain flagged only via map.wall() (unit-test fakes, legacy maps).
    if not objects:
        try:
            return bool(battle_map.wall(*square))
        except Exception:
            return False
    return False


def acoustic_profile(source, listener, battle_map, battle=None):
    profile = {
        'penalty_ft': 0,
        'closed_doors': 0,
        'walls': 0,
        'opaque_objects': 0,
        'line_blocked': False,
        'summary': '',
    }

    if source is None or listener is None or battle_map is None:
        return profile

    source_map = _entity_map_for(source, battle_map, battle=battle)
    listener_map = _entity_map_for(listener, battle_map, battle=battle)
    stack = _shared_stack(source_map, listener_map)
    if battle is not None and stack is not None and source_map is not listener_map:
        return _stack_acoustic_profile(source, listener, source_map, listener_map, stack, battle)

    effective_map = source_map if source in getattr(source_map, 'entities', {}) else listener_map
    source_pos = _map_position_for(source, effective_map or battle_map)
    listener_pos = _map_position_for(listener, effective_map or battle_map)
    if source_pos is None or listener_pos is None:
        return profile

    # Check cache
    source_uid = getattr(source, 'entity_uid', None) or id(source)
    listener_uid = getattr(listener, 'entity_uid', None) or id(listener)
    cache_key = (source_uid, listener_uid, source_pos, listener_pos, id(effective_map or battle_map))
    cached = _acoustic_cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        path = (effective_map or battle_map).squares_in_path(*source_pos, *listener_pos, inclusive=True)
    except Exception:
        return profile

    if not path:
        return profile

    seen_objects = set()
    path_end = len(path) - 1
    for index, square in enumerate(path):
        # Only count obstacles strictly between the speakers — not their own tiles.
        if index == 0 or index == path_end:
            continue

        prev_square = path[index - 1]

        square_is_wall = _path_square_blocks_speech(effective_map or battle_map, square, prev_square)
        if square_is_wall:
            profile['walls'] += 1
            profile['penalty_ft'] += ACOUSTIC_WALL_PENALTY_FT

        try:
            objects = (effective_map or battle_map).objects_at(*square)
        except Exception:
            objects = []

        if _passable_interactable_objects(effective_map or battle_map, square):
            continue

        for obj in objects or []:
            object_id = id(obj)
            if object_id in seen_objects:
                continue
            if _closed_door(obj):
                profile['closed_doors'] += 1
                profile['penalty_ft'] += ACOUSTIC_CLOSED_DOOR_PENALTY_FT
                seen_objects.add(object_id)
                continue
            if square_is_wall:
                seen_objects.add(object_id)
                continue
            if _wall_like_object(obj, origin=prev_square):
                profile['opaque_objects'] += 1
                profile['penalty_ft'] += ACOUSTIC_OPAQUE_OBJECT_PENALTY_FT
                seen_objects.add(object_id)

    if _acoustic_line_blocked(effective_map or battle_map, source_pos, listener_pos):
        if profile['penalty_ft'] <= 0:
            profile['penalty_ft'] += ACOUSTIC_BLOCKED_LINE_PENALTY_FT
            profile['line_blocked'] = True
        else:
            profile['penalty_ft'] += ACOUSTIC_BLOCKED_LINE_SUPPLEMENT_FT
            profile['line_blocked'] = True

    parts = []
    if profile['closed_doors']:
        label = 'closed door' if profile['closed_doors'] == 1 else 'closed doors'
        parts.append(f"{profile['closed_doors']} {label}")
    if profile['walls']:
        label = 'wall tile' if profile['walls'] == 1 else 'wall tiles'
        parts.append(f"{profile['walls']} {label}")
    if profile['opaque_objects']:
        label = 'opaque object' if profile['opaque_objects'] == 1 else 'opaque objects'
        parts.append(f"{profile['opaque_objects']} {label}")
    if profile.get('line_blocked'):
        parts.append('blocked acoustic line')
    profile['summary'] = ', '.join(parts)

    # Store in cache (evict oldest if full)
    if len(_acoustic_cache) >= _ACOUSTIC_CACHE_MAX_SIZE:
        oldest_key = next(iter(_acoustic_cache))
        del _acoustic_cache[oldest_key]
    _acoustic_cache[cache_key] = profile

    return profile


def _entities_in_search_radius(source, battle_map, search_distance, fallback_distances=None):
    try:
        nearby = battle_map.entities_in_range(source, search_distance)
    except Exception:
        nearby = []

    for fallback_distance in fallback_distances or []:
        if nearby or fallback_distance == search_distance:
            continue
        try:
            nearby = battle_map.entities_in_range(source, fallback_distance)
        except Exception:
            nearby = []

    return nearby


def minimum_speech_mode_for(listener, distance_ft):
    for mode in SPEECH_MODE_ORDER:
        if distance_ft <= effective_hearing_distance(listener, SPEECH_BASE_RANGES[mode]):
            return mode
    return None


def conversation_reachability(source, battle_map, mode=None, distance_ft=None, include_source=False, require_conversable=True, battle=None):
    if source is None or battle_map is None:
        return []

    selected_mode = normalize_speech_mode(mode=mode, distance_ft=distance_ft)
    selected_distance = speech_distance_for(mode=selected_mode, distance_ft=distance_ft)
    max_distance = SPEECH_BASE_RANGES['shout']
    search_distance = max_distance + MAX_HEARING_MODIFIER
    source_map = _entity_map_for(source, battle_map, battle=battle)
    stack = getattr(source_map, 'map_stack', None) if source_map else None
    listener_hits = _listeners_in_range(
        source, battle_map, search_distance, battle=battle, require_conversable=require_conversable,
    )

    reachability = []
    if include_source:
        reachability.append({
            'entity': source,
            'distance_ft': 0,
            'effective_distance_ft': selected_distance,
            'passive_perception': passive_perception_for(source),
            'hearing_modifier_ft': hearing_modifier_for(source),
            'reachable_now': True,
            'reachable_with_shout': True,
            'minimum_volume': 'whisper',
            'status': 'self',
        })

    for listener, preset_distance_ft in listener_hits:
        if listener == source:
            continue

        if preset_distance_ft is not None:
            distance_to_source = preset_distance_ft
        else:
            try:
                distance_to_source = battle_map.distance(source, listener) * battle_map.feet_per_grid
            except Exception:
                distance_to_source = selected_distance

        # Early-exit: if raw distance already exceeds the absolute maximum hearing
        # range (shout + best hearing modifier), skip the expensive acoustic profile
        # since penalties can only make it worse.
        max_possible_hearing = SPEECH_BASE_RANGES['shout'] + MAX_HEARING_MODIFIER
        if distance_to_source > max_possible_hearing:
            reachability.append({
                'entity': listener,
                'distance_ft': int(distance_to_source),
                'adjusted_distance_ft': int(distance_to_source),
                'effective_distance_ft': int(effective_hearing_distance(listener, SPEECH_BASE_RANGES['shout'])),
                'passive_perception': passive_perception_for(listener),
                'hearing_modifier_ft': hearing_modifier_for(listener),
                'reachable_now': False,
                'reachable_with_shout': False,
                'minimum_volume': None,
                'status': 'too_far',
                'acoustic_penalty_ft': 0,
                'acoustic_summary': '',
                'closed_doors': 0,
                'walls': 0,
                'opaque_objects': 0,
            })
            continue

        acoustic = acoustic_profile(source, listener, battle_map, battle=battle)
        adjusted_distance = int(distance_to_source + acoustic['penalty_ft'])

        current_effective_distance = effective_hearing_distance(listener, selected_distance)
        minimum_volume = minimum_speech_mode_for(listener, adjusted_distance)
        reachable_now = adjusted_distance <= current_effective_distance
        reachable_with_shout = minimum_volume is not None
        if reachable_now:
            status = 'reachable'
        elif reachable_with_shout:
            status = 'requires_louder_voice'
        else:
            status = 'too_far'

        reachability.append({
            'entity': listener,
            'distance_ft': int(distance_to_source),
            'adjusted_distance_ft': adjusted_distance,
            'effective_distance_ft': int(current_effective_distance),
            'passive_perception': passive_perception_for(listener),
            'hearing_modifier_ft': hearing_modifier_for(listener),
            'reachable_now': reachable_now,
            'reachable_with_shout': reachable_with_shout,
            'minimum_volume': minimum_volume,
            'status': status,
            'acoustic_penalty_ft': acoustic['penalty_ft'],
            'acoustic_summary': acoustic['summary'],
            'closed_doors': acoustic['closed_doors'],
            'walls': acoustic['walls'],
            'opaque_objects': acoustic['opaque_objects'],
        })

    return sorted(reachability, key=lambda entry: (entry['distance_ft'], entity_label(entry['entity']).lower()))


def audible_entities(source, battle_map, distance_ft=None, mode=None, include_source=False, require_conversable=True, battle=None):
    return [
        entry for entry in conversation_reachability(
            source,
            battle_map,
            mode=mode,
            distance_ft=distance_ft,
            include_source=include_source,
            require_conversable=require_conversable,
            battle=battle,
        )
        if entry.get('reachable_now') or entry.get('status') == 'self'
    ]


def _item_display_label(item):
    return (item.get('label') or item.get('name') or 'Unknown item').strip()


def format_entity_gear_for_conversation(entity, session):
    """Summarize equipped gear and carried inventory for NPC dialog prompts."""
    if entity is None:
        return 'None recorded.'

    lines = []
    equipped_keys = set()

    try:
        equipped = list(entity.equipped_items()) if hasattr(entity, 'equipped_items') else []
    except Exception:
        equipped = []

    if equipped:
        lines.append('Equipped:')
        for item in equipped:
            name_key = item.get('name')
            if name_key:
                equipped_keys.add(str(name_key))
            label = _item_display_label(item)
            item_type = item.get('type') or item.get('subtype') or 'item'
            lines.append(f'  - {label} ({item_type})')

    carried = []
    if session is not None and hasattr(entity, 'inventory_items'):
        try:
            inventory = entity.inventory_items(session) or []
        except Exception:
            inventory = []
        for item in inventory:
            name_key = item.get('name')
            if name_key and str(name_key) in equipped_keys:
                continue
            label = _item_display_label(item)
            qty = item.get('qty', 1)
            try:
                qty = int(qty)
            except (TypeError, ValueError):
                qty = 1
            if qty > 1:
                carried.append(f'{label} x{qty}')
            else:
                carried.append(label)

    if carried:
        lines.append('Carried (not equipped):')
        for entry in carried:
            lines.append(f'  - {entry}')

    if not lines:
        return 'Unarmed and carrying nothing.'

    return '\n'.join(lines)


def delivered_conversations(source, message, battle_map, distance_ft=None, mode=None, targets=None, language='common'):
    from natural20.utils.language_comprehension import comprehends_speech

    session = getattr(source, 'session', None) or getattr(battle_map, 'session', None)
    delivered = []
    for audience_entry in audible_entities(source, battle_map, distance_ft=distance_ft, mode=mode):
        listener = audience_entry['entity']
        if comprehends_speech(listener, language, source=source, session=session):
            rendered_message = message
        else:
            rendered_message = gibberish(message, language=language)
        delivered.append({
            'entity': listener,
            'message': rendered_message,
            'directed_to': targets or [],
            'distance_ft': audience_entry['distance_ft'],
            'effective_distance_ft': audience_entry['effective_distance_ft'],
        })
    return delivered