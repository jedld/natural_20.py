from flask import Flask, request, jsonify, session, redirect, url_for, render_template, send_file
from flask_socketio import SocketIO, emit
from flask_session import Session
from flask import send_from_directory
from flask_cors import CORS  # Add CORS support
import json
import os
import click
from PIL import Image
import logging
import importlib
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

from natural20.utils.movement import Movement
from natural20.generic_controller import GenericController
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
from webapp.llm_conversation_handler import LLMConversationHandler
import threading

app = Flask(__name__, static_folder='static', static_url_path='/')

# Determine if we're running in AWS or locally
is_aws = os.environ.get('AWS_ENVIRONMENT', 'false').lower() == 'true'
is_production = os.environ.get('FLASK_ENV', 'development') == 'production'

# Configure CORS for the Flask app based on environment
if is_aws or is_production:
    # In AWS/production, allow the ALB domain and any subdomains
    allowed_origins = [
        "http://natural20-alb-1402295348.us-east-1.elb.amazonaws.com",
        "https://natural20-alb-1402295348.us-east-1.elb.amazonaws.com",
        "*"  # Fallback to allow all origins in production
    ]
else:
    # In local development, allow localhost origins
    allowed_origins = ["http://localhost:5000", "http://127.0.0.1:5000", "http://localhost:5001", "http://127.0.0.1:5001"]

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
    message_queue=None  # Disable message queue since we're using a single worker
)
Session(app)

LEVEL = os.getenv('TEMPLATE_DIR', "../templates")

# Load level settings from JSON file
with open(os.path.join(LEVEL, 'index.json')) as f:
    index_data = json.load(f)

TITLE = index_data["title"]
TILE_PX = int(index_data["tile_size"])



LOGIN_BACKGROUND = index_data["login_background"]
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
game_session = GameSession.Session(LEVEL, event_manager=event_manager, conversation_handlers={'llm': LLMConversationHandler})
game_session.render_for_text = False # render for text is disabled since we are using a web renderer
current_soundtrack = None

logger = logging.getLogger('werkzeug')
logger.setLevel(logging.INFO)

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

i18n.set('locale', 'en')

# initialize all extensiond
for extension in EXTENSIONS:
    extension.init(app, current_game, game_session)

# Initialize the LLM conversation handler
# Initialize the LLM with API key from environment variable
# @app.before_first_request
# def initialize_llm():
#     api_key = os.environ.get('OPENAI_API_KEY')
#     if api_key:
#         llm_conversation_handler.initialize(api_key=api_key)
#         print("LLM conversation handler initialized successfully")
#     else:
#         print("OPENAI_API_KEY not found in environment variables. LLM conversations will not be available.")

def logged_in():
    return session.get('username') is not None

def user_role():
    login_info = next((login for login in LOGINS if login["name"].lower() == session['username']), None)
    return login_info["role"] if login_info else []

# Add a global lock for game state operations
game_state_lock = threading.Lock()

def check_and_notify_map_change(pov_map, pov_entity):
    global logger, current_game, username_to_sid

    # Use the lock to make the operation atomic
    with game_state_lock:
        new_battle_map = current_game.get_map_for_entity(pov_entity)
        if pov_map is None:
            return
        if new_battle_map is None:
            return
        logger.info(f"pov_map: {pov_map.name} new_battle_map: {new_battle_map.name}")

        if new_battle_map != pov_map:
            current_game.switch_map_for_user(session['username'], new_battle_map.name)
            sids = username_to_sid.get(session['username'], [])
            for sid in sids:
                socketio.emit('message', {'type': 'switch_map', 'message': {'map': new_battle_map.name}}, to=sid)

def commit_and_update(action):
    global current_game, logger

    # Use the lock to make the operation atomic
    with game_state_lock:
        battle = current_game.get_current_battle()

        pov_entity = current_game.get_pov_entity_for_user(session['username'])

        if not pov_entity:
            pov_entities = entities_controlled_by(session['username'])
            pov_entity = pov_entities[0] if pov_entities else None

        pov_map = current_game.get_map_for_entity(pov_entity)

        if battle:
            battle.action(action)
            battle.commit(action)
            if battle.battle_ends():
                current_game.end_current_battle()
        else:
            action_battle_map = current_game.get_map_for_entity(action.source)
            action.resolve(session, action_battle_map)

            for item in action.result:
                for klass in Action.__subclasses__():
                    klass.apply(None, item, session=game_session)

        # did the map change for the current pov?
        check_and_notify_map_change(pov_map, pov_entity)

        if battle:
            socketio.emit('message', {'type': 'move', 'message': {'animation_log': battle.get_animation_logs()}})
            battle.clear_animation_logs()
        else:
            current_game.loop_environment()
            socketio.emit('message', {'type': 'move', 'message': {'animation_log': []}})
        socketio.emit('message', {'type': 'turn', 'message': {}})

        if AUTOSAVE:
            print("autosave")
            current_game.save_game()
        return True

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
            if isinstance(thing, Entity):
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
   
@app.route('/assets/items/<filename>')
def serve_item_image(filename):
    if not filename.endswith('.png'):
        filename = f"{filename}.png"

    if os.path.exists(os.path.join("static", "assets", "items", filename)):
        return send_file(os.path.join("static", "assets", "items", filename))
    else:
        items_directory = os.path.join(game_session.root_path, "assets", "items")
        return send_from_directory(items_directory, filename)

@app.route('/assets/<asset_name>')
def get_asset(asset_name):
    file_path = os.path.join(LEVEL, "assets", asset_name)
    if os.path.exists(file_path):
        return send_file(file_path)
    else:
        resolved_path = os.path.join(game_session.root_path, "assets")
        if os.path.exists(resolved_path):
            return send_from_directory(resolved_path, asset_name)

        return jsonify(error="File not found"), 404

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].lower()
        password = request.form['password']

        login_info = next((login for login in LOGINS if login["name"].lower() == username), None)
        if login_info and login_info["password"] == password:
            session['username'] = username
            return jsonify(status='ok')
        return jsonify(error="Invalid Login Credentials")

    return render_template('login.html', title=TITLE, background=LOGIN_BACKGROUND)

@app.route('/')
def index():
    global current_game
    battle_map = current_game.get_map_for_user(session['username'])
    battle = current_game.get_current_battle()
    available_maps = current_game.get_available_maps()

    if not logged_in():
        print("not logged in")
        return redirect(url_for('login'))
   

    background = current_game.get_background_image_for_user(session['username'])
    renderer = JsonRenderer(battle_map, battle, padding=MAP_PADDING)

    if 'dm' in user_role():
        pov_entities = None
    else:
        pov_entities = entities_controlled_by(session['username'])

    my_2d_array = [renderer.render(entity_pov=pov_entities)]
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
                           pov_entities=entities_controlled_by(session['username']),
                           username=session['username'], role=user_role())
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

    path_data = {
        "path": path,
        "cost": cost.to_dict(),
        "placeable": placeable
    }
    return jsonify(path_data)


# Configure paths that don't require login
ALLOWED_PATHS = ['/login', '/health']
ALLOWED_PREFIXES = ['/favicon.ico', '/static/assets', '/assets/']

@app.before_request
def require_login():
    path = request.path
    if not logged_in() and (path not in ALLOWED_PATHS and not any(path.startswith(prefix) for prefix in ALLOWED_PREFIXES)):
        return redirect(url_for('login'))

username_to_sid = {}

@socketio.on('register')
def handle_connect(data):
    global current_game, first_connect, username_to_sid
    username = data.get('username')
    ws = request.sid
    if ws:
        sids = username_to_sid.get(username, [])
        sids.append(ws)
        username_to_sid[username] = sids
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
    global current_game, username_to_sid
    ws = request.sid
    username = session.get('username')
    if ws and username:
        sids = username_to_sid.get(username, [])
        if ws in sids:  # Only remove if the sid exists in the list
            sids.remove(ws)
            username_to_sid[username] = sids
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
    pov_entities = entities_controlled_by(username)
    current_pov_entity = current_game.get_pov_entity_for_user(username)
    return render_template('floating_portraits.html', pov_entities=pov_entities, current_pov_entity=current_pov_entity)

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

            if param_item['controller'] == 'ai':
                controller = GenericController(game_session)
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
    # Use the lock to make the operation atomic
    with game_state_lock:
        battle.end_turn()
        battle.next_turn()
        try:
            continue_game()
            return jsonify(status='ok')
        except AsyncReactionHandler as e:
            for _, entity, valid_actions in e.resolve():
                valid_actions_str = [[str(action.uid), str(action), action] for action in valid_actions]
                current_game.waiting_for_reaction = [entity, e, e.resolve(), valid_actions_str]
            socketio.emit('message', {'type': 'reaction', 'message': {'id': entity.entity_uid, 'reaction': e.reaction_type}})
            return jsonify(status='ok')


def continue_game():
    # Use the lock to make the operation atomic
    with game_state_lock:
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
        with game_state_lock:
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

@app.route('/update')
def update():
    global current_game

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

    # Handle POV changes
    if entity and ('dm' in user_role() or entity in entities_controlled_by(session['username'], battle_map)):
        # Set new POV to selected entity
        current_game.set_pov_entity_for_user(session['username'], entity)
        pov_entities = [entity]
    elif is_pov and not entity:
        current_game.set_pov_entity_for_user(session['username'], None)
        pov_entity = None
        pov_entities = None

    if not pov_entity and 'dm' not in user_role():
        # Default to entities controlled by the user
        pov_entities = entities_controlled_by(session['username'], battle_map)
    else:
        # Use existing POV
        pov_entities = [pov_entity] if pov_entity else None

    my_2d_array = [renderer.render(entity_pov=pov_entities)]
    return render_template('map.html', tiles=my_2d_array, tile_size_px=TILE_PX, random=random, is_setup=(request.args.get('is_setup') == 'true'))

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
            return render_template('actions.html', entity=entity, battle=battle, session=game_session, map=battle_map, available_actions=available_actions)
        else:
            return jsonify(error="Forbidden"), 403
    object_ = battle_map.object_by_uid(id)

    if object_:
        available_actions = object_.available_actions(session, battle, auto_target=False, map=battle_map, interact_only=True, admin_actions=True)
        return render_template('actions.html', entity=object_, battle=battle, session=game_session, map=battle_map, available_actions=available_actions)

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
        valid_target = True
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

        while not isinstance(build_map, Action):
            if build_map['param'][0]['type'] == 'select_choice':
                build_map = build_map['next'](choice)
            elif build_map['param'][0]['type'] == 'select_empty_space':
                build_map = build_map['next'](target)
            elif build_map['param'][0]['type'] == 'select_target':
                build_map = build_map['next'](target)
            else:
                raise ValueError(f"Unknown action type {build_map['param'][0]['type']}")

        action = build_map

        if isinstance(action, AttackSpell):
            adv_mod, adv_info, attack_mod = action.compute_advantage_info(battle)
            valid_target = True

            if battle:
                valid_targets = battle.valid_targets_for(entity, action)
                valid_target = target in valid_targets
            return jsonify(valid_target=valid_target, adv_mod=adv_mod, adv_info=adv_info, attack_mod=attack_mod)
        else:
            action.validate(battle_map, target)
            if len(action.errors)  > 0:
                return jsonify(valid_target=False, errors=action.errors)
            return jsonify(valid_target=True, errors=action.errors)
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
        with game_state_lock:
            battle.action(handler.action)
            battle.commit(handler.action)
            socketio.emit('message', {'type': 'dismiss_reaction', 'message': {}})
            current_game.ai_loop()
            continue_game()
    except AsyncReactionHandler as e:
        for battle, entity, valid_actions in e.resolve():
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
                    height=tiles_dimension_height,
                    width=tiles_dimension_width)

    return jsonify(status='ok')

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

    output_logger.log(f"{entity.name} read {item['label']}: {letter_content}")

    # process raw text so that linebreaks are preserved when rendering on the web page
    letter_content = letter_content.replace('\n', '<br>')

    return render_template('letter.html', letter_label=item['label'], letter_content=letter_content)

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

    action_info = {}
    action_hash = None
    target_coords = action_request.get('target', None)
    target = None

    if target_coords:
        if isinstance(target_coords, list):
            target = []
            for entity_uids in target_coords:
                target.append(battle_map.entity_by_uid(entity_uids))
        else:
            target = battle_map.entity_at(int(target_coords['x']), int(target_coords['y']))
            if not target:
                target = [target_coords['x'], target_coords['y']]

    try:
        if action_type == 'MoveAction':
            path = action_request.get('path', None)
            action = MoveAction(game_session, entity, 'move')
            if path:
                move_path = sorted([(int(index), [int(coord[0]), int(coord[1])]) for index, coord in enumerate(path)])
                move_path = [coords for _, coords in move_path]
                action.move_path = move_path
                if battle:
                    return jsonify(commit_and_update(action))
                else:
                    last_coords = move_path[-1]
                    if battle_map.placeable(entity, last_coords[0], last_coords[1]):
                        commit_and_update(action)
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

            valid_targets = battle_map.valid_targets_for(entity, action)
            valid_targets = { target.entity_uid: battle_map.entity_or_object_pos(target) for target in valid_targets}

            if action.npc_action:
                weapon_details = action.npc_action
            else:
                weapon_details = game_session.load_weapon(action.using)

            if target_coords:
                target = battle_map.entity_at(int(target_coords['x']), int(target_coords['y']))
                if valid_targets.get(target.entity_uid):
                    action.target = target
                    return jsonify(commit_and_update(action))
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
                            return jsonify(commit_and_update(interact))
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

            commit_and_update(action)
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
    info_id = request.args.get('id')
    # Fetch the necessary information based on the info_id
    entity = battle_map.entity_by_uid(info_id)
    if entity is None:
        entity = battle_map.object_by_uid(info_id)
    return render_template('info.html.jinja', entity=entity, session=game_session, restricted=False)

@app.route('/logout', methods=['POST'])
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
            return render_template('turn.jinja', battle=battle, username=session['username'])
        else:
            return render_template('turn.jinja', battle=battle, username=session['username'], readonly=True)
    else:
        return jsonify(error="No battle in progress"), 400


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
        return render_template('add.html', entity=entity, is_pc=isinstance(entity, PlayerCharacter))

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

@app.route('/talk', methods=['POST'])
def talk():
    data = request.get_json()
    entity_id = data.get('entity_id')
    message = data.get('message')
    language = data.get('language')
    targets = data.get('targets', [])
    distance_ft = data.get('distance_ft', 30)
    if not entity_id or not message:
        return jsonify({'error': 'Entity ID and message are required'}), 400

    entity = current_game.get_entity_by_uid(entity_id)
    if not entity:
        return jsonify({'error': 'Entity not found'}), 404
    # Create conversation message
    # Add message to entity's conversation history
    entity_targets = []
    if len(targets) > 0:
        for _entity_uid in targets:
            entity_targets.append(game_session.entity_by_uid(_entity_uid))
    processed_conversations = entity.send_conversation(message, distance_ft=distance_ft, targets=entity_targets, language=language)
    current_sids = username_to_sid.get(session['username'], [])
    for sid in current_sids:
        socketio.emit('message', {'type': 'conversation', 'message': {'entity_id': entity_id, 'message': message}}, to=sid)

    for target, message in processed_conversations:
        # # Trigger LLM response for NPCs if LLM is initialized
        # if llm_conversation_handler.initialized and target.npc():
        #     llm_conversation_handler.handle_conversation(target, entity, message, language)
            
        owners = entity_owners(target)
        for owner in owners:
            sids = username_to_sid.get(owner, [])
            for sid in sids:
                socketio.emit('message', {'type': 'conversation', 'message': {'entity_id': entity_id, 'message': message}}, to=sid)

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

    entity_map = current_game.get_map_for_entity(entity)    # Get all entities on the same map
    map_entities = entity_map.entities_in_range(entity, range_ft)
    nearby = []

    for other_entity in map_entities:
        if other_entity == entity:
            continue
        if not other_entity.conversable():
            continue

        line_of_sight = entity_map.can_see(entity, other_entity)
        if not line_of_sight:
            continue

        nearby.append({
            'id': other_entity.entity_uid,
            'name': other_entity.label(),
            'distance': entity_map.distance(entity, other_entity) * entity_map.feet_per_grid
        })

    return jsonify({
        'entities': nearby
    })

if __name__ == '__main__':
    socketio.run(app, debug=False, host='0.0.0.0', port=5001, allow_unsafe_werkzeug=True)
