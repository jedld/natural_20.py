from flask import Flask, request, jsonify, session, redirect, url_for, render_template, send_file
from flask_socketio import SocketIO, emit
from flask_session import Session
from flask import send_from_directory
from flask_cors import CORS  # Add CORS support
from natural20.utils.serialization import  object_type_to_klass
import json
import os
import click
import uuid
from PIL import Image
import logging
import importlib
import pdb

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
from natural20.web.json_renderer import JsonRenderer
from natural20.web.web_controller import WebController, ManualControl
from natural20.actions.attack_action import AttackAction, TwoWeaponAttackAction, LinkedAttackAction
from natural20.actions.move_action import MoveAction
from natural20.actions.second_wind_action import SecondWindAction
from natural20.actions.disengage_action import DisengageAction, DisengageBonusAction
from natural20.actions.dash import DashAction, DashBonusAction
from natural20.actions.dodge_action import DodgeAction
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
from natural20.actions.use_item_action import UseItemAction
from natural20.actions.interact_action import InteractAction
from natural20.actions.summon_familiar_action import SummonFamiliarAction
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
from webapp.llm_handler import LLMHandler
import threading
import pdb
import traceback
# Import the LLM handler
from webapp.llm_handler import llm_handler
from webapp.game_context import GameContextProvider
from webapp.entity_rag_handler import EntityRAGHandler
import requests
import re
from PIL import Image, ImageDraw
import io

app = Flask(__name__, static_folder='static', static_url_path='/')

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
            "http://*.ngrok.io",
            "http://*.ngrok-free.app"
        ]
    
    logger.info(f"Using default CORS origins for {'production' if (is_aws or is_production) else 'development'}: {default_origins}")
    return default_origins

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
    cors_allowed_origins=allowed_origins,  # Use the same origins as CORS
    async_mode=async_mode,  # Use eventlet for WebSocket support
    ping_timeout=120,  # Increased timeout
    ping_interval=30,  # Increased interval
    max_http_buffer_size=1e8,
    logger=True,
    engineio_logger=True,
    manage_session=True,
    cookie=True,
    always_connect=True,
    message_queue=None,  # Disable message queue since we're using a single worker
    # Add ngrok-specific settings
    transports=['websocket', 'polling'],  # Allow both WebSocket and polling
    allow_upgrades=True,
    upgrade_timeout=10
)
Session(app)

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
EXTENSIONS = []
first_connect = False

if 'extensions' in index_data:
    for extension in index_data['extensions']:
        # load extension and import extension from the extensions folder
        extension_name = extension['name']
        # import extensionfrom natural20.actions.dismiss_familiar_action import DismissFamiliarAction

sockets = []
MAP_PADDING = [6, 15]

output_logger = SocketIOOutputLogger(socketio)
output_logger.log("Server started")

event_manager = EventManager(output_logger=output_logger, movement_consolidation=True)
event_manager.standard_cli()
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
                              autosave=AUTOSAVE,
                              system_logger=logger,
                              soundtrack=SOUNDTRACKS)

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

# Register the functions
register_game_context_functions()

i18n.set('locale', 'en')

# initialize all extensiond
for extension in EXTENSIONS:
    extension.init(app, current_game, game_session)

# Initialize the LLM conversation handler
# Initialize the LLM with API key from environment variable
if os.path.exists(os.path.join(LEVEL, 'npc_system_prompt.txt')):
    with open(os.path.join(LEVEL, 'npc_system_prompt.txt')) as f:
        CONVERSATION_SYSTEM_PROMPT = f.read()
else:
    CONVERSATION_SYSTEM_PROMPT = ""

def initialize_llm_from_env():
    """Initialize LLM handler from environment variables."""
    llm_handler = LLMHandler()
    
    # Check for LLM provider configuration
    llm_provider = os.environ.get('LLM_PROVIDER', 'ollama').lower()
    
    if llm_provider == 'openai':
        # OpenAI configuration
        api_key = os.environ.get('OPENAI_API_KEY')
        base_url = os.environ.get('OPENAI_BASE_URL')
        model = os.environ.get('OPENAI_MODEL', 'gpt-4o')
        
        if not api_key:
            logger.warning("OPENAI_API_KEY not set, LLM features will be disabled")
            return llm_handler
        
        config = {
            'api_key': api_key,
            'model': model
        }
        if base_url:
            config['base_url'] = base_url
            
        success = llm_handler.initialize_provider('openai', config)
        if success:
            logger.info(f"Initialized OpenAI provider with model: {model}")
        else:
            logger.error("Failed to initialize OpenAI provider")
            
    elif llm_provider == 'anthropic':
        # Anthropic configuration
        api_key = os.environ.get('ANTHROPIC_API_KEY')
        model = os.environ.get('ANTHROPIC_MODEL', 'claude-3-5-sonnet-20241022')
        
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY not set, LLM features will be disabled")
            return llm_handler
        
        config = {
            'api_key': api_key,
            'model': model
        }
        
        success = llm_handler.initialize_provider('anthropic', config)
        if success:
            logger.info(f"Initialized Anthropic provider with model: {model}")
        else:
            logger.error("Failed to initialize Anthropic provider")
            
    elif llm_provider == 'ollama':
        # Ollama configuration
        base_url = os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434')
        model = os.environ.get('OLLAMA_MODEL', 'gemma3:27b')
        
        config = {
            'base_url': base_url,
            'model': model
        }
        
        success = llm_handler.initialize_provider('ollama', config)
        if success:
            logger.info(f"Initialized Ollama provider with model: {model} at {base_url}")
        else:
            logger.error(f"Failed to initialize Ollama provider: {config}")
            
    else:
        logger.warning(f"Unknown LLM provider: {llm_provider}, using mock provider")
        llm_handler.initialize_provider('mock', {})
    
    return llm_handler

# Initialize LLM handler from environment variables
llm_handler = initialize_llm_from_env()
llm_conversation_handler = LLMConversationController(llm_handler)

# Initialize Entity RAG Handler
entity_rag_handler = EntityRAGHandler(game_session, current_game)


def logged_in():
    return session.get('username') is not None

def user_role():
    login_info = next((login for login in LOGINS if login["name"].lower() == session['username']), None)
    return login_info["role"] if login_info else []


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


@app.route('/admin/save', methods=['POST'])
def admin_save():
    if not session.get('username'):
        return jsonify(error='Unauthorized'), 401
    if 'dm' not in user_role():
        return jsonify(error='Forbidden'), 403
    payload = request.get_json(silent=True) or {}
    name = payload.get('name')
    try:
        with current_game.game_state_lock:
            current_game.save_game(name=name)
        return jsonify(status='ok')
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

def describe_terrain(tile):
    battle_map = current_game.get_map_for_user(session['username'])
    battle = current_game.get_current_battle()
    description = []
    if tile.get('difficult'):
        description.append("Difficult Terrain")

    lights = battle_map.light_at(tile['x'], tile['y'])
    # Assuming `map` is accessible and has a method `thing_at(x, y)` returning an object with a `label` attribute
    things = battle_map.thing_at(tile['x'], tile['y'])
    if things:
        for thing in things:
            description.append(thing.label())
            if isinstance(thing, Object):
                if thing.dead():
                    description.append("Destroyed")
            if not isinstance(thing, Object):
                # obtain buffs and status effects on entity
                if thing.prone():
                    description.append("Prone")
                if thing.hidden():
                    description.append("Hiding")
                if thing.unconscious() and not thing.stable():
                    description.append("Unconscious")
                if thing.dead():
                    description.append("Dead")
                if thing.grappled():
                    description.append("Grappled")
                if thing.dodge(battle):
                    description.append("Dodge")
                if thing.stable():
                    description.append("Unconscious (but Stable)")
                for effect in thing.current_effects():
                    effect_class = effect['effect']
                    description.append(str(effect_class))
    if (lights == 0.0):
        description.append("Darkness (heavily obscured)")
    elif (lights == 0.5):
        description.append("Dim Light")
    else:
        description.append("Bright Light")

    return "".join(f"<p>{d}</p>" for d in description)

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
    file_path = os.path.join(LEVEL, "assets", asset_name)
    if os.path.exists(file_path):
        return send_file(file_path)
    else:
        resolved_path = os.path.join(game_session.root_path, "assets")
        if os.path.exists(resolved_path):
            return send_from_directory(resolved_path, asset_name)

        return jsonify(error="File not found"), 404

@app.route('/character_builder', methods=['GET'])
def character_builder():
    if not logged_in():
        return redirect(url_for('login'))

    try:
        races = game_session.load_races()
        classes = game_session.load_classes()
        return render_template('character_builder.html',
                               title=TITLE,
                               races=races,
                               classes=classes)
    except Exception as e:
        logger.exception('Failed to load character builder')
        return jsonify(error='Failed to load character builder'), 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].lower()
        password = request.form['password']

        login_info = next((login for login in LOGINS if login["name"].lower() == username), None)
        if login_info and login_info["password"] == password:
            session['username'] = username
            
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
                         taken_characters=taken_characters)

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

        # Parse optional structured selections
        def _parse_json_list(key):
            val = request.form.get(key)
            if not val:
                return []
            try:
                data = json.loads(val)
                if isinstance(data, list):
                    return [str(x) for x in data]
            except Exception:
                pass
            return []
        selected_skills = _parse_json_list('skills')
        selected_cantrips = _parse_json_list('cantrips')
        selected_level1 = _parse_json_list('level1_spells')

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

        # Validate and apply class choices from templates
        try:
            classes_def = game_session.load_classes() or {}
            cdef = classes_def.get(klass, {})
            # Skills
            max_skills = int(cdef.get('available_skills_choices', 0))
            available_skills = cdef.get('available_skills', []) or []
            if max_skills and available_skills:
                valid_skills = [s for s in selected_skills if s in available_skills][:max_skills]
                if valid_skills:
                    pc['skills'] = valid_skills

            # Spells and early-class specifics
            spell_list = cdef.get('spell_list', {}) or {}
            if spell_list:
                can_list = spell_list.get('cantrip', []) or []
                lvl1_list = spell_list.get('level_1', []) or []
                # Very light SRD-based counts for level 1/2
                klass_lower = klass.lower()
                cantrip_cap = 0
                lvl1_cap = 0
                spellbook_cap = 0
                if klass_lower == 'wizard':
                    cantrip_cap = 3
                    lvl1_cap = 2
                    spellbook_cap = 6 if level==1 else 8
                elif klass_lower == 'cleric':
                    cantrip_cap = 3
                    lvl1_cap = 2 if level==1 else 3
                elif klass_lower == 'bard':
                    cantrip_cap = 2
                    lvl1_cap = 4 if level==1 else 5

                cantrips = [s for s in selected_cantrips if s in can_list][:cantrip_cap]
                if cantrips:
                    # store within prepared_spells for compatibility
                    pc.setdefault('prepared_spells', [])
                    pc['prepared_spells'].extend(cantrips)

                lvl1_spells = [s for s in selected_level1 if s in lvl1_list][:lvl1_cap]
                if lvl1_spells:
                    pc.setdefault('prepared_spells', [])
                    # For wizard, also seed spellbook
                    if klass_lower == 'wizard':
                        # prepared spells include cantrips + a couple level1
                        pc['prepared_spells'].extend(lvl1_spells)
                        # Seed spellbook up to cap
                        book = list(dict.fromkeys(lvl1_spells))
                        # add more randomly if needed
                        import random as _r
                        pool = [s for s in lvl1_list if s not in book]
                        while len(book) < spellbook_cap and pool:
                            pick = _r.choice(pool)
                            pool.remove(pick)
                            book.append(pick)
                        pc['spellbook'] = book
                    else:
                        pc['prepared_spells'].extend(lvl1_spells)
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

        # Save uploaded images, if any
        try:
            assets_dir = os.path.join(game_session.root_path, 'assets')
            os.makedirs(assets_dir, exist_ok=True)
            # Profile portrait: assets/characters/<entity_uid>.png
            profile_file = request.files.get('profile_image')
            if profile_file and profile_file.filename:
                profiles_dir = os.path.join(assets_dir, 'characters')
                os.makedirs(profiles_dir, exist_ok=True)
                profile_path = os.path.join(profiles_dir, f"{entity_uid}.png")
                img = Image.open(profile_file.stream).convert('RGBA')
                img.save(profile_path, format='PNG')
            # Token image: assets/token_<entity_uid>.png
            token_file = request.files.get('token_image')
            if token_file and token_file.filename:
                token_path = os.path.join(assets_dir, f"token_{entity_uid}.png")
                timg = Image.open(token_file.stream).convert('RGBA')
                timg.save(token_path, format='PNG')
        except Exception:
            logger.exception('Failed to save uploaded character images')

    # Load into current session and place on a map (default to 'index')
        try:
            pc_entity = PlayerCharacter.load(game_session, f'characters/{safe_name}.yml')
            target_map = game_session.maps.get('index') or next(iter(game_session.maps.values()))
            # find a free tile
            width, height = target_map.size
            pos = None
            for y in range(height):
                for x in range(width):
                    if not target_map.entity_at(x, y):
                        pos = (x, y); break
                if pos: break
            if not pos:
                pos = (0, 0)
            target_map.add(pc_entity, pos[0], pos[1], group='a')
        except Exception:
            logger.exception('Failed to place new character on map')

        # Update index.json selectable_characters so it shows in selection page
        try:
            index_json_path = os.path.join(game_session.root_path, 'index.json')
            if os.path.exists(index_json_path):
                with open(index_json_path, 'r') as jf:
                    idx = json.load(jf)
            else:
                idx = {}
            selectable = idx.get('selectable_characters') or []
            # If not present, add basic entry (use entity_uid for consistency)
            lower = entity_uid
            if not any(c.get('name','').lower()==lower for c in selectable):
                selectable.append({
                    'name': lower,
                    'file': f'characters/{lower}.png',
                    'description': pc.get('description', lower)
                })
            idx['selectable_characters'] = selectable
            with open(index_json_path, 'w') as jf:
                json.dump(idx, jf, indent=2)
            # Also update in-memory index_data so UI sees it immediately
            try:
                global index_data
                index_data['selectable_characters'] = selectable
            except Exception:
                logger.exception('Failed to update in-memory selectable_characters')
        except Exception:
            logger.exception('Failed to update index.json with new character')

        # Optionally redirect to selection if a player
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
    username = session['username']
    
    if not character_name:
        return jsonify(error="No character specified")
    
    # Check if character exists in selectable characters
    selectable_characters = index_data.get("selectable_characters", [])
    character_exists = any(char['name'] == character_name for char in selectable_characters)
    
    if not character_exists:
        return jsonify(error="Invalid character selection")
    
    # Check if character is already taken
    for controller in CONTROLLERS:
        if controller['entity_uid'] == character_name and controller['controllers']:
            return jsonify(error="Character is already taken")
    
    # Assign character to user
    for controller in CONTROLLERS:
        if controller['entity_uid'] == character_name:
            if username not in controller['controllers']:
                controller['controllers'].append(username)
            break
    else:
        # Character not found in default controllers, create new entry
        CONTROLLERS.append({
            'entity_uid': character_name,
            'controllers': [username]
        })
    
    # Update the current_game controllers if needed
    current_game._setup_controllers()
    
    logger.info(f"User {username} selected character {character_name}")
    return jsonify(status='ok')

@app.route('/character_details/<character_name>', methods=['GET'])
def character_details(character_name):
    """Get detailed information about a character for preview"""
    try:
        # Load the character from the game session
        character = current_game.get_entity_by_uid(character_name)
        
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
        
        return jsonify(details)
        
    except Exception as e:
        logger.error(f"Error getting character details for {character_name}: {e}")
        return jsonify(error="Failed to load character details"), 500

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

@app.route('/')
def index():
    global current_game, logger
    if not logged_in():
        print("not logged in")
        return redirect(url_for('login'))
    
    # Check if user needs to select a character
    if 'dm' not in user_role():
        user_entities = entities_controlled_by(session['username'])
        if not user_entities:
            return redirect(url_for('character_selection'))
        
        pov_entity = current_game.get_pov_entity_for_user(session['username'])
        if not pov_entity:
            current_game.set_pov_entity_for_user(session['username'], user_entities[0])

    battle_map = current_game.get_map_for_user(session['username'])
    battle = current_game.get_current_battle()
    available_maps = current_game.get_available_maps()

    background = current_game.get_background_image_for_user(session['username'])
    renderer = JsonRenderer(battle_map, battle, padding=MAP_PADDING, logger=logger)

    my_2d_array = [renderer.render(entity_pov=pov_entities())]
    map_width, map_height = battle_map.size
    left_offset_px, top_offset_px = battle_map.image_offset_px

    tiles_dimension_height = map_height * TILE_PX
    tiles_dimension_width = map_width * TILE_PX
    messages = output_logger.get_all_logs()

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

    current_pov = [entity.entity_uid for entity in pov_entities()]
    return render_template('index.html', tiles=my_2d_array, tile_size_px=TILE_PX,
                           background_path=f"assets/{background}",
                           background_width=tiles_dimension_width,
                           messages=messages,
                           current_map=battle_map.name,
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
                           current_pov=current_pov[0] if current_pov else None,
                           game_session=current_game.game_session,
                           username=session['username'], role=user_role(),
                           DEFAULT_NPC_CONTROLLER=current_game.npc_controller)
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
    return jsonify(background=f"assets/{background}",
                   name=map_name,
                   image_offset_px=battle_map.image_offset_px,
                   height=tiles_dimension_height,
                   width=tiles_dimension_width)

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
    logs = output_logger.get_all_logs()
    response =[{'message': log} for log in logs]
    return jsonify(combat_log=response)

@app.route('/combat-log', methods=['GET'])
def get_combat_log():
    global current_game
    battle = current_game.get_current_battle()
    logs = output_logger.get_all_logs()
    return render_template('combat-log.html', combat_log=logs,
                           username=session['username'], role=user_role())

@app.route('/path', methods=['GET'])
def compute_path():
    global current_game
    battle_map = current_game.get_map_for_user(session['username'])
    print(battle_map.name)
    battle = current_game.get_current_battle()

    source = {
        'x': request.args.get('from[x]'),
        'y': request.args.get('from[y]')
    }
    destination = {
        'x': request.args.get('to[x]'),
        'y': request.args.get('to[y]')
    }

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
    if battle:
        available_movement = entity.available_movement(battle)
    else:
        available_movement = None
    path = PathCompute(battle, battle_map, entity).compute_path(int(source['x']),
                                                                int(source['y']),
                                                                int(destination['x']),
                                                                int(destination['y']),
                                                                accumulated_path=accumulated_path,
                                                                available_movement_cost=available_movement)
    if accumulated_path:
        accumulated_path.extend(path[1:])
    else:
        accumulated_path = path

    cost = battle_map.movement_cost(entity, accumulated_path)
    placeable = battle_map.placeable(entity, int(destination['x']), int(destination['y']), battle, False)

    # Get terrain information for each tile in the path
    terrain_info = []
    if path:
        for x, y in path:
            is_difficult = battle_map.difficult_terrain(entity, x, y, battle)
            terrain_info.append({
                'x': x,
                'y': y,
                'difficult': is_difficult
            })

    path_data = {
        "path": path,
        "cost": cost.to_dict(),
        "placeable": placeable,
        "terrain_info": terrain_info
    }
    return jsonify(path_data)


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
ALLOWED_PREFIXES = ['/favicon.ico', '/static/assets', '/assets/']

@app.before_request
def require_login():
    path = request.path
    if not logged_in() and (path not in ALLOWED_PATHS and not any(path.startswith(prefix) for prefix in ALLOWED_PREFIXES)):
        return redirect(url_for('login'))



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

        print(request.json['battle_turn_order'])
        for param_item in request.json['battle_turn_order']:
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
        output_logger.log("Battle started.")
        battle.start()
    else:
        print("skipping default battle start")
    current_game.execute_game_loop()
    return jsonify(status='ok')


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
    # Use the lock to make the operation atomic
    with current_game.game_state_lock:
        battle = current_game.get_current_battle()
        current_game.game_loop()

        current_turn = battle.current_turn()
    socketio.emit('message', { 'type': 'initiative', 'message': { 'index': battle.current_turn_index} })
    socketio.emit('message', { 'type': 'move', 'message': {'id': current_turn.entity_uid, 'animation_log' : battle.get_animation_logs() }})
    battle.clear_animation_logs()
    socketio.emit('message', { 'type': 'turn', 'message': {}})

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
        # Use the lock to make the operation atomic
        with current_game.game_state_lock:
            current_turn = battle.current_turn()
            if current_game.waiting_for_user_input():
                current_game.set_waiting_for_user_input(False)
                current_turn.resolve_trigger('end_of_turn')
                battle.end_turn()
                battle.next_turn()
                if battle.battle_ends():
                    current_game.end_current_battle()

            current_game.game_loop()
            socketio.emit('message', { 'type': 'initiative','message': {'index': battle.current_turn_index}})
            socketio.emit('message', { 'type': 'move', 'message': {'id': current_turn.entity_uid,
                                                                'animation_log' : battle.get_animation_logs() }})
            socketio.emit('message', { 'type': 'turn', 'message': {}})
            battle.clear_animation_logs()

    # with open('save.yml','w+') as f:
    #     f.write(yaml.dump(battle_map.to_dict()))
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
        # Use session.load_npcs() to get actual NPC instances with full data
        npcs = game_session.load_npcs()
        
        # Convert to list and sort alphabetically by label
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
        
        # Sort alphabetically by name
        npc_list.sort(key=lambda x: x['name'].lower())
        
        return jsonify(npcs=npc_list)
        
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
        # Load all objects from the objects.yml file
        all_objects = game_session.load_yaml_file('items', 'objects')
        
        # Convert to list and filter placeable objects
        object_list = []
        for object_id, object_data in all_objects.items():
            # Get token image, fallback to object id + .png
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
        
        # Sort alphabetically by name
        object_list.sort(key=lambda x: x['name'])
        
        return jsonify(objects=object_list)
        
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
    _pov_entities = pov_entities()  # Use the same function as the main index route
    
    # Handle POV changes
    if entity and ('dm' in user_role() or entity in entities_controlled_by(session['username'], battle_map)):
        # Set new POV to selected entity
        current_game.set_pov_entity_for_user(session['username'], entity)
        _pov_entities = pov_entities()  # Refresh the list after POV change
    elif is_pov and not entity:
        current_game.set_pov_entity_for_user(session['username'], None)
        pov_entity = None
        _pov_entities = None

    if not 'dm' in user_role() and pov_entity is None and (_pov_entities is None or len(_pov_entities) == 0):
        user_entities = entities_controlled_by(session['username'], battle_map)
        _pov_entities = user_entities if user_entities else []

    logger.info(f"entity: {entity}, pov_entity: {pov_entity}, _pov_entities: {_pov_entities}")
    my_2d_array = [renderer.render(entity_pov=_pov_entities)]
    return render_template('map.html', 
                         pov_entity=pov_entity, 
                         tiles=my_2d_array, 
                         tile_size_px=TILE_PX, 
                         random=random, 
                         is_setup=(request.args.get('is_setup') == 'true'),
                         current_map_name=battle_map.name)

@app.route('/actions', methods=['GET'])
def get_actions():
    global current_game
    current_user = session['username']
    battle_map = current_game.get_map_for_user(current_user)
    battle = current_game.get_current_battle()

    id = request.args.get('id')
    if id is None:
        return jsonify(error="No entity id provided"), 400

    entity = battle_map.entity_by_uid(id)
    if entity:
        if 'dm' in user_role() or current_user in entity_owners(entity):
            available_actions = entity.available_actions(session, battle, auto_target=False, map=battle_map, interact_only=True, admin_actions='dm' in user_role())
            # Create entity map for looking up target entities
            entity_map = battle_map.entities
            return render_template('actions.html', entity=entity, battle=battle, session=game_session, map=battle_map, available_actions=available_actions, entity_map=entity_map)
        else:
            return jsonify(error="Forbidden"), 403
    object_ = battle_map.object_by_uid(id)

    if object_:
        available_actions = object_.available_actions(session, battle, auto_target=False, map=battle_map, interact_only=True, admin_actions=True)
        # Create entity map for looking up target entities
        entity_map = battle_map.entities
        return render_template('actions.html', entity=object_, battle=battle, session=game_session, map=battle_map, available_actions=available_actions, entity_map=entity_map)

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
    else:
        raise ValueError(f"Unknown action type {action_type}")

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
            else:
                raise ValueError(f"Unknown action type {build_map['param'][0]['type']}")

        action = build_map

        if isinstance(action, AttackSpell):
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

        current_game.ai_loop()
        continue_game()
    except AsyncReactionHandler as e:
        for _, entity, valid_actions in e.resolve():
            valid_actions_str = [[str(action.uid), str(action), action] for action in valid_actions]
            current_game.waiting_for_reaction = [entity, e, e.resolve(), valid_actions_str]
        socketio.emit('message', {'type': 'reaction', 'message': {'id': entity.entity_uid, 'reaction': e.reaction_type}})
    except ManualControl:
        logger.info("waiting for user to end turn.")
        current_game.set_waiting_for_user_input(True)

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
    output_logger.log(f"{entity.name} rolled a {roll_result}={roll_result.result()} for {description}")
  
    return jsonify(roll_result=roll_result.result(), roll_explaination=str(roll_result))

@app.route('/switch_pov', methods=['POST'])
def switch_pov():
    global current_game
    battle_map = current_game.get_map_for_user(session['username'])
    entity_id = request.form['entity_uid']
    entity = current_game.get_entity_by_uid(entity_id)
    entity_battle_map = current_game.get_map_for_entity(entity)
    current_game.set_pov_entity_for_user(session['username'], entity)
    if battle_map != entity_battle_map:
        current_game.switch_map_for_user(session['username'], entity_battle_map.name)
        background = current_game.get_background_image_for_user(session['username'])
        map_width, map_height = entity_battle_map.size
        tiles_dimension_height = map_height * TILE_PX
        tiles_dimension_width = map_width * TILE_PX
        return jsonify(background=f"assets/{background}",
                    name=entity_battle_map.name,
                    image_offset_px=entity_battle_map.image_offset_px,
                    height=tiles_dimension_height,
                    width=tiles_dimension_width)

    return jsonify(status='ok', pov_entity=entity_id)

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

    output_logger.log(f"{entity.name} read {item.get('label', item['name'])}: {letter_content}")

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
    battle_map = current_game.get_map_for_entity(entity)
    pov_entities = entities_controlled_by(session['username'])
    action_info = {}
    action_hash = None
    target_coords = action_request.get('target', None)
    target = None

    if target_coords:
        mode = action_request.get('mode', None)
        if mode == 'cone' or mode == 'point_target':
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
                targets = battle_map.entities_at(int(target_coords['x']), int(target_coords['y']))
                if len(targets) == 1:
                    target = targets[0]
                elif len(targets) == 0:
                    target = [target_coords['x'], target_coords['y']]
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
                # store jump indices for backend computation if provided
                try:
                    if isinstance(manual_jump, list) and len(manual_jump) == 2:
                        # indices are inclusive of path indexes
                        start_i, end_i = int(manual_jump[0]), int(manual_jump[1])
                        if 0 <= start_i <= end_i < len(move_path):
                            action.jump_index = list(range(start_i, end_i + 1))
                    elif isinstance(manual_jump, list):
                        # already a list of indices
                        action.jump_index = [int(i) for i in manual_jump if 0 <= int(i) < len(move_path)]
                except Exception:
                    # ignore malformed manual_jump to remain backwards compatible
                    pass
                if battle:
                    return jsonify(current_game.commit_and_update(session['username'], action, pov_entities))
                else:
                    last_coords = move_path[-1]
                    if battle_map.placeable(entity, last_coords[0], last_coords[1]):

                        current_game.commit_and_update(session['username'], action, pov_entities)
                        if battle:
                            socketio.emit('message', {'type': 'move', 'message': {'from': move_path[0], 'to': move_path[-1],
                                                                                'animation_log': battle.get_animation_logs()}})
                            battle.clear_animation_logs()
                        else:
                            animation_log = []
                            animation_log.append((entity.entity_uid, move_path, None))
                            socketio.emit('message', {'type': 'move', 'message': {'from': move_path[0], 'to': move_path[-1], 'animation_log': animation_log}})
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
            action = action_class(game_session, entity, opts.get('action_type'))
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
                    elif param_details['type'] == 'select_target':
                        valid_targets = battle_map.valid_targets_for(entity, param_details)
                        valid_targets = {target.entity_uid: battle_map.entity_or_object_pos(target) for target in valid_targets}
                        if target:
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
        for battle, entity, valid_actions in e.resolve():
            valid_actions_str = [[str(action.uid), str(action), action] for action in valid_actions]
            current_game.set_waiting_for_reaction_input([entity, e, e.resolve(), valid_actions_str])
        socketio.emit('message', {'type': 'reaction', 'message': {'id': entity.entity_uid, 'reaction': e.reaction_type}})
        return jsonify(status='ok')


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
    # Fetch the necessary information based on the info_id
    entity = battle_map.entity_by_uid(info_id)
    if entity is None:
        entity = battle_map.object_by_uid(info_id)
    return render_template('info.html.jinja', entity=entity, session=game_session, battle=battle, restricted=False, role=user_role())

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
    if battle:
        default_group = 'a' if isinstance(entity, PlayerCharacter) else 'b'
        socketio.emit('message', {'type': 'initiative', 'message': {'index': battle.current_turn_index}})
        battle.add(entity, default_group)
        return ""
    else:
        is_pc = isinstance(entity, PlayerCharacter)
        default_controller = 'manual' if is_pc else DEFAULT_NPC_CONTROLLER
        return render_template('add.html', entity=entity, is_pc=is_pc, default_controller=default_controller)

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

@app.route("/dialog_history", methods=["GET"])
def dialog_history():
    global current_game
    entity_id = request.args.get('entity_id')
    entity_pov_id = request.args.get('entity_pov', None)
    if not entity_id:
        return jsonify({'error': 'Entity ID is required'}), 400
    entity = current_game.get_entity_by_uid(entity_id)
    if not entity:
        return jsonify({'error': 'Entity not found'}), 404

    
    if entity_pov_id:
        entity_pov = current_game.get_entity_by_uid(entity_pov_id)
        history = entity.conversation_history(entity_pov)
        return jsonify({
            'success': True,
            'history': history,
            'entity_id': entity_id,
            'entity_name': entity.label(),
            'entity_pov': entity_pov.entity_uid
        })
    else:
        return jsonify({
            'success': True,
            'history': [],
            'entity_id': entity_id,
            'entity_name': entity.label(),
            'entity_pov': False
        })

@app.route('/talk', methods=['POST'])
def talk():
    global llm_conversation_handler, current_game
    global CONVERSATION_SYSTEM_PROMPT
    data = request.get_json()
    entity_id = data.get('entity_id')
    message = data.get('message')
    language = data.get('language')
    primary_targets = data.get('targets', [])
    distance_ft = data.get('distance_ft', 30)
    if not entity_id or not message:
        return jsonify({'error': 'Entity ID and message are required'}), 400

    entity = current_game.get_entity_by_uid(entity_id)
    if not entity:
        return jsonify({'error': 'Entity not found'}), 404

    if isinstance(entity, PlayerCharacter):
        current_game.increment_game_time(entity)

    # Create conversation message
    # Add message to entity's conversation history
    entity_targets = []
    if len(primary_targets) > 0:
        for _entity_uid in primary_targets:
            entity_targets.append(game_session.entity_by_uid(_entity_uid))
    processed_conversations = entity.send_conversation(message, distance_ft=distance_ft, targets=entity_targets, language=language)
    current_sids = current_game.username_to_sid.get(session['username'], [])
    for sid in current_sids:
        socketio.emit('message', {'type': 'conversation', 'message': {'entity_id': entity_id, 'message': message}}, to=sid)

    for receiver, message, directed_to in processed_conversations:
        if receiver.entity_uid == entity_id:
            continue
        if receiver.is_npc() and receiver.dialog:
            attributes = receiver.ability_scores
            attributes_str = "\n".join([f"{k}: {v}" for k, v in attributes.items()])
            system_prompt = CONVERSATION_SYSTEM_PROMPT.format(backstory=receiver.backstory(),
                                                              name=receiver.label(),
                                                              attributes=attributes_str,
                                                              alignment=receiver.alignment().replace("_", " "),
                                                              languages=", ".join(receiver.languages()))
            llm_conversation_handler.create_conversation(receiver.entity_uid, system_prompt)
            llm_conversation_handler.update_conversation_history(receiver.entity_uid, receiver.conversation_buffer)

            if receiver in directed_to:
                logger.info(f"generating response for {receiver.label()}")
                response = llm_conversation_handler.generate_response(receiver.entity_uid)
                logger.info(f"response for {receiver.label()}: {response}")
                if response:
                    # Use EntityRAGHandler to process the response
                    language, response = entity_rag_handler.process_entity_response(
                        response, receiver, entity, llm_conversation_handler
                    )
                    receiver.send_conversation(response, targets=[entity], language=language)
                    owners = entity_owners(entity)
                    for owner in owners:
                        sids = current_game.username_to_sid.get(owner, [])
                        for sid in sids:
                            socketio.emit('message', {'type': 'conversation', 'message': {'entity_id': receiver.entity_uid, 'message': response, 'targets': [entity.entity_uid]}}, to=sid)

    return jsonify({'success': True})

@app.route('/nearby_entities')
def nearby_entities():
    entity_id = request.args.get('entity_id')
    range_ft = int(request.args.get('range', 30))  # Default 30ft earshot range

    if not entity_id:
        return jsonify({'error': 'Entity ID is required'}), 400

    entity = current_game.get_entity_by_uid(entity_id)
    if not entity:
        return jsonify({'error': 'Entity not found'}), 404

    # Use EntityRAGHandler to get nearby entities
    response = entity_rag_handler.get_nearby_entities(entity, range_ft)

    return jsonify({
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
        output_logger.log(f"DM updated {entity.label()}'s {resource_type.replace('_', ' ')} from {current_value} to {new_value}")
        
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
        output_logger.log(f"DM updated {entity.label()}'s {character_class} level {level} spell slots from {current_value} to {new_value}")
        
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
        output_logger.log(f"DM moved {entity.label()} from ({current_x}, {current_y}) to ({target_x}, {target_y})")
        
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

@app.route('/ai/chat', methods=['POST'])
def ai_chat():
    """Send a message to the AI and get a response."""
    if 'dm' not in user_role():
        return jsonify({'success': False, 'error': 'DM access required'}), 403
    
    try:
        message = request.form.get('message')
        
        if not message:
            return jsonify({'success': False, 'error': 'Message is required'})
        
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
        print("Context:", context)
        # Send message to AI with RAG context
        response = llm_handler.send_message(message, context)
        
        return jsonify({'success': True, 'response': response})
        
    except Exception as e:
        pdb.set_trace()
        print(f"Error in AI chat: {e}")
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
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Error clearing AI history: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/ai/history', methods=['GET'])
def ai_get_history():
    """Get the AI conversation history."""
    if 'dm' not in user_role():
        return jsonify({'success': False, 'error': 'DM access required'}), 403
    
    try:
        history = llm_handler.get_conversation_history()
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
