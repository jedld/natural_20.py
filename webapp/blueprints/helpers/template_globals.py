"""Template global functions extracted from app.py.

These functions are registered as Jinja2 template globals or filters on
the Flask app.  They are kept here so blueprints can share the same
templates without duplicating registration logic.
"""

from flask import session

from .runtime_state import (
    get_current_game,
    get_controllers,
    get_index_data,
    get_output_logger,
)
from .auth_utils import user_role, logged_in, roles_for_username


# ---------------------------------------------------------------------------
# Control / ownership helpers
# ---------------------------------------------------------------------------

def controller_of(entity_uid, username):
    """Return True if ``username`` currently controls ``entity_uid``."""
    if username == 'dm':
        return True

    current_game = get_current_game()
    entity = current_game.get_entity_by_uid(entity_uid)
    if hasattr(entity, 'owner') and entity.owner:
        entity_uid = entity.owner.entity_uid

    for info in get_controllers():
        if info['entity_uid'].lower() == entity_uid.lower() and username in info['controllers']:
            return True

    return False


def can_rest_for(entity_uid):
    """Template helper: True if the current user may issue rest commands."""
    try:
        if 'dm' in user_role():
            return True
        return controller_of(entity_uid, session.get('username'))
    except Exception:
        return False


def within_talking_distance(entity_uid):
    """Return True if the POV entity is within 2 tiles and has line of sight."""
    current_game = get_current_game()
    current_map = current_game.get_map_for_user(session['username'])
    pov_entity = current_game.get_pov_entity_for_user(session['username'])
    if not pov_entity:
        return False
    return current_map.distance(pov_entity.entity_uid, entity_uid) <= 2 and current_map.can_see(pov_entity, entity_uid)


def entities_controlled_by(username, battle_map=None):
    """Return entities controlled by ``username``."""
    current_game = get_current_game()
    entities = []
    for info in get_controllers():
        if username in info['controllers']:
            entity_uid = info['entity_uid']
            if battle_map:
                entity = battle_map.entity_by_uid(entity_uid)
            else:
                entity = current_game.get_entity_by_uid(entity_uid)

            if entity and entity not in entities:
                entities.append(entity)
                entities.extend(current_game.entities_owned_by(entity))

    return entities


def visible_log_messages_for_username(username, roles=None):
    """Return combat-log messages visible to ``username``."""
    if roles is None:
        roles = roles_for_username(username)
    return get_output_logger().get_all_logs(username=username, roles=roles)


def entity_owners(entity):
    """Return usernames that control ``entity``."""
    from natural20.entity import Entity

    if isinstance(entity, Entity):
        if hasattr(entity, 'owner') and entity.owner:
            entity_uid = entity.owner.entity_uid
        else:
            entity_uid = entity.entity_uid
    else:
        entity_uid = entity

    ctrl_info = next(
        (c for c in get_controllers() if c['entity_uid'] == entity_uid),
        None,
    )
    return [] if not ctrl_info else ctrl_info['controllers']


# ---------------------------------------------------------------------------
# Tile visual helpers
# ---------------------------------------------------------------------------

def opacity_for(tile):
    if tile['hiding']:
        return 0.7
    elif tile['dead']:
        return 0.4
    else:
        return 1.0


def transform_for(tile):
    transforms = []
    entity_size = tile.get('entity_size', None)
    if entity_size == 'medium':
        transforms.append('scale(0.8)')
    if entity_size == 'small':
        transforms.append('scale(0.6)')
    elif entity_size == 'tiny':
        transforms.append('scale(0.3)')

    if tile.get('prone', False):
        transforms.append('rotate(90deg)')
    if len(transforms) > 0:
        return ' '.join(transforms)
    else:
        return 'none'


def filter_for(tile):
    filters = []
    if tile['dead']:
        filters.append('brightness(50%) sepia(100%) hue-rotate(180deg)')
    elif tile['unconscious']:
        filters.append('brightness(50%)')
    elif tile['darkvision_color']:
        filters.append('grayscale(100%)')

    if len(filters) > 0:
        return ' '.join(filters)
    else:
        return 'none'


# ---------------------------------------------------------------------------
# Action display helpers
# ---------------------------------------------------------------------------

def interact_flavors(action):
    from natural20.actions.interact_action import InteractAction
    if isinstance(action, InteractAction):
        if action.object_action == 'give':
            return action.target.profile_image()
    return ""


def action_flavors(action):
    from natural20.actions.attack_action import AttackAction
    from natural20.actions.interact_action import InteractAction
    if isinstance(action, AttackAction):
        if action.second_hand():
            return "_second"
        elif action.unarmed():
            return "_melee"
        elif action.thrown:
            return "_thrown"
        elif action.ranged_attack():
            return "_ranged"
        else:
            return ""
    elif isinstance(action, InteractAction):
        if action.object_action:
            return f"_{action.object_action_name()}"
    return ""


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def ability_mod_str(ability_mod):
    if ability_mod is None:
        return ""
    if ability_mod >= 0:
        return f"+{ability_mod}"
    else:
        return str(ability_mod)


def casting_time(casting_time):
    qty, resource = casting_time.split(":")
    mapping = {
        "action": "A", "reaction": "R", "bonus_action": "B",
        "hour": "H", "minute": "M", "round": "R",
    }
    r_str = mapping.get(resource)
    if r_str is None:
        raise ValueError(f"Invalid casting time: {casting_time}")
    return f"{qty}{r_str}"


def format_languages(entity):
    """Return a display string of languages known by ``entity``, or empty string."""
    langs = []
    try:
        if hasattr(entity, 'languages') and callable(entity.languages):
            langs = entity.languages() or []
    except Exception:
        langs = []
    if not langs:
        props = getattr(entity, 'properties', None) or {}
        langs = props.get('languages') or []
    if isinstance(langs, str):
        langs = [langs]
    formatted = []
    for lang in langs:
        label = str(lang).strip().replace('_', ' ')
        if label:
            formatted.append(label.title())
    # Preserve order while deduplicating (PlayerCharacter.languages already sorts).
    seen = set()
    unique = []
    for label in formatted:
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(label)
    return ', '.join(unique)


def format_game_time(total_seconds):
    """Format game time in seconds to a human-readable format."""
    if total_seconds is None:
        return "0 seconds"
    total_seconds = int(total_seconds)
    days = total_seconds // (24 * 60 * 60)
    hours = (total_seconds % (24 * 60 * 60)) // (60 * 60)
    minutes = (total_seconds % (60 * 60)) // 60
    seconds = total_seconds % 60

    parts = []
    if days > 0:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes > 0:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if seconds > 0 or not parts:
        parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")

    return ', '.join(parts)


def t(key):
    import i18n
    return i18n.t(key)


def describe_terrain(tile):
    """Legacy Jinja helper; tooltips are precomputed in JsonRenderer."""
    from flask import g
    from natural20.web.terrain_tooltip import build_terrain_tooltip

    current_game = get_current_game()
    if not hasattr(g, '_describe_terrain_ctx'):
        g._describe_terrain_ctx = (
            current_game.get_map_for_user(session['username']),
            current_game.get_current_battle(),
        )
    battle_map, battle = g._describe_terrain_ctx
    if tile.get('terrain_tooltip') is not None:
        return tile['terrain_tooltip']
    return build_terrain_tooltip(tile, battle_map, battle)


# ---------------------------------------------------------------------------
# Registration helper — call once from app.py or each blueprint
# ---------------------------------------------------------------------------

def register_template_globals(flask_app):
    """Register all template globals/filters on ``flask_app``."""
    from webapp.blueprints.helpers.action_utils import process_action_hash

    flask_app.add_template_global(controller_of, name='controller_of')
    flask_app.add_template_global(can_rest_for, name='can_rest_for')
    flask_app.add_template_global(within_talking_distance, name='within_talking_distance')
    flask_app.add_template_global(opacity_for, name='opacity_for')
    flask_app.add_template_global(transform_for, name='transform_for')
    flask_app.add_template_global(filter_for, name='filter_for')
    flask_app.add_template_global(action_flavors, name='action_flavors')
    flask_app.add_template_global(entity_owners, name='entity_owners')
    flask_app.add_template_global(format_languages, name='format_languages')
    flask_app.add_template_global(t, name='t')
    flask_app.add_template_global(describe_terrain, name='describe_terrain')
    flask_app.add_template_global(process_action_hash, name='process_action_hash')
    flask_app.add_template_filter(ability_mod_str, name='mod_str')
    flask_app.add_template_filter(casting_time, name='casting_time')
    flask_app.add_template_filter(format_game_time, name='format_game_time')
