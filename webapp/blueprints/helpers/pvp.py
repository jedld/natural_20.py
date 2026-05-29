"""PvP autofill, team config, and character spawning helpers extracted from app.py.

These functions handle PvP team configuration, character materialization from
sheets, deferred spawning, and battle turn-order autofilling.
"""

import logging

from natural20.player_character import PlayerCharacter

from .runtime_state import (
    get_current_game,
    get_game_session,
    get_index_data,
    get_controllers,
)
from .auth_utils import user_role

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Team config
# ---------------------------------------------------------------------------

def selectable_character_entry(character_name):
    for character in get_index_data().get("selectable_characters", []):
        if character.get('name') == character_name:
            return character
    return None


def pvp_team_config():
    config = get_index_data().get('pvp_teams') or {}
    if config.get('enabled'):
        return config
    return None


def pvp_team_counts():
    config = pvp_team_config()
    if not config:
        return {}

    counts = {team_key: 0 for team_key in config.get('teams', {})}
    for controller in get_controllers():
        if not controller.get('controllers'):
            continue
        team = controller.get('team')
        if team in counts:
            counts[team] += 1
    return counts


# ---------------------------------------------------------------------------
# Character loading
# ---------------------------------------------------------------------------

def ensure_character_entity_loaded(character_name):
    current_game = get_current_game()
    game_session = get_game_session()
    index_data = get_index_data()

    entity = current_game.get_entity_by_uid(character_name)
    if entity is not None:
        return entity

    for map_name, map_obj in current_game.maps.items():
        map_ref = (game_session.game_properties.get('maps') or {}).get(map_name)
        if not map_ref:
            continue

        try:
            map_source = map_obj.load(map_ref)
        except Exception:
            logger.exception(f"Failed to load source map data for {map_name}")
            continue

        for player_def in map_source.get('player') or []:
            overrides = dict(player_def.get('overrides') or {})
            if str(overrides.get('entity_uid')) != str(character_name):
                continue

            sheet = player_def.get('sheet')
            if not sheet:
                continue

            entity = PlayerCharacter.load(game_session, sheet, override=overrides)
            game_session.register_entity(entity)

            if str(character_name) not in current_game.deferred_players:
                current_game.deferred_players[str(character_name)] = {
                    'entity': entity,
                    'map_name': map_name,
                    'position': list(player_def.get('position') or [0, 0]),
                }

            logger.info(f"Materialized selectable character {character_name} from {sheet} on map {map_name}")
            return entity

    # Fallback: use selectable_characters config (sheet + overrides) to load the
    # PC and place it at the next free player_spawn_point on a configured map.
    selectable = selectable_character_entry(character_name) or {}
    sheet = selectable.get('sheet')
    if not sheet:
        return None

    overrides = dict(selectable.get('overrides') or {})
    overrides.setdefault('entity_uid', character_name)

    # Determine candidate maps in order of preference.
    candidate_map_names = []
    explicit_map = selectable.get('map') or index_data.get('player_spawn_map')
    if explicit_map and explicit_map in current_game.maps:
        candidate_map_names.append(explicit_map)
    for map_name in current_game.maps.keys():
        if map_name not in candidate_map_names:
            candidate_map_names.append(map_name)

    chosen_map_name = None
    chosen_slot = None
    for map_name in candidate_map_names:
        map_obj = current_game.maps.get(map_name)
        if map_obj is None or not getattr(map_obj, 'player_spawn_points', None):
            continue
        slot = map_obj.allocate_player_spawn_point(character_name, group=selectable.get('group'))
        if slot is not None:
            chosen_map_name = map_name
            chosen_slot = slot
            break

    if chosen_slot is None:
        logger.warning(f"No free player_spawn_point available for {character_name}")
        return None

    try:
        entity = PlayerCharacter.load(game_session, sheet, override=overrides)
    except Exception:
        # Release slot if PC failed to load so it can be reused.
        current_game.maps[chosen_map_name].release_player_spawn_point(character_name)
        logger.exception(f"Failed to load sheet {sheet} for character {character_name}")
        return None

    game_session.register_entity(entity)
    current_game.deferred_players[str(character_name)] = {
        'entity': entity,
        'map_name': chosen_map_name,
        'position': list(chosen_slot['position']),
        'spawn_point': chosen_slot.get('name'),
    }
    logger.info(
        f"Materialized {character_name} from {sheet} at spawn slot {chosen_slot['position']} on map {chosen_map_name}"
    )
    return entity


# ---------------------------------------------------------------------------
# Team assignment & spawning
# ---------------------------------------------------------------------------

def assign_character_team_and_spawn(character_name, team):
    config = pvp_team_config()
    if not config:
        return None

    teams = config.get('teams', {})
    team_info = teams.get(team)
    if not team_info:
        raise ValueError('Invalid team selection')

    team_label = team_info.get('label', f'Team {team.upper()}')
    spawn_points = team_info.get('spawn_points') or []
    capacity = int(team_info.get('capacity') or len(spawn_points) or 0)
    controllers = get_controllers()
    current_game = get_current_game()
    controller_entry = next((controller for controller in controllers if controller['entity_uid'] == character_name), None)

    used_spawn_points = {
        controller.get('spawn_point')
        for controller in controllers
        if controller.get('controllers')
        and controller.get('team') == team
        and controller.get('entity_uid') != character_name
        and controller.get('spawn_point')
    }

    if capacity and len(used_spawn_points) >= capacity:
        raise ValueError(f'{team_label} is full')

    selected_spawn_point = next((spawn for spawn in spawn_points if spawn not in used_spawn_points), None)
    if selected_spawn_point is None:
        raise ValueError(f'No spawn points remain for {team_label}')

    map_name = team_info.get('map', 'index')
    target_map = current_game.maps.get(map_name)
    if target_map is None:
        raise ValueError(f'PvP map {map_name} is not loaded')

    spawn_meta = target_map.spawn_points.get(selected_spawn_point)
    if spawn_meta is None:
        raise ValueError(f'Spawn point {selected_spawn_point} is not configured on map {map_name}')

    entity = ensure_character_entity_loaded(character_name)
    if entity is None:
        raise ValueError('Character entity not found')

    entity.group = team
    if hasattr(entity, 'properties') and isinstance(entity.properties, dict):
        entity.properties['group'] = team

    deferred = current_game.deferred_players.get(str(character_name))
    if deferred is None:
        entity_map = current_game.get_map_for_entity(entity)
        if entity_map is not None and entity in entity_map.entities:
            entity_map.remove(entity)
        deferred = {
            'entity': entity,
            'map_name': map_name,
            'position': list(spawn_meta['location']),
        }
        current_game.deferred_players[str(character_name)] = deferred

    deferred['map_name'] = map_name
    deferred['position'] = list(spawn_meta['location'])
    deferred['spawn_point'] = selected_spawn_point

    if controller_entry is not None:
        controller_entry['team'] = team
        controller_entry['spawn_point'] = selected_spawn_point

    return {
        'team': team,
        'label': team_label,
        'spawn_point': selected_spawn_point,
    }


def ensure_controller_entry(entity_uid):
    entity_uid = str(entity_uid)
    controllers = get_controllers()
    for controller in controllers:
        if str(controller.get('entity_uid')) == entity_uid:
            controller.setdefault('controllers', [])
            return controller

    controller = {
        'entity_uid': entity_uid,
        'controllers': [],
    }
    controllers.append(controller)
    return controller


def spawn_deferred_entity(entity_uid):
    entity_uid = str(entity_uid)
    current_game = get_current_game()
    deferred = current_game.deferred_players.get(entity_uid)
    if deferred is None:
        return current_game.get_entity_by_uid(entity_uid)

    entity = deferred['entity']
    map_name = deferred['map_name']
    position = list(deferred.get('position') or [0, 0])
    target_map = current_game.maps.get(map_name)
    if target_map is None:
        raise ValueError(f'Map {map_name} is not loaded for deferred entity {entity_uid}')

    pos_x, pos_y = position
    if not target_map.placeable(entity, pos_x, pos_y):
        pos_x, pos_y = target_map.find_empty_placeable_position(entity, pos_x, pos_y)
        logger.info(f"Original position {position} occupied, using {pos_x},{pos_y} for autofilled entity {entity_uid}")

    target_map.place((pos_x, pos_y), entity)
    del current_game.deferred_players[entity_uid]
    logger.info(f"Spawned autofilled entity {entity_uid} at ({pos_x},{pos_y}) on map {map_name}")
    return entity


# ---------------------------------------------------------------------------
# Autofill
# ---------------------------------------------------------------------------

def pvp_autofill_candidates():
    config = pvp_team_config()
    if not config:
        return {}

    teams = {str(team_key).lower(): team_info for team_key, team_info in (config.get('teams') or {}).items()}
    candidates = {team_key: [] for team_key in teams}
    seen = set()
    current_game = get_current_game()

    def add_entity(entity):
        if entity is None or not isinstance(entity, PlayerCharacter):
            return

        entity_uid = str(getattr(entity, 'entity_uid', '') or '')
        if not entity_uid or entity_uid in seen:
            return

        group = getattr(entity, 'group', None)
        if group is None and isinstance(getattr(entity, 'properties', None), dict):
            group = entity.properties.get('group')
        if group is None:
            return

        group = str(group).lower()
        if group not in candidates:
            return

        seen.add(entity_uid)
        ensure_controller_entry(entity_uid).setdefault('team', group)
        candidates[group].append(entity_uid)

    for controller in get_controllers():
        entity_uid = controller.get('entity_uid')
        if not entity_uid:
            continue
        entity = current_game.get_entity_by_uid(entity_uid)
        if entity is None:
            entity = ensure_character_entity_loaded(entity_uid)
        add_entity(entity)

    for battle_map in current_game.maps.values():
        for entity in battle_map.entities:
            add_entity(entity)

    for deferred in current_game.deferred_players.values():
        add_entity(deferred.get('entity'))

    return candidates


def autofill_pvp_battle_turn_order(turn_order):
    config = pvp_team_config()
    if not config or 'dm' not in user_role():
        return turn_order

    teams = {str(team_key).lower(): team_info for team_key, team_info in (config.get('teams') or {}).items()}
    if not teams:
        return turn_order

    current_game = get_current_game()
    augmented_turn_order = []
    present_ids = set()
    team_counts = {team_key: 0 for team_key in teams}

    for item in turn_order or []:
        normalized = dict(item)
        entity_uid = str(normalized.get('id') or '')
        if not entity_uid:
            continue
        normalized['id'] = entity_uid
        group = str(normalized.get('group') or '').lower()
        normalized['group'] = group
        present_ids.add(entity_uid)
        augmented_turn_order.append(normalized)
        if group in team_counts:
            team_counts[group] += 1

    def append_candidate_to_turn_order(entity_uid, team_key, controller_kind=None):
        entity = current_game.get_entity_by_uid(entity_uid)
        if entity is None:
            entity = ensure_character_entity_loaded(entity_uid)
        if entity is None:
            logger.warning(f"Skipping PvP autofill for missing entity {entity_uid}")
            return False

        controller_entry = ensure_controller_entry(entity_uid)
        entity.group = team_key
        if isinstance(getattr(entity, 'properties', None), dict):
            entity.properties['group'] = team_key
        controller_entry['team'] = team_key

        try:
            spawn_deferred_entity(entity_uid)
        except Exception:
            logger.exception(f"Failed to spawn autofilled PvP entity {entity_uid}")
            return False

        turn_order_item = {
            'id': entity_uid,
            'group': team_key,
        }
        if controller_kind:
            turn_order_item['controller'] = controller_kind

        augmented_turn_order.append(turn_order_item)
        present_ids.add(entity_uid)
        team_counts[team_key] += 1
        return True

    candidates = pvp_autofill_candidates()
    for team_key, team_info in teams.items():
        capacity = int(team_info.get('capacity') or len(team_info.get('spawn_points') or []) or 0)
        if capacity <= team_counts.get(team_key, 0):
            continue

        missing_slots = capacity - team_counts[team_key]

        for entity_uid in candidates.get(team_key, []):
            if missing_slots <= 0:
                break
            if entity_uid in present_ids:
                continue

            controller_entry = ensure_controller_entry(entity_uid)
            if not controller_entry.get('controllers'):
                continue

            if append_candidate_to_turn_order(entity_uid, team_key):
                missing_slots -= 1

        for entity_uid in candidates.get(team_key, []):
            if missing_slots <= 0:
                break
            if entity_uid in present_ids:
                continue

            controller_entry = ensure_controller_entry(entity_uid)
            if controller_entry.get('controllers'):
                continue

            if append_candidate_to_turn_order(entity_uid, team_key, controller_kind='llm'):
                missing_slots -= 1
                logger.info(f"Autofilled PvP slot with LLM controller for {entity_uid} on team {team_key}")

    return augmented_turn_order
