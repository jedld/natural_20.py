from flask import Flask, request, jsonify, session, redirect, url_for, render_template, send_file, make_response
from flask_socketio import SocketIO, emit
from flask_session import Session
from flask import send_from_directory
from flask_cors import CORS  # Add CORS support
from natural20.utils.serialization import  object_type_to_klass
import json
import os
import click
import uuid
from fnmatch import fnmatch
from collections import OrderedDict
from PIL import Image
import logging
import importlib
import pdb
import atexit

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    # Try to load from webapp/.env first, then from parent directory
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
    else:
        # Try parent directory
        parent_env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
        if os.path.exists(parent_env_path):
            load_dotenv(parent_env_path)
except ImportError:
    # python-dotenv not installed, continue without it
    pass
from natural20.ai.path_compute import PathCompute
from natural20.ai.pathfinding_cost_map import build_pathfinding_snapshot
from natural20.web.json_renderer import JsonRenderer
from natural20.web.web_controller import WebController, ManualControl
from natural20.actions.attack_action import AttackAction, TwoWeaponAttackAction, LinkedAttackAction
from natural20.actions.move_action import MoveAction
from natural20.actions.second_wind_action import SecondWindAction
from natural20.actions.flurry_of_blows_action import FlurryOfBlowsAction
from natural20.actions.patient_defense_action import PatientDefenseAction
from natural20.actions.step_of_the_wind_action import StepOfTheWindAction
from natural20.actions.feline_agility_action import FelineAgilityAction
from natural20.actions.martial_arts_bonus_attack_action import MartialArtsBonusAttackAction
from natural20.actions.bardic_inspiration_action import BardicInspirationAction
from natural20.actions.wild_shape_action import WildShapeAction, RevertWildShapeAction, WildShapeAttackAction
from natural20.actions.rage_action import RageAction, RecklessAttackAction, EndRageAction
from natural20.actions.disengage_action import DisengageAction, DisengageBonusAction
from natural20.actions.dash import DashAction, DashBonusAction
from natural20.actions.dodge_action import DodgeAction
from natural20.actions.ready_action import ReadyAction
from natural20.actions.prone_action import ProneAction
from natural20.actions.spell_action import SpellAction
from natural20.actions.stand_action import StandAction
from natural20.actions.look_action import LookAction
from natural20.actions.help_action import HelpAction
from natural20.actions.drop_concentration_action import DropConcentrationAction
from natural20.actions.action_surge_action import ActionSurgeAction
from natural20.actions.shove_action import ShoveAction
from natural20.actions.hide_action import HideAction, HideBonusAction
from natural20.actions.first_aid_action import FirstAidAction
from natural20.actions.grapple_action import GrappleAction, DropGrappleAction
from natural20.actions.escape_grapple_action import EscapeGrappleAction
from natural20.actions.lay_on_hands_action import LayOnHandsAction
from natural20.actions.use_item_action import UseItemAction
from natural20.actions.interact_action import InteractAction
from natural20.actions.summon_familiar_action import SummonFamiliarAction
from natural20.actions.mage_hand_action import MageHandAction
from natural20.actions.find_familiar_action import FindFamiliarAction
from natural20.spell.extensions.hit_computations import AttackSpell
from natural20.entity import Entity
from natural20.action import Action, AsyncReactionHandler
from natural20.battle import Battle
from natural20.item_library.object import Object
from natural20.utils.movement import Movement
from natural20.generic_controller import GenericController
from natural20.llm_controller import LlmMcpController
import natural20.session as GameSession
from natural20.event_manager import EventManager
from natural20.player_character import PlayerCharacter
from natural20.utils.conversation import (
    audible_entities,
    entity_label,
    mention_handle_for,
    normalize_speech_mode,
    resolve_named_targets,
    resolve_mention_targets,
    speech_distance_for,
    unique_entities,
)
from natural20.utils.gibberish import gibberish

from natural20.utils.action_builder import acquire_targets
from natural20.dm import DungeonMaster
from natural20.die_roll import DieRoll
import random
import optparse
import pdb
import i18n
import yaml
import time
import uuid
from utils import SocketIOOutputLogger, GameManagement
from datetime import datetime
from webapp.llm_conversation_controller import LLMConversationController
from webapp.llm_handler import (
    LLMHandler,
    LlamaCppProvider,
    llm_handler,
    read_npc_system_prompt,
    set_campaign_prompt_root,
)
import threading
import pdb
import traceback
from webapp.game_context import GameContextProvider
from webapp.conversation_service import ConversationService, register_conversation_routes
from webapp.entity_rag_handler import EntityRAGHandler
from webapp.mcp import MCPContext, register_mcp_blueprint
from webapp.dndbeyond_import import (
    import_character_from_dndbeyond,
    parse_character_id_from_url,
    prepare_imported_pc_dict,
)
import requests
import re
from PIL import Image, ImageDraw
import io

app = Flask(__name__, static_folder='static', static_url_path='/')
app.config['CHARACTER_BUILDER_ONLY'] = os.environ.get('CHARACTER_BUILDER_ONLY', 'false').lower() == 'true'

# In-process per-user LRU cache for /path responses; bounded to keep memory
# flat under sustained mouse hover.
_PATH_RESPONSE_CACHE = {}
_PATH_RESPONSE_CACHE_LIMIT = 256

# Memoize a per-(map, entity, battle) difficult-terrain lookup. Keyed by the
# Python id() of the map plus the entity uid; invalidated implicitly when the
# map object changes (e.g. on level/map switch).
_DIFFICULT_TERRAIN_CACHE = {}

def _difficult_terrain_lookup(battle_map, entity, battle):
    """Return a callable(x, y) -> bool with per-tile memoization."""
    entity_uid = None
    try:
        eu = getattr(entity, 'entity_uid', None)
        entity_uid = eu() if callable(eu) else eu
    except Exception:
        entity_uid = None
    key = (id(battle_map), entity_uid, id(battle))
    bucket = _DIFFICULT_TERRAIN_CACHE.get(key)
    if bucket is None:
        bucket = {}
        # Cap dictionary count to avoid unbounded growth across maps.
        if len(_DIFFICULT_TERRAIN_CACHE) > 32:
            _DIFFICULT_TERRAIN_CACHE.clear()
        _DIFFICULT_TERRAIN_CACHE[key] = bucket
    def _lookup(x, y):
        k = (x, y)
        v = bucket.get(k)
        if v is None:
            v = bool(battle_map.difficult_terrain(entity, x, y, battle))
            bucket[k] = v
        return v
    return _lookup


# Enable response compression (gzip/brotli) for HTML/JSON/JS/CSS.
try:
    from flask_compress import Compress
    app.config.setdefault('COMPRESS_MIMETYPES', [
        'text/html', 'text/css', 'text/xml', 'text/plain',
        'application/json', 'application/javascript', 'application/xml',
        'image/svg+xml',
    ])
    app.config.setdefault('COMPRESS_LEVEL', 6)
    app.config.setdefault('COMPRESS_MIN_SIZE', 500)
    # Disable streaming compression: flask-compress 1.24 has a bug where the
    # streaming path calls `compressor.process()` which doesn't exist, breaking
    # send_file/send_from_directory responses (e.g. /styles.css, bootstrap).
    app.config.setdefault('COMPRESS_STREAMS', False)
    Compress(app)
except ImportError:
    logging.getLogger(__name__).warning("Flask-Compress not installed; responses will not be compressed")


# Allow browsers to cache static assets (action icons, token sprites, map
# PNGs, JS, CSS). Without this, Flask defaults to `Cache-Control: no-cache`,
# forcing a conditional GET on every asset on every action-bar reveal /
# tile click. Over high-RTT links (e.g. ngrok) that round-trips dominate
# perceived UI latency in Firefox especially. JS/CSS already use
# `?salt=<hash>` cache-busting so a long max-age is safe; image assets
# rarely change at runtime. Override via N20_STATIC_MAX_AGE.
try:
    _static_max_age = int(os.environ.get('N20_STATIC_MAX_AGE', 60 * 60 * 24))
except (TypeError, ValueError):
    _static_max_age = 60 * 60 * 24
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = _static_max_age


def _env_flag(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return str(value).strip().lower() not in {'0', 'false', 'no', 'off', 'disabled'}


app.config['SPECIAL_EFFECTS_ENABLED'] = _env_flag('SPECIAL_EFFECTS_ENABLED', False)
app.config['NPC_LLM_COMBAT_ENABLED'] = _env_flag('NPC_LLM_COMBAT_ENABLED', False)

HEAVY_SPECIAL_EFFECTS = frozenset({'fog', 'rain', 'snow', 'water', 'point_fire'})

# Determine if we're running in AWS or locally
is_aws = os.environ.get('AWS_ENVIRONMENT', 'false').lower() == 'true'
is_production = os.environ.get('FLASK_ENV', 'development') == 'production'

logger = logging.getLogger('werkzeug')
logger.setLevel(logging.INFO)
# Configure CORS for the Flask app based on environment variables
def get_allowed_origins():
    """Get allowed origins from environment variables or use defaults."""
    
    # Check for explicit CORS origins configuration
    cors_origins = os.environ.get('CORS_ORIGINS')
    if cors_origins:
        # Parse comma-separated list of origins
        origins = [origin.strip() for origin in cors_origins.split(',') if origin.strip()]
        logger.info(f"Using CORS origins from environment: {origins}")
        return origins
    
    # Fallback to environment-based defaults
    if is_aws or is_production:
        # In AWS/production, allow the ALB domain and any subdomains
        default_origins = [
            "http://natural20-alb-1402295348.us-east-1.elb.amazonaws.com",
            "https://natural20-alb-1402295348.us-east-1.elb.amazonaws.com",
            "https://0ad1d39fb719.ngrok.app",
            "https://*.ngrok-free.dev",
            "http://*.ngrok-free.dev",
            "*"  # Fallback to allow all origins in production
        ]
    else:
        # In local development, allow localhost origins and common ngrok patterns
        default_origins = [
            "http://localhost:5000", 
            "http://127.0.0.1:5000", 
            "http://localhost:5001", 
            "http://127.0.0.1:5001",
            "https://0ad1d39fb719.ngrok.app",
            # Add common ngrok patterns
            "https://*.ngrok.io",
            "https://*.ngrok-free.app",
            "https://*.ngrok-free.dev",
            "http://*.ngrok.io",
            "http://*.ngrok-free.app",
            "http://*.ngrok-free.dev"
        ]
    
    logger.info(f"Using default CORS origins for {'production' if (is_aws or is_production) else 'development'}: {default_origins}")
    return default_origins


def origin_allowed(origin, allowed_origins):
    if not origin:
        return False

    normalized_origin = origin.lower()
    for allowed_origin in allowed_origins:
        candidate = str(allowed_origin).strip().lower()
        if not candidate:
            continue
        if candidate == '*':
            return True
        if candidate == normalized_origin:
            return True
        if '*' in candidate and fnmatch(normalized_origin, candidate):
            return True

    return False

allowed_origins = get_allowed_origins()

CORS(app, resources={r"/*": {"origins": allowed_origins, "supports_credentials": True}})

app.config['SECRET_KEY'] = 'fe9707b4704da2a96d0fd3cbbb465756e124b8c391c72a27ff32a062110de589'
app.config['SESSION_TYPE'] = 'filesystem'

if is_aws or is_production:
    async_mode = 'eventlet'
else:
    async_mode = 'threading'

# Configure Socket.IO with proper settings
socketio = SocketIO(app, 
    cors_allowed_origins=lambda origin, environ=None: origin_allowed(origin, allowed_origins),
    async_mode=async_mode,  # Use eventlet for WebSocket support
    ping_timeout=120,  # Increased timeout
    ping_interval=30,  # Increased interval
    max_http_buffer_size=1e8,
    logger=True,
    engineio_logger=True,
    manage_session=True,
    cookie='io',
    always_connect=True,
    message_queue=None,  # Disable message queue since we're using a single worker
    # Add ngrok-specific settings
    transports=['websocket', 'polling'],  # Allow both WebSocket and polling
    allow_upgrades=True,
    upgrade_timeout=10
)
Session(app)


def builder_only_mode():
    return app.config.get('CHARACTER_BUILDER_ONLY', False)


def special_effects_enabled():
    return bool(app.config.get('SPECIAL_EFFECTS_ENABLED', False))


def is_heavy_special_effect(effect_name):
    return effect_name in HEAVY_SPECIAL_EFFECTS


def filter_effect_payload(payload, stop_when_disabled=False):
    if not isinstance(payload, dict):
        return None

    effect_name = payload.get('effect')
    if special_effects_enabled() or not is_heavy_special_effect(effect_name):
        return dict(payload)

    if stop_when_disabled and effect_name:
        return {'effect': effect_name, 'action': 'stop'}

    return None


def filter_effect_payloads(payloads):
    filtered_payloads = []
    for payload in payloads or []:
        filtered = filter_effect_payload(payload)
        if filtered:
            filtered_payloads.append(filtered)
    return filtered_payloads


def has_enabled_effect_payloads(payloads):
    return bool(filter_effect_payloads(payloads))


def map_default_effect_payloads(battle_map):
    props = getattr(battle_map, 'properties', {}) or {}
    effect_defs = []
    payloads = []

    try:
        if isinstance(props.get('default_effects'), (list, tuple)):
            effect_defs.extend(props.get('default_effects') or [])
    except Exception:
        pass

    try:
        default_effect = props.get('default_effect')
        if default_effect:
            if isinstance(default_effect, (list, tuple)):
                effect_defs.extend(list(default_effect))
            else:
                effect_defs.append(default_effect)
    except Exception:
        pass

    for effect_def in effect_defs:
        try:
            payload = dict(effect_def)
        except Exception:
            continue
        payload['exclusive'] = False
        filtered = filter_effect_payload(payload)
        if filtered:
            payloads.append(filtered)

    return payloads


def point_fire_effect_payload(battle_map):
    props = getattr(battle_map, 'properties', {}) or {}
    point_fires = props.get('point_fires') or props.get('point_fire')

    if point_fires and isinstance(point_fires, (list, tuple)):
        return filter_effect_payload({
            'effect': 'point_fire',
            'action': 'start',
            'config': {'points': point_fires},
            'exclusive': False,
        }, stop_when_disabled=True)

    return {'effect': 'point_fire', 'action': 'stop'}


@socketio.on('connect')
def _on_connect():
    # When a client connects, send any active effects for the current game so
    # a page refresh or new client receives the same visual state.
    try:
        game_key = getattr(current_game.game_session, 'root_path', None) or getattr(game_session, 'root_path', None) or LEVEL
        effects = filter_effect_payloads(active_effects.get(game_key, {}).values())
        if effects:
            for payload in effects:
                emit('effect:set', payload)
        else:
            # No global DM override; first try per-map overrides
            try:
                username = session.get('username')
                if username:
                    cur_map = current_game.get_map_for_user(username)
                else:
                    try:
                        cur_map = current_game.get_map_for_user(None)
                    except Exception:
                        cur_map = current_game.get_current_battle_map()
                cur_name = getattr(cur_map, 'name', None)
                map_overrides = filter_effect_payloads(active_effects_map.get(game_key, {}).get(cur_name, {}).values())
                if map_overrides:
                    for payload in map_overrides:
                        emit('effect:set', payload)
                else:
                    for payload in map_default_effect_payloads(cur_map):
                        emit('effect:set', payload)
            except Exception:
                pass
    except Exception:
        pass

LEVEL = os.getenv('TEMPLATE_DIR', "../templates")

# Load level settings from JSON file
with open(os.path.join(LEVEL, 'index.json')) as f:
    index_data = json.load(f)

TITLE = index_data["title"]
TILE_PX = int(index_data["tile_size"])



LOGIN_BACKGROUND = index_data["login_background"]
CHARACTER_SELECTION_BACKGROUND = index_data.get("character_selection_background", index_data["login_background"])
BATTLEMAP = index_data["map"]
OTHERMAPS = index_data.get("other_maps", {})
SOUNDTRACKS = index_data["soundtracks"]
LOGINS = index_data["logins"]
DEFAULT_NPC_CONTROLLER = index_data.get("npc_default_controller", "ai")
CONTROLLERS = index_data["default_controllers"]
AUTOSAVE = index_data.get("autosave", False)
DEFER_PLAYER_SPAWN = index_data.get("defer_player_spawn", False)
EXTENSIONS = []
first_connect = False

if 'extensions' in index_data:
    for extension in index_data['extensions']:
        # load extension and import extension from the extensions folder
        extension_name = extension['name']
        # import extensionfrom natural20.actions.dismiss_familiar_action import DismissFamiliarAction

sockets = []
MAP_PADDING = [6, 15]

# Persistent in-memory active effects per game key (global overrides) and per-map overrides
active_effects = {}
active_effects_map = {}

# Health check endpoint for container orchestration
@app.route('/health')
def health():
    return jsonify({"status": "ok"}), 200

output_logger = SocketIOOutputLogger(socketio)
output_logger.log("Server started", visibility='public')

event_manager = EventManager(output_logger=output_logger, movement_consolidation=True)
event_manager.standard_cli()

def _emit_narration_overlay(event):
    narration = event.get('narration') or {}
    entry = narration.get('on_enter') or {}
    if not entry.get('text'):
        return
    map_name = event.get('map_name')
    if not map_name:
        source = event.get('source')
        if source is not None:
            try:
                resolved_map = game_session.map_for(source)
                if resolved_map is not None:
                    map_name = resolved_map.name
            except Exception:
                map_name = None
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
        _record_narration_for_pcs(
            narration,
            map_name=map_name,
            target_uids=target_uids,
            source=source_uid,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug(f"Failed to record narration in journals: {exc}")

event_manager.register_event_listener('narration', _emit_narration_overlay)


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
        game = globals().get('current_game')
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
    game = globals().get('current_game')
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
    game = globals().get('current_game')
    sent = False
    if game and usernames:
        sid_map = getattr(game, 'username_to_sid', {}) or {}
        for username in usernames:
            for sid in sid_map.get(username, []) or []:
                socketio.emit('message', payload, to=sid)
                sent = True
    if not sent:
        socketio.emit('message', payload)


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


event_manager.register_event_listener('control_override_added', _on_control_override_added)
event_manager.register_event_listener('control_override_removed', _on_control_override_removed)
event_manager.register_event_listener('turn_skipped', _on_turn_skipped)

game_session = GameSession.Session(LEVEL, event_manager=event_manager)
game_session.render_for_text = False # render for text is disabled since we are using a web renderer
current_soundtrack = None



current_game = GameManagement(game_session=game_session,
                              map_location=BATTLEMAP,
                              other_maps=OTHERMAPS,
                              socketio=socketio,
                              output_logger=output_logger,
                              tile_px=TILE_PX,
                              controllers=CONTROLLERS,
                              npc_controller=DEFAULT_NPC_CONTROLLER,
                              force_llm_npc_combat=app.config['NPC_LLM_COMBAT_ENABLED'],
                              autosave=AUTOSAVE,
                              system_logger=logger,
                              soundtrack=SOUNDTRACKS,
                              defer_player_spawn=DEFER_PLAYER_SPAWN)

# Enable PvP-style auto-battle triggers (proximity / line-of-sight) only when
# the loaded campaign declares PvP teams. Non-PvP campaigns keep combat
# manual unless an entity takes an actually aggressive action.
_pvp_cfg = index_data.get('pvp_teams') or {}
current_game.pvp_enabled = bool(_pvp_cfg.get('enabled'))

output_logger.configure_persistence(
    campaign_log_db_getter=lambda: getattr(current_game, 'campaign_log_db', None)
)


@app.before_request
def _n20_bind_campaign_prompt_root():
    """Per-request campaign directory for DM/NPC LLM prompt file overrides."""
    try:
        gs = getattr(current_game, 'game_session', None)
        rp = getattr(gs, 'root_path', None) if gs else None
        set_campaign_prompt_root(rp)
    except Exception:
        set_campaign_prompt_root(None)

# ── MCP tool surface ──────────────────────────────────────────────────────
# Expose the running game over a small HTTP/JSON tool surface under
# ``/mcp/*`` so an external LLM acting as DM can inspect, mutate and
# drive entities. See ``webapp/mcp/__init__.py`` for the module layout.
_mcp_context = MCPContext(
    game_session_getter=lambda: game_session,
    current_game_getter=lambda: current_game,
    socketio_getter=lambda: socketio,
    output_logger_getter=lambda: output_logger,
    action_class_resolver=lambda action_type: action_type_to_class(action_type),
)
from webapp.mcp import build_default_registry as _mcp_build_default_registry
_mcp_registry = _mcp_build_default_registry()
try:
    register_mcp_blueprint(app, _mcp_context, registry=_mcp_registry,
                           user_role_fn=lambda: user_role())
except Exception as _mcp_exc:  # noqa: BLE001 - never block app startup on MCP wiring
    logger.warning(f"Failed to register MCP blueprint: {_mcp_exc}")

# Ensure pending saves are flushed on process exit
def _shutdown_flush():
    try:
        getattr(current_game, 'shutdown_save_worker', lambda timeout=2.0: None)(timeout=3.0)
    except Exception:
        pass

atexit.register(_shutdown_flush)

# ── Battle-end campaign narration ─────────────────────────────────────────
# When a battle ends, surface campaign-flavored narration to the players.
# The text comes from the loaded campaign's ``game.yml`` under either
# ``tpk_narration`` (when the party is wiped) or ``victory_narration`` (when
# the players win). Each section may provide a ``default`` block and/or a
# ``by_map`` map keyed by the battle's map name.
def _select_outcome_narration(battle, outcome):
    """Look up campaign narration for the given outcome ('tpk' | 'victory').

    Returns a narration dict shaped like the standard narration overlay
    payload, or ``None`` if the campaign has not declared one for this
    outcome/map combination.
    """
    try:
        properties = getattr(game_session, 'game_properties', None) or {}
    except Exception:
        properties = {}
    key = 'tpk_narration' if outcome == 'tpk' else 'victory_narration'
    section = properties.get(key) or {}
    if not isinstance(section, dict):
        return None, None

    map_name = None
    try:
        battle_map = current_game.get_current_battle_map()
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


def _on_battle_end_narrate(game_manager, session):
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
        socketio.emit('message', {
            'type': 'narration',
            'message': narration,
            'map_name': map_name,
        })
    except Exception as exc:  # pragma: no cover - socket emit best-effort
        logger.warning(f"Failed to emit battle-end narration: {exc}")
        return False
    try:
        _record_narration_for_pcs(narration, map_name=map_name)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug(f"Failed to record battle-end narration: {exc}")
    return True


current_game.register_event_handler('on_battle_end', _on_battle_end_narrate)

# Initialize game context provider for LLM RAG
game_context_provider = GameContextProvider(game_session, current_game)
llm_conversation_handler = None

# Register game context functions with the LLM handler
def register_game_context_functions():
    """Register all game context functions with the LLM handler."""
    llm_handler.register_game_context_function(
        "get_map_info",
        game_context_provider.get_map_info,
        "Get current map information including terrain, layout, and basic details"
    )
    
    llm_handler.register_game_context_function(
        "get_entities",
        game_context_provider.get_entities,
        "Get all entities on the current map with their positions and basic information"
    )
    
    llm_handler.register_game_context_function(
        "get_player_characters",
        game_context_provider.get_player_characters,
        "Get information about player characters on the current map"
    )
    
    llm_handler.register_game_context_function(
        "get_npcs",
        game_context_provider.get_npcs,
        "Get information about NPCs on the current map"
    )
    
    # Create a proxy for get_entity_details that can handle function calling
    def get_entity_details_proxy(*args, **kwargs):
        """Proxy function for get_entity_details that can handle function calling."""
        return game_context_provider.get_entity_details(*args, **kwargs)
    
    llm_handler.register_game_context_function(
        "get_entity_details",
        get_entity_details_proxy,
        "Get detailed information about a specific entity by name"
    )
    
    llm_handler.register_game_context_function(
        "get_battle_status",
        game_context_provider.get_battle_status,
        "Get current battle information if combat is active"
    )

    # ── MCP bridge ────────────────────────────────────────────────────
    # Expose the full MCP tool registry to the DM AI assistant so it
    # uses the same tool surface as external MCP clients. The model
    # invokes [FUNCTION_CALL: mcp("tool.name", {"k": "v"})]. The bridge
    # delegates to the shared ToolRegistry and unwraps the MCP envelope.
    def mcp_call_bridge(tool_name, arguments=None):
        """Invoke an MCP tool by name and return its JSON payload (or error text)."""
        if isinstance(arguments, str):
            import json as _json
            try:
                arguments = _json.loads(arguments) if arguments.strip() else {}
            except Exception as exc:
                return f"Invalid JSON arguments: {exc}"
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return f"Arguments must be a JSON object, got: {type(arguments).__name__}"

        # Compatibility alias: several models emit `entity_name` for DM tools
        # that actually require `entity_uid`. Resolve it from live entities,
        # including fuzzy matching for minor typos.
        manifest = next((m for m in _mcp_registry.list() if m.get('name') == tool_name), None)
        input_schema = (manifest or {}).get('inputSchema') or {}
        schema_props = input_schema.get('properties') or {}
        needs_entity_uid = 'entity_uid' in schema_props
        if needs_entity_uid and not arguments.get('entity_uid') and isinstance(arguments.get('entity_name'), str):
            raw_name = arguments.get('entity_name', '').strip()
            if raw_name:
                import difflib as _difflib

                candidates = []  # [(uid, name_key), ...]
                seen_uids = set()
                cg = _mcp_context.current_game
                for battle_map in (getattr(cg, 'maps', {}) or {}).values():
                    for ent in (getattr(battle_map, 'entities', {}) or {}).keys():
                        uid = str(getattr(ent, 'entity_uid', '') or '').strip()
                        if not uid or uid in seen_uids:
                            continue
                        seen_uids.add(uid)
                        label = str((ent.label() if hasattr(ent, 'label') else getattr(ent, 'name', '')) or '').strip()
                        name = str(getattr(ent, 'name', '') or '').strip()
                        keys = [uid, label, name]
                        for key in keys:
                            if key:
                                candidates.append((uid, key.lower()))

                query = raw_name.lower()
                # Exact first
                exact = [uid for uid, key in candidates if key == query]
                resolved_uid = exact[0] if exact else None
                # Then substring match
                if resolved_uid is None:
                    contains = [uid for uid, key in candidates if query in key]
                    if len(contains) == 1:
                        resolved_uid = contains[0]
                # Finally fuzzy match
                if resolved_uid is None:
                    all_keys = sorted(set(key for _, key in candidates))
                    match = _difflib.get_close_matches(query, all_keys, n=1, cutoff=0.78)
                    if match:
                        for uid, key in candidates:
                            if key == match[0]:
                                resolved_uid = uid
                                break

                if resolved_uid:
                    arguments['entity_uid'] = resolved_uid
                else:
                    return f"MCP error: Could not resolve entity_name '{raw_name}' to an entity_uid"

        # Compatibility aliases: some models emit `target_uid` or
        # `near_entity` for the *_near tools. Normalize to the expected
        # fields used by the MCP schema.
        if tool_name in ('dm.spawn_npc_near', 'dm.spawn_object_near'):
            if (arguments.get('target_entity_uid') is None and
                    isinstance(arguments.get('target_uid'), str) and
                    arguments.get('target_uid').strip()):
                arguments['target_entity_uid'] = arguments.pop('target_uid').strip()
            if (arguments.get('target_name') is None and
                    arguments.get('target_entity_uid') is None and
                    isinstance(arguments.get('near_entity'), str) and
                    arguments.get('near_entity').strip()):
                arguments['target_name'] = arguments.pop('near_entity').strip()

        # Guardrail: models sometimes hallucinate map_name="Unknown" when
        # context extraction fails. For spawn tools, normalize that to the
        # active map instead of hard-failing.
        if tool_name in ('dm.spawn_npc', 'dm.spawn_object'):
            map_name = arguments.get('map_name')
            if isinstance(map_name, str) and map_name.strip().lower() in ('unknown', 'none', 'null', ''):
                arguments.pop('map_name', None)

        envelope = _mcp_registry.call(tool_name, arguments, context=_mcp_context)
        if envelope.get('isError'):
            for item in envelope.get('content') or []:
                if item.get('type') == 'text':
                    return f"MCP error: {item.get('text')}"
            return "MCP error (unknown)"
        for item in envelope.get('content') or []:
            if item.get('type') == 'json':
                return item.get('json')
        return envelope

    llm_handler.register_game_context_function(
        "mcp",
        mcp_call_bridge,
        "Invoke any MCP tool by name. Args: tool_name (str), arguments (JSON object). "
        "Use this in preference to the legacy get_* functions for richer data."
    )
    # Stash the shared registry on the function-info dict so the LLM
    # system prompt can enumerate the *real* tool catalogue instead of
    # advertising hand-curated examples that may not exist.
    if 'mcp' in llm_handler.game_context_functions:
        llm_handler.game_context_functions['mcp']['mcp_registry'] = _mcp_registry

# NOTE: do NOT call register_game_context_functions() here. The module-level
# `llm_handler` is reassigned below by initialize_llm_from_env(); any
# registrations on the imported singleton would be lost when that fresh
# instance shadows the name. Registration happens after the reassignment.

i18n.set('locale', 'en')

# initialize all extensiond
for extension in EXTENSIONS:
    extension.init(app, current_game, game_session)

def configure_llm_handler_from_environment(handler: LLMHandler) -> bool:
    """Apply ``LLM_PROVIDER`` and related env vars to an existing handler.

    Used at process startup and when the DM UI asks to sync from server config.
    Returns True if a provider was initialized successfully.
    """
    llm_provider = os.environ.get('LLM_PROVIDER', 'llama_cpp').lower()

    if llm_provider == 'openai':
        api_key = os.environ.get('OPENAI_API_KEY')
        base_url = os.environ.get('OPENAI_BASE_URL')
        model = os.environ.get('OPENAI_MODEL', 'gpt-4o')

        if not api_key:
            logger.warning("OPENAI_API_KEY not set, LLM features will be disabled")
            return False

        config = {'api_key': api_key, 'model': model}
        if base_url:
            config['base_url'] = base_url

        success = handler.initialize_provider('openai', config)
        if success:
            logger.info(f"Initialized OpenAI provider with model: {model}")
        else:
            logger.error("Failed to initialize OpenAI provider")
        return success

    if llm_provider == 'anthropic':
        api_key = os.environ.get('ANTHROPIC_API_KEY')
        model = os.environ.get('ANTHROPIC_MODEL', 'claude-3-5-sonnet-20241022')

        if not api_key:
            logger.warning("ANTHROPIC_API_KEY not set, LLM features will be disabled")
            return False

        config = {'api_key': api_key, 'model': model}
        success = handler.initialize_provider('anthropic', config)
        if success:
            logger.info(f"Initialized Anthropic provider with model: {model}")
        else:
            logger.error("Failed to initialize Anthropic provider")
        return success

    if llm_provider == 'ollama':
        base_url = os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434')
        model = os.environ.get('OLLAMA_MODEL', 'gemma3:27b')
        config = {'base_url': base_url, 'model': model}
        success = handler.initialize_provider('ollama', config)
        if success:
            logger.info(f"Initialized Ollama provider with model: {model} at {base_url}")
        else:
            logger.error(f"Failed to initialize Ollama provider: {config}")
        return success

    if llm_provider in ('llama_cpp', 'llama.cpp', 'llamacpp'):
        base_url = os.environ.get('LLAMA_CPP_BASE_URL', 'http://localhost:8011')
        model = os.environ.get('LLAMA_CPP_MODEL', os.environ.get('N20_LLM_MODEL'))
        api_key = os.environ.get('LLAMA_CPP_API_KEY', 'llama-cpp')

        config = {'base_url': base_url, 'api_key': api_key}
        if model:
            config['model'] = model

        success = handler.initialize_provider('llama_cpp', config)
        if success:
            logger.info(
                f"Initialized llama.cpp provider with model: "
                f"{getattr(handler.current_provider, 'current_model', model)} at {base_url}"
            )
        else:
            logger.error(f"Failed to initialize llama.cpp provider: {config}")
        return success

    logger.warning(f"Unknown LLM provider: {llm_provider}, using mock provider")
    return handler.initialize_provider('mock', {})


def initialize_llm_from_env():
    """Construct a handler and configure it from environment variables."""
    llm_handler = LLMHandler()
    configure_llm_handler_from_environment(llm_handler)
    return llm_handler

# Initialize LLM handler from environment variables
llm_handler = initialize_llm_from_env()
# Register game-context + MCP bridge functions on the *active* handler.
register_game_context_functions()
llm_conversation_handler = LLMConversationController(llm_handler)

# Initialize Entity RAG Handler
entity_rag_handler = EntityRAGHandler(game_session, current_game)


def logged_in():
    if builder_only_mode():
        if 'username' not in session:
            session['username'] = 'builder'
        return True
    return session.get('username') is not None

def roles_for_username(username):
    if builder_only_mode():
        return ['dm']
    if not username:
        return []
    login_info = next((login for login in LOGINS if login["name"].lower() == username), None)
    return login_info["role"] if login_info else []

def user_role():
    return roles_for_username(session.get('username'))


def selectable_character_entry(character_name):
    for character in index_data.get("selectable_characters", []):
        if character.get('name') == character_name:
            return character
    return None


def pvp_team_config():
    config = index_data.get('pvp_teams') or {}
    if config.get('enabled'):
        return config
    return None


def pvp_team_counts():
    config = pvp_team_config()
    if not config:
        return {}

    counts = {team_key: 0 for team_key in config.get('teams', {})}
    for controller in CONTROLLERS:
        if not controller.get('controllers'):
            continue
        team = controller.get('team')
        if team in counts:
            counts[team] += 1
    return counts


def ensure_character_entity_loaded(character_name):
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
    controller_entry = next((controller for controller in CONTROLLERS if controller['entity_uid'] == character_name), None)

    used_spawn_points = {
        controller.get('spawn_point')
        for controller in CONTROLLERS
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
    for controller in CONTROLLERS:
        if str(controller.get('entity_uid')) == entity_uid:
            controller.setdefault('controllers', [])
            return controller

    controller = {
        'entity_uid': entity_uid,
        'controllers': [],
    }
    CONTROLLERS.append(controller)
    return controller


def spawn_deferred_entity(entity_uid):
    entity_uid = str(entity_uid)
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


def pvp_autofill_candidates():
    config = pvp_team_config()
    if not config:
        return {}

    teams = {str(team_key).lower(): team_info for team_key, team_info in (config.get('teams') or {}).items()}
    candidates = {team_key: [] for team_key in teams}
    seen = set()

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

    for controller in CONTROLLERS:
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


def controller_of(entity_uid, username):
    if username == 'dm':
        return True

    entity = current_game.get_entity_by_uid(entity_uid)
    if hasattr(entity, 'owner') and entity.owner:
        entity_uid = entity.owner.entity_uid

    for info in CONTROLLERS:
        if info['entity_uid'].lower() == entity_uid.lower() and username in info['controllers']:
            return True

    logger.info(f"controller_of: {entity_uid} {username} missing")
    return False

app.add_template_global(controller_of, name='controller_of')

def can_rest_for(entity_uid):
    """Template helper: True if the current user may issue rest commands for entity."""
    try:
        if 'dm' in user_role():
            return True
        return controller_of(entity_uid, session.get('username'))
    except Exception:
        return False
app.add_template_global(can_rest_for, name='can_rest_for')

def within_talking_distance(entity_uid):
    current_map = current_game.get_map_for_user(session['username'])
    pov_entity = current_game.get_pov_entity_for_user(session['username'])
    if not pov_entity:
        return False
    return current_map.distance(pov_entity.entity_uid, entity_uid) <= 2 and current_map.can_see(pov_entity, entity_uid)
app.add_template_global(within_talking_distance, name='within_talking_distance')

# -----------------------
# Admin save/load endpoints (DM only)
# -----------------------

@app.route('/admin/saves', methods=['GET'])
def list_saves():
    if not session.get('username'):
        return jsonify(error='Unauthorized'), 401
    if 'dm' not in user_role():
        return jsonify(error='Forbidden'), 403
    saves = []
    try:
        save_dir = getattr(current_game, 'save_dir', os.getcwd())
        for fname in current_game.list_states():
            try:
                path = fname if os.path.isabs(fname) else os.path.join(save_dir, fname)
                mtime = os.path.getmtime(path)
                size = os.path.getsize(path)
            except Exception:
                mtime = None
                size = None
            saves.append({
                'filename': fname,
                'mtime': mtime,
                'size': size,
            })
        # Include any additional save_* files not in list_states, for named saves
        try:
            for f in os.listdir(save_dir):
                if f.startswith('save_') and (f.endswith('.yml') or f.endswith('.yml.gz')) and f not in [s['filename'] for s in saves]:
                    try:
                        mtime = os.path.getmtime(os.path.join(save_dir, f))
                        size = os.path.getsize(os.path.join(save_dir, f))
                    except Exception:
                        mtime = None
                        size = None
                    saves.append({'filename': f, 'mtime': mtime, 'size': size})
        except Exception:
            pass

        # Sort by mtime desc if available
        saves.sort(key=lambda x: (x['mtime'] is not None, x['mtime']), reverse=True)
        return jsonify(saves=saves)
    except Exception as e:
        return jsonify(error=str(e)), 500


@socketio.on('request_effects')
def _on_request_effects():
    # Mirror connect behavior: emit active DM effects or the current map default to the requesting client
    try:
        game_key = getattr(current_game.game_session, 'root_path', None) or getattr(game_session, 'root_path', None) or LEVEL

        # Determine current map early so we can also emit map-defined point fires alongside other effects
        cur_map = None
        try:
            username = session.get('username')
            if username:
                cur_map = current_game.get_map_for_user(username)
            else:
                try:
                    cur_map = current_game.get_map_for_user(None)
                except Exception:
                    cur_map = current_game.get_current_battle_map()
        except Exception:
            cur_map = None

        effects = filter_effect_payloads(active_effects.get(game_key, {}).values())
        if effects:
            for payload in effects:
                emit('effect:set', payload)
        else:
            try:
                cur_name = getattr(cur_map, 'name', None)
                map_overrides = filter_effect_payloads(active_effects_map.get(game_key, {}).get(cur_name, {}).values())
                if map_overrides:
                    for payload in map_overrides:
                        emit('effect:set', payload)
                else:
                    for payload in map_default_effect_payloads(cur_map):
                        emit('effect:set', payload)
            except Exception:
                pass

        # Emit map-defined point fires separately (independent of DM overlay effects)
        try:
            emit('effect:set', point_fire_effect_payload(cur_map))
        except Exception:
            pass
    except Exception:
        pass


@app.route('/admin/save', methods=['POST'])
def admin_save():
    if not session.get('username'):
        return jsonify(error='Unauthorized'), 401
    if 'dm' not in user_role():
        return jsonify(error='Forbidden'), 403
    payload = request.get_json(silent=True) or {}
    name = payload.get('name')
    try:
        # Queue async save to avoid blocking request handler
        current_game.save_game_async(name=name)
        return jsonify(status='queued')
    except Exception as e:
        return jsonify(error=str(e)), 500


@app.route('/admin/load', methods=['POST'])
def admin_load():
    if not session.get('username'):
        return jsonify(error='Unauthorized'), 401
    if 'dm' not in user_role():
        return jsonify(error='Forbidden'), 403
    payload = request.get_json(silent=True) or {}
    filename = payload.get('filename')
    index = payload.get('index')
    try:
        # Load under lock to avoid race with in-flight actions
        with current_game.game_state_lock:
            if filename:
                # Pass through as relative; GameManagement.resolve will join with save_dir
                current_game.load_save(filename=filename)
            elif index is not None:
                try:
                    idx = int(index)
                except Exception:
                    return jsonify(error='index must be integer'), 400
                current_game.load_save(index=idx)
            else:
                # Load latest
                current_game.load_save()

        # Notify clients to refresh
        try:
            # Ensure all users reference the newly loaded battle map instance
            current_game.set_current_battle_map(current_game.get_current_battle_map())
        except Exception:
            pass
        # Update module-level session reference used by many routes
        try:
            global game_session
            game_session = current_game.game_session
        except Exception:
            pass
        try:
            current_game.refresh_client_map()
        except Exception:
            pass
        # Ensure any tile/object overlays are rebuilt
        socketio.emit('message', {'type': 'refresh_map'})
        socketio.emit('message', {'type': 'turn', 'message': {'game_time': current_game.game_session.game_time}})
        return jsonify(status='ok')
    except Exception as e:
        return jsonify(error=str(e)), 500


@app.route('/admin/manage_saves', methods=['GET'])
def admin_manage_saves():
    if not session.get('username'):
        return redirect(url_for('login'))
    if 'dm' not in user_role():
        return jsonify(error='Forbidden'), 403
    return render_template('manage_saves.html', title='Manage Saves')


@app.route('/admin/effect', methods=['POST'])
def admin_effect():
    """DM-only endpoint to broadcast visual effects to connected clients.
    Expects JSON: { effect: 'fog'|'rain'|'snow', action: 'start'|'stop'|'update', config: {...} }
    """
    if not session.get('username'):
        return jsonify(error='Unauthorized'), 401
    if 'dm' not in user_role():
        return jsonify(error='Forbidden'), 403
    payload = request.get_json(silent=True) or {}
    effect = payload.get('effect')
    action = payload.get('action')
    config = payload.get('config') or {}
    scope = (payload.get('scope') or 'global').lower()  # 'global' or 'map'
    target_map_name = payload.get('map')  # optional explicit map name
    if not effect or not action:
        return jsonify(error='effect and action required'), 400
    if not special_effects_enabled() and action != 'stop' and (effect == 'map_default' or is_heavy_special_effect(effect)):
        return jsonify(error='Special effects are disabled by configuration'), 409
    try:
        # Validate and sanitize config per effect type
        def _hex_color(c):
            try:
                return bool(re.match(r'^#[0-9a-fA-F]{6}$', str(c)))
            except Exception:
                return False

        def _clamp(v, lo, hi, cast=float):
            try:
                vv = cast(v)
            except Exception:
                vv = lo
            return max(lo, min(hi, vv))

        def validate_effect_config(name, cfg):
            cfg = dict(cfg or {})
            if name == 'snow':
                cfg['intensity'] = _clamp(cfg.get('intensity', 0.6), 0.0, 1.0)
                cfg['wind'] = _clamp(cfg.get('wind', 0.0), -1.0, 1.0)
                cfg['speed'] = _clamp(cfg.get('speed', 1.0), 0.0, 3.0)
                cfg['flakeSize'] = _clamp(cfg.get('flakeSize', 1.0), 0.2, 3.0)
                cfg['turbulence'] = _clamp(cfg.get('turbulence', 0.35), 0.0, 1.0)
                cfg['gusts'] = bool(cfg.get('gusts', False))
                cfg['gustFreq'] = _clamp(cfg.get('gustFreq', 0.04), 0.0, 2.0)
                cfg['gustStrength'] = _clamp(cfg.get('gustStrength', 0.5), 0.0, 1.0)
                cfg['gustDuration'] = _clamp(cfg.get('gustDuration', 1.8), 0.0, 10.0)
                cfg['dof'] = _clamp(cfg.get('dof', 0.35), 0.0, 1.0)
                cfg['accumulationEnabled'] = bool(cfg.get('accumulationEnabled', False))
                cfg['accumulationRate'] = _clamp(cfg.get('accumulationRate', 0.02), 0.0, 1.0)
                cfg['accumulationMax'] = _clamp(cfg.get('accumulationMax', 0.35), 0.0, 1.0)
                if not _hex_color(cfg.get('accumulationColor', '#ffffff')):
                    cfg['accumulationColor'] = '#ffffff'
                if not _hex_color(cfg.get('color', '#ffffff')):
                    cfg['color'] = '#ffffff'
            elif name == 'rain':
                cfg['intensity'] = _clamp(cfg.get('intensity', 0.6), 0.0, 1.0)
                cfg['wind'] = _clamp(cfg.get('wind', 0.0), -1.0, 1.0)
                cfg['speed'] = _clamp(cfg.get('speed', 1.0), 0.0, 3.0)
                cfg['lightning'] = bool(cfg.get('lightning', False))
                cfg['lightningFreq'] = _clamp(cfg.get('lightningFreq', 0.01), 0.0, 1.0)
                cfg['lightningIntensity'] = _clamp(cfg.get('lightningIntensity', 1.0), 0.0, 3.0)
                if not _hex_color(cfg.get('color', '#a8c0e6')):
                    cfg['color'] = '#a8c0e6'
            elif name == 'fog':
                cfg['density'] = _clamp(cfg.get('density', 0.45), 0.0, 2.0)
                cfg['speed'] = _clamp(cfg.get('speed', 0.7), 0.0, 3.0)
                cfg['contrast'] = _clamp(cfg.get('contrast', 1.0), 0.2, 3.0)
                cfg['grain'] = _clamp(cfg.get('grain', 0.15), 0.0, 0.5)
                cfg['falloff'] = _clamp(cfg.get('falloff', 1.0), 0.0, 3.0)
                if not _hex_color(cfg.get('color', '#cfcfd6')):
                    cfg['color'] = '#cfcfd6'
            else:
                # unknown effect: keep as-is to avoid breaking custom effects
                cfg = cfg
            return cfg

        config = validate_effect_config(effect, config)

        # Broadcast to all connected clients
        payload = {'effect': effect, 'action': action, 'config': config}
        socketio.emit('effect:set', payload)
        # persist effect state per game so new clients or refreshed pages will re-apply the effect
        try:
            game_key = getattr(current_game.game_session, 'root_path', None) or getattr(game_session, 'root_path', None) or LEVEL
            if scope == 'map':
                # Determine target map name
                try:
                    if not target_map_name:
                        cur_map = current_game.get_map_for_user(session['username'])
                        target_map_name = getattr(cur_map, 'name', None)
                except Exception:
                    target_map_name = None

                if effect == 'map_default' and action == 'start':
                    # Clear per-map overrides and broadcast map default
                    try:
                        if game_key in active_effects_map and target_map_name in active_effects_map[game_key]:
                            prev = active_effects_map[game_key].pop(target_map_name, {})
                        else:
                            prev = {}
                        for ef_name in list(prev.keys()):
                            try:
                                socketio.emit('effect:set', {'effect': ef_name, 'action': 'stop'})
                            except Exception:
                                pass
                        # emit map default
                        try:
                            cur_map = current_game.get_map_for_user(session['username'])
                            props = getattr(cur_map, 'properties', {}) or {}
                            map_def = props.get('default_effect')
                            if map_def:
                                socketio.emit('effect:set', map_def)
                        except Exception:
                            pass
                    except Exception:
                        pass
                else:
                    # Persist per-map override
                    active_effects_map.setdefault(game_key, {}).setdefault(target_map_name, {})
                    if action == 'stop':
                        # Remove this effect from the map overrides
                        try:
                            active_effects_map[game_key][target_map_name].pop(effect, None)
                        except Exception:
                            pass
                    else:
                        active_effects_map[game_key][target_map_name][effect] = {'effect': effect, 'action': 'start', 'config': config}
            else:
                # Global scope (existing behavior)
                if effect == 'map_default' and action == 'start':
                    # remove any DM-persisted effects for this game
                    prev = active_effects.pop(game_key, {})
                    for ef_name in list(prev.keys()):
                        try:
                            socketio.emit('effect:set', {'effect': ef_name, 'action': 'stop'})
                        except Exception:
                            pass
                    try:
                        cur_map = current_game.get_map_for_user(session['username'])
                        props = getattr(cur_map, 'properties', {}) or {}
                        map_def = props.get('default_effect')
                        if map_def:
                            socketio.emit('effect:set', map_def)
                    except Exception:
                        pass
                else:
                    if action == 'stop':
                        if game_key in active_effects and effect in active_effects[game_key]:
                            del active_effects[game_key][effect]
                    else:
                        active_effects.setdefault(game_key, {})[effect] = {'effect': effect, 'action': 'start', 'config': config}
        except Exception:
            # non-fatal; proceed
            pass
        return jsonify(status='ok')
    except Exception as e:
        return jsonify(error=str(e)), 500

def t(key):
    return i18n.t(key)
app.add_template_global(t, name='t')

def opacity_for(tile):
    if tile['hiding']:
        return 0.7
    elif tile['dead']:
        return 0.4
    else:
        return 1.0
app.add_template_global(opacity_for, name='opacity_for')

def transform_for(tile):
    transforms = []
    entity_size = tile.get('entity_size', None)
    if entity_size == 'medium':
        transforms.append('scale(0.8)')
    if entity_size =='small':
        transforms.append('scale(0.6)')
    elif entity_size == 'tiny':
        transforms.append('scale(0.3)')

    if tile.get('prone', False):
        transforms.append('rotate(90deg)')
    if len(transforms) > 0:
        return ' '.join(transforms)
    else:
        return 'none'
app.add_template_global(transform_for, name='transform_for')

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

app.add_template_global(filter_for, name='filter_for')


def entities_controlled_by(username, battle_map=None):
    entities = []
    for info in CONTROLLERS:
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

def interact_flavors(action):
    if isinstance(action, InteractAction):
        if action.object_action == 'give':
            return action.target.profile_image()
    return ""

def action_flavors(action):
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

app.add_template_global(action_flavors, name='action_flavors')

def ability_mod_str(ability_mod):
    if ability_mod is None:
        return ""
   
    if ability_mod >= 0:
        return f"+{ability_mod}"
    else:
        return str(ability_mod)

app.add_template_filter(ability_mod_str, name='mod_str')

def casting_time(casting_time):
    qty, resource = casting_time.split(":")
    if resource=="action":
        r_str = "A"
    elif resource=="reaction":
        r_str = "R"
    elif resource=="bonus_action":
        r_str = "B"
    elif resource=="hour":
        r_str = "H"
    elif resource=="minute":
        r_str = "M"
    elif resource=="round":
        r_str = "R"
    else:
        raise ValueError(f"Invalid casting time: {casting_time}")
    return f"{qty}{r_str}"
app.add_template_filter(casting_time, name='casting_time')

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

app.add_template_filter(format_game_time, name='format_game_time')

def entity_owners(entity):
    if isinstance(entity, Entity):
        if hasattr(entity, 'owner') and entity.owner:
            entity_uid = entity.owner.entity_uid
        else:
            entity_uid = entity.entity_uid
    else:
        entity_uid = entity

    ctrl_info = next((controller for controller in CONTROLLERS if controller['entity_uid'] == entity_uid), None)
    return [] if not ctrl_info else ctrl_info['controllers']

app.add_template_global(entity_owners, name='entity_owners')

conversation_service = ConversationService(
    current_game_getter=lambda: current_game,
    game_session=game_session,
    socketio=socketio,
    entity_rag_handler_getter=lambda: entity_rag_handler,
    llm_conversation_handler_getter=lambda: llm_conversation_handler,
    roles_for_username_getter=lambda: roles_for_username,
    entity_owners_getter=lambda: entity_owners,
    entities_controlled_by_getter=lambda: entities_controlled_by,
    logins_getter=lambda: LOGINS,
    logger=logger,
)

register_conversation_routes(
    app,
    conversation_service,
    lambda: read_npc_system_prompt(LEVEL),
)

def visible_log_messages_for_username(username, roles=None):
    if roles is None:
        roles = roles_for_username(username)
    return output_logger.get_all_logs(username=username, roles=roles)

entity_audience_usernames = conversation_service.entity_audience_usernames
conversation_audience_usernames = conversation_service.conversation_audience_usernames
conversation_visible_whisper_usernames = conversation_service.conversation_visible_whisper_usernames
conversation_payload = conversation_service.conversation_payload
conversation_listener_for_username = conversation_service.conversation_listener_for_username
listener_understands_language = conversation_service.listener_understands_language
render_conversation_payload_for_username = conversation_service.render_conversation_payload_for_username
resolve_conversation_targets = conversation_service.resolve_conversation_targets
select_conversation_responders = conversation_service.select_conversation_responders
emit_conversation_to_usernames = conversation_service.emit_conversation_to_usernames
conversation_status_summary = conversation_service.conversation_status_summary
conversation_effect_summary = conversation_service.conversation_effect_summary
conversation_goal_summary = conversation_service.conversation_goal_summary
conversation_attitude_toward_speaker = conversation_service.conversation_attitude_toward_speaker
conversation_pressure_summary = conversation_service.conversation_pressure_summary
conversation_response_prompt = conversation_service.conversation_response_prompt
conversation_recipient_usernames = conversation_service.conversation_recipient_usernames
effective_talk_volume = conversation_service.effective_talk_volume

output_logger.configure_visibility(
    game_getter=lambda: current_game,
    role_lookup=roles_for_username,
    controlled_entities_lookup=entities_controlled_by,
)

def describe_terrain(tile):
    """Legacy Jinja helper; tooltips are precomputed in JsonRenderer."""
    from flask import g
    from natural20.web.terrain_tooltip import build_terrain_tooltip

    if not hasattr(g, '_describe_terrain_ctx'):
        g._describe_terrain_ctx = (
            current_game.get_map_for_user(session['username']),
            current_game.get_current_battle(),
        )
    battle_map, battle = g._describe_terrain_ctx
    if tile.get('terrain_tooltip') is not None:
        return tile['terrain_tooltip']
    return build_terrain_tooltip(tile, battle_map, battle)

app.add_template_global(describe_terrain, name='describe_terrain')

def validate_targets(action, entity, target, current_map, battle=None):
    if battle:
        valid_targets = battle.valid_targets_for(entity, action)
        if isinstance(target, list):
            for t in target:
                if t not in valid_targets:
                    raise ValueError(f"Invalid target {t} ({current_map.entity_by_uid(t)})")
        else:
            if target not in valid_targets:
                raise ValueError(f"Invalid target {target}")


def process_action_hash(action):
    return action.to_h()

app.add_template_global(process_action_hash, name='process_action_hash')


@app.route('/assets/maps/<path:filename>')
def serve_map_image(filename):
    maps_directory = os.path.join(game_session.root_path, "assets", "maps")
    return send_from_directory(maps_directory, filename)

@app.route('/assets/sounds/<filename>')
def serve_sound_file(filename):
    secondary_path = os.path.join(game_session.root_path, "assets", "sounds", filename)
    if os.path.exists(secondary_path):
        return send_file(secondary_path)
    else:
        return jsonify(error="File not found"), 404
   
@app.route('/assets/objects/<filename>')
def serve_object_image(filename):
    if not filename.endswith('.png'):
        filename = f"{filename}.png"

    if os.path.exists(os.path.join("static", "assets", "objects", filename)):
        return send_file(os.path.join("static", "assets", "objects", filename))
    else:
        objects_directory = os.path.join(game_session.root_path, "assets", "objects")
        return send_from_directory(objects_directory, filename)

@app.route('/assets/editor/<filename>')
def serve_editor_image(filename):
    if not filename.endswith('.png'):
        filename = f"{filename}.png"

    if os.path.exists(os.path.join("static", "assets", "editor", filename)):
        return send_file(os.path.join("static", "assets", "editor", filename))
    else:
        objects_directory = os.path.join(game_session.root_path, "assets", "editor")
        return send_from_directory(objects_directory, filename)
   
@app.route('/assets/items/<filename>')
def serve_item_image(filename):
    if not filename.endswith('.png'):
        filename = f"{filename}.png"

    if os.path.exists(os.path.join("static", "assets", "items", filename)):
        return send_file(os.path.join("static", "assets", "items", filename))
    else:
        items_directory = os.path.join(game_session.root_path, "assets", "items")
        return send_from_directory(items_directory, filename)

@app.route('/assets/<path:asset_name>')
def get_asset(asset_name):
    """Serve asset files from multiple possible locations."""
    asset_paths = [
        os.path.join(LEVEL, "assets", asset_name),
        os.path.join(game_session.root_path, "assets", asset_name),
        os.path.join("static", "assets", asset_name)
    ]

    for file_path in asset_paths:
        if os.path.exists(file_path):
            return send_file(file_path)

    return jsonify(error="File not found"), 404

@app.route('/create_map', methods=['POST'])
def create_map():
    """Create a new empty map in the current game's maps folder and register it.
    Expects form data: name (map id). Creates:
      - assets/maps/<name>.yml (basic empty map)
      - assets/maps/<name>.png (placeholder image)
    """
    try:
        name = request.form.get('name') or ''
        name = name.strip().lower()
        if not name or not re.match(r'^[a-z0-9_\-]+$', name):
            return jsonify(error='Invalid map name'), 400

        # Dimensions (optional)
        try:
            width = int(request.form.get('width') or 16)
            height = int(request.form.get('height') or 8)
        except ValueError:
            return jsonify(error='Invalid dimensions'), 400
        width = max(2, min(width, 100))
        height = max(2, min(height, 100))

        # YAML lives in <root>/maps, PNG lives in <root>/assets/maps
        maps_yml_dir = os.path.join(game_session.root_path, 'maps')
        maps_png_dir = os.path.join(game_session.root_path, 'assets', 'maps')
        os.makedirs(maps_yml_dir, exist_ok=True)
        os.makedirs(maps_png_dir, exist_ok=True)

        yml_path = os.path.join(maps_yml_dir, f'{name}.yml')
        png_path = os.path.join(maps_png_dir, f'{name}.png')

        if os.path.exists(yml_path) or os.path.exists(png_path):
            return jsonify(error='Map already exists'), 400

        # Generate a small empty map template
        empty_map = {
            'name': name,
            'description': f'Empty map {name}',
            'map': {
                'illumination': 1.0,
                'base': ['.' * width for _ in range(height)],
            },
            'legend': {},
            'player': [],
        }

        # Save YAML
        with open(yml_path, 'w') as f:
            import yaml as _yaml
            _yaml.safe_dump(empty_map, f, sort_keys=False)

        # Create a placeholder PNG thumbnail
        img = Image.new('RGB', (max(160, width * 10), max(100, height * 10)), color=(230, 233, 237))
        d = ImageDraw.Draw(img)
        d.text((10, 10), name, fill=(90, 90, 90))
        img.save(png_path)

        # Register into current session maps if needed
        map_id = name
        relative_map_ref = f'maps/{name}'
        if map_id not in game_session.maps:
            game_session.register_map(map_id, relative_map_ref)
            current_game.maps = game_session.maps

        # Ensure available for switching/reloading
        OTHERMAPS[map_id] = relative_map_ref
        current_game.other_maps[map_id] = relative_map_ref

        # Persist to game.yml so maps load after restart
        try:
            import yaml as _yaml
            game_yml_path = os.path.join(game_session.root_path, 'game.yml')
            if os.path.exists(game_yml_path):
                with open(game_yml_path, 'r') as f:
                    props = _yaml.safe_load(f) or {}
            else:
                props = {}
            maps_dict = props.get('maps') or {}
            maps_dict[map_id] = f'maps/{map_id}'
            props['maps'] = maps_dict
            with open(game_yml_path, 'w') as f:
                _yaml.safe_dump(props, f, sort_keys=False)
            # update in-memory
            game_session.game_properties = props
        except Exception:
            logger.exception('Failed to persist new map to game.yml')

        # Persist to index.json other_maps for auxiliary use
        try:
            index_json_path = os.path.join(game_session.root_path, 'index.json')
            if os.path.exists(index_json_path):
                with open(index_json_path, 'r') as jf:
                    idx = json.load(jf)
            else:
                idx = {}
            other_maps = idx.get('other_maps') or {}
            other_maps[map_id] = f'maps/{map_id}'
            idx['other_maps'] = other_maps
            with open(index_json_path, 'w') as jf:
                json.dump(idx, jf, indent=2)
        except Exception:
            logger.exception('Failed to persist new map to index.json')

        return jsonify(status='ok', name=map_id)
    except Exception as e:
        logger.exception('Failed to create map')
        return jsonify(error=str(e)), 500

@app.route('/upload_map_background', methods=['POST'])
def upload_map_background():
    """Upload and set a map's background image. Expects form fields:
    - map: map name
    - image: file upload
    Saves to assets/maps/<map>.png and updates maps/<map>.yml background_image.
    """
    try:
        map_name = request.form.get('map') or ''
        if not map_name or map_name not in game_session.maps:
            return jsonify(error='Unknown map'), 400

        if 'image' not in request.files:
            return jsonify(error='No file provided'), 400
        file = request.files['image']
        if file.filename == '':
            return jsonify(error='Empty filename'), 400

        # Save PNG (force .png extension)
        maps_png_dir = os.path.join(game_session.root_path, 'assets', 'maps')
        os.makedirs(maps_png_dir, exist_ok=True)
        png_path = os.path.join(maps_png_dir, f'{map_name}.png')

        # Convert to PNG if needed using PIL
        try:
            image = Image.open(file.stream).convert('RGBA')
            image.save(png_path, format='PNG')
        except Exception:
            # Fallback: save directly (may already be PNG)
            file.stream.seek(0)
            file.save(png_path)

        # Update in-memory properties
        _map = game_session.maps.get(map_name)
        if _map:
            _map.properties['background_image'] = f'{map_name}.png'

        # Persist to YAML
        maps_ref = game_session.game_properties.get('maps', {})
        rel_ref = maps_ref.get(map_name, f'maps/{map_name}')
        if not rel_ref.endswith('.yml'):
            rel_ref += '.yml'
        yml_path = os.path.join(game_session.root_path, rel_ref)
        try:
            import yaml as _yaml
            if os.path.exists(yml_path):
                with open(yml_path, 'r') as f:
                    content = _yaml.safe_load(f) or {}
            else:
                content = {}
            content['background_image'] = f'{map_name}.png'
            with open(yml_path, 'w') as f:
                _yaml.safe_dump(content, f, sort_keys=False)
        except Exception as e:
            logger.exception('Failed to update YAML with background_image')

        return jsonify(status='ok', name=map_name, background=f'assets/maps/{map_name}.png')
    except Exception as e:
        logger.exception('Failed to upload map background')
        return jsonify(error=str(e)), 500

@app.route('/delete_map', methods=['POST'])
def delete_map():
    """Delete an existing map safely.
    Expects form data: name
    Removes maps/<name>.yml and assets/maps/<name>.png if present,
    unregisters from session, updates game.yml maps and index.json other_maps.
    Prevent deleting 'index' or the only remaining map.
    """
    try:
        # Only DMs can delete maps
        if 'dm' not in user_role():
            return jsonify(error='Forbidden'), 403
        map_name = request.form.get('name') or ''
        map_name = map_name.strip()
        if not map_name:
            return jsonify(error='No map specified'), 400

        # Safety checks
        if map_name == 'index':
            return jsonify(error='Cannot delete the default index map'), 400
        if map_name not in game_session.maps:
            return jsonify(error='Unknown map'), 404
        if len(game_session.maps) <= 1:
            return jsonify(error='Cannot delete the only remaining map'), 400

        # File paths
        # Resolve YAML reference via game.yml maps entry if available
        maps_ref = game_session.game_properties.get('maps', {})
        rel_ref = maps_ref.get(map_name, f'maps/{map_name}')
        if not rel_ref.endswith('.yml'):
            rel_ref += '.yml'
        yml_path = os.path.join(game_session.root_path, rel_ref)
        png_path = os.path.join(game_session.root_path, 'assets', 'maps', f'{map_name}.png')

        # If deleting current map for this user, switch to another map first
        try:
            current_for_user = current_game.get_map_for_user(session['username']).name
        except Exception:
            current_for_user = None
        if current_for_user == map_name:
            # pick any other map (prefer 'index' if exists)
            fallback = 'index' if 'index' in game_session.maps and map_name != 'index' else None
            if not fallback:
                # pick first key that's not the one being deleted
                fallback = next((k for k in game_session.maps.keys() if k != map_name), None)
            if fallback:
                current_game.switch_map_for_user(session['username'], fallback)

        # Remove from in-memory maps and current_game references
        if map_name in current_game.other_maps:
            try:
                del current_game.other_maps[map_name]
            except Exception:
                pass
        try:
            global OTHERMAPS
            OTHERMAPS.pop(map_name, None)
        except Exception:
            pass
        if map_name in game_session.maps:
            try:
                del game_session.maps[map_name]
            except Exception:
                pass
        # Keep current_game maps reference aligned
        current_game.maps = game_session.maps

        # Update game.yml: remove from maps
        try:
            import yaml as _yaml
            game_yml_path = os.path.join(game_session.root_path, 'game.yml')
            if os.path.exists(game_yml_path):
                with open(game_yml_path, 'r') as f:
                    props = _yaml.safe_load(f) or {}
            else:
                props = {}
            maps_dict = props.get('maps') or {}
            if map_name in maps_dict:
                maps_dict.pop(map_name, None)
            props['maps'] = maps_dict
            with open(game_yml_path, 'w') as f:
                _yaml.safe_dump(props, f, sort_keys=False)
            game_session.game_properties = props
        except Exception:
            logger.exception('Failed to update game.yml while deleting map')

        # Update index.json other_maps
        try:
            index_json_path = os.path.join(game_session.root_path, 'index.json')
            if os.path.exists(index_json_path):
                with open(index_json_path, 'r') as jf:
                    idx = json.load(jf)
            else:
                idx = {}
            other_maps = idx.get('other_maps') or {}
            other_maps.pop(map_name, None)
            idx['other_maps'] = other_maps
            with open(index_json_path, 'w') as jf:
                json.dump(idx, jf, indent=2)
        except Exception:
            logger.exception('Failed to update index.json while deleting map')

        # Delete files last
        try:
            if os.path.exists(yml_path):
                os.remove(yml_path)
        except Exception:
            logger.exception('Failed to delete map YAML')
        try:
            if os.path.exists(png_path):
                os.remove(png_path)
        except Exception:
            logger.exception('Failed to delete map image')

        return jsonify(status='ok', name=map_name)
    except Exception as e:
        logger.exception('Failed to delete map')
        return jsonify(error=str(e)), 500


def _parse_json_list_form(form, key):
    val = form.get(key)
    if not val:
        return []
    try:
        data = json.loads(val)
        if isinstance(data, list):
            return [str(x) for x in data]
    except Exception:
        pass
    return []


def _parse_json_dict_form(form, key):
    val = form.get(key)
    if not val:
        return {}
    try:
        data = json.loads(val)
        if isinstance(data, dict):
            parsed = {}
            for k, v in data.items():
                parsed[str(k)] = int(v)
            return parsed
    except Exception:
        pass
    return {}


def _ability_mod(score):
    try:
        return (int(score) - 10) // 2
    except Exception:
        return 0


def _spell_choice_caps(klass, level, ability, class_def):
    klass_lower = str(klass or '').lower()
    lvl = max(1, int(level or 1))
    caps = {'cantrip_cap': 0, 'level1_cap': 0, 'spellbook_cap': 0}

    try:
        from natural20.entity_class.wizard import WIZARD_SPELL_SLOT_TABLE
        from natural20.entity_class.cleric import CLERIC_SPELL_SLOT_TABLE
        from natural20.entity_class.druid import DRUID_SPELL_SLOT_TABLE
        from natural20.entity_class.bard import BARD_SPELL_SLOT_TABLE
        from natural20.entity_class.warlock import WARLOCK_SPELL_SLOT_TABLE
        from natural20.entity_class.sorcerer import SORCERER_SPELL_SLOT_TABLE
        from natural20.entity_class.paladin import PALADIN_SPELL_SLOT_TABLE
        from natural20.entity_class.ranger import RANGER_SPELL_SLOT_TABLE
    except Exception:
        WIZARD_SPELL_SLOT_TABLE = []
        CLERIC_SPELL_SLOT_TABLE = []
        DRUID_SPELL_SLOT_TABLE = []
        BARD_SPELL_SLOT_TABLE = []
        WARLOCK_SPELL_SLOT_TABLE = []
        SORCERER_SPELL_SLOT_TABLE = []
        PALADIN_SPELL_SLOT_TABLE = []
        RANGER_SPELL_SLOT_TABLE = []

    slot_tables = {
        'wizard': WIZARD_SPELL_SLOT_TABLE,
        'cleric': CLERIC_SPELL_SLOT_TABLE,
        'druid': DRUID_SPELL_SLOT_TABLE,
        'bard': BARD_SPELL_SLOT_TABLE,
        'warlock': WARLOCK_SPELL_SLOT_TABLE,
        'sorcerer': SORCERER_SPELL_SLOT_TABLE,
        'paladin': PALADIN_SPELL_SLOT_TABLE,
        'ranger': RANGER_SPELL_SLOT_TABLE,
    }

    table = slot_tables.get(klass_lower) or []
    row = []
    if table and lvl <= len(table):
        row = table[lvl - 1]

    if row:
        if len(row) > 0:
            caps['cantrip_cap'] = max(0, int(row[0] or 0))
        if len(row) > 1:
            caps['level1_cap'] = max(0, int(row[1] or 0))

    # Known/prepared rules for early levels where engine supports custom builds.
    if klass_lower == 'wizard':
        caps['spellbook_cap'] = 6 + (max(1, lvl) - 1) * 2
        caps['level1_cap'] = max(caps['level1_cap'], max(1, lvl + _ability_mod((ability or {}).get('int', 10))))
    elif klass_lower in ('cleric', 'druid', 'paladin'):
        spell_ability = str((class_def or {}).get('spellcasting_ability') or ('wisdom' if klass_lower in ('cleric', 'druid') else 'charisma'))
        key = spell_ability[:3].lower()
        caps['level1_cap'] = max(caps['level1_cap'], max(1, lvl + _ability_mod((ability or {}).get(key, 10))))
    elif klass_lower == 'bard':
        bard_known = [0, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14,
                      15, 15, 16, 18, 19, 19, 20, 22, 22, 22]
        caps['level1_cap'] = max(caps['level1_cap'], bard_known[min(lvl, len(bard_known) - 1)])
    elif klass_lower == 'warlock':
        warlock_known = [0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10,
                         11, 11, 12, 12, 13, 13, 14, 14, 15, 15]
        caps['level1_cap'] = max(caps['level1_cap'], warlock_known[min(lvl, len(warlock_known) - 1)])
    elif klass_lower == 'sorcerer':
        sorc_known = [0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11,
                      12, 12, 13, 13, 14, 14, 15, 15, 15, 15]
        caps['level1_cap'] = max(caps['level1_cap'], sorc_known[min(lvl, len(sorc_known) - 1)])
    elif klass_lower == 'ranger':
        ranger_known = [0, 0, 2, 3, 3, 4, 4, 5, 5, 6, 6,
                        7, 7, 8, 8, 9, 9, 10, 10, 11, 11]
        caps['level1_cap'] = max(caps['level1_cap'], ranger_known[min(lvl, len(ranger_known) - 1)])

    return caps


def _apply_class_and_feat_choices(pc, klass, level, classes_def, selected_skills, selected_cantrips, selected_level1, selected_feats):
    cdef = (classes_def or {}).get(klass, {}) or {}

    # Skills
    max_skills = int(cdef.get('available_skills_choices', 0) or 0)
    available_skills = cdef.get('available_skills', []) or []
    if max_skills and available_skills:
        valid_skills = [s for s in selected_skills if s in available_skills][:max_skills]
        if valid_skills:
            pc['skills'] = valid_skills

    # Spells
    spell_list = cdef.get('spell_list', {}) or {}
    can_list = spell_list.get('cantrip', []) or []
    lvl1_list = spell_list.get('level_1', []) or []
    caps = _spell_choice_caps(klass, level, pc.get('ability') or {}, cdef)

    cantrip_cap = min(caps['cantrip_cap'], len(can_list)) if can_list else 0
    level1_cap = min(caps['level1_cap'], len(lvl1_list)) if lvl1_list else 0

    prepared = []
    if cantrip_cap > 0:
        prepared.extend([s for s in selected_cantrips if s in can_list][:cantrip_cap])
    if level1_cap > 0:
        prepared.extend([s for s in selected_level1 if s in lvl1_list][:level1_cap])

    if prepared:
        pc['prepared_spells'] = list(dict.fromkeys(prepared))
    elif 'prepared_spells' in pc:
        pc.pop('prepared_spells', None)

    if str(klass).lower() == 'wizard':
        spellbook_cap = max(0, int(caps.get('spellbook_cap') or 0))
        if spellbook_cap > 0:
            book = [s for s in lvl1_list if s in (pc.get('prepared_spells') or [])]
            for spell in lvl1_list:
                if len(book) >= spellbook_cap:
                    break
                if spell not in book:
                    book.append(spell)
            pc['spellbook'] = book[:spellbook_cap]

    # Feats
    feat_options = cdef.get('feat_choices') or cdef.get('available_feats') or []
    feat_count = int(cdef.get('feat_choices_count') or cdef.get('available_feats_choices') or 0)
    if feat_options:
        feats = [f for f in selected_feats if f in feat_options]
        if feat_count > 0:
            feats = feats[:feat_count]
        pc['feats'] = list(dict.fromkeys(feats))
    elif selected_feats:
        pc['feats'] = list(dict.fromkeys(selected_feats))


def _resolve_character_yaml_path(character_name):
    chars_dir = os.path.join(game_session.root_path, 'characters')
    if not os.path.isdir(chars_dir):
        return None

    direct_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', str(character_name or ''))
    if direct_name:
        direct_path = os.path.join(chars_dir, f"{direct_name}.yml")
        if os.path.exists(direct_path):
            return direct_path

    target = str(character_name or '').lower()
    for file_name in os.listdir(chars_dir):
        if not file_name.endswith('.yml'):
            continue
        file_path = os.path.join(chars_dir, file_name)
        try:
            with open(file_path, 'r', encoding='utf-8') as fh:
                data = yaml.safe_load(fh) or {}
        except Exception:
            continue

        candidate_uid = str(data.get('entity_uid') or '').lower()
        candidate_name = str(data.get('name') or '').lower()
        if candidate_uid == target or candidate_name == target:
            return file_path

    return None


def _can_edit_character(character_name):
    if builder_only_mode():
        return True
    if 'dm' in user_role():
        return True
    username = session.get('username')
    if not username:
        return False
    if controller_of(character_name, username):
        return True

    # Selection-flow editing: allow a logged-in player to edit a selectable
    # character before confirming ownership, as long as another user has not
    # already claimed it.
    entry = selectable_character_entry(character_name)
    if entry is not None:
        for controller in CONTROLLERS:
            if controller.get('entity_uid') != character_name:
                continue
            controllers = controller.get('controllers') or []
            if controllers and username not in controllers:
                return False
        return True

    return False

PREBUILT_CHARACTER_DIR = os.path.join('static', 'assets', 'prebuild_character')


def _make_circular_token(pil_img, size=256, ring_width=4, ring_color=(74, 47, 25, 255)):
    """Convert any PIL image into a circular 256x256 token style PNG.

    Center-crops to a square, scales to ``size``, then masks with a circle so
    the corners become transparent. Optionally draws a thin dark-brown ring
    around the circle (matching the existing D&D theme).
    """
    img = pil_img.convert('RGBA')
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    img = img.crop((left, top, left + side, top + side))
    img = img.resize((size, size), Image.LANCZOS)

    mask = Image.new('L', (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)

    out = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)

    if ring_width and ring_width > 0:
        draw = ImageDraw.Draw(out)
        for i in range(ring_width):
            draw.ellipse(
                (i, i, size - 1 - i, size - 1 - i),
                outline=ring_color,
            )

    return out


def _decode_data_url_image(data_url):
    """Decode a ``data:image/...;base64,...`` URL into a PIL Image, or None."""
    if not data_url or not isinstance(data_url, str):
        return None
    try:
        if not data_url.startswith('data:'):
            return None
        _, _, b64 = data_url.partition(',')
        if not b64:
            return None
        import base64
        from io import BytesIO
        return Image.open(BytesIO(base64.b64decode(b64)))
    except Exception:
        logger.exception('Failed to decode data URL image')
        return None


def _resolve_prebuilt_character_image(name):
    """Return absolute filesystem path to a prebuilt character image, or None.

    Strict allow-list against ``PREBUILT_CHARACTER_DIR`` to avoid path traversal.
    """
    if not name:
        return None
    safe = os.path.basename(str(name))
    if safe != str(name):
        return None
    candidate = os.path.join(PREBUILT_CHARACTER_DIR, safe)
    if not os.path.isfile(candidate):
        return None
    return candidate


def _save_character_images(entity_uid, assets_dir, profile_pil=None, token_pil=None):
    """Persist profile + token images for a character.

    - profile saved to ``assets/characters/<uid>.png``
    - token saved to ``assets/token_<uid>.png`` (auto-generated from profile
      when token_pil is None and profile_pil is provided).
    """
    if profile_pil is None and token_pil is None:
        return
    profiles_dir = os.path.join(assets_dir, 'characters')
    os.makedirs(profiles_dir, exist_ok=True)

    if profile_pil is not None:
        profile_path = os.path.join(profiles_dir, f"{entity_uid}.png")
        profile_pil.convert('RGBA').save(profile_path, format='PNG')

    if token_pil is None and profile_pil is not None:
        token_pil = _make_circular_token(profile_pil)

    if token_pil is not None:
        # Token uploads/data-URLs may already be square; normalize to circular
        # token style so the on-map look stays consistent.
        if token_pil.size != (256, 256):
            token_pil = _make_circular_token(token_pil)
        token_path = os.path.join(assets_dir, f"token_{entity_uid}.png")
        token_pil.convert('RGBA').save(token_path, format='PNG')


def _load_character_image_from_request(req, file_field, prebuilt_field, data_url_field=None):
    """Resolve a character image from one of the supported input sources.

    Order of precedence:
      1. ``data_url_field`` (canvas-cropped data URL)
      2. ``file_field`` (uploaded file)
      3. ``prebuilt_field`` (prebuilt filename under ``static/assets/prebuild_character``)
    Returns a PIL Image or None.
    """
    if data_url_field:
        data_url = req.form.get(data_url_field)
        img = _decode_data_url_image(data_url)
        if img is not None:
            return img

    f = req.files.get(file_field) if file_field else None
    if f and getattr(f, 'filename', ''):
        try:
            return Image.open(f.stream)
        except Exception:
            logger.exception('Failed to open uploaded image %s', file_field)

    if prebuilt_field:
        prebuilt = req.form.get(prebuilt_field)
        path = _resolve_prebuilt_character_image(prebuilt)
        if path:
            try:
                return Image.open(path)
            except Exception:
                logger.exception('Failed to open prebuilt image %s', prebuilt)

    return None


@app.route('/character_builder/prebuilt_images', methods=['GET'])
def list_prebuilt_character_images():
    """Return the gallery of prebuilt character portrait images."""
    if not logged_in():
        return jsonify(error='Not logged in'), 401
    items = []
    if os.path.isdir(PREBUILT_CHARACTER_DIR):
        for name in sorted(os.listdir(PREBUILT_CHARACTER_DIR)):
            if not name.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif')):
                continue
            items.append({
                'name': name,
                'url': url_for('static', filename=f'assets/prebuild_character/{name}'),
            })
    return jsonify(images=items)


@app.route('/character_builder/items', methods=['GET'])
def character_builder_items():
    """Return available items (weapons + equipment) for the character builder inventory manager."""
    if not logged_in():
        return jsonify(error='Not logged in'), 401

    try:
        weapons = game_session.load_weapons() or {}
        equipment = game_session.load_all_equipments() or {}
        items = {}

        # Merge weapons and equipment into a single catalog
        for key, data in weapons.items():
            items[key] = {
                'id': key,
                'name': data.get('name', key.replace('_', ' ').title()),
                'type': data.get('type', data.get('subtype', 'weapon')),
                'cost': data.get('cost', ''),
                'weight': data.get('weight', 0),
                'category': 'weapon',
            }

        for key, data in equipment.items():
            if key not in items:  # Don't overwrite weapons
                items[key] = {
                    'id': key,
                    'name': data.get('name', key.replace('_', ' ').title()),
                    'type': data.get('type', data.get('subtype', 'equipment')),
                    'cost': data.get('cost', ''),
                    'weight': data.get('weight', 0),
                    'category': 'equipment',
                }

        # Add campaign-specific custom items if configured in game.yml
        game_props = getattr(game_session, 'game_properties', None) or {}
        custom_items = game_props.get('inventory_items') or {}
        allow_custom = game_props.get('allow_custom_inventory', True)

        if allow_custom and custom_items:
            for key, data in custom_items.items():
                if isinstance(data, dict):
                    items[key] = {
                        'id': key,
                        'name': data.get('name', key.replace('_', ' ').title()),
                        'type': data.get('type', 'custom'),
                        'cost': data.get('cost', ''),
                        'weight': data.get('weight', 0),
                        'category': 'custom',
                    }
                else:
                    # Simple string value treated as item name
                    items[key] = {
                        'id': key,
                        'name': str(data) if not isinstance(data, str) else data,
                        'type': 'custom',
                        'cost': '',
                        'weight': 0,
                        'category': 'custom',
                    }

        return jsonify(items=items, allow_custom_inventory=allow_custom)
    except Exception as e:
        logger.exception('Failed to load character builder items')
        return jsonify(error='Failed to load items'), 500


@app.route('/character_builder', methods=['GET'])
def character_builder():
    if not logged_in():
        return redirect(url_for('login'))

    try:
        races = game_session.load_races()
        classes = game_session.load_classes()
        backgrounds = game_session.load_backgrounds()
        equipment_packs = game_session.load_equipment_packs()
        return render_template('character_builder.html',
                               title=TITLE,
                               races=races,
                               classes=classes,
                               backgrounds=backgrounds,
                               equipment_packs=equipment_packs,
                               edit_mode=False,
                               cancel_url='/')
    except Exception as e:
        logger.exception('Failed to load character builder')
        return jsonify(error='Failed to load character builder'), 500


@app.route('/character_editor/<character_name>', methods=['GET'])
def character_editor(character_name):
    if not logged_in():
        return redirect(url_for('login'))
    if not _can_edit_character(character_name):
        return jsonify(error='Forbidden'), 403

    yml_path = _resolve_character_yaml_path(character_name)
    if not yml_path:
        return jsonify(error='Character not found'), 404

    try:
        with open(yml_path, 'r', encoding='utf-8') as fh:
            pc = yaml.safe_load(fh) or {}

        races = game_session.load_races() or {}
        classes = game_session.load_classes() or {}
        equipment_packs = game_session.load_equipment_packs() or {}
        backgrounds = game_session.load_backgrounds() or {}

        class_map = pc.get('classes') or {}
        klass = next(iter(class_map.keys()), None)
        level = int(class_map.get(klass, pc.get('level', 1))) if klass else int(pc.get('level', 1) or 1)

        spell_list = ((classes.get(klass or '', {}) or {}).get('spell_list') or {})
        can_list = set(spell_list.get('cantrip') or [])
        lvl1_list = set(spell_list.get('level_1') or [])
        prepared = list(pc.get('prepared_spells') or [])

        edit_character = {
            'name': pc.get('name', ''),
            'pronoun': pc.get('pronoun', ''),
            'race': pc.get('race', ''),
            'subrace': pc.get('subrace', ''),
            'klass': klass or '',
            'level': level,
            'ability': pc.get('ability', {}),
            'skills': list(pc.get('skills') or []),
            'cantrips': [s for s in prepared if s in can_list],
            'level1_spells': [s for s in prepared if s in lvl1_list],
            'feats': list(pc.get('feats') or []),
            'inventory': list(pc.get('inventory') or []),
        }

        cancel_url = request.args.get('next') or '/'
        return render_template(
            'character_builder.html',
            title=TITLE,
            races=races,
            classes=classes,
            backgrounds=backgrounds,
            equipment_packs=equipment_packs,
            edit_mode=True,
            edit_character=edit_character,
            editing_character=character_name,
            cancel_url=cancel_url,
        )
    except Exception:
        logger.exception('Failed to load character editor')
        return jsonify(error='Failed to load character editor'), 500


@app.route('/update_character/<character_name>', methods=['POST'])
def update_character(character_name):
    if not logged_in():
        return jsonify(error='Not logged in'), 401
    if not _can_edit_character(character_name):
        return jsonify(error='Forbidden'), 403

    yml_path = _resolve_character_yaml_path(character_name)
    if not yml_path:
        return jsonify(error='Character not found'), 404

    try:
        with open(yml_path, 'r', encoding='utf-8') as fh:
            pc = yaml.safe_load(fh) or {}

        class_map = pc.get('classes') or {}
        klass = next(iter(class_map.keys()), None)
        if not klass:
            return jsonify(error='Character class is missing'), 400
        level = int(class_map.get(klass, pc.get('level', 1) or 1))

        selected_skills = _parse_json_list_form(request.form, 'skills')
        selected_cantrips = _parse_json_list_form(request.form, 'cantrips')
        selected_level1 = _parse_json_list_form(request.form, 'level1_spells')
        selected_feats = _parse_json_list_form(request.form, 'feats')

        classes_def = game_session.load_classes() or {}
        cdef = classes_def.get(klass, {}) or {}
        class_skill_pool = set(cdef.get('available_skills') or [])
        existing_skills = list(pc.get('skills') or [])
        non_class_skills = [s for s in existing_skills if s not in class_skill_pool]

        _apply_class_and_feat_choices(
            pc,
            klass,
            level,
            classes_def,
            selected_skills,
            selected_cantrips,
            selected_level1,
            selected_feats,
        )

        if non_class_skills:
            pc.setdefault('skills', [])
            for skill in non_class_skills:
                if skill not in pc['skills']:
                    pc['skills'].append(skill)

        pronoun = (request.form.get('pronoun') or '').strip()
        if pronoun:
            pc['pronoun'] = pronoun
        else:
            pc.pop('pronoun', None)

        # Update inventory from character builder
        inventory_json = (request.form.get('inventory') or '').strip()
        if inventory_json:
            try:
                import json as _json
                custom_inventory = _json.loads(inventory_json)
                if custom_inventory:
                    pc['inventory'] = custom_inventory
            except Exception:
                logger.exception('Failed to parse custom inventory for update')

        with open(yml_path, 'w', encoding='utf-8') as fh:
            yaml.safe_dump(pc, fh, sort_keys=False)

        entity_uid = str(pc.get('entity_uid') or character_name)
        entity = current_game.get_entity_by_uid(entity_uid)
        if entity is not None and isinstance(getattr(entity, 'properties', None), dict):
            for key in ('skills', 'prepared_spells', 'spellbook', 'feats', 'pronoun'):
                if key in pc:
                    entity.properties[key] = pc.get(key)
                elif key in entity.properties:
                    entity.properties.pop(key, None)
        # Refresh entity inventory if loaded in session
        if entity is not None and hasattr(entity, 'inventory') and 'inventory' in pc:
            try:
                entity.load_inventory()
            except Exception:
                pass

        redirect_to = request.form.get('next') or '/'
        return jsonify(status='ok', redirect=redirect_to)
    except Exception:
        logger.exception('Failed to update character')
        return jsonify(error='Failed to update character'), 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    if builder_only_mode():
        return redirect(url_for('character_builder'))
    if request.method == 'POST':
        username = request.form['username'].lower()
        password = request.form['password']

        login_info = next((login for login in LOGINS if login["name"].lower() == username), None)
        if login_info and login_info["password"] == password:
            session['username'] = username

            if 'dm' in login_info.get('role', []):
                current_game.set_pov_entity_for_user(username, None)
                try:
                    current_game.switch_map_for_user(username, current_game.get_current_battle_map().name)
                except Exception:
                    logger.exception(f"Failed to switch DM {username} to the current battle map")

            # Spawn deferred PCs for this user on first login
            current_game.spawn_player_for_user(username)
            
            # Check if user has any assigned controllers
            user_entities = entities_controlled_by(username)
            if not user_entities and 'dm' not in user_role():
                # Redirect to character selection if no characters assigned
                return jsonify(status='character_selection_required')
            
            return jsonify(status='ok')
        return jsonify(error="Invalid Login Credentials")

    return render_template('login.html', title=TITLE, background=LOGIN_BACKGROUND)

@app.route('/character_selection', methods=['GET'])
def character_selection():
    if not logged_in():
        return redirect(url_for('login'))
    
    # Check if user already has characters assigned
    user_entities = entities_controlled_by(session['username'])
    if user_entities:
        return redirect(url_for('index'))
    
    # Get list of selectable characters from index.json
    selectable_characters = index_data.get("selectable_characters", [])
    
    # Find characters that are already taken by other users
    taken_characters = set()
    for controller in CONTROLLERS:
        if controller['controllers']:  # If anyone is assigned to this character
            taken_characters.add(controller['entity_uid'])
    
    return render_template('character_selection.html', 
                         title=TITLE, 
                         background=CHARACTER_SELECTION_BACKGROUND,
                         selectable_characters=selectable_characters,
                         taken_characters=taken_characters,
                         pvp_team_config=pvp_team_config(),
                         pvp_team_counts=pvp_team_counts())

def _register_new_character_in_campaign(pc, safe_name):
    """Place a new PC on the default map and expose it on the selection screen."""
    global index_data
    entity_uid = pc.get('entity_uid') or safe_name.lower()

    if builder_only_mode():
        return

    try:
        pc_entity = PlayerCharacter.load(game_session, f'characters/{safe_name}.yml')
        target_map = game_session.maps.get('index') or next(iter(game_session.maps.values()))
        width, height = target_map.size
        pos = None
        for y in range(height):
            for x in range(width):
                if not target_map.entity_at(x, y):
                    pos = (x, y)
                    break
            if pos:
                break
        if not pos:
            pos = (0, 0)
        target_map.add(pc_entity, pos[0], pos[1], group='a')
    except Exception:
        logger.exception('Failed to place new character on map')

    try:
        index_json_path = os.path.join(game_session.root_path, 'index.json')
        if os.path.exists(index_json_path):
            with open(index_json_path, 'r') as jf:
                idx = json.load(jf)
        else:
            idx = {}
        selectable = idx.get('selectable_characters') or []
        lower = str(entity_uid).lower()
        if not any(c.get('name', '').lower() == lower for c in selectable):
            selectable.append({
                'name': lower,
                'file': f'characters/{lower}.png',
                'description': pc.get('description', lower),
            })
        idx['selectable_characters'] = selectable
        with open(index_json_path, 'w') as jf:
            json.dump(idx, jf, indent=2)
        try:
            index_data['selectable_characters'] = selectable
        except Exception:
            logger.exception('Failed to update in-memory selectable_characters')
    except Exception:
        logger.exception('Failed to update index.json with new character')


@app.route('/character_builder/import_dndbeyond', methods=['POST'])
def import_dndbeyond_character():
  """Import a character sheet from a D&D Beyond URL and save it as campaign YAML."""
  if not logged_in():
    return jsonify(error='Not logged in'), 401

  payload = request.get_json(silent=True) or {}
  url = (payload.get('url') or request.form.get('url') or '').strip()
  cobalt_token = (
      (payload.get('cobalt_token') or request.form.get('cobalt_token') or '').strip()
      or os.environ.get('DND_BEYOND_COBALT_TOKEN')
      or os.environ.get('COBALT_SESSION')
      or None
  )

  character_id = parse_character_id_from_url(url)
  if character_id is None:
    return jsonify(
        error='Paste a D&D Beyond character sheet URL like '
              'https://www.dndbeyond.com/characters/12345678'
    ), 400

  try:
    pc, import_warnings = import_character_from_dndbeyond(
      character_id,
      cobalt_token=cobalt_token,
    )
  except RuntimeError as exc:
    return jsonify(error=str(exc)), 500
  except Exception as exc:
    logger.exception('D&D Beyond import failed for character %s', character_id)
    message = str(exc).strip() or 'Failed to import character from D&D Beyond'
    if '401' in message or '403' in message or 'Unauthorized' in message:
      message = (
          'Could not access that character. For private sheets, paste your '
          'CobaltSession cookie value (browser devtools → Application → Cookies '
          '→ dndbeyond.com → CobaltSession) or set DND_BEYOND_COBALT_TOKEN on the server.'
      )
    return jsonify(error=message), 502

  pc, safe_name = prepare_imported_pc_dict(pc)
  if not pc.get('name'):
    return jsonify(error='Imported character has no name'), 400

  races_def = game_session.load_races() or {}
  if pc.get('race') and pc['race'] not in races_def:
    return jsonify(
        error=f"Race '{pc.get('race')}' is not available in this campaign"
    ), 400

  classes_def = game_session.load_classes() or {}
  for klass in (pc.get('classes') or {}):
    if klass not in classes_def:
      return jsonify(
          error=f"Class '{klass}' is not available in this campaign"
      ), 400

  backgrounds_def = game_session.load_backgrounds() or {}
  bg = pc.get('background')
  if bg and bg not in backgrounds_def:
    return jsonify(
        error=f"Background '{bg}' is not available in this campaign"
    ), 400

  chars_dir = os.path.join(game_session.root_path, 'characters')
  os.makedirs(chars_dir, exist_ok=True)
  yml_path = os.path.join(chars_dir, f'{safe_name}.yml')
  if os.path.exists(yml_path):
    return jsonify(error='A character with that name already exists'), 400

  with open(yml_path, 'w', encoding='utf-8') as fh:
    yaml.safe_dump(pc, fh, sort_keys=False, allow_unicode=True)

  _register_new_character_in_campaign(pc, safe_name)

  if builder_only_mode():
    redirect_to = url_for('character_builder')
  else:
    redirect_to = '/character_selection' if 'dm' not in user_role() else '/'

  return jsonify(
      status='ok',
      redirect=redirect_to,
      character_name=pc.get('name'),
      character_file=f'characters/{safe_name}.yml',
      warnings=import_warnings,
  )


@app.route('/create_character', methods=['POST'])
def create_character():
    if not logged_in():
        return jsonify(error="Not logged in"), 401

    try:
        name = (request.form.get('name') or '').strip()
        pronoun = (request.form.get('pronoun') or '').strip()
        race = (request.form.get('race') or '').strip()
        subrace = (request.form.get('subrace') or '').strip()
        klass = (request.form.get('klass') or '').strip()
        try:
            level = int(request.form.get('level') or 1)
            if level not in (1,2):
                level = 1
        except Exception:
            level = 1

        try:
            ability = {
                'str': int(request.form.get('str') or 8),
                'dex': int(request.form.get('dex') or 8),
                'con': int(request.form.get('con') or 8),
                'int': int(request.form.get('int') or 8),
                'wis': int(request.form.get('wis') or 8),
                'cha': int(request.form.get('cha') or 8),
            }
        except ValueError:
            return jsonify(error='Invalid ability values'), 400

        if not name or not race or not klass:
            return jsonify(error='Name, race, and class are required'), 400

        races_def = game_session.load_races() or {}
        race_def = races_def.get(race)
        if race_def is None:
            return jsonify(error='Unknown race selection'), 400
        subrace_def = {}
        if subrace:
            subrace_def = (race_def.get('subrace') or {}).get(subrace, {})

        selected_skills = _parse_json_list_form(request.form, 'skills')
        selected_cantrips = _parse_json_list_form(request.form, 'cantrips')
        selected_level1 = _parse_json_list_form(request.form, 'level1_spells')
        selected_feats = _parse_json_list_form(request.form, 'feats')
        race_bonus_map = _parse_json_dict_form(request.form, 'race_ability_bonuses')
        race_skill_selections = _parse_json_list_form(request.form, 'race_skills')
        race_language_selections = _parse_json_list_form(request.form, 'race_languages')

        # Background handling
        background_key = (request.form.get('background') or '').strip()
        background_language_selections = _parse_json_list_form(request.form, 'background_languages')
        backgrounds_def = game_session.load_backgrounds() or {}
        background_def = backgrounds_def.get(background_key) if background_key else None
        if background_key and background_def is None:
            return jsonify(error='Unknown background selection'), 400

        flexible_cfg = subrace_def.get('flexible_ability') or race_def.get('flexible_ability') or {}
        expected_picks = flexible_cfg.get('picks') or []
        if expected_picks:
            if not race_bonus_map:
                return jsonify(error='Select all racial ability bonuses.'), 400
            expected_amounts = [int(pick.get('amount', 1)) for pick in expected_picks]
            try:
                actual_amounts = sorted([int(v) for v in race_bonus_map.values()])
            except Exception:
                return jsonify(error='Invalid racial ability bonuses'), 400
            expected_sorted = sorted(expected_amounts)
            if flexible_cfg.get('unique', True):
                if actual_amounts != expected_sorted:
                    return jsonify(error='Invalid racial ability bonuses'), 400
            else:
                if sum(actual_amounts) != sum(expected_amounts):
                    return jsonify(error='Invalid racial ability bonuses'), 400
            if any(ab not in ability for ab in race_bonus_map.keys()):
                return jsonify(error='Invalid racial ability bonuses'), 400
        else:
            if race_bonus_map:
                return jsonify(error='Unexpected racial ability bonuses'), 400
            race_bonus_map = {}

        skill_choice_cfg = subrace_def.get('skill_choices') or race_def.get('skill_choices') or {}
        if skill_choice_cfg.get('count'):
            expected_count = int(skill_choice_cfg['count'])
            options = set(skill_choice_cfg.get('options') or [])
            if len(race_skill_selections) != expected_count:
                plural = '' if expected_count == 1 else 's'
                return jsonify(error=f'Choose {expected_count} racial skill{plural}.'), 400
            if not all(choice in options for choice in race_skill_selections):
                return jsonify(error='Invalid racial skill choices'), 400
        else:
            if race_skill_selections:
                return jsonify(error='Unexpected racial skill choices'), 400
            race_skill_selections = []

        language_choice_cfg = subrace_def.get('language_choices') or race_def.get('language_choices') or {}
        if language_choice_cfg.get('count'):
            expected_language_count = int(language_choice_cfg['count'])
            options = set(language_choice_cfg.get('options') or [])
            if len(race_language_selections) != expected_language_count:
                plural = '' if expected_language_count == 1 else 's'
                return jsonify(error=f'Choose {expected_language_count} bonus language{plural}.'), 400
            if not all(choice in options for choice in race_language_selections):
                return jsonify(error='Invalid racial language choices'), 400
        else:
            if race_language_selections:
                return jsonify(error='Unexpected racial language choices'), 400
            race_language_selections = []

        def _apply_racial_bonus(bonus_map):
            if not isinstance(bonus_map, dict):
                return
            for key, value in bonus_map.items():
                if key in ability:
                    try:
                        ability[key] = min(20, ability[key] + int(value))
                    except Exception:
                        continue

        _apply_racial_bonus(race_def.get('attribute_bonus'))
        if subrace_def:
            _apply_racial_bonus(subrace_def.get('attribute_bonus'))
        if race_bonus_map:
            for key, value in race_bonus_map.items():
                ability[key] = min(20, ability[key] + int(value))

        base_languages = []
        for lang_src in (race_def.get('languages', []), subrace_def.get('languages', [])):
            if lang_src:
                base_languages.extend([str(l) for l in lang_src])

        # Build PC YAML compatible with existing templates
        # Basic defaults: level 1, hit_die inherit, simple equipment empty
        entity_uid = re.sub(r'[^a-zA-Z0-9_\-]', '_', name).lower()
        pc = {
            'name': name,
            'race': race,
            'classes': { klass: level },
            'level': level,
            'hit_die': 'inherit',
            'max_hp': 8,  # coarse default; real HP will be class-based later
            'ability': ability,
            'equipped': [],
            'inventory': [],
            'token': [ name[:1].upper() ],
            'description': f"A newly forged {race} {klass}.",
            'entity_uid': entity_uid,
            'token_image': f"token_{entity_uid}.png",
            'profile_image': f"characters/{entity_uid}.png",
        }
        if pronoun:
            pc['pronoun'] = pronoun
        if subrace:
            pc['subrace'] = subrace

        # Background assignment
        if background_key and background_def:
            pc['background'] = background_key
            # Background skill proficiencies are auto-added to skills list
            for skill in background_def.get('skill_proficiencies', []):
                pc.setdefault('skills', [])
                if skill not in pc['skills']:
                    pc['skills'].append(skill)
            # Background tool proficiencies
            for tool in background_def.get('tool_proficiencies', []):
                pc.setdefault('tool_proficiencies', [])
                if tool not in pc['tool_proficiencies']:
                    pc['tool_proficiencies'].append(tool)
            # Background fixed languages
            for lang in background_def.get('languages', []):
                pc.setdefault('languages', [])
                if lang not in pc['languages']:
                    pc['languages'].append(lang)

        languages = list(dict.fromkeys(base_languages + race_language_selections))
        # Add background language choices
        if background_language_selections:
            languages = list(dict.fromkeys(languages + background_language_selections))
        if languages:
            pc['languages'] = languages

        # Validate and apply class choices from templates
        try:
            classes_def = game_session.load_classes() or {}
            _apply_class_and_feat_choices(
                pc,
                klass,
                level,
                classes_def,
                selected_skills,
                selected_cantrips,
                selected_level1,
                selected_feats,
            )

            # Apply equipment pack if selected
            equipment_pack_id = (request.form.get('equipment_pack') or '').strip()
            if equipment_pack_id:
                equipment_packs = game_session.load_equipment_packs() or {}
                pack = equipment_packs.get(equipment_pack_id)
                if pack and 'items' in pack:
                    for item_id, qty in pack['items'].items():
                        pc.setdefault('inventory', []).append({
                            'item': item_id,
                            'qty': int(qty)
                        })

            # Apply custom inventory from character builder
            inventory_json = (request.form.get('inventory') or '').strip()
            if inventory_json:
                try:
                    import json as _json
                    custom_inventory = _json.loads(inventory_json)
                    if custom_inventory:
                        pc['inventory'] = custom_inventory
                except Exception:
                    logger.exception('Failed to parse custom inventory')

            if race_skill_selections:
                pc.setdefault('skills', [])
                for skill in race_skill_selections:
                    if skill not in pc['skills']:
                        pc['skills'].append(skill)
        except Exception:
            logger.exception('Failed to apply class choices')

    # Save to templates/characters
        chars_dir = os.path.join(game_session.root_path, 'characters')
        os.makedirs(chars_dir, exist_ok=True)
        safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', name)
        yml_path = os.path.join(chars_dir, f"{safe_name}.yml")
        if os.path.exists(yml_path):
            return jsonify(error='A character with that name already exists'), 400

        import yaml as _yaml
        with open(yml_path, 'w') as f:
            _yaml.safe_dump(pc, f, sort_keys=False)

        # Save provided images (uploaded, prebuilt, or canvas-cropped data URL).
        # If a portrait was provided but no token, auto-generate a circular
        # token from the portrait so the on-map look stays consistent.
        try:
            assets_dir = os.path.join(game_session.root_path, 'assets')
            os.makedirs(assets_dir, exist_ok=True)
            profile_pil = _load_character_image_from_request(
                request,
                file_field='profile_image',
                prebuilt_field='profile_prebuilt',
            )
            token_pil = _load_character_image_from_request(
                request,
                file_field='token_image',
                prebuilt_field='token_prebuilt',
                data_url_field='token_image_data',
            )
            _save_character_images(entity_uid, assets_dir, profile_pil=profile_pil, token_pil=token_pil)
        except Exception:
            logger.exception('Failed to save character images')

        _register_new_character_in_campaign(pc, safe_name)

        # Optionally redirect to selection if a player
        if builder_only_mode():
            redirect_to = url_for('character_builder')
        else:
            redirect_to = '/character_selection' if 'dm' not in user_role() else '/'
        return jsonify(status='ok', redirect=redirect_to)
    except Exception as e:
        logger.exception('Failed to create character')
        return jsonify(error='Failed to create character'), 500

@app.route('/select_character', methods=['POST'])
def select_character():
    if not logged_in():
        return jsonify(error="Not logged in"), 401
    
    character_name = request.form.get('character')
    selected_team = (request.form.get('team') or '').lower()
    username = session['username']
    
    if not character_name:
        return jsonify(error="No character specified")
    
    # Check if character exists in selectable characters
    character_exists = selectable_character_entry(character_name) is not None
    
    if not character_exists:
        return jsonify(error="Invalid character selection")
    
    # Check if character is already taken
    for controller in CONTROLLERS:
        if controller['entity_uid'] == character_name and controller['controllers']:
            return jsonify(error="Character is already taken")

    team_config = pvp_team_config()
    if team_config and not selected_team:
        return jsonify(error='Choose Team A or Team B before confirming your slot')
    
    # Assign character to user
    controller_entry = None
    controller_entry = ensure_controller_entry(character_name)
    if username not in controller_entry['controllers']:
        controller_entry['controllers'].append(username)

    if team_config:
        try:
            assign_character_team_and_spawn(character_name, selected_team)
        except ValueError as exc:
            if controller_entry and username in controller_entry.get('controllers', []):
                controller_entry['controllers'].remove(username)
            return jsonify(error=str(exc))
    else:
        # Non-PvP flow: materialize the selected character (loads the PC sheet
        # and reserves a player_spawn_point if needed) so the subsequent
        # spawn_player_for_user call has something deferred to place.
        try:
            if ensure_character_entity_loaded(character_name) is None:
                if controller_entry and username in controller_entry.get('controllers', []):
                    controller_entry['controllers'].remove(username)
                return jsonify(error='No spawn slot available for this character')
        except Exception as exc:
            logger.exception(f"Failed to materialize character {character_name}")
            if controller_entry and username in controller_entry.get('controllers', []):
                controller_entry['controllers'].remove(username)
            return jsonify(error=f'Failed to load character: {exc}')

    # Update the current_game controllers if needed
    current_game._setup_controllers()

    # Spawn deferred PC for this user after character selection
    current_game.spawn_player_for_user(username)

    # Proactively set POV and sync current map to the selected character to avoid stale map on first load
    try:
        entity = current_game.get_entity_by_uid(character_name)
        if entity is not None:
            current_game.set_pov_entity_for_user(username, entity)
            try:
                entity_map = current_game.get_map_for_entity(entity)
                if entity_map is not None:
                    current_game.switch_map_for_user(username, entity_map.name)
            except Exception:
                pass
    except Exception:
        # Non-fatal; index() will still attempt to correct on first render
        pass

    logger.info(f"User {username} selected character {character_name}")
    return jsonify(status='ok')

@app.route('/character_details/<character_name>', methods=['GET'])
def character_details(character_name):
    """Get detailed information about a character for preview"""
    try:
        # Load the character from the game session (may need to materialize from sheet)
        character = ensure_character_entity_loaded(character_name)
        
        if not character:
            return jsonify(error="Character not found"), 404
        
        # Extract important character information
        details = {
            'name': character.name.title(),
            'display_name': character.display_name,
            'race': character.race(),
            'subrace': character.subrace() or 'None',
            'classes': character.c_class(),
            'level': character.level(),
            'hit_points': {
                'current': character.hp(),
                'maximum': character.max_hp()
            },
            'armor_class': character.armor_class(),
            'speed': character.speed(),
            'ability_scores': {
                'str': character.ability_score_str(),
                'dex': character.ability_score_dex(), 
                'con': character.ability_score_con(),
                'int': character.ability_score_int(),
                'wis': character.ability_score_wis(),
                'cha': character.ability_score_cha()
            },
            'ability_modifiers': {
                'str': character.str_mod(),
                'dex': character.dex_mod(),
                'con': character.con_mod(), 
                'int': character.int_mod(),
                'wis': character.wis_mod(),
                'cha': character.cha_mod()
            },
            'proficiency_bonus': character.proficiency_bonus(),
            'passive_perception': character.passive_perception(),
            'languages': character.languages(),
            'equipment': {
                'weapons': [],
                'armor': [],
                'other': []
            },
            'spells': {
                'has_spells': character.has_spells() if hasattr(character, 'has_spells') else False,
                'spell_slots': {},
                'known_spells': []
            },
            'class_features': [],
            'racial_features': []
        }
        
        # Get equipped items
        equipped_items = character.equipped_items()
        for item in equipped_items:
            item_type = item.get('type', 'other')
            item_info = {
                'name': item.get('label', item.get('name', 'Unknown')),
                'damage': item.get('damage'),
                'range': item.get('range'),
                'properties': item.get('properties', [])
            }
            
            if item_type in ['melee_attack', 'ranged_attack']:
                details['equipment']['weapons'].append(item_info)
            elif item_type in ['armor', 'shield']:
                item_info['ac'] = item.get('ac')
                item_info['bonus_ac'] = item.get('bonus_ac')
                details['equipment']['armor'].append(item_info)
            else:
                details['equipment']['other'].append(item_info)
        
        # Get spell information if character has spells
        if details['spells']['has_spells']:
            try:
                # Get available spells
                available_spells = character.available_spells(None)
                details['spells']['known_spells'] = available_spells
                
                # Get spell slots for each class
                for class_name in character.c_class().keys():
                    class_slots = {}
                    for level in range(1, 10):
                        slots = character.spell_slots_count(level, class_name)
                        if slots > 0:
                            class_slots[f'level_{level}'] = slots
                    if class_slots:
                        details['spells']['spell_slots'][class_name] = class_slots
            except:
                # If spell info fails, just mark as having spells but no details
                pass
        
        # Get some key class features
        important_features = [
            'action_surge', 'second_wind', 'sneak_attack', 'rage', 'bardic_inspiration',
            'channel_divinity', 'lay_on_hands', 'fighting_style', 'spellcasting'
        ]
        for feature in important_features:
            if character.class_feature(feature):
                details['class_features'].append(feature.replace('_', ' ').title())
        
        # Get racial features
        racial_features = character.race_properties.get('race_features', [])
        details['racial_features'] = [f.replace('_', ' ').title() for f in racial_features[:5]]  # Limit to first 5

        # Journal entries (per-PC quest log). Returned in chronological order
        # so the UI can render newest-first via simple slicing.
        details['journal'] = list(getattr(character, 'journal', None) or [])

        return jsonify(details)
        
    except Exception as e:
        logger.error(f"Error getting character details for {character_name}: {e}")
        return jsonify(error="Failed to load character details"), 500


# ── Per-character Journal ─────────────────────────────────────────────────
def _journal_owner_check(character):
    """Return (allowed, error_response). Players may only act on their own
    PCs; DMs may act on any character.
    """
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
    try:
        save = getattr(current_game, 'save_game_async', None)
        if callable(save):
            save()
    except Exception as exc:  # pragma: no cover - autosave is best-effort
        logger.debug(f"Journal autosave skipped: {exc}")


def _log_journal_entry_to_campaign_db(character, entry):
    db = getattr(current_game, 'campaign_log_db', None)
    if db is None or not entry:
        return
    try:
        db.append_journal_entry(getattr(character, 'entity_uid', None), entry)
    except Exception as exc:
        logger.debug(f"Campaign journal log skipped: {exc}")


def _record_narration_for_pcs(narration, map_name=None, target_uids=None,
                              source=None):
    """Append a narration entry to every relevant PC's journal.

    ``target_uids`` constrains the recipients; otherwise every PC currently
    on ``map_name`` (or every PC in the campaign if no map context exists)
    receives the entry. Emits a ``journal_update`` socket message so any
    open journal panels can refresh.
    """
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
        for m in maps:
            for ent in getattr(m, 'entities', []) or []:
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


@app.route('/character/<character_name>/journal', methods=['GET'])
def character_journal_list(character_name):
    """Return a PC's journal entries. Supports ``?q=`` substring search,
    ``?kind=`` filter, and ``?limit=`` truncation.
    """
    character = current_game.get_entity_by_uid(character_name)
    if not character:
        return jsonify(error="Character not found"), 404
    if not isinstance(character, PlayerCharacter):
        return jsonify(error="Journals are only available for player characters"), 400
    allowed, err = _journal_owner_check(character)
    if not allowed:
        return err
    query = request.args.get('q') or request.args.get('query')
    kind = request.args.get('kind')
    limit_raw = request.args.get('limit')
    limit = None
    if limit_raw:
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError):
            limit = None
    entries = _serialize_journal(character, query=query, kind=kind, limit=limit)
    return jsonify({
        'entity_uid': character.entity_uid,
        'count': len(entries),
        'entries': entries,
    })


@app.route('/character/<character_name>/journal', methods=['POST'])
def character_journal_add(character_name):
    """Append a manual journal entry for ``character_name``."""
    character = current_game.get_entity_by_uid(character_name)
    if not character:
        return jsonify(error="Character not found"), 404
    if not isinstance(character, PlayerCharacter):
        return jsonify(error="Journals are only available for player characters"), 400
    allowed, err = _journal_owner_check(character)
    if not allowed:
        return err
    payload = request.get_json(silent=True) or {}
    text = (payload.get('text') or '').strip()
    if not text:
        return jsonify(error='Entry text is required'), 400
    title = payload.get('title')
    tags = payload.get('tags') or []
    if not isinstance(tags, list):
        tags = [str(tags)]
    requester_role = 'dm' if 'dm' in user_role() else 'player'
    kind = payload.get('kind') or ('dm' if requester_role == 'dm' else 'note')
    entry = character.add_journal_entry(
        text,
        kind=kind,
        title=title,
        source=session.get('username'),
        tags=tags,
    )
    if entry:
        _log_journal_entry_to_campaign_db(character, entry)
    _persist_journal_change(character)
    try:
        socketio.emit('message', {
            'type': 'journal_update',
            'entity_uids': [character.entity_uid],
            'reason': kind,
        })
    except Exception:
        pass
    return jsonify({'entry': entry, 'count': len(character.journal)})


@app.route('/character/<character_name>/journal/<entry_id>', methods=['DELETE'])
def character_journal_delete(character_name, entry_id):
    character = current_game.get_entity_by_uid(character_name)
    if not character:
        return jsonify(error="Character not found"), 404
    if not isinstance(character, PlayerCharacter):
        return jsonify(error="Journals are only available for player characters"), 400
    allowed, err = _journal_owner_check(character)
    if not allowed:
        return err
    removed = character.remove_journal_entry(entry_id)
    if not removed:
        return jsonify(error='Entry not found'), 404
    _persist_journal_change(character)
    try:
        socketio.emit('message', {
            'type': 'journal_update',
            'entity_uids': [character.entity_uid],
            'reason': 'delete',
        })
    except Exception:
        pass
    return jsonify({'status': 'ok', 'count': len(character.journal)})

def pov_entities():
    global current_game
    if 'dm' in user_role():
        # get all maps
        pov_entities = []
        for map in current_game.maps.values():
            for e in map.entities:
                if isinstance(e, PlayerCharacter):
                    if e not in pov_entities:
                        pov_entities.append(e)
    else:
        pov_entities = entities_controlled_by(session['username'])
    return pov_entities


def render_pov_entities():
    global current_game
    if 'dm' in user_role():
        pov_entity = current_game.get_pov_entity_for_user(session['username'])
        return [pov_entity] if pov_entity else None
    return entities_controlled_by(session['username'])

@app.route('/')
def index():
    global current_game, logger
    if builder_only_mode():
        return redirect(url_for('character_builder'))
    if not logged_in():
        print("not logged in")
        return redirect(url_for('login'))

    # Spawn any deferred PCs for this user (handles returning sessions that skip login)
    current_game.spawn_player_for_user(session['username'])

    # Check if user needs to select a character
    if 'dm' not in user_role():
        user_entities = entities_controlled_by(session['username'])
        if not user_entities:
            return redirect(url_for('character_selection'))

        pov_entity = current_game.get_pov_entity_for_user(session['username'])
        if not pov_entity:
            # Initialize POV to the selected character and sync current map accordingly
            current_game.set_pov_entity_for_user(session['username'], user_entities[0])
            pov_entity = user_entities[0]
            entity_map = current_game.get_map_for_entity(pov_entity)
            if entity_map is not None:
                try:
                    current_game.switch_map_for_user(session['username'], entity_map.name)
                except Exception:
                    pass
            battle_map = entity_map or current_game.get_map_for_user(session['username'])
        else:
            battle_map = current_game.get_map_for_entity(pov_entity)
    else:
        battle_map = current_game.get_map_for_user(session['username'])

    battle = current_game.get_current_battle()
    available_maps = current_game.get_available_maps()

    background = current_game.get_background_image_for_user(session['username'])
    renderer = JsonRenderer(battle_map, battle, padding=MAP_PADDING, logger=logger)
    rendered_pov_entities = render_pov_entities()

    my_2d_array = [renderer.render(entity_pov=rendered_pov_entities)]
    map_width, map_height = battle_map.size
    left_offset_px, top_offset_px = battle_map.image_offset_px

    tiles_dimension_height = map_height * TILE_PX
    tiles_dimension_width = map_width * TILE_PX
    messages = visible_log_messages_for_username(session['username'], user_role())

    # get entity ids of the current user
    entity_ids = []
    for info in CONTROLLERS:
        if session['username'] in info['controllers']:
            entity_ids.append(info['entity_uid'])
    web_extensions = battle_map.properties.get('extensions', { "web": {} })
    web_extensions = web_extensions.get('web', {})
    background_color = web_extensions.get('background_color', '#FFFFFF')
    width_px = (map_width + 2) * TILE_PX
    height_px = (map_height + 2) * TILE_PX
    if current_game.current_soundtrack:
        time_s = (time.time() - current_game.current_soundtrack
                        ['start_time']) % current_game.current_soundtrack['duration']
        current_game.current_soundtrack['time'] = int(time_s)

    current_pov_entity = current_game.get_pov_entity_for_user(session['username'])
    return render_template('index.html', tiles=my_2d_array, tile_size_px=TILE_PX,
                           pov_entity=current_pov_entity,
                           background_path=f"assets/{background}",
                           background_width=tiles_dimension_width,
                           messages=messages,
                           current_map=battle_map.name,
                           current_map_name=battle_map.name,
                           read_notes=current_game.read_notes,
                           is_setup=False,
                        background_height=tiles_dimension_height,
                           battle=battle,
                           entity_ids=entity_ids,
                           background_color=background_color,
                           width_px=width_px,
                           height_px=height_px,
                           waiting_for_reaction=current_game.waiting_for_reaction,
                           soundtrack=current_game.current_soundtrack,
                           title=TITLE,
                           top_offset_px=top_offset_px,
                           left_offset_px=left_offset_px,
                           available_maps=available_maps,
                           user_entity_ids=[e.entity_uid for e in entities_controlled_by(session['username'])],
                           pov_entities=pov_entities(),
                           current_pov=current_pov_entity.entity_uid if current_pov_entity else None,
                           game_session=current_game.game_session,
                           username=session['username'], role=user_role(),
                           DEFAULT_NPC_CONTROLLER=current_game.effective_npc_combat_controller(),
                           NPC_LLM_COMBAT_ENABLED=current_game.force_llm_npc_combat,
                           pvp_enabled=bool(pvp_team_config()),
                           narration=battle_map.narration(),
                           special_effects_enabled=special_effects_enabled())
eval_context = {}

@app.route('/command', methods=['POST'])
def command():
    global current_game, eval_context
    battle_map = current_game.get_map_for_user(session['username'])
    battle = current_game.get_current_battle()

    command = request.form['command']
    logger.info(f"command: {command}")
    # execute the command using the current python session and return the
    # the result as a string
    try:
        if command:
            # Create context with map, battle, and session
            battle_map = current_game.get_map_for_user(session['username'])
            battle = current_game.get_current_battle()
            eval_context.update({
                'map': battle_map,
                'battle': battle,
                'session': game_session,
                'game': current_game,
                'json': json
            })

            # if command starts with "." than it is referencing the map object
            # prefix it with map
            if command.startswith('.'):
                command = f"map{command}"

            # if command starts with "!" than it is referencing an entity,
            # first resolve the entity name by using map.entity_by_uid

            if command.startswith('!'):
                entity_uid = command[1:]
                entity = current_game.get_entity_by_uid(entity_uid)
                if entity:
                    eval_context[entity.name] = entity
                    eval_context['entity'] = entity
                    eval_context['entity_uid'] = entity_uid
                    return jsonify(str(entity))
                else:
                    return jsonify(error=f"Entity {entity_uid} not found")

            output = eval(command, eval_context)
            eval_context['__output'] = output
            return jsonify(output)
    except Exception as e:
        return jsonify(error=str(e))
    return jsonify(status='ok')

@app.route('/reload_map', methods=['POST'])
def reload_map():
    global current_game
    current_game.reload_map_for_user(session['username'])
    return jsonify(status='ok')

@app.route('/response', methods=['POST'])
def response():
    global current_game
    callback_id = request.json['callback']
    callback = current_game.callbacks.pop(callback_id, None)
    if callback:
        callback(request.json)
    return jsonify(status='ok')

@app.route('/focus', methods=['POST'])
def focus():
    x = request.form['x']
    y = request.form['y']

    socketio.emit('message', {'type': 'focus', 'message': {'x': x, 'y': y}})
    return jsonify(status='ok')

@app.route('/switch_map', methods=['POST'])
def switch_map():
    global current_game
    map_name = request.form['map']
    current_game.switch_map_for_user(session['username'], map_name)
    battle_map = current_game.get_map_for_user(session['username'])
    background = current_game.get_background_image_for_user(session['username'])
    map_width, map_height = battle_map.size
    tiles_dimension_height = map_height * TILE_PX
    tiles_dimension_width = map_width * TILE_PX
    # Check for a map-default effect defined in the map properties
    map_default = None
    map_defaults = []
    try:
        map_defaults = map_default_effect_payloads(battle_map)
        map_default = map_defaults[0] if map_defaults else None
    except Exception:
        map_default = None

    # Determine whether a DM-initiated effect is currently active for this game
    dm_active = False
    try:
        game_key = getattr(current_game.game_session, 'root_path', None) or getattr(game_session, 'root_path', None) or LEVEL
        dm_active = has_enabled_effect_payloads(active_effects.get(game_key, {}).values())
        # Include per-map overrides
        try:
            dm_active = dm_active or has_enabled_effect_payloads(active_effects_map.get(game_key, {}).get(map_name, {}).values())
        except Exception:
            pass
    except Exception:
        dm_active = False

    return jsonify(background=f"assets/{background}",
                   name=map_name,
                   image_offset_px=battle_map.image_offset_px,
                   height=tiles_dimension_height,
                   width=tiles_dimension_width,
                   map_default_effect=map_default,
                   map_default_effects=map_defaults,
                   dm_active=dm_active,
                   narration=battle_map.narration(),
                   special_effects_enabled=special_effects_enabled())

#                 // Fetch combat log messages from the server
# $.get('/api/combat-log', function(data) {
#     $('#console').empty();
#     data.messages.forEach(function(message) {
#         $('#console').append('<p>' + message + '</p>');
#     });
# });
@app.route('/api/combat-log', methods=['GET'])
def combat_log():
    global current_game
    battle = current_game.get_current_battle()
    logs = visible_log_messages_for_username(session['username'], user_role())
    response =[{'message': log} for log in logs]
    return jsonify(combat_log=response)

@app.route('/combat-log', methods=['GET'])
def get_combat_log():
    global current_game
    battle = current_game.get_current_battle()
    logs = visible_log_messages_for_username(session['username'], user_role())
    return render_template('combat-log.html', combat_log=logs,
                           username=session['username'], role=user_role())

@app.route('/path', methods=['GET'])
def compute_path():
    global current_game
    battle_map = current_game.get_map_for_user(session['username'])
    battle = current_game.get_current_battle()

    source = {
        'x': request.args.get('from[x]'),
        'y': request.args.get('from[y]')
    }
    destination = {
        'x': request.args.get('to[x]'),
        'y': request.args.get('to[y]')
    }
    dest = (int(destination['x']), int(destination['y']))
    entity_x = int(source['x'])
    entity_y = int(source['y'])

    accumulated_path = request.args.get('accumulatedPath')
    if accumulated_path:
        accumulated_path = json.loads(accumulated_path)
        # remove duplicates but preserve order
        # Convert each coordinate pair to a tuple so it can be used as a dict key
        accumulated_path = [tuple(coord) for coord in accumulated_path]
        accumulated_path = list(dict.fromkeys(accumulated_path))
        if len(accumulated_path) > 0:
            entity_x, entity_y = accumulated_path[0]
            entity_x = int(entity_x)
            entity_y = int(entity_y)
    else:
        accumulated_path = []

    entity = battle_map.entity_at(entity_x, entity_y)
    if entity is None:
        return jsonify(error='No entity at source'), 400

    # ----- Per-session LRU cache for /path responses --------------------------
    # Repeated hovers over the same tile (or returning to a recently visited
    # one) are very common; this avoids re-running A* for them.
    cache_key = (
        id(battle_map),
        getattr(entity, 'entity_uid', lambda: None)() if callable(getattr(entity, 'entity_uid', None)) else getattr(entity, 'entity_uid', None),
        int(source['x']), int(source['y']),
        dest[0], dest[1],
        tuple(accumulated_path),
    )
    cache = session.setdefault('_path_cache', None)
    # Flask sessions don't support OrderedDict directly; keep an in-process
    # dict keyed by username + battle_map id instead.
    user_key = session.get('username') or 'anonymous'
    proc_cache = _PATH_RESPONSE_CACHE.setdefault(user_key, OrderedDict())
    cached = proc_cache.get(cache_key)
    if cached is not None:
        # Refresh LRU order
        proc_cache.move_to_end(cache_key)
        return jsonify(cached)

    if battle and entity in getattr(battle, 'entities', {}):
        available_movement = entity.available_movement(battle)
    else:
        # Out-of-combat exploration: don't cap path length so users can
        # plan long traversal routes through the web UI.
        available_movement = None

    path_compute = PathCompute(battle, battle_map, entity)
    path = path_compute.compute_path(int(source['x']),
                                     int(source['y']),
                                     dest[0], dest[1],
                                     accumulated_path=accumulated_path,
                                     available_movement_cost=available_movement)
    # Only retry with door navigation when the first pass didn't reach the
    # destination. Skipping the redundant second A* halves CPU on most hovers.
    if not path or dest not in path:
        path = path_compute.compute_path(int(source['x']),
                                         int(source['y']),
                                         dest[0], dest[1],
                                         accumulated_path=accumulated_path,
                                         available_movement_cost=available_movement,
                                         door_navigation=True)

    if accumulated_path:
        full_path = list(accumulated_path)
        full_path.extend(path[1:])
    else:
        full_path = path

    cost = battle_map.movement_cost(entity, full_path)
    placeable = battle_map.placeable(entity, dest[0], dest[1], battle, False)

    # Build terrain info via a per-(map, entity, battle) memoized helper to
    # avoid recomputing difficult-terrain for the same tile across hovers.
    terrain_info = []
    if path:
        diff_lookup = _difficult_terrain_lookup(battle_map, entity, battle)
        for x, y in path:
            terrain_info.append({
                'x': x,
                'y': y,
                'difficult': bool(diff_lookup(x, y)),
            })

    path_data = {
        "path": path,
        "cost": cost.to_dict(),
        "placeable": placeable,
        "terrain_info": terrain_info,
    }

    proc_cache[cache_key] = path_data
    if len(proc_cache) > _PATH_RESPONSE_CACHE_LIMIT:
        proc_cache.popitem(last=False)
    return jsonify(path_data)


@app.route('/path/cost_map', methods=['GET'])
def path_cost_map():
    """Return a pathfinding snapshot for client-side A* (see webapp/static/path_compute.js)."""
    global current_game
    battle_map = current_game.get_map_for_user(session['username'])
    battle = current_game.get_current_battle()

    try:
        source_x = int(request.args.get('from[x]'))
        source_y = int(request.args.get('from[y]'))
    except (TypeError, ValueError):
        return jsonify(error='from[x] and from[y] are required'), 400

    entity = battle_map.entity_at(source_x, source_y)
    if entity is None:
        return jsonify(error='No entity at source'), 400

    if battle and entity in getattr(battle, 'entities', {}):
        available_movement = entity.available_movement(battle)
    else:
        available_movement = None

    snapshot = build_pathfinding_snapshot(
        battle_map,
        entity,
        battle,
        ignore_opposing=False,
    )
    return jsonify({
        'snapshot': snapshot,
        'available_movement': available_movement,
        'feet_per_grid': battle_map.feet_per_grid,
    })


@app.route('/jump_info', methods=['GET'])
def jump_info():
    """Return jump distance information for an entity.
    Query params:
      - id or entity_id: the entity UID
      - running: '1' or '0' (optional). If provided, compute the jump grids for that context.
    Response:
      { 'feet_per_grid': int, 'standing_grids': int, 'running_grids': int, 'grids': int }
    """
    global current_game
    try:
        entity_id = request.args.get('id') or request.args.get('entity_id')
        if not entity_id:
            return jsonify(error='Missing entity id'), 400
        entity = current_game.get_entity_by_uid(entity_id)
        if not entity:
            return jsonify(error='Entity not found'), 404

        battle_map = current_game.get_map_for_entity(entity)
        feet_per_grid = getattr(battle_map, 'feet_per_grid', 5)
        # Compute grids for standing and running jumps
        try:
            standing_grids = int(entity.standing_jump_distance() / feet_per_grid)
        except Exception:
            standing_grids = 0
        try:
            running_grids = int(entity.long_jump_distance() / feet_per_grid)
        except Exception:
            running_grids = standing_grids

        running_flag = request.args.get('running')
        if running_flag is not None:
            running_flag = running_flag in ('1', 'true', 'True')
            grids = running_grids if running_flag else standing_grids
        else:
            grids = running_grids  # default to the more permissive value if not specified

        return jsonify({
            'feet_per_grid': feet_per_grid,
            'standing_grids': standing_grids,
            'running_grids': running_grids,
            'grids': grids
        })
    except Exception as e:
        logger.exception('Failed to compute jump info')
        return jsonify(error=str(e)), 500


# Configure paths that don't require login
ALLOWED_PATHS = ['/login', '/health']
ALLOWED_PREFIXES = ['/favicon.ico', '/static/assets', '/assets/', '/libs/', '/character_builder/']

@app.before_request
def require_login():
    path = request.path
    if not logged_in() and (path not in ALLOWED_PATHS and not any(path.startswith(prefix) for prefix in ALLOWED_PREFIXES)):
        return redirect(url_for('login'))


# -----------------------
# Performance instrumentation (lightweight, always-on)
# -----------------------
# Rolling per-route stats. Bounded in size; no external deps.
_PERF_LOCK = threading.Lock()

_PERF_STATS = {
    'routes': {},          # endpoint -> {count, total_ms, max_ms, last_ms, slow}
    'socket_emits': {},    # event_name -> count
    'slow_threshold_ms': float(os.environ.get('PERF_SLOW_MS', '250')),
    'recent_slow': [],     # bounded list of recent slow requests
}
_PERF_RECENT_SLOW_MAX = 50

# Routes we never time (would be too noisy / static-like).
_PERF_SKIP_PREFIXES = ('/static', '/assets', '/libs', '/favicon', '/socket.io', '/health')


def _perf_should_track(path):
    if not path:
        return False
    return not any(path.startswith(p) for p in _PERF_SKIP_PREFIXES)


@app.before_request
def _perf_start_timer():
    if _perf_should_track(request.path):
        try:
            request._perf_t0 = time.perf_counter()
        except Exception:
            pass


@app.after_request
def _perf_stop_timer(response):
    try:
        t0 = getattr(request, '_perf_t0', None)
        if t0 is None:
            return response
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        endpoint = request.endpoint or request.path
        # Server-Timing header so devtools shows it.
        try:
            existing = response.headers.get('Server-Timing')
            new_val = f'app;dur={elapsed_ms:.1f}'
            response.headers['Server-Timing'] = f'{existing}, {new_val}' if existing else new_val
        except Exception:
            pass

        slow = elapsed_ms >= _PERF_STATS['slow_threshold_ms']
        with _PERF_LOCK:
            bucket = _PERF_STATS['routes'].setdefault(endpoint, {
                'count': 0, 'total_ms': 0.0, 'max_ms': 0.0, 'last_ms': 0.0, 'slow': 0,
            })
            bucket['count'] += 1
            bucket['total_ms'] += elapsed_ms
            bucket['last_ms'] = elapsed_ms
            if elapsed_ms > bucket['max_ms']:
                bucket['max_ms'] = elapsed_ms
            if slow:
                bucket['slow'] += 1
                _PERF_STATS['recent_slow'].append({
                    'ts': time.time(),
                    'endpoint': endpoint,
                    'path': request.path,
                    'method': request.method,
                    'ms': round(elapsed_ms, 1),
                    'status': response.status_code,
                })
                if len(_PERF_STATS['recent_slow']) > _PERF_RECENT_SLOW_MAX:
                    del _PERF_STATS['recent_slow'][0:len(_PERF_STATS['recent_slow']) - _PERF_RECENT_SLOW_MAX]
        if slow:
            try:
                logger.warning(f"[perf] slow {request.method} {request.path} -> {elapsed_ms:.1f}ms (status {response.status_code})")
            except Exception:
                pass
    except Exception:
        pass
    return response


# Wrap socketio.emit to count event rates without changing call sites.
try:
    _orig_socketio_emit = socketio.emit

    def _perf_socketio_emit(event, *args, **kwargs):
        try:
            with _PERF_LOCK:
                _PERF_STATS['socket_emits'][event] = _PERF_STATS['socket_emits'].get(event, 0) + 1
        except Exception:
            pass
        return _orig_socketio_emit(event, *args, **kwargs)

    socketio.emit = _perf_socketio_emit
except Exception:
    pass


@app.route('/admin/perf', methods=['GET'])
def admin_perf():
    if not session.get('username'):
        return jsonify(error='Unauthorized'), 401
    if 'dm' not in user_role():
        return jsonify(error='Forbidden'), 403
    with _PERF_LOCK:
        routes = []
        for ep, b in _PERF_STATS['routes'].items():
            routes.append({
                'endpoint': ep,
                'count': b['count'],
                'avg_ms': round(b['total_ms'] / b['count'], 2) if b['count'] else 0,
                'max_ms': round(b['max_ms'], 2),
                'last_ms': round(b['last_ms'], 2),
                'slow': b['slow'],
            })
        routes.sort(key=lambda r: r['avg_ms'] * r['count'], reverse=True)
        snapshot = {
            'slow_threshold_ms': _PERF_STATS['slow_threshold_ms'],
            'routes': routes,
            'socket_emits': dict(_PERF_STATS['socket_emits']),
            'recent_slow': list(_PERF_STATS['recent_slow']),
        }
    return jsonify(snapshot)


@app.route('/admin/perf/reset', methods=['POST'])
def admin_perf_reset():
    if not session.get('username'):
        return jsonify(error='Unauthorized'), 401
    if 'dm' not in user_role():
        return jsonify(error='Forbidden'), 403
    with _PERF_LOCK:
        _PERF_STATS['routes'].clear()
        _PERF_STATS['socket_emits'].clear()
        _PERF_STATS['recent_slow'].clear()
    return jsonify(status='ok')



@socketio.on('register')
def handle_connect(data):
    global current_game, first_connect
    username = data.get('username')
    ws = request.sid
    if ws:
        sids = current_game.username_to_sid.get(username, [])
        sids.append(ws)
        current_game.username_to_sid[username] = sids
        logger.info(f"open connection {ws} for {username}")
        emit('info', {'type': 'info', 'message': ''})

@socketio.on('message')
def handle_message(data):
    if data['type'] == 'ping':
        emit('ping', {'type': 'ping', 'message': 'pong'})
    elif data['type'] == 'message':
        logger.info(f"message {data['message']}")
        if data['message']['action'] == 'move':
            entity = map.entity_at(data['message']['from']['x'], data['message']['from']['y'])
            if map.placeable(entity, data['message']['to']['x'], data['message']['to']['y']):
                battle = current_game.get_current_battle()
                map.move_to(entity, data['message']['to']['x'], data['message']['to']['y'], battle)
                emit('move', {'type': 'move', 'message': {'from': data['message']['from'], 'to': data['message']['to']}})
        else:
            emit('error', {'type': 'error', 'message': 'Unknown command!'})
    elif data['type'] == 'command':
        logger.info(f"command {data['message']}")
        command = data['message']['command']
        # Process the command
        try:
            # Execute the command
            result = current_game.execute_command(command)
            emit('command_response', {'type': 'command_response', 'message': result})
        except Exception as e:
            logger.error(f"Error executing command: {e}")
            emit('command_response', {'type': 'command_response', 'message': f"Error: {str(e)}"})
    else:
        emit('error', {'type': 'error', 'message': 'Unknown command!'})

@socketio.on('disconnect')
def handle_disconnect():
    global current_game
    ws = request.sid
    username = session.get('username')
    if ws and username:
        sids = current_game.username_to_sid.get(username, [])
        if ws in sids:  # Only remove if the sid exists in the list
            sids.remove(ws)
            current_game.username_to_sid[username] = sids
            logger.info(f"close connection {ws} for {username}")

@app.route('/health', methods=['GET'])
def health_check():
    """Simple health check endpoint for AWS load balancer."""
    return jsonify(status='ok'), 200

@app.route('/refresh-portraits', methods=['GET'])
def refresh_portraits():
    """Endpoint to refresh the floating entity portraits."""
    global current_game
    username = session.get('username')
    if not username:
        return "", 200
    current_pov_entity = current_game.get_pov_entity_for_user(username)
    return render_template('floating_portraits.html', pov_entities=pov_entities(), current_pov_entity=current_pov_entity)

@app.route('/start', methods=['POST'])
def start_battle():
    if current_game.trigger_event('start_battle'):
        battle_map = current_game.get_current_battle_map()
        current_game.set_current_battle(Battle(game_session, battle_map, animation_log_enabled=True))
    return jsonify(status='ok')

@app.route('/stop', methods=['POST'])
def stop_battle():
    battle = current_game.get_current_battle()

    if battle:
        current_game.end_current_battle()
    return jsonify(status='ok')

@app.route('/battle', methods=['POST'])
def start_battle_with_initiative():
    global current_game
    if not current_game.trigger_event('start_battle'):

        battle_map = current_game.get_current_battle_map()

        if not request.json or 'battle_turn_order' not in request.json:
            return jsonify(error='No entities in turn order'), 400

        battle = Battle(game_session, battle_map, animation_log_enabled=True)
        current_game.set_current_battle(battle)

        battle_turn_order = autofill_pvp_battle_turn_order(request.json['battle_turn_order'])
        print(battle_turn_order)
        for param_item in battle_turn_order:
            entity = current_game.get_entity_by_uid(param_item['id'])

            ctrl_kind = param_item.get('controller')
            if ctrl_kind == 'ai':
                controller = GenericController(game_session)
            elif ctrl_kind == 'llm':
                # Use the same LLM provider configured for the webapp (e.g., Ollama)
                controller = LlmMcpController(game_session, llm_provider=llm_handler.current_provider)
            else:
                controller = current_game.get_controller_for_entity(entity)

            if controller is None:
                controller = web_controllers = WebController(game_session, None)
                web_controllers.add_user("dm")

            controller.register_handlers_on(entity)
            battle.add(entity, param_item['group'], controller=controller)
        output_logger.log("Battle started.", visibility='public')
        battle.start()
    else:
        print("skipping default battle start")
    scheduled = current_game.execute_game_loop()
    return jsonify(status='ok', game_loop='scheduled' if scheduled else 'already_running')


@app.route('/end_turn', methods=['POST'])
def end_turn():
    global current_game
    battle = current_game.get_current_battle()

    end_turn_state = True
    try:
        battle.end_turn()
        end_turn_state = False
        battle.next_turn()
        continue_game()
        return jsonify(status='ok')
    except AsyncReactionHandler as e:
        for _, entity, valid_actions in e.resolve():
            valid_actions_str = [[str(action.uid), str(action), action] for action in valid_actions]
            current_game.waiting_for_reaction = [entity, e, e.resolve(), valid_actions_str]
            current_game.end_turn_state = end_turn_state
            socketio.emit('message', {'type': 'reaction', 'message': {'id': entity.entity_uid, 'reaction': e.reaction_type}})
        return jsonify(status='ok')


def continue_game():
    global current_game
    current_game.schedule_continue_game_loop()

@app.route('/turn_order', methods=['GET'])
def get_turn_order():
    global current_game
    battle = current_game.get_current_battle()
    return render_template('battle.html', battle=battle, username=session['username'], role=user_role())

@app.route('/next_turn', methods=['POST'])
def next_turn():
    global current_game
    battle = current_game.get_current_battle()
    if battle:
        with current_game.game_state_lock:
            current_turn = battle.current_turn()
            if current_game.waiting_for_user_input():
                current_game.set_waiting_for_user_input(False)
                current_turn.resolve_trigger('end_of_turn')
                battle.end_turn()
                battle.next_turn()
                if battle.battle_ends():
                    current_game.end_current_battle()
                    return jsonify(status='ok')

        if current_game.get_current_battle():
            current_game.schedule_continue_game_loop()

    return jsonify(status='ok')

@app.route('/reorder_initiative', methods=['POST'])
def reorder_initiative():
    global current_game
    
    # Check if user is DM
    if 'dm' not in user_role():
        return jsonify(error='Only DMs can reorder initiative'), 403
    
    battle = current_game.get_current_battle()
    if not battle:
        return jsonify(error='No active battle'), 400
    
    if not request.json or 'entity_order' not in request.json:
        return jsonify(error='No entity order provided'), 400
    
    entity_order = request.json['entity_order']
    
    try:
        # Use the lock to make the operation atomic
        with current_game.game_state_lock:
            battle.reorder_initiative(entity_order)
        
        # Notify all clients of the initiative update
        socketio.emit('message', { 'type': 'initiative', 'message': {'index': battle.current_turn_index}})
        
        logger.info(f"Initiative reordered by {session['username']}: {entity_order}")
        return jsonify(status='ok')
        
    except ValueError as e:
        logger.error(f"Failed to reorder initiative: {str(e)}")
        return jsonify(error=str(e)), 400
    except Exception as e:
        logger.error(f"Unexpected error reordering initiative: {str(e)}")
        return jsonify(error='Internal server error'), 500

@app.route('/available_npcs', methods=['GET'])
def get_available_npcs():
    """Get list of available NPCs for spawning"""
    global current_game

    # Check if user is DM
    if 'dm' not in user_role():
        return jsonify(error='Only DMs can access NPC list'), 403

    try:
        cached = getattr(app, '_available_npcs_cache', None)
        if cached is None:
            # Use session.load_npcs() to get actual NPC instances with full data
            npcs = game_session.load_npcs()

            npc_list = []
            for npc in npcs:
                npc_list.append({
                    'id': npc.npc_type if hasattr(npc, 'npc_type') else npc.properties.get('id', 'unknown'),
                    'name': npc.label() if hasattr(npc, 'label') else npc.properties.get('label', npc.name),
                    'type': npc.properties.get('type', 'Unknown'),
                    'image': npc.token_image() if hasattr(npc, 'token_image') else npc.properties.get('token', f'{npc.name}.png'),
                    'cr': npc.properties.get('cr', 'Unknown'),
                    'size': npc.properties.get('size', 'Medium'),
                    'ac': npc.armor_class() if hasattr(npc, 'armor_class') else npc.properties.get('ac', 'Unknown'),
                    'hp': npc.max_hp() if hasattr(npc, 'max_hp') else npc.properties.get('hp', 'Unknown')
                })

            npc_list.sort(key=lambda x: x['name'].lower())
            app._available_npcs_cache = npc_list
            cached = npc_list

        return jsonify(npcs=cached)

    except Exception as e:
        logger.error(f"Error getting available NPCs: {str(e)}")
        return jsonify(error='Failed to load NPCs'), 500

@app.route('/available_objects', methods=['GET'])
def get_available_objects():
    """Get list of available objects for spawning"""
    global current_game

    # Check if user is DM
    if 'dm' not in user_role():
        return jsonify(error='Only DMs can access object list'), 403

    try:
        cached = getattr(app, '_available_objects_cache', None)
        if cached is None:
            # Load all objects from the objects.yml file
            all_objects = game_session.load_yaml_file('items', 'objects')

            object_list = []
            for object_id, object_data in all_objects.items():
                if object_data.get('token_editor_image'):
                    token_image = object_data['token_editor_image']
                else:
                    token_image = f'{object_id}.png'

                object_list.append({
                    'id': object_id,
                    'name': object_data.get('name', object_id.replace('_', ' ').title()),
                    'description': object_data.get('description', ''),
                    'image': token_image,
                    'ac': object_data.get('default_ac', 'N/A'),
                    'hp': object_data.get('max_hp', 'N/A'),
                    'passable': object_data.get('passable', False),
                    'opaque': object_data.get('opaque', True),
                    'color': object_data.get('color', 'brown')
                })

            object_list.sort(key=lambda x: x['name'])
            app._available_objects_cache = object_list
            cached = object_list

        return jsonify(objects=cached)

    except Exception as e:
        logger.error(f"Error loading objects: {str(e)}")
        return jsonify(error=f'Failed to load objects: {str(e)}'), 500

@app.route('/spawn_npc', methods=['POST'])
def spawn_npc():
    """Spawn an NPC at the specified coordinates"""
    global current_game
    
    # Check if user is DM
    if 'dm' not in user_role():
        return jsonify(error='Only DMs can spawn NPCs'), 403
    
    if not request.json:
        return jsonify(error='No data provided'), 400
    
    npc_type = request.json.get('npc_type')
    x = request.json.get('x')
    y = request.json.get('y')
    
    if not npc_type or x is None or y is None:
        return jsonify(error='Missing required parameters'), 400
    
    try:
        battle_map = current_game.get_map_for_user(session['username'])
        
        # Check if the position is within map bounds
        if (x < 0 or y < 0 or x >= battle_map.size[1] or y >= battle_map.size[0]):
            return jsonify(error='Position is outside map bounds'), 400
        
        # Check if the position is occupied by an entity
        if battle_map.entity_at(x, y):
            return jsonify(error='Position is occupied'), 400
        
        # Create the NPC
        try:
            npc = game_session.npc(npc_type, {"rand_life": True})
        except FileNotFoundError:
            return jsonify(error=f'NPC type "{npc_type}" not found'), 400
        except Exception as e:
            return jsonify(error=f'Failed to create NPC: {str(e)}'), 400
        
        # Add to map using the add method (which handles placement and group assignment)
        battle_map.add(npc, x, y, group='b')
        
        # If there's an active battle, optionally add to initiative
        battle = current_game.get_current_battle()
        if battle:
            # For now, don't automatically add to initiative
            # The DM can manually add them if needed
            pass
        
        logger.info(f"DM {session['username']} spawned {npc_type} at ({x}, {y})")
        
        # Notify all clients of the map update
        socketio.emit('message', {'type': 'refresh_map'})
        
        return jsonify(status='ok', entity_uid=npc.entity_uid)
        
    except Exception as e:
        logger.error(f"Error spawning NPC: {str(e)}")
        return jsonify(error=f'Failed to spawn NPC: {str(e)}'), 500

@app.route('/spawn_object', methods=['POST'])
def spawn_object():
    """Spawn an object at the specified coordinates"""
    global current_game
    
    # Check if user is DM
    if 'dm' not in user_role():
        return jsonify(error='Only DMs can spawn objects'), 403
    
    if not request.json:
        return jsonify(error='No data provided'), 400
    
    object_type = request.json.get('object_type')
    x = request.json.get('x')
    y = request.json.get('y')
    
    if not object_type or x is None or y is None:
        return jsonify(error='Missing required parameters'), 400
    
    try:
        battle_map = current_game.get_map_for_user(session['username'])
        
        # Check if the position is within map bounds
        if (x < 0 or y < 0 or x >= battle_map.size[0] or y >= battle_map.size[1]):
            return jsonify(error='Position is outside map bounds'), 400
        
        # For objects, we allow placement on occupied squares (unlike NPCs)
        # Objects can be placed on top of terrain or other non-entity objects
        
        # Create the object
        try:
            # Load object properties from objects.yml
            object_properties = game_session.load_object(object_type)
            if not object_properties:
                return jsonify(error=f'Object type "{object_type}" not found'), 400
            
            # Check if object is placeable
            if not object_properties.get('placeable', True):
                return jsonify(error=f'Object type "{object_type}" is not placeable'), 400
            
            # Create object instance
            object_klass = object_type_to_klass(object_properties['item_class'])
            object_instance = object_klass(game_session, battle_map, {
                **object_properties,
                'type': object_type,
                'entity_uid': str(uuid.uuid4())
            })
            
        except Exception as e:
            return jsonify(error=f'Failed to create object: {str(e)}'), 400
        
        # Add object to the map
        battle_map.place_object(object_instance, x, y)
        
        # Also add to interactable_objects if it has interactions
        if hasattr(object_instance, 'available_interactions') and object_instance.available_interactions(object_instance, None, admin=True):
            battle_map.interactable_objects[object_instance] = [x, y]
        
        logger.info(f"DM {session['username']} spawned {object_type} at ({x}, {y})")
        
        # Notify all clients of the map update
        socketio.emit('message', {'type': 'refresh_map'})
        
        return jsonify(status='ok', entity_uid=object_instance.entity_uid)
        
    except Exception as e:
        logger.error(f"Error spawning object: {str(e)}")
        return jsonify(error=f'Failed to spawn object: {str(e)}'), 500

@app.route('/delete_entity', methods=['POST'])
def delete_entity():
    """Delete an entity from the battlefield"""
    global current_game
    
    # Check if user is DM
    if 'dm' not in user_role():
        return jsonify(error='Only DMs can delete entities'), 403
    
    if not request.json:
        return jsonify(error='No data provided'), 400
    
    entity_uid = request.json.get('entity_uid')
    
    if not entity_uid:
        return jsonify(error='Missing entity_uid parameter'), 400
    
    try:
        # Find the entity across all maps
        entity = current_game.get_entity_by_uid(entity_uid)
        if not entity:
            return jsonify(error='Entity not found'), 404
        
        # Find which map contains the entity
        battle_map = None
        for map_obj in current_game.maps.values():
            if map_obj.entity_by_uid(entity_uid):
                battle_map = map_obj
                break
        
        if not battle_map:
            return jsonify(error='Entity not found on any map'), 404
        
        # Remove from battle if it exists
        battle = current_game.get_current_battle()
        if battle and entity in battle.combat_order:
            battle.remove(entity, from_map=False)
        
        # Remove from map
        battle_map.remove(entity)
        
        logger.info(f"DM {session['username']} deleted entity {entity.label()} ({entity_uid})")
        
        # Notify all clients of the map update
        socketio.emit('message', {'type': 'refresh_map'})
        
        return jsonify(status='ok', entity_uid=entity_uid)
        
    except Exception as e:
        logger.error(f"Error deleting entity: {str(e)}")
        return jsonify(error=f'Failed to delete entity: {str(e)}'), 500

@app.route('/move_entity', methods=['POST'])
def move_entity():
    """Move an existing entity to a new position (for PCs that already exist)"""
    global current_game
    
    # Check if user is DM
    if 'dm' not in user_role():
        return jsonify(error='Only DMs can move entities'), 403
    
    if not request.json:
        return jsonify(error='No data provided'), 400
    
    entity_uid = request.json.get('entity_uid')
    x = request.json.get('x')
    y = request.json.get('y')
    
    if not entity_uid or x is None or y is None:
        return jsonify(error='Missing required parameters'), 400
    
    try:
        # Find the entity across all maps
        entity = current_game.get_entity_by_uid(entity_uid)
        if not entity:
            return jsonify(error='Entity not found'), 404
        
        # Get the target map (current map for user)
        target_map = current_game.get_map_for_user(session['username'])
        
        # Check if the position is within map bounds
        if (x < 0 or y < 0 or x >= target_map.size[1] or y >= target_map.size[0]):
            return jsonify(error='Position is outside map bounds'), 400
        
        # Check if the position is occupied by another entity
        if target_map.entity_at(x, y):
            return jsonify(error='Position is occupied'), 400
        
        # Find current map containing the entity
        current_map = None
        for map_obj in current_game.maps.values():
            if map_obj.entity_by_uid(entity_uid):
                current_map = map_obj
                break
        
        # Remove from current map if it's on a different map
        if current_map and current_map != target_map:
            current_map.remove(entity)
        elif current_map == target_map:
            # Just move within the same map
            current_map.remove(entity)
        
        # Add to target map at new position
        target_map.add(entity, x, y, entity.group)
        
        logger.info(f"DM {session['username']} moved entity {entity.label()} to ({x}, {y})")
        
        # Notify all clients of the map update
        socketio.emit('message', {'type': 'refresh_map'})
        
        return jsonify(status='ok', entity_uid=entity_uid)
        
    except Exception as e:
        logger.error(f"Error moving entity: {str(e)}")
        return jsonify(error=f'Failed to move entity: {str(e)}'), 500

@app.route('/available_pcs', methods=['GET'])
def available_pcs():
    """Get available player characters for spawning"""
    global current_game
    
    # Check if user is DM
    if 'dm' not in user_role():
        return jsonify(error='Only DMs can access player characters'), 403
    
    try:
        # Load all characters from the session
        characters = game_session.load_characters()
        
        # Convert to list of dictionaries for JSON response
        pc_list = []
        for char in characters:
            pc_list.append({
                'entity_uid': char.entity_uid,
                'name': char.name,
                'label': char.label(),
                'token_image': char.token_image(),
                'class_and_level': char.class_and_level() if hasattr(char, 'class_and_level') else [],
                'race': char.race() if hasattr(char, 'race') else 'Unknown'
            })
        
        # Sort alphabetically by name
        pc_list.sort(key=lambda x: x['name'])
        
        return jsonify(status='ok', pcs=pc_list)
        
    except Exception as e:
        logger.error(f"Error loading player characters: {str(e)}")
        return jsonify(error=f'Failed to load player characters: {str(e)}'), 500

@app.route('/update_npc', methods=['POST'])
def update_npc():
    """Update NPC properties (name, group, description, backstory)"""
    global current_game
    
    # Check if user is DM
    if 'dm' not in user_role():
        return jsonify(error='Only DMs can update NPCs'), 403
    
    if not request.json:
        return jsonify(error='No data provided'), 400
    
    entity_id = request.json.get('entity_id')
    name = request.json.get('name')
    group = request.json.get('group')
    description = request.json.get('description')
    backstory = request.json.get('backstory')
    
    if not entity_id:
        return jsonify(error='Missing entity_id parameter'), 400
    
    try:
        battle_map = current_game.get_map_for_user(session['username'])
        entity = battle_map.entity_by_uid(entity_id)
        
        if not entity:
            return jsonify(error='Entity not found'), 404
        
        if not entity.is_npc():
            return jsonify(error='Can only update NPCs'), 400
        
        # Update properties
        if name is not None:
            if name.strip():
                entity.properties['label'] = name.strip()
            elif 'label' in entity.properties:
                del entity.properties['label']  # Remove custom label to fall back to original name
        
        if group is not None and group in ['a', 'b', 'c']:
            entity.group = group
            entity.properties['group'] = group
        
        if description is not None:
            entity.properties['description'] = description.strip()
        
        if backstory is not None:
            entity.properties['backstory'] = backstory.strip()
        
        logger.info(f"DM {session['username']} updated NPC {entity_id}: name='{name}', group='{group}'")
        
        # Notify all clients of the entity update (in case name/group affects display)
        socketio.emit('message', {'type': 'refresh_map'})
        
        return jsonify(success=True)
        
    except Exception as e:
        logger.error(f"Error updating NPC: {str(e)}")
        return jsonify(error=f'Failed to update NPC: {str(e)}'), 500

@app.route('/update')
def update():
    global current_game, logger

    x = int(request.args.get('x'))
    y = int(request.args.get('y'))
    entity_uid = request.args.get('entity_uid')
    is_pov = request.args.get('pov', 'false') == 'true'
    battle_map = current_game.get_map_for_user(session['username'])
    battle = current_game.get_current_battle()
    renderer = JsonRenderer(battle_map, battle, padding=MAP_PADDING)

    # Get entity from coordinates or UID
    entity = battle_map.entity_by_uid(entity_uid) if entity_uid else battle_map.entity_at(x, y)

    # Get current POV entity
    pov_entity = current_game.get_pov_entity_for_user(session['username'])
    _pov_entities = render_pov_entities()

    # Handle POV changes
    if entity and ('dm' in user_role() or entity in entities_controlled_by(session['username'], battle_map)):
        current_game.set_pov_entity_for_user(session['username'], entity)
        pov_entity = entity
        _pov_entities = render_pov_entities()
    elif is_pov and not entity:
        current_game.set_pov_entity_for_user(session['username'], None)
        pov_entity = None
        _pov_entities = render_pov_entities()

    if 'dm' not in user_role() and pov_entity is None and (_pov_entities is None or len(_pov_entities) == 0):
        user_entities = entities_controlled_by(session['username'], battle_map)
        _pov_entities = user_entities if user_entities else []

    logger.debug(f"entity: {entity}, pov_entity: {pov_entity}, _pov_entities: {_pov_entities}")
    _t_render = time.perf_counter()
    my_2d_array = [renderer.render(entity_pov=_pov_entities)]
    _t_after_render = time.perf_counter()
    response = render_template('map.html', 
                         pov_entity=pov_entity, 
                         tiles=my_2d_array, 
                         tile_size_px=TILE_PX, 
                         random=random, 
                         is_setup=(request.args.get('is_setup') == 'true'),
                         current_map_name=battle_map.name,
                         read_notes=current_game.read_notes)
    _t_after_tpl = time.perf_counter()
    resp = make_response(response)
    resp.headers['Server-Timing'] = (
        f"render;dur={(_t_after_render - _t_render) * 1000:.1f}, "
        f"template;dur={(_t_after_tpl - _t_after_render) * 1000:.1f}"
    )
    return resp

@app.route('/mark_note_read', methods=['POST'])
def mark_note_read():
    global current_game
    note_id = request.json.get('note_id') if request.is_json else request.form.get('note_id')
    if not note_id:
        return jsonify(error="No note_id provided"), 400
    current_game.read_notes.add(note_id)
    return jsonify(ok=True)

@app.route('/actions', methods=['GET'])
def get_actions():
    global current_game
    current_user = session['username']
    battle_map = current_game.get_map_for_user(current_user)
    battle = current_game.get_current_battle()

    id = request.args.get('id')
    if id is None:
        return jsonify(error="No entity id provided"), 400

    entity = current_game.get_entity_by_uid(id)
    if entity:
        entity_map = current_game.get_map_for_entity(entity) or battle_map
        if entity_map is None:
            return jsonify(error="Entity is not currently on a map"), 409
        if 'dm' in user_role() or current_user in entity_owners(entity):
            # If a battle is in progress but this entity hasn't been added
            # to its initiative yet, treat it as out-of-battle for action
            # availability so the player isn't locked out (they can still
            # walk around, interact with objects, etc.). They will be
            # lazy-joined on contact via loop_environment.
            effective_battle = battle if (battle and entity in battle.entities) else None
            available_actions = entity.available_actions(session, effective_battle, auto_target=False, map=entity_map, interact_only=True, admin_actions='dm' in user_role())
            # Create entity map for looking up target entities
            entity_lookup = entity_map.entities
            return render_template('actions.html', entity=entity, battle=effective_battle, session=game_session, map=entity_map, available_actions=available_actions, entity_map=entity_lookup, is_dm=('dm' in user_role()))
        else:
            return jsonify(error="Forbidden"), 403
    object_ = battle_map.object_by_uid(id)

    if object_:
        available_actions = object_.available_actions(session, battle, auto_target=False, map=battle_map, interact_only=True, admin_actions=True)
        # Create entity map for looking up target entities
        entity_map = battle_map.entities
        return render_template('actions.html', entity=object_, battle=battle, session=game_session, map=battle_map, available_actions=available_actions, entity_map=entity_map, is_dm=('dm' in user_role()))

    return jsonify(error="Entity not found"), 404

@app.route("/hide", methods=['GET'])
def get_hiding_spots():
    global current_game
   
    battle = current_game.get_current_battle()
    entity_id = request.args.get('id')
    entity = current_game.get_entity_by_uid(entity_id)
    if entity is None:
        return jsonify(error="Entity not found"), 404
    battle_map = current_game.get_map_for_entity(entity)
    hiding_spots = battle_map.hiding_spots_for(entity, battle)
    return jsonify(hiding_spots=hiding_spots)

def action_type_to_class(action_type):
    if action_type == 'SecondWindAction':
        return SecondWindAction
    elif action_type == 'DodgeAction':
        return DodgeAction
    elif action_type == 'DisengageAction':
        return DisengageAction
    elif action_type == 'DisengageBonusAction':
        return DisengageBonusAction
    elif action_type == 'DashAction':
        return DashAction
    elif action_type == 'DashBonusAction':
        return DashBonusAction
    elif action_type == 'ProneAction':
        return ProneAction
    elif action_type == 'SpellAction':
        return SpellAction
    elif action_type == 'StandAction':
        return StandAction
    elif action_type == 'TwoWeaponAttackAction':
        return TwoWeaponAttackAction
    elif action_type == 'ActionSurgeAction':
        return ActionSurgeAction
    elif action_type == 'DropConcentrationAction':
        return DropConcentrationAction
    elif action_type == 'ShoveAction':
        return ShoveAction
    elif action_type == 'HideAction':
        return HideAction
    elif action_type == 'HideBonusAction':
        return HideBonusAction
    elif action_type == 'FirstAidAction':
        return FirstAidAction
    elif action_type == 'GrappleAction':
        return GrappleAction
    elif action_type == 'DropGrappleAction':
        return DropGrappleAction
    elif action_type == 'EscapeGrappleAction':
        return EscapeGrappleAction
    elif action_type == 'UseItemAction':
        return UseItemAction
    elif action_type == 'InteractAction':
        return InteractAction
    elif action_type == 'LookAction':
        return LookAction
    elif action_type == 'LinkedAttackAction':
        return LinkedAttackAction
    elif action_type == 'HelpAction':
        return HelpAction
    elif action_type == 'FindFamiliarAction':
        return FindFamiliarAction
    elif action_type == 'SummonFamiliarAction':
        return SummonFamiliarAction
    elif action_type == 'MageHandAction':
        return MageHandAction
    elif action_type == 'LayOnHandsAction':
        return LayOnHandsAction
    elif action_type == 'FlurryOfBlowsAction':
        return FlurryOfBlowsAction
    elif action_type == 'PatientDefenseAction':
        return PatientDefenseAction
    elif action_type == 'StepOfTheWindAction':
        return StepOfTheWindAction
    elif action_type == 'FelineAgilityAction':
        return FelineAgilityAction
    elif action_type == 'MartialArtsBonusAttackAction':
        return MartialArtsBonusAttackAction
    elif action_type == 'BardicInspirationAction':
        return BardicInspirationAction
    elif action_type == 'WildShapeAction':
        return WildShapeAction
    elif action_type == 'RevertWildShapeAction':
        return RevertWildShapeAction
    elif action_type == 'WildShapeAttackAction':
        return WildShapeAttackAction
    elif action_type == 'RageAction':
        return RageAction
    elif action_type == 'EndRageAction':
        return EndRageAction
    elif action_type == 'RecklessAttackAction':
        return RecklessAttackAction
    elif action_type == 'ReadyAction':
        return ReadyAction
    else:
        raise ValueError(f"Unknown action type {action_type}")


def resolve_requested_action_type(entity, session, battle, battle_map, action_class, requested_action_type):
    if requested_action_type:
        return requested_action_type

    try:
        available_actions = entity.available_actions(
            session,
            battle,
            auto_target=False,
            map=battle_map,
        )
        for available_action in available_actions:
            if isinstance(available_action, action_class) and available_action.action_type:
                return available_action.action_type
    except Exception:
        pass

    return None

@app.route('/target', methods=['GET'])
def get_target():
    global current_game
   
    battle = current_game.get_current_battle()
    payload = json.loads(request.args.get('payload'))
   
    entity_id = payload.get('id')
    x = int(payload.get('x'))
    y = int(payload.get('y'))
    action_info = payload.get('action_info')
    opts = payload.get('opts', {})
    choice = opts.get('choice')
    entity = current_game.get_entity_by_uid(entity_id)
    battle_map = current_game.get_map_for_entity(entity)
    target_entity = battle_map.entity_at(x, y)
    if not target_entity:
        target_position = [x, y]

    if entity and target_entity and action_info in ['AttackAction', 'LinkedAttackAction']:
        action = AttackAction(game_session, entity, 'attack')
        action.using = opts.get('using')
        action.npc_action = opts.get('npc_action', None)
        action.thrown = opts.get('thrown', False)
        action.target = target_entity

        adv_mod, adv_info, attack_mod = action.compute_advantage_info(battle)
        valid_target = target_entity.allow_targeting()
        if battle:
            valid_targets = battle.valid_targets_for(entity, action)
            valid_target = target_entity in valid_targets
        return jsonify(valid_target=valid_target, adv_mod=adv_mod, adv_info=adv_info, attack_mod=attack_mod)

    elif entity and (target_entity or target_position) and action_info =='SpellAction':
        build_map = SpellAction.build(game_session, entity)
        spell_choice = (opts['spell'], opts['at_level'])
        build_map = build_map['next'](spell_choice)
        if target_entity:
            target = target_entity
        else:
            target = target_position

        target_squares = []
        while not isinstance(build_map, Action):
            target_squares = []
            if build_map['param'][0]['type'] == 'select_choice':
                build_map = build_map['next'](choice)
            elif build_map['param'][0]['type'] == 'select_empty_space':
                build_map = build_map['next'](target)
            elif build_map['param'][0]['type'] == 'select_target':
                build_map = build_map['next'](target)
            elif build_map['param'][0]['type'] == 'select_cone':
                entity_x, entity_y = battle_map.entity_or_object_pos(entity)
                require_los = build_map['param'][0]['require_los']
                target_squares = battle_map.squares_in_cone((entity_x, entity_y), (x, y), build_map['param'][0]['range'] // battle_map.feet_per_grid, require_los=require_los)
                build_map = build_map['next']([x, y])
            elif build_map['param'][0]['type'] == 'select_cube':
                # For directional cube AoE (e.g., Thunderwave) originating from caster
                entity_x, entity_y = battle_map.entity_or_object_pos(entity)
                target_squares = battle_map.squares_in_adjacent_cube((entity_x, entity_y), (x, y), size_squares=3)
                build_map = build_map['next']([x, y])
            elif build_map['param'][0]['type'] == 'select_radius':
                # Sphere AoE centered on the targeted square.
                radius_ft = build_map['param'][0].get('radius', 20)
                require_los = build_map['param'][0].get('require_los', False)
                target_squares = battle_map.squares_in_radius(
                    (x, y), radius_ft, require_los=require_los)
                build_map = build_map['next']([x, y])
            elif build_map['param'][0]['type'] == 'select_square':
                # Square AoE centered on the targeted square.
                size_ft = int(build_map['param'][0].get('size', 10))
                side = max(1, size_ft // battle_map.feet_per_grid)
                target_squares = []
                for dx in range(side):
                    for dy in range(side):
                        tx, ty = x + dx, y + dy
                        if 0 <= tx < battle_map.size[0] and 0 <= ty < battle_map.size[1]:
                            target_squares.append([tx, ty])
                build_map = build_map['next']([x, y])
            elif build_map['param'][0]['type'] == 'select_line':
                entity_x, entity_y = battle_map.entity_or_object_pos(entity)
                length_ft = build_map['param'][0].get('range', 30)
                width_ft = build_map['param'][0].get('width', 5)
                target_squares = battle_map.squares_in_line(
                    (entity_x, entity_y), (x, y), length_ft, width_ft)
                build_map = build_map['next']([x, y])
            elif build_map['param'][0]['type'] == 'select_emanation':
                entity_x, entity_y = battle_map.entity_or_object_pos(entity)
                radius_ft = build_map['param'][0].get('radius', 10)
                target_squares = battle_map.squares_in_emanation(
                    entity, radius_ft, include_origin=True)
                build_map = build_map['next']([entity_x, entity_y])
            else:
                raise ValueError(f"Unknown action type {build_map['param'][0]['type']}")

        action = build_map

        if isinstance(action, AttackSpell):
            if not isinstance(target, Entity):
                # Spell attack must resolve to a real creature; otherwise
                # downstream advantage checks call ``target.has_effect`` on
                # raw [x, y] coords and crash. Surface as not-targetable.
                return jsonify(valid_target=False, target_squares=target_squares,
                               errors=['No valid target at the selected square.'])
            adv_mod, adv_info, attack_mod = action.compute_advantage_info(battle)
            valid_target = target.allow_targeting()

            if battle:
                valid_targets = battle.valid_targets_for(entity, action)
                valid_target = target in valid_targets
            return jsonify(valid_target=valid_target, target_squares=target_squares, adv_mod=adv_mod, adv_info=adv_info, attack_mod=attack_mod)
        else:
            action.validate(battle_map, target)
            if len(action.errors)  > 0:
                return jsonify(valid_target=False, errors=action.errors)
            return jsonify(valid_target=True, target_squares=target_squares, errors=action.errors)
    elif entity and target_entity and action_info == 'UseItemAction':
        action = UseItemAction(game_session, entity, 'use_item')
        valid_target = True
        return jsonify(valid_target=valid_target, adv_info=[[],[]], attack_mod=0)
    else:
        success_rate = None

    return jsonify(success_rate=success_rate)

@app.route('/spells', methods=['GET'])
def get_spell():
    global current_game
    battle_map = current_game.get_map_for_user(session['username'])
    battle = current_game.get_current_battle()

    entity_id = request.args.get('id')
    entity = battle_map.entity_by_uid(entity_id)
    if entity.familiar():
        entity_class_level = entity.owner.class_and_level()
    else:
        entity_class_level = entity.class_and_level()
    spells_by_level = {}
    for spell_name in entity.available_spells(battle):
        # get spell available levels
        if SpellAction.can_cast(entity, battle, spell_name):
            spell_info = game_session.load_spell(spell_name)
            spells_by_level[spell_info['level']] = spells_by_level.get(spell_info['level'], []) + [spell_name]

    entity_x, entity_y = battle_map.entity_or_object_pos(entity)
    return render_template('spells.html', entity=entity, spells_by_level=spells_by_level,
                           entity_x=entity_x, entity_y=entity_y, entity_class_level=entity_class_level)


@app.route('/reaction', methods=['GET'])
def get_reaction():
    global current_game
    battle = current_game.get_current_battle()
    reaction_type = current_game.waiting_for_reaction_input()[1].reaction_type
    return render_template(f"reactions/{reaction_type}.html",
                           username=session['username'],
                           waiting_for_reaction=current_game.waiting_for_reaction,
                           battle=battle)

@app.route('/reaction', methods=['POST'])
def handle_reaction():
    global current_game
    battle = current_game.get_current_battle()
    reaction_id = request.form.get('reaction')
    if not reaction_id:
        return jsonify(error="No reaction provided"), 400
    if not current_game.waiting_for_reaction:
        return jsonify(error="No reaction expected"), 400
    entity, handler, generator, valid_actions_str = current_game.waiting_for_reaction_input()

    if reaction_id == 'no-reaction':
        handler.send(None)
    else:
        for _, _, action in valid_actions_str:
            print(f"action {action.uid} == reaction {reaction_id}")
            if str(action.uid) == reaction_id:
                print(f"selected action {action}")
                handler.send(action)
                break
    current_game.clear_reaction_input()
    try:
        # Use the lock to make the operation atomic
        with current_game.game_state_lock:
            battle.action(handler.action)
            battle.commit(handler.action)
        socketio.emit('message', {'type': 'dismiss_reaction', 'message': {}})

        # reaction was during a players end step, in that case we need to start the next turn
        if current_game.end_turn_state:
            current_game.end_turn_state = False
            battle.next_turn()

        current_game.schedule_after_reaction()
    except AsyncReactionHandler as e:
        for _, entity, valid_actions in e.resolve():
            valid_actions_str = [[str(action.uid), str(action), action] for action in valid_actions]
            current_game.waiting_for_reaction = [entity, e, e.resolve(), valid_actions_str]
        socketio.emit('message', {'type': 'reaction', 'message': {'id': entity.entity_uid, 'reaction': e.reaction_type}})

    return jsonify(status='ok')

@app.route('/manual_roll', methods=['POST'])
def manual_roll():
    global current_game
    battle = current_game.get_current_battle()
    battle_map = current_game.get_map_for_user(session['username'])
    entity_id = request.json['id']
    entity = battle_map.entity_by_uid(entity_id)
    roll = request.json['roll']
    advantage = request.json.get('advantage', False)
    disadvantage = request.json.get('disadvantage', False)
    description = request.json.get('description', None)
    roll_result = DieRoll.roll(roll, disadvantage=disadvantage, advantage=advantage,
                entity=entity, battle=battle, description=description)
    output_logger.log(
        f"{entity.name} rolled a {roll_result}={roll_result.result()} for {description}",
        visibility={'kind': 'combat', 'entities': [entity]},
    )
  
    return jsonify(roll_result=roll_result.result(), roll_explaination=str(roll_result))

@app.route('/switch_pov', methods=['POST'])
def switch_pov():
    global current_game
    battle_map = current_game.get_map_for_user(session['username'])
    entity_id = request.form['entity_uid']
    entity = current_game.get_entity_by_uid(entity_id)
    entity_battle_map = current_game.get_map_for_entity(entity)
    current_game.set_pov_entity_for_user(session['username'], entity)
    # Switch the user's current map BEFORE resolving the background so a POV
    # change to an entity on a different map returns that map's background
    # (otherwise the previous map's background is returned and the client UI
    # appears stuck on the old map until a manual refresh).
    map_changed = battle_map != entity_battle_map
    if map_changed:
        current_game.switch_map_for_user(session['username'], entity_battle_map.name)
    background = current_game.get_background_image_for_user(session['username'])
    map_width, map_height = entity_battle_map.size
    tiles_dimension_height = map_height * TILE_PX
    tiles_dimension_width = map_width * TILE_PX
    dm_active = False
    # Include map default effect and whether DM has an active override
    map_default = None
    map_defaults = []
    if map_changed:
        try:
            map_defaults = map_default_effect_payloads(entity_battle_map)
            map_default = map_defaults[0] if map_defaults else None
        except Exception:
            map_default = None

        try:
            game_key = getattr(current_game.game_session, 'root_path', None) or getattr(game_session, 'root_path', None) or LEVEL
            dm_active = has_enabled_effect_payloads(active_effects.get(game_key, {}).values())
            try:
                dm_active = dm_active or has_enabled_effect_payloads(active_effects_map.get(game_key, {}).get(entity_battle_map.name, {}).values())
            except Exception:
                pass
        except Exception:
            dm_active = False
    return jsonify(background=f"assets/{background}",
        name=entity_battle_map.name,
        pov_entity=entity_id,
        image_offset_px=entity_battle_map.image_offset_px,
        height=tiles_dimension_height,
        width=tiles_dimension_width,
        map_default_effect=map_default,
        map_default_effects=map_defaults,
        dm_active=dm_active,
        special_effects_enabled=special_effects_enabled())

@app.route('/read_letter', methods=['POST'])
def read_letter():
    global current_game
    battle_map = current_game.get_map_for_user(session['username'])
    battle = current_game.get_current_battle()
    entity_id = request.form['id']
    item_id = request.form['item_id']

    entity = battle_map.entity_by_uid(entity_id)
    if not entity:
        return jsonify(error="Entity not found"), 404

    # Process the letter for the entity using the provided item_id.
    item, letter_content = entity.read_item(item_id)

    output_logger.log(
        f"{entity.name} read {item.get('label', item['name'])}: {letter_content}",
        visibility={'kind': 'entity_only', 'entities': [entity]},
    )

    # process raw text so that linebreaks are preserved when rendering on the web page
    letter_content = letter_content.replace('\n', '<br>')

    return render_template('letter.html', letter_label=item.get('label', item['name']), letter_content=letter_content)

@app.route('/action', methods=['POST'])
def action():
    global current_game

    battle = current_game.get_current_battle()
    action_request = request.json
    entity_id = action_request['id']
    action_type = action_request['action']
    opts = action_request.get('opts', {})

    selected_spell = opts.get('spell')
    at_level = opts.get('at_level')
    choice = action_request.get('choice', opts.get('choice'))
    entity = current_game.get_entity_by_uid(entity_id)
    if entity is None:
        return jsonify({'status': 'error', 'message': 'Entity not found'}), 404

    battle_map = current_game.get_map_for_entity(entity)
    if battle_map is None:
        return jsonify({'status': 'error', 'message': 'Entity is not currently on a map'}), 409

    pov_entities = entities_controlled_by(session['username'])
    action_info = {}
    action_hash = None
    target_coords = action_request.get('target', None)
    target = None

    # ReadyAction is collected through a chat dialog with the DM rather than
    # the standard target/param flow. Tell the client to open the dialog.
    if action_type == 'ReadyAction':
        return jsonify({
            'action': 'ReadyAction',
            'type': 'requires_dialog',
            'dialog': 'ready_action',
            'endpoint': '/ready_action',
            'entity_uid': entity_id,
            'prompt': 'Describe the trigger and the action you are readying.',
        })

    if target_coords:
        mode = action_request.get('mode', None)
        if mode == 'cone' or mode == 'point_target' or mode == 'cube' or mode == 'square':
            target = [target_coords['x'], target_coords['y']]
        else:
            if isinstance(target_coords, list):
                target = []
                for entity_uids in target_coords:
                    target.append(battle_map.entity_by_uid(entity_uids))
            elif isinstance(target_coords, str):
                # Target is an entity UID
                target = battle_map.entity_by_uid(target_coords)
            else:
                # Target is coordinates
                tx, ty = int(target_coords['x']), int(target_coords['y'])
                targets = battle_map.entities_at(tx, ty)
                if len(targets) == 1:
                    target = targets[0]
                elif len(targets) == 0:
                    # ``entities_at`` filters out hidden / non-targetable
                    # tokens; fall back to the raw token at that square so
                    # entity-required actions (spell attacks, attacks) can
                    # still resolve when the caster legitimately can see
                    # them. If still nothing, surface as a coordinate
                    # target for AoE actions (cone/cube/grease/etc.).
                    fallback = battle_map.entity_at(tx, ty)
                    target = fallback if fallback is not None else [tx, ty]
                else:
                    target_list = [[target.label(), target.entity_uid] for target in targets]
                    return jsonify(status='multiple_targets', message=f"Multiple entities at {target_coords['x']}, {target_coords['y']}",
                                   entities=target_list)

    try:
        if action_type == 'MoveAction':
            path = action_request.get('path', None)
            manual_jump = action_request.get('manual_jump') or []
            action = MoveAction(game_session, entity, 'move')
            if path:
                move_path = sorted([(int(index), [int(coord[0]), int(coord[1])]) for index, coord in enumerate(path)])
                move_path = [coords for _, coords in move_path]
                action.move_path = move_path
                # When this PC isn't a combatant in an active battle, treat
                # the move as exploration and allow paths longer than the
                # entity's standard speed so the user can traverse the map.
                if not battle or entity not in getattr(battle, 'entities', {}):
                    action.unlimited_movement = True
                # store jump indices for backend computation if provided.
                # The web UI sends [takeoff_index, landing_index] where
                # ``takeoff_index`` is the path index of the square the
                # entity launches FROM (the last walked square) and
                # ``landing_index`` is the square it lands ON. The squares
                # that are actually "in flight" — and therefore the ones
                # that need to be marked as jump squares so area triggers
                # treat them as flying — are ``takeoff_index + 1 ..
                # landing_index`` inclusive. Including the takeoff itself
                # would (a) burn a square of jump budget on the spot the
                # PC is standing on, and (b) prevent the long-jump
                # running-start budget from kicking in (because the
                # takeoff square is no longer counted as a "walk").
                try:
                    if isinstance(manual_jump, list) and len(manual_jump) == 2:
                        start_i, end_i = int(manual_jump[0]), int(manual_jump[1])
                        if 0 <= start_i <= end_i < len(move_path):
                            action.jump_index = list(range(start_i + 1, end_i + 1))
                    elif isinstance(manual_jump, list):
                        # already a list of in-flight indices
                        action.jump_index = [int(i) for i in manual_jump if 0 <= int(i) < len(move_path)]
                except Exception:
                    # ignore malformed manual_jump to remain backwards compatible
                    pass
                if battle:
                    result = current_game.commit_and_update(session['username'], action, pov_entities)
                    # Check area narrations after battle movement
                    area_narration = battle_map.check_area_narration(entity, move_path[-1])
                    if area_narration:
                        socketio.emit('message', {'type': 'narration', 'message': area_narration, 'map_name': battle_map.name})
                        narration_entry = area_narration.get('on_enter', {})
                        narration_text = narration_entry.get('text', '')
                        if narration_text:
                            output_logger.log(narration_text, visibility={'kind': 'entities', 'entity_uids': [entity.entity_uid]})
                        try:
                            _record_narration_for_pcs(area_narration, map_name=battle_map.name, target_uids=[entity.entity_uid])
                        except Exception:
                            pass
                    return jsonify(result)
                else:
                    last_coords = move_path[-1]
                    if battle_map.placeable(entity, last_coords[0], last_coords[1]):

                        current_game.commit_and_update(session['username'], action, pov_entities)
                        if battle:
                            # POV-aware logs are emitted via commit_and_update; avoid duplicate raw emission
                            logs = battle.get_animation_logs()
                            if logs:
                                socketio.emit('message', {'type': 'move', 'message': {
                                    'from': move_path[0], 'to': move_path[-1], 'animation_log': logs
                                }})
                            battle.clear_animation_logs()
                        else:
                            animation_log = []
                            animation_log.append((entity.entity_uid, move_path, None))
                            socketio.emit('message', {'type': 'move', 'message': {'from': move_path[0], 'to': move_path[-1], 'animation_log': animation_log}})
                        # Flush any deferred map switch now that the move
                        # animation event has been queued on the client. This
                        # ensures the entity finishes animating into the
                        # teleporter/stairs tile before the destination map
                        # is rendered.
                        try:
                            current_game.flush_pending_map_switch(session['username'])
                        except Exception:
                            pass
                        # Check area narrations after free movement
                        area_narration = battle_map.check_area_narration(entity, move_path[-1])
                        if area_narration:
                            socketio.emit('message', {'type': 'narration', 'message': area_narration, 'map_name': battle_map.name})
                            narration_entry = area_narration.get('on_enter', {})
                            narration_text = narration_entry.get('text', '')
                            if narration_text:
                                output_logger.log(narration_text, visibility={'kind': 'entities', 'entity_uids': [entity.entity_uid]})
                            try:
                                _record_narration_for_pcs(area_narration, map_name=battle_map.name, target_uids=[entity.entity_uid])
                            except Exception:
                                pass
                        current_game.loop_environment()
                        return jsonify({'status': 'ok'})
                    else:
                        return jsonify({'status': 'error', 'message': 'Entity not placeable at target location'})
            else:
                action_info['action'] = 'movement'
                action_info['type'] = 'select_path'
                build_map = action.build_map()
                action_info['param'] = build_map['param']
                return jsonify(action_info)
        elif action_type in ['LinkedAttackAction', 'AttackAction', 'TwoWeaponAttackAction']:
            if action_type == 'AttackAction':
                action = AttackAction(game_session, entity, 'attack')
            else:
                action = TwoWeaponAttackAction(game_session, entity, 'attack')
            action.using = opts.get('using')
            action.npc_action = opts.get('npc_action', None)
            action.thrown = opts.get('thrown', False)

            valid_targets = battle_map.valid_targets_for(entity, action, include_objects=True)
            valid_targets = { target.entity_uid: battle_map.entity_or_object_pos(target) for target in valid_targets}

            if action.npc_action:
                weapon_details = action.npc_action
            else:
                weapon_details = game_session.load_weapon(action.using)

            if target_coords:
                if isinstance(target_coords, str):
                    # Target is an entity UID
                    target = battle_map.entity_by_uid(target_coords)
                else:
                    # Target is coordinates
                    target = battle_map.entities_at(int(target_coords['x']), int(target_coords['y']))[0]

                if target and valid_targets.get(target.entity_uid):
                    action.target = target
                    return jsonify(current_game.commit_and_update(session['username'], action, pov_entities))
                else:
                    return jsonify(status='error', message=f"Invalid Target {target_coords}")
            else:
                action_info['action'] = 'attack'
                action_info['type'] = 'select_target'
                action_info['valid_targets'] = valid_targets
                action_info['total_targets'] = 1
                if action.thrown:
                    action_info['range'] = weapon_details.get('thrown', {}).get('range')
                    action_info['range_max'] = weapon_details.get('thrown', {}).get('range_max', weapon_details.get('thrown', {}).get('range'))
                else:
                    action_info['range'] = weapon_details['range']
                    action_info['range_max'] = weapon_details.get('range_max', weapon_details['range'])
                action_info['param'] = [
                    {
                        'type': 'select_target',
                        'num': 1,
                        'weapon': action.using,
                        'target_types': ['enemies'],
                    }
                    ]
        else:
            action_class = action_type_to_class(action_type)
            opts = action_request.get('opts', {})
            resolved_action_type = resolve_requested_action_type(
                entity,
                game_session,
                battle,
                battle_map,
                action_class,
                opts.get('action_type'),
            )
            action = action_class(game_session, entity, resolved_action_type)
            action = action.build_map()

            while not isinstance(action, Action):
                if len(action['param'])==1:
                    param_details = action['param'][0]
                    if param_details['type'] == 'select_spell':
                        if selected_spell:
                            action = action['next']((selected_spell, at_level))
                            continue
                        else:
                            action_info['action'] = action_type
                            action_info['type'] = 'select_spell'
                            action_info['param'] = action['param']
                            return jsonify(action_info)
                    elif param_details['type'] == 'select_choice':
                        if choice:
                            action = action['next'](choice)
                            continue
                        else:
                            action_info['action'] = action_type
                            action_info['type'] = 'select_choice'
                            action_info['param'] = action['param']
                            return jsonify(action_info)
                    elif param_details['type'] == 'select_empty_space':
                        if target:
                            action = action['next'](target)
                            continue
                        else:
                            action_info['action'] = action_type
                            action_info['type'] = 'select_empty_space'
                            action_info['param'] = action['param']
                            action_info['range'] = param_details.get('range', 5)
                            action_info['range_max'] = param_details.get('max_range', param_details.get('range', 5))
                            return jsonify(action_info)
                    elif param_details['type'] == 'select_cone':
                        if target:
                            action = action['next'](target)
                            continue
                        else:
                            action_info['action'] = action_type
                            action_info['type'] = 'select_cone'
                            action_info['param'] = action['param']
                            action_info['range'] = param_details.get('range', 5)
                            action_info['range_max'] = param_details.get('max_range', param_details.get('range', 5))
                            return jsonify(action_info)
                    elif param_details['type'] == 'select_cube':
                        if target:
                            action = action['next'](target)
                            continue
                        else:
                            action_info['action'] = action_type
                            action_info['type'] = 'select_cube'
                            action_info['param'] = action['param']
                            action_info['range'] = param_details.get('range', 5)
                            action_info['range_max'] = param_details.get('max_range', param_details.get('range', 5))
                            return jsonify(action_info)
                    elif param_details['type'] == 'select_radius':
                        if target:
                            action = action['next'](target)
                            continue
                        else:
                            action_info['action'] = action_type
                            action_info['type'] = 'select_radius'
                            action_info['param'] = action['param']
                            action_info['range'] = param_details.get('range', 60)
                            action_info['range_max'] = param_details.get('max_range', param_details.get('range', 60))
                            action_info['radius'] = param_details.get('radius', 20)
                            return jsonify(action_info)
                    elif param_details['type'] == 'select_square':
                        if target:
                            action = action['next'](target)
                            continue
                        else:
                            action_info['action'] = action_type
                            action_info['type'] = 'select_square'
                            action_info['param'] = action['param']
                            action_info['range'] = param_details.get('range', 60)
                            action_info['range_max'] = param_details.get('max_range', param_details.get('range', 60))
                            action_info['size'] = param_details.get('size', 10)
                            return jsonify(action_info)
                    elif param_details['type'] == 'select_line':
                        if target:
                            action = action['next'](target)
                            continue
                        else:
                            action_info['action'] = action_type
                            action_info['type'] = 'select_line'
                            action_info['param'] = action['param']
                            action_info['range'] = param_details.get('range', 30)
                            action_info['range_max'] = param_details.get('max_range', param_details.get('range', 30))
                            action_info['width'] = param_details.get('width', 5)
                            return jsonify(action_info)
                    elif param_details['type'] == 'select_emanation':
                        # Emanation centers on the caster — auto-resolve.
                        entity_x, entity_y = battle_map.entity_or_object_pos(entity)
                        action = action['next']([entity_x, entity_y])
                        continue
                    elif param_details['type'] == 'select_target':
                        valid_targets = battle_map.valid_targets_for(entity, param_details)
                        valid_targets = {target.entity_uid: battle_map.entity_or_object_pos(target) for target in valid_targets}
                        if target:
                            # ``select_target`` requires an actual Entity (or a
                            # list of entities for multi-target spells). If
                            # the client clicked an empty square the upstream
                            # resolver hands us a ``[x, y]`` coordinate pair,
                            # which would explode deep inside the spell when
                            # something like ``target.has_effect(...)`` is
                            # called. Reject those up front with a clear
                            # error so the UI can prompt the user again.
                            if not isinstance(target, Entity) and not (
                                isinstance(target, list)
                                and target
                                and all(isinstance(t, Entity) for t in target)
                            ):
                                return jsonify(
                                    status='error',
                                    error='No valid target at the selected square. Click on a creature.',
                                ), 400
                            action = action['next'](target)
                            continue
                        else:
                            action_info['action'] = action_type
                            action_info['type'] = 'select_target'
                            action_info['valid_targets'] = valid_targets
                            action_info['total_targets'] = param_details['num']
                            action_info['param'] = action['param']
                            action_info['range'] = param_details.get('range', 5)
                            action_info['range_max'] = param_details.get('max_range', param_details.get('range', 5))
                            if param_details.get('num', 1) > 1:
                                target_hints = [ t.entity_uid for t in acquire_targets(param_details, entity, battle, battle_map)]
                                action_info['target_hints'] = target_hints
                                action_info['unique_targets'] = param_details.get('unique_targets', False)
                            return jsonify(action_info)
                    elif param_details['type'] == 'select_item':
                        target_item = opts.get('name', None)
                        if target_item:
                            action = action['next'](target_item)
                            continue
                        else:
                            valid_items = entity.usable_items()
                            action_info['action'] = action_type
                            action_info['type'] = 'select_item'
                            action_info['valid_items'] = valid_items
                            action_info['param'] = action['param']
                            return jsonify(action_info)
                    elif param_details['type'] == 'select_object':
                        object_action_a = opts.get('object_action')
                        if isinstance(object_action_a, list):
                            object_action_a = object_action_a[0]

                        if entity.object() and 'dm' in user_role():
                            gm = DungeonMaster(game_session, name='dm')
                            interact = InteractAction(game_session, gm, 'interact')
                            interact.object_action = object_action_a
                            interact.target = entity
                            return jsonify(current_game.commit_and_update(session['username'], interact, pov_entities))
                        else:
                            interact = InteractAction(game_session, entity, 'interact')
                            object =  battle_map.entity_by_uid(opts.get('target'))
                            interact.object_action =  object_action_a
                            interact.target = object
                            action = interact.build_custom_action(interact.object_action, object)
                            continue
                    elif param_details['type'] == 'select_items':
                        target_items = opts.get('items', [])
                        if target_items:
                            action = action['next'](target_items)
                            continue
                        else:
                            valid_items = entity.usable_items()
                            action_info['action'] = action_type
                            action_info['type'] = 'select_items'
                            action_info['mode'] = param_details.get('mode', 'transfer')
                            action_info['valid_items'] = param_details['items']
                            action_info['param'] = action['param']
                            return jsonify(action_info)
                    else:
                        raise ValueError(f"Unknown action type {action_type} {param_details['type']}")
                else:
                    raise ValueError(f"Invalid action map {action}")

            action.validate(battle_map, target=target)
           
            if len(action.errors) > 0:
                return jsonify(status='error', errors=action.errors)

            current_game.commit_and_update(session['username'], action, pov_entities)
            return jsonify(status='ok')
        return jsonify(action_info)
    except AsyncReactionHandler as e:
        logger.info(f"AsyncReactionHandler during action: {e}")
        for battle, entity, valid_actions in e.resolve():
            valid_actions_str = [[str(action.uid), str(action), action] for action in valid_actions]
            current_game.set_waiting_for_reaction_input([entity, e, e.resolve(), valid_actions_str])
        socketio.emit('message', {'type': 'reaction', 'message': {'id': entity.entity_uid, 'reaction': e.reaction_type}})
        return jsonify(status='ok')


@app.route('/ready_action', methods=['POST'])
def ready_action_endpoint():
    """Declare a 5e Ready (Hold) action.

    Body: ``{ id: <entity_uid>, description: "<player free text>" }``

    The webapp passes the description through the configured LLM (with a
    rule-based fallback) to produce a structured trigger + action_spec, and
    if approved commits a :class:`ReadyAction` for the entity.
    """
    global current_game
    from webapp.ready_action_handler import (
        parse_ready_action_request,
        make_llm_resolver,
    )

    payload = request.json or {}
    entity_id = payload.get('id')
    description = (payload.get('description') or '').strip()
    if not entity_id:
        return jsonify(status='error', message='Missing entity id'), 400

    entity = current_game.get_entity_by_uid(entity_id)
    if entity is None:
        return jsonify(status='error', message='Entity not found'), 404
    battle = current_game.get_current_battle()
    if battle is None:
        return jsonify(status='error', message='No active battle'), 400
    if not ReadyAction.can(entity, battle):
        return jsonify(status='error',
                       message='You cannot ready an action right now.'), 400

    parsed = parse_ready_action_request(entity, battle, description, llm_handler)
    if not parsed.get('approved'):
        return jsonify(status='rejected',
                       reason=parsed.get('reason'),
                       trigger=parsed.get('trigger'),
                       action_spec=parsed.get('action_spec')), 200

    # Make sure the engine knows how to resolve trigger time (idempotent).
    if getattr(battle, '_ready_action_resolver', None) is None:
        battle.set_ready_action_resolver(make_llm_resolver(llm_handler))

    ready = ReadyAction(current_game.game_session, entity, 'ready', opts={
        'description': description,
        'trigger': parsed['trigger'],
        'action_spec': parsed['action_spec'],
    })
    pov_entities = entities_controlled_by(session['username'])
    current_game.commit_and_update(session['username'], ready, pov_entities)
    return jsonify(status='ok',
                   reason=parsed.get('reason'),
                   trigger=parsed['trigger'],
                   action_spec=parsed['action_spec'])


@app.route('/items', methods=['GET'])
# GET /items?id=rumblebelly&action=InteractAction&opts[action_type]=interact&opts[object_action]=loot&opts[target]=3fb25042-df48-4003-8ddc-dd2b04d5fbeb HTTP/1.1
def get_items():
    global current_game
    battle_map = current_game.get_map_for_user(session['username'])
    entity_id = request.args.get('id')
    entity = battle_map.entity_by_uid(entity_id)
    if entity is None:
        return jsonify(error="Entity not found"), 404
    action_type = request.args.get('opts[object_action][]')
    target_object = battle_map.entity_by_uid(request.args.get("opts[target]"))
    if action_type == 'give':
        inventory = entity.inventory_items(game_session) or []
        source_inventory = []
        return render_template('loot_items.html', entity=target_object, source_inventory=source_inventory, inventory=inventory, action_type=action_type, target_object=entity)
    else:
        inventory = target_object.inventory_items(game_session) or []
        source_inventory = entity.inventory_items(game_session) or []
    return render_template('loot_items.html', entity=entity, source_inventory=source_inventory, inventory=inventory, action_type=action_type, target_object=target_object)


@app.route('/info', methods=['GET'])
def get_info():
    battle_map = current_game.get_map_for_user(session['username'])
    battle = current_game.get_current_battle()
    info_id = request.args.get('id')
    if not info_id:
        return jsonify(error="Missing required id"), 400

    # Fetch the necessary information based on the info_id
    entity = battle_map.entity_by_uid(info_id)
    if entity is None:
        entity = battle_map.object_by_uid(info_id)
    if entity is None:
        return jsonify(error="Entity not found"), 404

    # Filter out None/empty usernames to avoid mixed-type sorting errors.
    configured_users = [
        login.get('name')
        for login in LOGINS
        if isinstance(login, dict) and isinstance(login.get('name'), str) and login.get('name').strip()
    ]
    connected_users = [
        username
        for username in (current_game.username_to_sid or {}).keys()
        if isinstance(username, str) and username.strip()
    ]
    all_users = sorted(set(configured_users + connected_users))
    return render_template('info.html.jinja', entity=entity, session=game_session, battle=battle, restricted=False, role=user_role(), all_users=all_users)

@app.route('/entity_info', methods=['GET'])
def get_entity_info():
    """Get entity information for the JRPG dialog modal."""
    global current_game
    
    entity_id = request.args.get('entity_id')
    if not entity_id:
        return jsonify({'success': False, 'error': 'Entity ID is required'}), 400
    
    try:
        entity = current_game.get_entity_by_uid(entity_id)
        if not entity:
            return jsonify({'success': False, 'error': 'Entity not found'}), 404
        
        # Use EntityRAGHandler to get comprehensive entity context
        entity_info = entity_rag_handler.get_entity_context(entity)
        
        return jsonify({'success': True, 'entity': entity_info})
        
    except Exception as e:
        logger.error(f"Error getting entity info: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/reset_narrations', methods=['POST'])
def reset_narrations():
    global current_game
    if not session.get('username'):
        return jsonify({'status': 'error', 'message': 'Not logged in'}), 401
    for m in current_game.maps.values():
        m._triggered_area_narrations.clear()
    return jsonify({'status': 'ok'})

@app.route('/logout', methods=['POST', 'GET'])
def logout():
    session['username'] = None
    return redirect(url_for('login'))

@app.route('/turn')
def get_turn():
    global current_game
    battle = current_game.get_current_battle()
    if battle:
        print(f"current turn: {battle.current_turn().entity_uid} {session['username']}")
        if 'dm' in user_role() or controller_of(battle.current_turn().entity_uid, session['username']):
            return render_template('turn.jinja', battle=battle, game_session=current_game.game_session, username=session['username'])
        else:
            return render_template('turn.jinja', battle=battle, game_session=current_game.game_session, username=session['username'], readonly=True)
    else:
        return jsonify(error="No battle in progress"), 400

@app.route('/game_time')
def get_game_time():
    global current_game
    return jsonify({'game_time': current_game.game_session.game_time})

@app.route('/update_npc_default_controller', methods=['POST'])
def update_npc_default_controller():
    global current_game
    if 'dm' not in user_role():
        return jsonify({'success': False, 'error': 'DM access required'}), 403
    try:
        data = request.get_json() if request.is_json else request.form
        new_value = data.get('value')
        if new_value not in ['manual', 'ai', 'llm']:
            return jsonify({'success': False, 'error': 'Invalid controller value'}), 400
        current_game.npc_controller = new_value
        return jsonify({'success': True, 'npc_default_controller': current_game.npc_controller})
    except Exception as e:
        logger.error(f"Failed to update npc_default_controller: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/add', methods=['GET'])
def add():
    global current_game
    battle_map = current_game.get_map_for_user(session['username'])
    battle = current_game.get_current_battle()
    entity_uid = request.args.get('id')
    entity = battle_map.entity_by_uid(entity_uid)
    if entity is None:
        return jsonify(error='Entity not found'), 404

    if battle:
        # Mid-battle add: actually roll initiative for the new entity, build
        # a controller for it, and slot it in to act NEXT (i.e. at the "top"
        # of the remaining round) without disturbing the current turn.
        if 'dm' not in user_role():
            return jsonify(error='Only DMs can add entities to an active battle'), 403

        # If already in the battle, no-op (idempotent), but still return the
        # rendered turn-order row so the caller doesn't break.
        already_in_battle = entity in battle.entities

        default_group = 'a' if isinstance(entity, PlayerCharacter) else 'b'

        if not already_in_battle:
            controller = current_game.build_combat_controller_for_entity(entity)
            if controller is None:
                controller = GenericController(current_game.game_session)
            try:
                controller.register_handlers_on(entity)
            except Exception:
                pass

            with current_game.game_state_lock:
                # Add to the battle (don't auto-add to initiative; we want to
                # control placement so the new entity acts next this round).
                battle.add(entity, default_group, controller=controller)
                # Roll initiative for the new entity and insert it directly
                # after the current turn so it acts on this round at the
                # "top" relative to whoever still has to go.
                state = battle.entities.get(entity)
                if state is not None:
                    try:
                        state['initiative'] = entity.initiative(battle)
                    except Exception:
                        state['initiative'] = 0
                    # Make sure it's not already in combat_order, then insert
                    # right after the current actor.
                    if entity not in battle.combat_order:
                        insert_at = (battle.current_turn_index + 1) if battle.combat_order else 0
                        battle.combat_order.insert(insert_at, entity)

        socketio.emit('message', {'type': 'initiative', 'message': {'index': battle.current_turn_index}})
        socketio.emit('message', {'type': 'turn', 'message': {}})
        socketio.emit('message', {'type': 'refresh_map'})
        # Return the rendered turn-order row so the existing client code
        # (which appends the response to #turn-order) keeps working.
        return render_template('add.html', entity=entity, is_pc=isinstance(entity, PlayerCharacter),
                               default_controller=('manual' if isinstance(entity, PlayerCharacter)
                                                   else current_game.effective_npc_combat_controller()))
    else:
        is_pc = isinstance(entity, PlayerCharacter)
        default_controller = 'manual' if is_pc else current_game.effective_npc_combat_controller()
        return render_template('add.html', entity=entity, is_pc=is_pc, default_controller=default_controller)


@app.route('/remove_from_battle', methods=['POST'])
def remove_from_battle():
    """DM-only: remove an entity from the active battle's initiative without
    removing it from the map. The entity becomes a non-participant again and
    can act/move freely (subject to lazy-add rules)."""
    global current_game
    if 'dm' not in user_role():
        return jsonify(error='Only DMs can modify the initiative'), 403
    battle = current_game.get_current_battle()
    if not battle:
        return jsonify(error='No active battle'), 400
    data = request.get_json(silent=True) or request.form
    entity_uid = data.get('entity_uid') or data.get('id')
    if not entity_uid:
        return jsonify(error='Missing entity_uid'), 400
    entity = current_game.get_entity_by_uid(entity_uid)
    if entity is None:
        return jsonify(error='Entity not found'), 404
    with current_game.game_state_lock:
        if entity in battle.entities or entity in battle.combat_order:
            battle.remove(entity, from_map=False)
        # If we just removed the last combatant on one side the battle may
        # be over; check and clean up so non-participants can act freely.
        try:
            if battle.battle_ends():
                current_game.end_current_battle()
        except Exception:
            pass
    socketio.emit('message', {'type': 'initiative',
                              'message': {'index': battle.current_turn_index if current_game.get_current_battle() else None}})
    socketio.emit('message', {'type': 'turn', 'message': {}})
    socketio.emit('message', {'type': 'refresh_map'})
    return jsonify(status='ok')


@app.route('/tracks', methods=['GET'])
def get_tracks():
    global current_game
    current_soundtrack = current_game.current_soundtrack
    tracks = []
    for index, track in enumerate(SOUNDTRACKS):
        track_data = {
            'id': track['name'],
            'url': track['file'],
            'name': track['name'],
        }
        tracks.append(track_data)
    if current_soundtrack:
        current_soundtrack_name = current_soundtrack['name']
    else:
        current_soundtrack_name = None
    print(f"current soundtrack {current_soundtrack_name}")
    return render_template('soundtrack.jinja', tracks=tracks, current_soundtrack=current_soundtrack, current_soundtrack_name=current_soundtrack_name)

@app.route('/sound', methods=['POST'])
def sound():
    global current_game
    track_id = request.json.get('track_id', 'background')

    current_game.play_soundtrack(track_id)
    return jsonify(status='ok')

@app.route('/volume', methods=['POST'])
def set_volume():
    volume = int(request.json['volume'])
    current_game.set_volume(volume)
   
    return jsonify(status='ok')

@app.route('/seek', methods=['POST'])
def seek():
    global current_game
    time_s = int(request.json['time'])
    current_game.seek_soundtrack(time_s)
    return jsonify(status='ok')



@app.route('/unequip', methods=['POST'])
def unequip():
    global current_game
    battle_map = current_game.get_map_for_user(session['username'])
    entity_id = request.form['id']
    item_id = request.form['item_id']
    entity = battle_map.entity_by_uid(entity_id)
    if entity:
        entity.unequip(item_id)
        socketio.emit('message', {'type': 'refresh_map'})
        return jsonify(status='ok')
    return jsonify(error="Entity not found"), 404

@app.route('/equip', methods=['POST'])
def equip():
    global current_game
    battle_map = current_game.get_map_for_user(session['username'])
    entity_id = request.form['id']
    item_id = request.form['item_id']
    entity = battle_map.entity_by_uid(entity_id)
    if entity:
        entity.equip(item_id)
        socketio.emit('message', {'type': 'refresh_map'})
        return jsonify(status='ok')

    return jsonify(error="Entity not found"), 404


@app.route('/dm/items_catalog', methods=['GET'])
def dm_items_catalog():
    """Return the full catalog of items (weapons + equipment + objects) for DM autocomplete."""
    if 'dm' not in user_role():
        return jsonify(error='DM access required'), 403

    query = (request.args.get('q') or '').strip().lower()
    catalog = []

    def _push(name, payload, category):
        if not isinstance(payload, dict):
            return
        label = payload.get('label') or payload.get('name') or str(name)
        entry = {
            'name': str(name),
            'label': str(label),
            'category': category,
            'type': payload.get('type') or payload.get('subtype') or category,
            'image': payload.get('image') or str(name),
            'weight': payload.get('weight'),
            'cost': payload.get('cost'),
        }
        if query and query not in entry['name'].lower() and query not in entry['label'].lower():
            return
        catalog.append(entry)

    try:
        for name, payload in (game_session.load_weapons() or {}).items():
            _push(name, payload, 'weapon')
    except Exception:
        pass
    try:
        for name, payload in (game_session.load_all_equipments() or {}).items():
            _push(name, payload, 'equipment')
    except Exception:
        pass
    try:
        objects = game_session.load_yaml_file('items', 'objects') or {}
        for name, payload in objects.items():
            _push(name, payload, 'object')
    except Exception:
        pass

    catalog.sort(key=lambda e: (e['category'], e['label'].lower()))
    return jsonify(items=catalog)


def _dm_resolve_entity(entity_id):
    """Locate an entity (or object with inventory) by uid for DM operations."""
    global current_game
    entity = current_game.get_entity_by_uid(entity_id)
    if entity is not None:
        return entity
    maps_attr = getattr(current_game, 'maps', None)
    if maps_attr:
        for battle_map in maps_attr.values():
            try:
                ent = battle_map.object_by_uid(entity_id)
            except Exception:
                ent = None
            if ent is not None:
                return ent
    return None


@app.route('/dm/inventory', methods=['GET'])
def dm_inventory_get():
    """Return current inventory of an entity for DM editing."""
    if 'dm' not in user_role():
        return jsonify(error='DM access required'), 403
    entity_id = request.args.get('id')
    if not entity_id:
        return jsonify(error='Missing id'), 400
    entity = _dm_resolve_entity(entity_id)
    if entity is None:
        return jsonify(error='Entity not found'), 404

    items = []
    for name, info in (getattr(entity, 'inventory', {}) or {}).items():
        try:
            details = game_session.load_thing(name) or {}
        except Exception:
            details = {}
        items.append({
            'name': str(name),
            'label': details.get('label') or details.get('name') or str(name),
            'qty': int(info.get('qty', 0)) if isinstance(info, dict) else 0,
            'type': details.get('type') or info.get('type') if isinstance(info, dict) else None,
            'image': details.get('image') or str(name),
        })
    items.sort(key=lambda e: e['label'].lower())
    return jsonify(entity_id=entity_id, items=items)


@app.route('/dm/inventory/add', methods=['POST'])
def dm_inventory_add():
    """DM: add an item (by catalog name) to an entity's inventory."""
    if 'dm' not in user_role():
        return jsonify(success=False, error='DM access required'), 403
    data = request.get_json(silent=True) or request.form
    entity_id = (data.get('entity_id') or '').strip()
    item_name = (data.get('item_name') or '').strip()
    try:
        qty = int(data.get('qty', 1))
    except (TypeError, ValueError):
        qty = 1
    if not entity_id or not item_name:
        return jsonify(success=False, error='entity_id and item_name are required'), 400
    if qty <= 0:
        return jsonify(success=False, error='qty must be positive'), 400

    entity = _dm_resolve_entity(entity_id)
    if entity is None:
        return jsonify(success=False, error='Entity not found'), 404

    try:
        source_item = game_session.load_thing(item_name)
    except Exception:
        source_item = None
    if source_item is None:
        return jsonify(success=False, error=f'Unknown item: {item_name}'), 404

    try:
        entity.add_item(item_name, amount=qty)
    except Exception as exc:
        return jsonify(success=False, error=f'Failed to add item: {exc}'), 500

    try:
        output_logger.log(
            f"DM gave {qty} x {source_item.get('label') or source_item.get('name') or item_name} to {entity.label()}",
            visibility='dm_only',
        )
    except Exception:
        pass

    socketio.emit('message', {'type': 'refresh_map'})
    new_qty = int((entity.inventory.get(item_name) or {}).get('qty', 0))
    return jsonify(success=True, item_name=item_name, qty=new_qty)


@app.route('/dm/inventory/remove', methods=['POST'])
def dm_inventory_remove():
    """DM: remove (or decrement) an item from an entity's inventory."""
    if 'dm' not in user_role():
        return jsonify(success=False, error='DM access required'), 403
    data = request.get_json(silent=True) or request.form
    entity_id = (data.get('entity_id') or '').strip()
    item_name = (data.get('item_name') or '').strip()
    all_flag = bool(data.get('all'))
    try:
        qty = int(data.get('qty', 1))
    except (TypeError, ValueError):
        qty = 1
    if not entity_id or not item_name:
        return jsonify(success=False, error='entity_id and item_name are required'), 400

    entity = _dm_resolve_entity(entity_id)
    if entity is None:
        return jsonify(success=False, error='Entity not found'), 404

    inventory = getattr(entity, 'inventory', None) or {}
    if item_name not in inventory:
        # Allow removing equipped items as well.
        try:
            equipped = list(entity.properties.get('equipped', []) or [])
        except Exception:
            equipped = []
        if item_name in equipped:
            try:
                entity.unequip(item_name, transfer_inventory=False)
            except Exception as exc:
                return jsonify(success=False, error=f'Failed to unequip: {exc}'), 500
            socketio.emit('message', {'type': 'refresh_map'})
            return jsonify(success=True, item_name=item_name, qty=0)
        return jsonify(success=False, error='Entity does not have that item'), 404

    current_qty = int((inventory.get(item_name) or {}).get('qty', 0))
    drop = current_qty if all_flag else max(1, qty)
    try:
        entity.remove_item(item_name, amount=drop)
    except Exception as exc:
        return jsonify(success=False, error=f'Failed to remove item: {exc}'), 500

    try:
        output_logger.log(
            f"DM removed {drop} x {item_name} from {entity.label()}",
            visibility='dm_only',
        )
    except Exception:
        pass

    socketio.emit('message', {'type': 'refresh_map'})
    new_qty = int((entity.inventory.get(item_name) or {}).get('qty', 0))
    return jsonify(success=True, item_name=item_name, qty=new_qty)


@app.route('/dm/container/contents', methods=['GET'])
def dm_container_contents():
    """DM: get contents of a container item."""
    if 'dm' not in user_role():
        return jsonify(success=False, error='DM access required'), 403
    
    entity_id = request.args.get('entity_id', '').strip()
    container_name = request.args.get('container_name', '').strip()
    
    if not entity_id or not container_name:
        return jsonify(success=False, error='entity_id and container_name are required'), 400
    
    entity = _dm_resolve_entity(entity_id)
    if entity is None:
        return jsonify(success=False, error='Entity not found'), 404
    
    if not hasattr(entity, 'is_container') or not entity.is_container(container_name):
        return jsonify(success=False, error='Item is not a container'), 404
    
    contents = entity.get_container_contents(container_name)
    return jsonify(success=True, contents=contents)


@app.route('/dm/container/add', methods=['POST'])
def dm_container_add():
    """DM: add an item to a container."""
    if 'dm' not in user_role():
        return jsonify(success=False, error='DM access required'), 403
    
    data = request.get_json(silent=True) or request.form
    entity_id = (data.get('entity_id') or '').strip()
    container_name = (data.get('container_name') or '').strip()
    item_name = (data.get('item_name') or '').strip()
    try:
        qty = int(data.get('qty', 1))
    except (TypeError, ValueError):
        qty = 1
    
    if not entity_id or not container_name or not item_name:
        return jsonify(success=False, error='entity_id, container_name, and item_name are required'), 400
    
    entity = _dm_resolve_entity(entity_id)
    if entity is None:
        return jsonify(success=False, error='Entity not found'), 404
    
    if not entity.add_to_container(container_name, item_name, qty):
        return jsonify(success=False, error='Failed to add item to container'), 500
    
    socketio.emit('message', {'type': 'refresh_map'})
    return jsonify(success=True)


@app.route('/dm/container/remove', methods=['POST'])
def dm_container_remove():
    """DM: remove an item from a container."""
    if 'dm' not in user_role():
        return jsonify(success=False, error='DM access required'), 403
    
    data = request.get_json(silent=True) or request.form
    entity_id = (data.get('entity_id') or '').strip()
    container_name = (data.get('container_name') or '').strip()
    item_name = (data.get('item_name') or '').strip()
    try:
        qty = int(data.get('qty', 1))
    except (TypeError, ValueError):
        qty = 1
    
    if not entity_id or not container_name or not item_name:
        return jsonify(success=False, error='entity_id, container_name, and item_name are required'), 400
    
    entity = _dm_resolve_entity(entity_id)
    if entity is None:
        return jsonify(success=False, error='Entity not found'), 404
    
    if not entity.remove_from_container(container_name, item_name, qty):
        return jsonify(success=False, error='Failed to remove item from container'), 500
    
    socketio.emit('message', {'type': 'refresh_map'})
    return jsonify(success=True)


@app.route('/equipment', methods=['GET'])
def get_equipment():
    global current_game
    battle_map = current_game.get_map_for_user(session['username'])
    entity_id = request.args.get('id')
    entity = battle_map.entity_by_uid(entity_id)
    if entity:
        return render_template('equipment.html', entity=entity)
    return jsonify(error="Entity not found"), 404

@app.route('/usable_items', methods=['GET'])
def usable_items():
    global current_game
    battle_map = current_game.get_map_for_user(session['username'])
    entity_id = request.args.get('id', None)
    if not entity_id:
        return jsonify({"error": "entity_id parameter is required"}), 400
    entity = battle_map.entity_by_uid(entity_id)

    if not entity:
        return jsonify({"error": f"Entity with id {entity_id} not found"}), 404
    available_items = entity.usable_items()
    available_items.sort(key=lambda item: item['name'])
    action = UseItemAction(game_session, entity, 'use_item')
    return render_template('usable_items.html', entity=entity, usable_items=available_items, action=action)

 

    return jsonify({
        'volume': volume,
        'distance_ft': range_ft,
        'entities': response
    })

@app.route('/update_group', methods=['POST'])
def update_group():
    if not request.is_json:
        return jsonify(error='Request must be JSON'), 400
    
    data = request.get_json()
    if not data or 'entity_uid' not in data or 'group' not in data:
        return jsonify(error='Missing required parameters'), 400

    entity_uid = data['entity_uid']
    new_group = data['group']
    
    battle = current_game.get_current_battle()
    if not battle:
        return jsonify(error='No active battle'), 400

    entity = current_game.get_entity_by_uid(entity_uid)
    if not entity:
        return jsonify(error='Entity not found'), 404

    # Update the entity's group in the battle
    if entity in battle.entities:
        old_group = battle.entities[entity]['group']
        battle.entities[entity]['group'] = new_group
        
        # Update the groups dictionary
        if old_group in battle.groups:
            battle.groups[old_group].discard(entity)
        battle.groups.setdefault(new_group, set()).add(entity)
        
        return jsonify(status='ok')
    else:
        return jsonify(error='Entity not in battle'), 400

@app.route('/update_controller', methods=['POST'])
def update_controller():
    if not request.is_json:
        return jsonify(error='Request must be JSON'), 400
    
    data = request.get_json()
    if not data or 'entity_uid' not in data or 'controller' not in data:
        return jsonify(error='Missing required parameters'), 400

    entity_uid = data['entity_uid']
    new_controller = data['controller']
    action = data.get('action', 'add')  # Default to add if not specified
    
    battle = current_game.get_current_battle()
    if not battle:
        return jsonify(error='No active battle'), 400

    entity = current_game.get_entity_by_uid(entity_uid)
    if not entity:
        return jsonify(error='Entity not found'), 404

    battle = current_game.get_current_battle()

    # Handle setting engine-side controller kinds
    if action == 'set':
        engine_controller = None
        if new_controller == 'manual':
            engine_controller = WebController(game_session, None)
            engine_controller.add_user("dm")
            current_game.web_controllers[entity] = engine_controller
        elif new_controller == 'ai':
            engine_controller = GenericController(game_session)
        elif new_controller == 'llm':
            from natural20.llm_controller import LlmMcpController
            engine_controller = LlmMcpController(game_session, llm_provider=llm_handler.current_provider)

        if engine_controller and battle:
            engine_controller.register_handlers_on(entity)
            battle.set_controller_for(entity, engine_controller)
        return jsonify(status='ok')

    # Backward-compatible: maintain web controller user sets
    controller = current_game.get_controller_for_entity(entity)
    if not controller:
        controller = WebController(game_session, None)
        controller.add_user("dm")
        current_game.web_controllers[entity] = controller

    if action == 'add':
        controller.add_user(new_controller)
    elif action == 'remove':
        controller.users.discard(new_controller)

    return jsonify(status='ok')

@app.route('/update_hp', methods=['POST'])
def update_hp():
    """Update HP values for an entity (DM only)."""
    if 'dm' not in user_role():
        return jsonify({'success': False, 'error': 'DM access required'}), 403
    
    if not request.is_json:
        return jsonify({'success': False, 'error': 'Request must be JSON'}), 400
    
    data = request.get_json()
    if not data or 'entity_id' not in data or 'hp_type' not in data or 'value' not in data:
        return jsonify({'success': False, 'error': 'Missing required parameters'}), 400

    entity_id = data['entity_id']
    hp_type = data['hp_type']
    value = data['value']
    
    # Validate hp_type
    if hp_type not in ['max_hp', 'current_hp', 'temp_hp']:
        return jsonify({'success': False, 'error': 'Invalid HP type'}), 400
    
    # Validate value
    try:
        value = int(value)
        if value < 0:
            return jsonify({'success': False, 'error': 'HP value cannot be negative'}), 400
        if hp_type == 'max_hp' and value < 1:
            return jsonify({'success': False, 'error': 'Max HP must be at least 1'}), 400
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'HP value must be a number'}), 400

    # Find the entity
    battle_map = current_game.get_map_for_user(session['username'])
    entity = battle_map.entity_by_uid(entity_id)
    if not entity:
        return jsonify({'success': False, 'error': 'Entity not found'}), 404

    try:
        if hp_type == 'max_hp':
            # Update max HP - need to handle player characters properly
            if hasattr(entity, 'properties') and isinstance(entity.properties, dict):
                # For player characters, we need to set the base max_hp in properties
                # The max_hp() method will add class features like dwarven_toughness
                if hasattr(entity, 'class_feature') and entity.class_feature('dwarven_toughness'):
                    # If they have dwarven toughness, the base max_hp should exclude the level bonus
                    entity.properties['max_hp'] = value - entity.level()
                else:
                    # Normal case - set the max_hp directly
                    entity.properties['max_hp'] = value
                
                # Adjust current HP if it exceeds new max
                if entity.hp() > value:
                    entity.attributes['hp'] = value
            else:
                # For NPCs or other entities without properties
                entity.attributes['max_hp'] = value
                if entity.hp() > value:
                    entity.attributes['hp'] = value
                    
        elif hp_type == 'current_hp':
            # Validate current HP doesn't exceed max HP
            max_hp = entity.max_hp()
            if value > max_hp:
                return jsonify({'success': False, 'error': f'Current HP cannot exceed Max HP ({max_hp})'}), 400
            entity.attributes['hp'] = value
            
        elif hp_type == 'temp_hp':
            entity._temp_hp = value

        # Emit update to refresh the UI for all connected clients
        socketio.emit('message', {'type': 'refresh_map'})
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'success': False, 'error': f'Failed to update HP: {str(e)}'}), 500

@app.route('/update_action_resources', methods=['POST'])
def update_action_resources():
    """Update action resources for an entity during battle (DM only)."""
    if 'dm' not in user_role():
        return jsonify({'success': False, 'error': 'DM access required'}), 403
    
    if not request.is_json:
        return jsonify({'success': False, 'error': 'Request must be JSON'}), 400
    
    data = request.get_json()
    if not data or 'entity_id' not in data or 'resource_type' not in data or 'value' not in data:
        return jsonify({'success': False, 'error': 'Missing required parameters'}), 400

    entity_id = data['entity_id']
    resource_type = data['resource_type']
    value = data['value']
    operation = data.get('operation', 'set')  # 'set', 'add', or 'subtract'
    
    # Validate resource_type
    valid_resources = ['action', 'bonus_action', 'reaction']
    if resource_type not in valid_resources:
        return jsonify({'success': False, 'error': 'Invalid resource type'}), 400
    
    # Validate value
    try:
        value = int(value)
        if value < 0:
            return jsonify({'success': False, 'error': 'Resource value cannot be negative'}), 400
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Resource value must be a number'}), 400

    # Check if there's an active battle
    battle = current_game.get_current_battle()
    if not battle:
        return jsonify({'success': False, 'error': 'No active battle found'}), 400

    # Find the entity
    entity = current_game.get_entity_by_uid(entity_id)
    if not entity:
        return jsonify({'success': False, 'error': 'Entity not found'}), 404

    # Check if entity is in the battle
    entity_state = battle.entity_state_for(entity)
    if not entity_state:
        return jsonify({'success': False, 'error': 'Entity is not in the current battle'}), 400

    try:
        current_value = entity_state.get(resource_type, 0)
        
        if operation == 'set':
            new_value = value
        elif operation == 'add':
            new_value = current_value + value
        elif operation == 'subtract':
            new_value = max(0, current_value - value)  # Don't allow negative values
        else:
            return jsonify({'success': False, 'error': 'Invalid operation. Use set, add, or subtract'}), 400
        
        # Cap values at reasonable maximums
        max_values = {'action': 10, 'bonus_action': 10, 'reaction': 10}  # Arbitrary but reasonable limits
        new_value = min(new_value, max_values[resource_type])
        
        # Update the resource
        entity_state[resource_type] = new_value
        
        # Log the change for tracking
        output_logger.log(
            f"DM updated {entity.label()}'s {resource_type.replace('_', ' ')} from {current_value} to {new_value}",
            visibility='dm_only',
        )
        
        # Emit update to refresh the UI for all connected clients
        socketio.emit('message', {'type': 'refresh_map'})
        
        return jsonify({
            'success': True,
            'resource_type': resource_type,
            'old_value': current_value,
            'new_value': new_value
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': f'Failed to update resource: {str(e)}'}), 500

@app.route('/update_spell_slots', methods=['POST'])
def update_spell_slots():
    """Update spell slots for an entity (DM only)."""
    if 'dm' not in user_role():
        return jsonify({'success': False, 'error': 'DM access required'}), 403
    
    if not request.is_json:
        return jsonify({'success': False, 'error': 'Request must be JSON'}), 400
    
    data = request.get_json()
    if not data or 'entity_id' not in data or 'character_class' not in data or 'level' not in data or 'value' not in data:
        return jsonify({'success': False, 'error': 'Missing required parameters'}), 400

    entity_id = data['entity_id']
    character_class = data['character_class']
    level = data['level']
    value = data['value']
    operation = data.get('operation', 'set')  # 'set', 'add', or 'subtract'
    
    # Validate level
    try:
        level = int(level)
        if level < 1 or level > 9:
            return jsonify({'success': False, 'error': 'Spell level must be between 1 and 9'}), 400
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Level must be a number'}), 400
    
    # Validate value
    try:
        value = int(value)
        if value < 0:
            return jsonify({'success': False, 'error': 'Spell slot value cannot be negative'}), 400
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Spell slot value must be a number'}), 400

    # Find the entity
    battle_map = current_game.get_map_for_user(session['username'])
    entity = battle_map.entity_by_uid(entity_id)
    if not entity:
        return jsonify({'success': False, 'error': 'Entity not found'}), 404

    # Check if entity has spells
    if not hasattr(entity, 'spell_slots') or not entity.spell_slots:
        return jsonify({'success': False, 'error': 'Entity does not have spell slots'}), 400

    # Check if character class exists for this entity
    if character_class not in entity.spell_slots:
        return jsonify({'success': False, 'error': f'Character class {character_class} not found for entity'}), 400

    try:
        current_value = entity.spell_slots[character_class].get(level, 0)
        max_value = entity.max_spell_slots(level, character_class)
        
        if operation == 'set':
            new_value = value
        elif operation == 'add':
            new_value = current_value + value
        elif operation == 'subtract':
            new_value = max(0, current_value - value)  # Don't allow negative values
        else:
            return jsonify({'success': False, 'error': 'Invalid operation. Use set, add, or subtract'}), 400
        
        # Cap values at maximum spell slots
        new_value = min(new_value, max_value)
        
        # Update the spell slot
        entity.spell_slots[character_class][level] = new_value
        
        # Log the change for tracking
        output_logger.log(
            f"DM updated {entity.label()}'s {character_class} level {level} spell slots from {current_value} to {new_value}",
            visibility='dm_only',
        )
        
        # Emit update to refresh the UI for all connected clients
        socketio.emit('message', {'type': 'refresh_map'})
        
        return jsonify({
            'success': True,
            'character_class': character_class,
            'level': level,
            'old_value': current_value,
            'new_value': new_value,
            'max_value': max_value
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': f'Failed to update spell slots: {str(e)}'}), 500


def _can_act_for_entity(entity_uid):
    """True if the current session may issue rest commands for this entity."""
    if 'dm' in user_role():
        return True
    return controller_of(entity_uid, session.get('username'))


def _wizard_arcane_recovery_state(entity):
    """Return (budget, available_levels) for a wizard's arcane recovery, or None."""
    if not hasattr(entity, 'wizard_level'):
        return None
    if int(getattr(entity, 'arcane_recovery', 0) or 0) <= 0:
        return None
    import math as _math
    budget = _math.ceil(entity.wizard_level / 2)
    slots = entity.spell_slots.get('wizard', {}) or {}
    avail = []
    for level in sorted(slots.keys()):
        try:
            lvl_i = int(level)
        except (TypeError, ValueError):
            continue
        if lvl_i < 1 or lvl_i > 5:
            continue
        if lvl_i > budget:
            continue
        if slots.get(level, 0) < entity.max_spell_slots(lvl_i, 'wizard'):
            avail.append(lvl_i)
    return budget, avail


class _WebRestController:
    """Inline controller used to drive the engine's rest hooks from a request."""

    def __init__(self, arcane_picks=None, hit_die_picks=None):
        self._arcane_picks = list(arcane_picks or [])
        # Queue of integer die types (e.g. 8 for d8) the entity should spend
        # during the short rest. ``prompt_hit_die_roll`` returns each in order
        # and yields 'skip' when the queue is empty so the engine stops
        # spending dice.
        self._hit_die_picks = list(hit_die_picks or [])
        self.consumed_picks = []
        self.consumed_hit_die = []

    def arcane_recovery_ui(self, entity, available_levels):
        while self._arcane_picks:
            level = self._arcane_picks.pop(0)
            if level in available_levels:
                self.consumed_picks.append(level)
                return level
        return None

    def prompt_hit_die_roll(self, entity, available_die_types):
        """Pull the next die type the player wants to spend, or 'skip'."""
        while self._hit_die_picks:
            die_type = self._hit_die_picks.pop(0)
            if die_type in available_die_types:
                self.consumed_hit_die.append(die_type)
                return die_type
        return 'skip'


def _entity_rest_snapshot(entity):
    """JSON-friendly snapshot of mutable rest-related state."""
    snapshot = {
        'hp': entity.hp(),
        'max_hp': entity.max_hp(),
        'hit_die': dict(entity.hit_die()) if hasattr(entity, 'hit_die') else {},
        'spell_slots': {
            klass: dict(slots) for klass, slots in (getattr(entity, 'spell_slots', {}) or {}).items()
        },
        'statuses': list(entity.statuses) if hasattr(entity, 'statuses') else [],
    }
    for attr in ('arcane_recovery', 'second_wind_count', 'lay_on_hands_count', 'ki_count', 'max_ki', 'bardic_inspiration_count', 'bardic_inspiration_max', 'wild_shape_count', 'wild_shape_max', 'rage_count', 'rage_max', 'raging', 'rage_rounds_remaining', 'reckless_attack_active'):
        if hasattr(entity, attr):
            snapshot[attr] = getattr(entity, attr)
    return snapshot


@app.route('/rest/preview', methods=['GET'])
def rest_preview():
    """Return current state and rest options for an entity."""
    if not session.get('username'):
        return jsonify(success=False, error='Unauthorized'), 401
    entity_id = request.args.get('entity_id')
    rest_type = (request.args.get('type') or 'short').lower()
    if rest_type not in ('short', 'long'):
        return jsonify(success=False, error='Invalid rest type'), 400
    if not entity_id:
        return jsonify(success=False, error='Missing entity_id'), 400
    if not _can_act_for_entity(entity_id):
        return jsonify(success=False, error='Forbidden'), 403

    battle_map = current_game.get_map_for_user(session['username'])
    entity = battle_map.entity_by_uid(entity_id)
    if entity is None:
        return jsonify(success=False, error='Entity not found'), 404

    battle = current_game.get_current_battle()
    in_combat = bool(battle and getattr(battle, 'started', False))
    try:
        availability = entity.rest_status(battle=battle, battle_map=battle_map,
                                          require_rations=True)
    except Exception:
        availability = None
    payload = {
        'success': True,
        'entity_id': entity_id,
        'entity_name': entity.label() if hasattr(entity, 'label') else getattr(entity, 'name', entity_id),
        'type': rest_type,
        'in_combat': in_combat,
        'requires_force': in_combat,
        'is_dm': 'dm' in user_role(),
        'state': _entity_rest_snapshot(entity),
        'availability': availability,
    }
    if availability is not None:
        this_kind = availability.get(rest_type) or {}
        payload['allowed'] = bool(this_kind.get('allowed'))
        payload['blocking_reasons'] = list(this_kind.get('reasons') or [])
        payload['force_overrides'] = bool(this_kind.get('force_overrides'))
        if rest_type == 'long':
            payload['requires_rations'] = bool(this_kind.get('requires_rations'))
            payload['rations_available'] = int(this_kind.get('rations_available') or 0)
    arcane = _wizard_arcane_recovery_state(entity)
    if rest_type == 'short' and arcane is not None:
        budget, levels = arcane
        payload['arcane_recovery'] = {
            'budget': budget,
            'available_levels': levels,
        }
    return jsonify(payload)


@app.route('/rest', methods=['POST'])
def take_rest():
    """Run a short or long rest for an entity."""
    if not session.get('username'):
        return jsonify(success=False, error='Unauthorized'), 401
    data = request.get_json(silent=True) or request.form
    entity_id = data.get('entity_id')
    rest_type = (data.get('type') or 'short').lower()
    force = bool(data.get('force'))
    arcane_picks = data.get('arcane_picks') or []
    if isinstance(arcane_picks, str):
        try:
            arcane_picks = [int(x) for x in arcane_picks.split(',') if x.strip()]
        except ValueError:
            return jsonify(success=False, error='arcane_picks must be integers'), 400
    try:
        arcane_picks = [int(x) for x in arcane_picks]
    except (TypeError, ValueError):
        return jsonify(success=False, error='arcane_picks must be integers'), 400

    hit_die_picks = data.get('hit_die_picks') or []
    if isinstance(hit_die_picks, str):
        try:
            hit_die_picks = [int(x) for x in hit_die_picks.split(',') if x.strip()]
        except ValueError:
            return jsonify(success=False, error='hit_die_picks must be integers'), 400
    try:
        hit_die_picks = [int(x) for x in hit_die_picks]
    except (TypeError, ValueError):
        return jsonify(success=False, error='hit_die_picks must be integers'), 400

    if rest_type not in ('short', 'long'):
        return jsonify(success=False, error='Invalid rest type'), 400
    if not entity_id:
        return jsonify(success=False, error='Missing entity_id'), 400
    if not _can_act_for_entity(entity_id):
        return jsonify(success=False, error='Forbidden'), 403
    if force and 'dm' not in user_role():
        return jsonify(success=False, error='Only the DM may force a rest during combat'), 403

    battle_map = current_game.get_map_for_user(session['username'])
    entity = battle_map.entity_by_uid(entity_id)
    if entity is None:
        return jsonify(success=False, error='Entity not found'), 404

    battle = current_game.get_current_battle()
    before = _entity_rest_snapshot(entity)

    # Validate arcane picks against budget and availability before running the rest.
    if rest_type == 'short' and arcane_picks:
        arcane = _wizard_arcane_recovery_state(entity)
        if arcane is None:
            return jsonify(success=False, error='Entity cannot use arcane recovery'), 400
        budget, _avail = arcane
        if sum(arcane_picks) > budget:
            return jsonify(
                success=False,
                error=f'Arcane recovery picks total {sum(arcane_picks)} exceed budget {budget}'
            ), 400

    # Validate hit-die picks against the entity's currently available hit dice.
    if rest_type == 'short' and hit_die_picks:
        if not hasattr(entity, 'hit_die'):
            return jsonify(success=False, error='Entity has no hit dice to spend'), 400
        available = dict(entity.hit_die() or {})
        remaining = {int(k): int(v) for k, v in available.items()}
        for die_type in hit_die_picks:
            if remaining.get(die_type, 0) <= 0:
                return jsonify(
                    success=False,
                    error=f'No d{die_type} hit dice available to spend'
                ), 400
            remaining[die_type] -= 1

    # Inject a controller so wizard arcane recovery can pick slots from request.
    controller_holder = {}
    rest_controller = _WebRestController(
        arcane_picks=arcane_picks,
        hit_die_picks=hit_die_picks,
    )
    if battle is not None:
        original_controller_for = battle.controller_for

        def _proxy_controller_for(target):
            if target is entity:
                return rest_controller
            return original_controller_for(target)

        battle.controller_for = _proxy_controller_for
        controller_holder['restore'] = lambda: setattr(battle, 'controller_for', original_controller_for)

    try:
        if rest_type == 'short':
            entity.short_rest(battle, force=force, prompt=bool(hit_die_picks),
                              battle_map=battle_map)
            time_advance = 60 * 60  # 1 in-game hour
        else:
            entity.long_rest(battle=battle, battle_map=battle_map, force=force,
                             require_rations=True)
            time_advance = 8 * 60 * 60  # 8 in-game hours

        try:
            current_game.game_session.increment_game_time(time_advance)
        except Exception:
            pass

        try:
            output_logger.log(
                f"{entity.label() if hasattr(entity, 'label') else entity.name} took a {rest_type} rest"
                + (' (DM forced)' if force else '')
            )
        except Exception:
            pass

        socketio.emit('message', {'type': 'refresh_map'})
        return jsonify({
            'success': True,
            'entity_id': entity_id,
            'type': rest_type,
            'forced': force,
            'before': before,
            'after': _entity_rest_snapshot(entity),
            'arcane_picks_consumed': rest_controller.consumed_picks,
            'hit_die_consumed': rest_controller.consumed_hit_die,
            'game_time': current_game.game_session.game_time,
        })
    except ValueError as e:
        return jsonify(success=False, error=str(e)), 409
    except Exception as e:
        logger.exception('Failed to run rest')
        return jsonify(success=False, error=str(e)), 500
    finally:
        if 'restore' in controller_holder:
            controller_holder['restore']()


@app.route('/dm_move_entity', methods=['POST'])
def dm_move_entity():
    """Move an entity to a specific position (DM only)."""
    if 'dm' not in user_role():
        return jsonify({'success': False, 'error': 'DM access required'}), 403
    
    if not request.is_json:
        return jsonify({'success': False, 'error': 'Request must be JSON'}), 400
    
    data = request.get_json()
    if not data or 'entity_id' not in data or 'x' not in data or 'y' not in data:
        return jsonify({'success': False, 'error': 'Missing required parameters'}), 400

    entity_id = data['entity_id']
    target_x = data['x']
    target_y = data['y']
    
    # Validate coordinates
    try:
        target_x = int(target_x)
        target_y = int(target_y)
        if target_x < 0 or target_y < 0:
            return jsonify({'success': False, 'error': 'Coordinates must be non-negative'}), 400
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Coordinates must be numbers'}), 400

    # Find the entity
    entity = current_game.get_entity_by_uid(entity_id)
    if not entity:
        return jsonify({'success': False, 'error': 'Entity not found'}), 404

    # Get the entity's current map
    battle_map = current_game.get_map_for_entity(entity)
    if not battle_map:
        return jsonify({'success': False, 'error': 'Entity map not found'}), 404

    # Validate target coordinates are within map bounds
    if target_x >= battle_map.size[0] or target_y >= battle_map.size[1]:
        return jsonify({'success': False, 'error': f'Coordinates out of bounds. Map size is {battle_map.size[0]}x{battle_map.size[1]}'}), 400

    try:
        # Get current position for logging
        current_x, current_y = battle_map.entity_or_object_pos(entity)
        
        # Check if the target position is placeable for this entity
        battle = current_game.get_current_battle()
        if not battle_map.placeable(entity, target_x, target_y, battle):
            return jsonify({'success': False, 'error': 'Target position is not placeable for this entity'}), 400
        
        # Perform the move
        battle_map.move_to(entity, target_x, target_y, battle)
        
        # Log the move for tracking
        output_logger.log(
            f"DM moved {entity.label()} from ({current_x}, {current_y}) to ({target_x}, {target_y})",
            visibility='dm_only',
        )
        
        # Emit update to refresh the UI for all connected clients
        socketio.emit('message', {'type': 'refresh_map'})
        
        return jsonify({
            'success': True,
            'entity_id': entity_id,
            'from': {'x': current_x, 'y': current_y},
            'to': {'x': target_x, 'y': target_y}
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': f'Failed to move entity: {str(e)}'}), 500

@app.route('/get_users')
def get_users():
    global current_game
    query = request.args.get('query', '').lower()
    if not query:
        return jsonify([])
    
    # Get all users from username_to_sid
    users = []
    for username in current_game.username_to_sid.keys():
        if query in username.lower():
            users.append(username)
    
    return jsonify(users)

# AI Chatbot Routes
@app.route('/ai/initialize', methods=['POST'])
def ai_initialize():
    """Initialize the AI provider."""
    if 'dm' not in user_role():
        return jsonify({'success': False, 'error': 'DM access required'}), 403
    
    try:
        provider = request.form.get('provider')
        api_key = request.form.get('api_key')
        base_url = request.form.get('base_url')
        model = request.form.get('model')
        
        if not provider:
            return jsonify({'success': False, 'error': 'Provider is required'})
        
        config = {}
        if api_key:
            config['api_key'] = api_key
        if base_url:
            config['base_url'] = base_url
        if model:
            config['model'] = model
        
        success = llm_handler.initialize_provider(provider, config)
        
        if success:
            # Get provider info for response
            provider_info = llm_handler.get_provider_info()
            response_data = {'success': True}
            
            # Add model information if available
            if provider_info.get('current_model'):
                response_data['model'] = provider_info['current_model']
            if provider_info.get('available_models'):
                response_data['available_models'] = provider_info['available_models']
            
            return jsonify(response_data)
        else:
            return jsonify({'success': False, 'error': f'Failed to initialize {provider} provider'})
            
    except Exception as e:
        logger.error(f"Error initializing AI: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/ai/initialize-from-env', methods=['POST'])
def ai_initialize_from_env():
    """Re-apply ``LLM_PROVIDER`` / API keys to the shared handler (same as NPC/dialog LLM)."""
    if 'dm' not in user_role():
        return jsonify({'success': False, 'error': 'DM access required'}), 403
    try:
        # Avoid blocking HTTP calls to Ollama/llama.cpp again if startup already succeeded.
        if getattr(llm_handler, 'current_provider', None):
            info = llm_handler.get_provider_info()
            return jsonify({'success': bool(info.get('initialized')), 'info': info})
        ok = configure_llm_handler_from_environment(llm_handler)
        info = llm_handler.get_provider_info()
        return jsonify({
            'success': bool(ok and info.get('initialized')),
            'info': info,
        })
    except Exception as e:
        logger.error(f"Error syncing LLM from environment: {e}")
        return jsonify({'success': False, 'error': str(e)})


DM_AI_CHAT_SESSION_KEY = 'dm_ai_chat_history'


def _restore_dm_ai_history_from_session():
    """Reload in-memory DM assistant history after page refresh or worker swap."""
    if 'dm' not in user_role():
        return
    if llm_handler.get_conversation_history():
        return
    stored = session.get(DM_AI_CHAT_SESSION_KEY)
    if stored:
        llm_handler.conversation_history = list(stored)
        return
    db = getattr(current_game, 'campaign_log_db', None)
    if db is not None:
        try:
            rows = db.dm_assistant_history_for_llm()
            if rows:
                llm_handler.conversation_history = rows
        except Exception as exc:
            logger.debug(f"DM assistant history restore from DB skipped: {exc}")


def _persist_dm_ai_history_to_session():
    if 'dm' not in user_role():
        return
    session[DM_AI_CHAT_SESSION_KEY] = LLMHandler.conversation_history_for_storage(
        llm_handler.get_conversation_history()
    )
    session.modified = True


def _log_dm_assistant_turn(role, content):
    db = getattr(current_game, 'campaign_log_db', None)
    if db is None:
        return
    try:
        db.append_dm_turn(role, content, username=session.get('username'))
    except Exception as exc:
        logger.debug(f"DM assistant campaign log skipped: {exc}")


@app.route('/ai/chat', methods=['POST'])
def ai_chat():
    """Send a message to the AI and get a response."""
    if 'dm' not in user_role():
        return jsonify({'success': False, 'error': 'DM access required'}), 403
    
    try:
        message = request.form.get('message')
        
        if not message:
            return jsonify({'success': False, 'error': 'Message is required'})

        _restore_dm_ai_history_from_session()
        _log_dm_assistant_turn('user', message)

        # Get comprehensive game context using the LLM handler's RAG system
        context = llm_handler.get_game_context()
        username = session.get('username')
        current_pov_entity = current_game.get_pov_entity_for_user(username)
        # Add basic session context
        context['session'] = {
            'username': session.get('username'),
            'role': user_role(),
            'current_map': current_game.get_map_for_user(session['username']).name,
            'pov_entity': current_pov_entity.entity_uid if current_pov_entity else None
        }
        # Send message to AI with RAG context (offloaded so Socket.IO stays responsive)
        response = llm_handler.send_message(message, context)
        _log_dm_assistant_turn('assistant', response)
        _persist_dm_ai_history_to_session()

        return jsonify({'success': True, 'response': response})
        
    except Exception as e:
        logger.error(f"Error in AI chat: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/ai/context', methods=['GET'])
def ai_get_context():
    """Get current game context for the AI."""
    if 'dm' not in user_role():
        return jsonify({'success': False, 'error': 'DM access required'}), 403
    
    try:
        # Get comprehensive game context using the LLM handler's RAG system
        context = llm_handler.get_game_context()
        
        # Add basic session context
        context['session'] = {
            'username': session.get('username'),
            'role': user_role()
        }
        
        return jsonify({'success': True, 'context': context})
        
    except Exception as e:
        logger.error(f"Error getting game context: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/ai/clear-history', methods=['POST'])
def ai_clear_history():
    """Clear the AI conversation history."""
    if 'dm' not in user_role():
        return jsonify({'success': False, 'error': 'DM access required'}), 403
    
    try:
        llm_handler.clear_history()
        session.pop(DM_AI_CHAT_SESSION_KEY, None)
        session.modified = True
        db = getattr(current_game, 'campaign_log_db', None)
        if db is not None:
            db.clear_category('dm_assistant')
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Error clearing AI history: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/admin/campaign-logs/reset', methods=['POST'])
def admin_reset_campaign_logs():
    """DM-only wipe of persisted campaign logs (combat, chat, assistant, journals)."""
    if not session.get('username'):
        return jsonify(error='Unauthorized'), 401
    if 'dm' not in user_role():
        return jsonify(error='Forbidden'), 403
    payload = request.get_json(silent=True) or {}
    clear_buffers = bool(payload.get('clear_live_conversation_buffers'))
    try:
        removed = current_game.reset_campaign_logs(
            clear_live_conversation_buffers=clear_buffers,
        )
        llm_handler.clear_history()
        session.pop(DM_AI_CHAT_SESSION_KEY, None)
        session.modified = True
        try:
            socketio.emit('message', {'type': 'console', 'messages': []})
        except Exception:
            pass
        return jsonify(success=True, removed_counts=removed)
    except Exception as e:
        logger.error(f"Error resetting campaign logs: {e}")
        return jsonify(success=False, error=str(e)), 500


@app.route('/admin/campaign-logs/status', methods=['GET'])
def admin_campaign_logs_status():
    if not session.get('username'):
        return jsonify(error='Unauthorized'), 401
    if 'dm' not in user_role():
        return jsonify(error='Forbidden'), 403
    try:
        db = getattr(current_game, 'campaign_log_db', None)
        counts = db.counts_by_category() if db is not None else {}
        return jsonify(
            success=True,
            db_path=getattr(db, 'db_path', None),
            counts=counts,
        )
    except Exception as e:
        return jsonify(success=False, error=str(e)), 500


@app.route('/ai/history', methods=['GET'])
def ai_get_history():
    """Get the AI conversation history."""
    if 'dm' not in user_role():
        return jsonify({'success': False, 'error': 'DM access required'}), 403
    
    try:
        _restore_dm_ai_history_from_session()
        history = LLMHandler.displayable_conversation_history(
            llm_handler.get_conversation_history()
        )
        return jsonify({'success': True, 'history': history})
        
    except Exception as e:
        logger.error(f"Error getting AI history: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/ai/ollama/models', methods=['GET'])
def ai_get_ollama_models():
    """Get available Ollama models."""
    if 'dm' not in user_role():
        return jsonify({'success': False, 'error': 'DM access required'}), 403
    
    try:
        base_url = request.args.get('base_url', 'http://localhost:11434')
        
        # Test connection to Ollama
        response = requests.get(f"{base_url}/api/tags", timeout=10)
        if response.status_code == 200:
            data = response.json()
            models = [model['name'] for model in data.get('models', [])]
            return jsonify({'success': True, 'models': models})
        else:
            return jsonify({'success': False, 'error': f'Ollama API error: {response.status_code}'})
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Error connecting to Ollama: {e}")
        return jsonify({'success': False, 'error': f'Failed to connect to Ollama: {str(e)}'})
    except Exception as e:
        logger.error(f"Error getting Ollama models: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/ai/llama_cpp/models', methods=['GET'])
def ai_get_llama_cpp_models():
    """Get available llama.cpp models from an OpenAI-compatible server."""
    if 'dm' not in user_role():
        return jsonify({'success': False, 'error': 'DM access required'}), 403

    try:
        base_url = request.args.get('base_url', 'http://localhost:8011').rstrip('/')
        api_key = request.args.get('api_key', 'llama-cpp')
        headers = {'Authorization': f'Bearer {api_key}'}

        response = requests.get(f"{base_url}/v1/models", headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            models = LlamaCppProvider._extract_model_ids(data)
            return jsonify({'success': True, 'models': models})
        return jsonify({'success': False, 'error': f'llama.cpp API error: {response.status_code}'})

    except requests.exceptions.RequestException as e:
        logger.error(f"Error connecting to llama.cpp: {e}")
        return jsonify({'success': False, 'error': f'Failed to connect to llama.cpp: {str(e)}'})
    except Exception as e:
        logger.error(f"Error getting llama.cpp models: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/ai/set-model', methods=['POST'])
def ai_set_model():
    """Set the model for the current AI provider."""
    if 'dm' not in user_role():
        return jsonify({'success': False, 'error': 'DM access required'}), 403
    
    try:
        model_name = request.form.get('model')
        
        if not model_name:
            return jsonify({'success': False, 'error': 'Model name is required'})
        
        success = llm_handler.set_model(model_name)
        
        if success:
            return jsonify({'success': True, 'model': model_name})
        else:
            return jsonify({'success': False, 'error': f'Failed to set model: {model_name}'})
            
    except Exception as e:
        logger.error(f"Error setting AI model: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/ai/provider-info', methods=['GET'])
def ai_get_provider_info():
    """Get information about the current AI provider."""
    if 'dm' not in user_role():
        return jsonify({'success': False, 'error': 'DM access required'}), 403
    
    try:
        info = llm_handler.get_provider_info()
        return jsonify({'success': True, 'info': info})
        
    except Exception as e:
        logger.error(f"Error getting provider info: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/ai/entity-details', methods=['GET'])
def ai_get_entity_details():
    """Get detailed information about a specific entity for RAG."""
    if 'dm' not in user_role():
        return jsonify({'success': False, 'error': 'DM access required'}), 403
    
    try:
        entity_name = request.args.get('entity_name')
        if not entity_name:
            return jsonify({'success': False, 'error': 'Entity name is required'})
        
        details = game_context_provider.get_entity_details(entity_name)
        return jsonify({'success': True, 'details': details})
        
    except Exception as e:
        logger.error(f"Error getting entity details: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/ai/terrain-info', methods=['GET'])
def ai_get_terrain_info():
    """Get terrain information for a specific location for RAG."""
    if 'dm' not in user_role():
        return jsonify({'success': False, 'error': 'DM access required'}), 403
    
    try:
        x = request.args.get('x', type=int)
        y = request.args.get('y', type=int)
        
        if x is None or y is None:
            return jsonify({'success': False, 'error': 'X and Y coordinates are required'})
        
        terrain_info = game_context_provider.get_map_terrain_info(x, y)
        return jsonify({'success': True, 'terrain_info': terrain_info})
        
    except Exception as e:
        logger.error(f"Error getting terrain info: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/ai/available-actions', methods=['GET'])
def ai_get_available_actions():
    """Get available actions for a specific entity for RAG."""
    if 'dm' not in user_role():
        return jsonify({'success': False, 'error': 'DM access required'}), 403
    
    try:
        entity_name = request.args.get('entity_name')
        if not entity_name:
            return jsonify({'success': False, 'error': 'Entity name is required'})
        
        actions = game_context_provider.get_available_actions(entity_name)
        return jsonify({'success': True, 'actions': actions})
        
    except Exception as e:
        logger.error(f"Error getting available actions: {e}")
        return jsonify({'success': False, 'error': str(e)})



def get_game_context():
    """Get current game context for the AI."""
    context = {}
    
    try:
        # Get current map
        battle_map = current_game.get_map_for_user(session['username'])
        if battle_map:
            context['current_map'] = battle_map.name
        
        # Get current battle status
        battle = current_game.get_current_battle()
        if battle:
            context['battle'] = True
            current_turn = battle.current_turn()
            if current_turn:
                context['current_turn'] = current_turn.label()
        
        # Get entities in the current map
        if battle_map:
            entities = []
            for entity in battle_map.entities:
                if hasattr(entity, 'label'):
                    entity_info = {
                        'name': entity.label(),
                        'type': entity.__class__.__name__,
                        'position': battle_map.entity_or_object_pos(entity) if hasattr(battle_map, 'entity_or_object_pos') else None
                    }
                    entities.append(entity_info)
            context['entities'] = entities
        
        # Get POV entity
        pov_entity = current_game.get_pov_entity_for_user(session['username'])
        if pov_entity:
            context['pov_entity'] = pov_entity.label()
        
    except Exception as e:
        logger.error(f"Error getting game context: {e}")
        context['error'] = str(e)
    
    return context

@app.route('/targets_at_position', methods=['GET'])
def get_targets_at_position():
    """Get all valid targets at a specific tile position for target selection modal."""
    global current_game
    
    try:
        entity_id = request.args.get('entity_id')
        x = int(request.args.get('x'))
        y = int(request.args.get('y'))
        action_info = request.args.get('action_info')
        opts = json.loads(request.args.get('opts', '{}'))
        
        if not entity_id or x is None or y is None or not action_info:
            return jsonify({'success': False, 'error': 'Missing required parameters'}), 400
        
        entity = current_game.get_entity_by_uid(entity_id)
        if not entity:
            return jsonify({'success': False, 'error': 'Entity not found'}), 404
        
        battle_map = current_game.get_map_for_entity(entity)
        battle = current_game.get_current_battle()
        
        # Get all things at the position
        things_at_position = battle_map.thing_at(x, y)
        
        # Filter to only valid targets based on the action
        valid_targets = []
        
        if action_info in ['AttackAction', 'LinkedAttackAction']:
            action = AttackAction(game_session, entity, 'attack')
            action.using = opts.get('using')
            action.npc_action = opts.get('npc_action', None)
            action.thrown = opts.get('thrown', False)
            
            # Check each thing at the position
            for thing in things_at_position:
                if thing and thing.allow_targeting():
                    action.target = thing
                    action.validate(battle_map, target=thing)
                    
                    if not action.errors:
                        if battle:
                            battle_valid_targets = battle.valid_targets_for(entity, action)
                            if thing in battle_valid_targets:
                                valid_targets.append({
                                    'id': thing.entity_uid,
                                    'name': thing.label() if hasattr(thing, 'label') else str(thing),
                                    'type': thing.__class__.__name__,
                                    'image': getattr(thing, 'profile_image', lambda: None)()
                                })
                        else:
                            map_valid_targets = battle_map.valid_targets_for(entity, action)
                            if thing in map_valid_targets:
                                valid_targets.append({
                                    'id': thing.entity_uid,
                                    'name': thing.label() if hasattr(thing, 'label') else str(thing),
                                    'type': thing.__class__.__name__,
                                    'image': getattr(thing, 'profile_image', lambda: None)()
                                })
        
        elif action_info == 'SpellAction':
            build_map = SpellAction.build(game_session, entity)
            spell_choice = (opts['spell'], opts['at_level'])
            build_map = build_map['next'](spell_choice)
            
            # Check each thing at the position
            for thing in things_at_position:
                if thing and thing.allow_targeting():
                    try:
                        # Try to build the action with this target
                        test_build = build_map
                        while not isinstance(test_build, Action):
                            if test_build['param'][0]['type'] == 'select_target':
                                test_build = test_build['next'](thing)
                            elif test_build['param'][0]['type'] == 'select_empty_space':
                                test_build = test_build['next']([x, y])
                            else:
                                break
                        
                        if isinstance(test_build, Action):
                            test_build.validate(battle_map, target=thing)
                            if not test_build.errors:
                                valid_targets.append({
                                    'id': thing.entity_uid,
                                    'name': thing.label() if hasattr(thing, 'label') else str(thing),
                                    'type': thing.__class__.__name__,
                                    'image': getattr(thing, 'profile_image', lambda: None)()
                                })
                    except:
                        # If validation fails, skip this target
                        continue
        
        # Also check if the position itself is a valid target (for area spells)
        try:
            if action_info == 'SpellAction':
                build_map = SpellAction.build(game_session, entity)
                spell_choice = (opts['spell'], opts['at_level'])
                build_map = build_map['next'](spell_choice)
                
                test_build = build_map
                while not isinstance(test_build, Action):
                    if test_build['param'][0]['type'] == 'select_empty_space':
                        test_build = test_build['next']([x, y])
                    else:
                        break
                
                if isinstance(test_build, Action):
                    test_build.validate(battle_map, target=[x, y])
                    if not test_build.errors:
                        valid_targets.append({
                            'id': f'position_{x}_{y}',
                            'name': f'Position ({x}, {y})',
                            'type': 'position',
                            'image': None
                        })
        except:
            # If position validation fails, skip
            pass
        
        return jsonify({
            'success': True,
            'targets': valid_targets,
            'position': {'x': x, 'y': y}
        })
        
    except Exception as e:
        logger.error(f"Error getting targets at position: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    # Configure for better ngrok compatibility
    socketio.run(
        app, 
        debug=False, 
        host='0.0.0.0', 
        port=5001, 
        allow_unsafe_werkzeug=True,
        # Add ngrok-specific settings
        use_reloader=False,  # Disable reloader for ngrok
        log_output=True
    )
