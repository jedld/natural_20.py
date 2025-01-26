from flask import Flask, request, jsonify, session, redirect, url_for, render_template, send_file
from flask_socketio import SocketIO, emit
from flask_session import Session
from flask import send_from_directory
import json
import os
import click
from PIL import Image
import logging
import importlib
from natural20.ai.path_compute import PathCompute
from natural20.web.json_renderer import JsonRenderer
from webapp.controller.web_controller import WebController, ManualControl
from natural20.actions.attack_action import AttackAction, TwoWeaponAttackAction
from natural20.actions.move_action import MoveAction
from natural20.actions.second_wind_action import SecondWindAction
from natural20.actions.disengage_action import DisengageAction, DisengageBonusAction
from natural20.actions.dash import DashAction, DashBonusAction
from natural20.actions.dodge_action import DodgeAction
from natural20.actions.prone_action import ProneAction
from natural20.actions.spell_action import SpellAction
from natural20.actions.stand_action import StandAction
from natural20.actions.drop_concentration_action import DropConcentrationAction
from natural20.actions.action_surge_action import ActionSurgeAction
from natural20.actions.shove_action import ShoveAction
from natural20.actions.hide_action import HideAction, HideBonusAction
from natural20.actions.first_aid_action import FirstAidAction
from natural20.actions.grapple_action import GrappleAction, DropGrappleAction
from natural20.actions.escape_grapple_action import EscapeGrappleAction
from natural20.entity import Entity
from natural20.action import Action
from natural20.battle import Battle
from natural20.map import Map
from natural20.utils.movement import Movement
from natural20.generic_controller import GenericController
import natural20.session as GameSession
from natural20.event_manager import EventManager
from natural20.player_character import PlayerCharacter
from collections import deque
from natural20.utils.action_builder import acquire_targets
import optparse
import pdb
import i18n
import yaml
import time
import uuid

app = Flask(__name__, static_folder='static', static_url_path='/')
app.config['SECRET_KEY'] = 'fe9707b4704da2a96d0fd3cbbb465756e124b8c391c72a27ff32a062110de589'
app.config['SESSION_TYPE'] = 'filesystem'

socketio = SocketIO(app)
Session(app)

LEVEL = os.getenv('TEMPLATE_DIR', "../templates")

# Load level settings from JSON file
with open(os.path.join(LEVEL, 'index.json')) as f:
    index_data = json.load(f)

TITLE = index_data["title"]
TILE_PX = int(index_data["tile_size"])

if 'background' not in index_data:
    # auto determine the background name based on the map name
    BACKGROUND = index_data["map"] + ".png"
else:
    BACKGROUND = index_data["background"]

LOGIN_BACKGROUND = index_data["login_background"]
BATTLEMAP = index_data["map"]
SOUNDTRACKS = index_data["soundtracks"]
LOGINS = index_data["logins"]
CONTROLLERS = index_data["default_controllers"]
EXTENSIONS = []
first_connect = False

if 'extensions' in index_data:
    for extension in index_data['extensions']:
        # load extension and import extension from the extensions folder
        extension_name = extension['name']
        # import extension
        print(f"loading {extension_name}")
        extension_module = importlib.import_module(f"{extension_name}")
        EXTENSIONS.append(extension_module)

sockets = []
controllers = {}

class SocketIOOutputLogger:
    """
    A simple logger that logs to stdout
    """
    def __init__(self):
        self.logging_queue = deque(maxlen=1000)

    def get_all_logs(self):
        return self.logging_queue

    def clear_logs(self):
        self.logging_queue.clear()

    def update(self):
        socketio.emit('message', {'type': 'console', 'messages': self.get_all_logs()})

    def log(self, event_msg):
        # add time to the message
        current_time_str = time.strftime("%Y:%m:%d.%H:%M:%S", time.localtime())
        event_msg = f"{current_time_str}: {event_msg}"

        self.logging_queue.append(event_msg)
        socketio.emit('message', {'type': 'console', 'message': event_msg})

output_logger = SocketIOOutputLogger()
output_logger.log("Server started")

event_manager = EventManager(output_logger=output_logger)
event_manager.standard_cli()
game_session = GameSession.Session(LEVEL, event_manager=event_manager)


class GameManagement:
    def __init__(self, game_session, map_location):
        self.map_location = map_location
        self.game_session = game_session
        if os.path.exists('save.yml'):
            with open('save.yml','r') as f:
                map_dict = yaml.safe_load(f)
                self.battle_map = Map.from_dict(game_session, map_dict)
        else:
            self.battle_map = Map(game_session, BATTLEMAP)
        self.battle = None
        self.trigger_handlers = {}
        self.callbacks = {}

    def reset(self):
        self.battle_map = Map(self.game_session, self.map_location)
        self.battle = None
        socketio.emit('message', {'type': 'reset', 'message': {}})

    def set_current_battle_map(self, battle_map):
        self.battle_map = battle_map

    def set_current_battle(self, battle):
        self.battle = battle

    def get_current_battle(self) -> Battle:
        return self.battle

    def get_current_battle_map(self) -> Map:
        return self.battle_map

    def register_event_handler(self, event, handler):
        """
        Register an event handler
        """
        if event not in self.trigger_handlers:
            self.trigger_handlers[event] = []
        self.trigger_handlers[event].append(handler)

    def trigger_event(self, event):
        """
        Trigger an event
        """
        results = []
        if event in self.trigger_handlers:
            for handlers in self.trigger_handlers[event]:
                results.append(handlers(self, self.game_session))
        if len(results) == 0:
            return False
        return any(results)

    def prompt(self, message, callback=None):
        callback_id = uuid.uuid4().hex
        self.callbacks[callback_id] = callback
        socketio.emit('message', {'type': 'prompt', 'message': message, 'callback': callback_id})

    def push_animation(self):
        socketio.emit('message', {'type': 'move', 'message': {'animation_log': self.battle.get_animation_logs()}})
        self.battle.clear_animation_logs()

    def execute_game_loop(self):
        output_logger.log("Battle started.")
        game_loop()
        socketio.emit('message',{'type': 'initiative', 'message': {}})

        if self.battle:
            socketio.emit('message', {
                'type': 'move',
                'message': { 'animation_log' : self.battle.get_animation_logs() }
                })
            self.battle.clear_animation_logs()

        socketio.emit('message',{ 'type': 'turn', 'message': {}})

    def refresh_client_map(self):
        width, height = self.battle_map.size
        tiles_dimension_width = width * TILE_PX
        tiles_dimension_height = height * TILE_PX
        map_image_url = f"assets/{ self.battle_map.name + '.png'}"

        socketio.emit('message', {'type': 'map',
                                  'width': tiles_dimension_width,
                                  'height': tiles_dimension_height,
                                  'message': map_image_url})
        socketio.emit('message', {'type': 'initiative', 'message': {}})
        socketio.emit('message', {'type': 'turn', 'message': {}})


current_game = GameManagement(game_session=game_session, map_location=BATTLEMAP)
waiting_for_user = None
current_soundtrack = None
i18n.set('locale', 'en')

# initialize all extensiond
for extension in EXTENSIONS:
    extension.init(app, current_game, game_session)


logger = logging.getLogger('werkzeug')
logger.setLevel(logging.INFO)

# Assuming Natural20 and other dependencies are available in Python, they should be implemented or imported accordingly.
# This is a placeholder import
# from natural20 import EventManager, Session as GameSession, BattleMap, WebJsonRenderer, AiController, WebController, MoveAction, AttackAction

def logged_in():
    return session.get('username') is not None

def user_role():
    login_info = next((login for login in LOGINS if login["name"].lower() == session['username']), None)
    return login_info["role"] if login_info else []

def commit_and_update(action):
    global current_game

    battle = current_game.get_current_battle()
    battle_map = current_game.get_current_battle_map()

    if battle:
        battle.action(action)
        battle.commit(action)
        if battle.battle_ends():
            end_current_battle()
    else:
      action.resolve(session, battle_map)
      events = action.result
      for event in events:
        action.apply(None, event, session=game_session)
    if battle:
        socketio.emit('message', {'type': 'move', 'message': {'animation_log': battle.get_animation_logs()}})
        battle.clear_animation_logs()
    else:
        socketio.emit('message', {'type': 'move', 'message': {'animation_log': []}})
    socketio.emit('message', {'type': 'turn', 'message': {}})


def controller_of(entity_uid, username):
    if username == 'dm':
        return True

    for info in CONTROLLERS:
        if info['entity_uid'] == entity_uid and username in info['controllers']:
            return True

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

    if entity_size =='small':
        transforms.append('scale(0.8)')
    elif entity_size == 'tiny':
        transforms.append('scale(0.5)')

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


def entities_controlled_by(username, map):
    entities = set()
    for info in CONTROLLERS:
        if username in info['controllers']:
            entity_uid = info['entity_uid']
            entity = map.entity_by_uid(entity_uid)
            if entity:
                entities.add(entity)


    return list(entities)

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
    return ""

app.add_template_global(action_flavors, name='action_flavors')

def ability_mod_str(ability_mod):
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
    return f"{qty}{r_str}"
app.add_template_filter(casting_time, name='casting_time')

def entity_owners(entity_uid):
    ctrl_info = next((controller for controller in CONTROLLERS if controller['entity_uid'] == entity_uid), None)
    return [] if not ctrl_info else ctrl_info['controllers']
app.add_template_global(entity_owners, name='entity_owners')

def describe_terrain(tile):
    battle_map = current_game.get_current_battle_map()
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
                    raise ValueError(f"Invalid target {t}")
        else:
            if target not in valid_targets:
                raise ValueError(f"Invalid target {target}")


def process_action_hash(action):
    return action.to_h()

app.add_template_global(process_action_hash, name='process_action_hash')

def game_loop():
    global waiting_for_user, current_game

    battle = current_game.get_current_battle()
    try:
        while True:
            battle.start_turn()
            current_turn = current_game.get_current_battle().current_turn()
            current_turn.reset_turn(battle)

            if battle.battle_ends():
                end_current_battle()
                return


            while current_turn.dead() or current_turn.unconscious():
                current_turn.resolve_trigger('end_of_turn')
                battle.end_turn()
                battle.next_turn()
                current_turn = battle.current_turn()
                battle.start_turn()
                current_turn.reset_turn(battle)

                if battle.battle_ends():
                    end_current_battle()
                    return


            ai_loop()
            current_turn.resolve_trigger('end_of_turn')

            if battle.battle_ends():
                end_current_battle()
                break

            battle.end_turn()
            battle.next_turn()


    except ManualControl:
        logger.info("waiting for user to end turn.")
        waiting_for_user = True

@app.route('/assets/maps/<path:filename>')
def serve_map_image(filename):
    maps_directory = os.path.join(game_session.root_path, "assets", "maps")
    return send_from_directory(maps_directory, filename)

@app.route('/assets/<asset_name>')
def get_asset(asset_name):
    file_path = os.path.join(LEVEL, "assets", asset_name)
    if os.path.exists(file_path):
        return send_file(file_path)
    else:
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
    global current_game, current_soundtrack
    battle_map = current_game.get_current_battle_map()
    battle = current_game.get_current_battle()

    if not logged_in():
        print("not logged in")
        return redirect(url_for('login'))
    if battle_map and battle_map.name:
        background = battle_map.name + ".png"
    else:
        background = BACKGROUND

    file_path = os.path.join(LEVEL, "assets", background)
    image = Image.open(file_path)
    width, height = image.size

    renderer = JsonRenderer(battle_map, battle)

    if 'dm' in user_role():
        pov_entities = None
    else:
        pov_entities = entities_controlled_by(session['username'], battle_map)

    my_2d_array = [renderer.render(entity_pov=pov_entities)]
    map_width, map_height = battle_map.size
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
    return render_template('index.html', tiles=my_2d_array, tile_size_px=TILE_PX,
                           background_path=f"assets/{background}", background_width=tiles_dimension_width,
                           messages=messages,
                           background_height=tiles_dimension_height,
                           battle=battle,
                           entity_ids=entity_ids,
                           background_color=background_color,
                           width_px=width_px,
                           height_px=height_px,
                           soundtrack=current_soundtrack, title=TITLE, username=session['username'], role=user_role())


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
    battle_map = current_game.get_current_battle_map()
    battle = current_game.get_current_battle()

    source = {
        'x': request.args.get('from[x]'),
        'y': request.args.get('from[y]')
    }
    destination = {
        'x': request.args.get('to[x]'),
        'y': request.args.get('to[y]')
    }

    entity = battle_map.entity_at(int(source['x']), int(source['y']))
    if battle:
        available_movement = entity.available_movement(battle)
    else:
        available_movement = None
    path = PathCompute(battle, battle_map, entity).compute_path(int(source['x']),
                                                                int(source['y']),
                                                                int(destination['x']),
                                                                int(destination['y']),
                                                                available_movement_cost=available_movement)
    cost = battle_map.movement_cost(entity, path)
    placeable = battle_map.placeable(entity, int(destination['x']), int(destination['y']), battle, False)

    path_data = {
        "path": path,
        "cost": cost.to_dict(),
        "placeable": placeable
    }
    return jsonify(path_data)

@app.before_request
def require_login():
    if not logged_in() and request.path != '/login' and not request.path.startswith('/static/assets'):
        return redirect(url_for('login'))

@socketio.on('register')
def handle_connect(data):
    global current_game, first_connect
    username = data.get('username')
    ws = request.sid
    web_controller_for_user = controllers.get(username, WebController(game_session, username))
    web_controller_for_user.add_sid(ws)
    controllers[username] = web_controller_for_user

    battle = current_game.get_current_battle()
    if battle:
        for info in CONTROLLERS:
            users = info.get('controllers', [])
            entity_uid = info.get('entity_uid')
            if username in users:
                entity = battle.map.entity_by_uid(entity_uid)
                if entity:
                    web_controller_for_user.add_user(username)
                    battle.set_controller_for(entity, web_controller_for_user)

    if not first_connect:
        first_connect = True
        current_game.trigger_event('on_session_ready')

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
    else:
        emit('error', {'type': 'error', 'message': 'Unknown command!'})

@socketio.on('disconnect')
def handle_disconnect():
    pass

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
        battle = None
        socketio.emit('message', {'type': 'stop', 'message': {}})
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
            entity = battle_map.entity_by_uid(param_item['id'])

            if param_item['controller'] == 'ai':
                controller = GenericController(game_session)
            else:
                usernames = entity_owners(entity.entity_uid)
                if not usernames:
                    controller = controllers["dm"]
                else:
                    controller = controllers.get(usernames[0], None) or controllers["dm"]
            controller.register_handlers_on(entity)
            battle.add(entity, param_item['group'], controller=controller)
        output_logger.log("Battle started.")
        battle.start()
    else:
        print("skipping default battle start")
    current_game.execute_game_loop()
    with open('save.yml','w+') as f:
        f.write(yaml.dump(battle_map.to_dict()))
    return jsonify(status='ok')


@app.route('/end_turn', methods=['POST'])
def end_turn():
    battle = current_game.get_current_battle()
    battle_map = current_game.get_current_battle_map()
    battle.end_turn()
    battle.next_turn()
    game_loop()
    current_turn = battle.current_turn()
    socketio.emit('message', { 'type': 'initiative', 'message': { 'index': battle.current_turn_index} })
    socketio.emit('message', { 'type': 'move', 'message': {'id': current_turn.entity_uid, 'animation_log' : battle.get_animation_logs() }})
    battle.clear_animation_logs()
    socketio.emit('message', { 'type': 'turn', 'message': {}})
    # battle.clear_animation_logs()
    with open('save.yml','w+') as f:
        f.write(yaml.dump(battle_map.to_dict()))
    return jsonify(status='ok')

@app.route('/turn_order', methods=['GET'])
def get_turn_order():
    global current_game
    battle = current_game.get_current_battle()
    return render_template('battle.html', battle=battle, role=user_role())

@app.route('/next_turn', methods=['POST'])
def next_turn():
    global current_game
    battle = current_game.get_current_battle()
    battle_map = current_game.get_current_battle_map()
    global waiting_for_user
    if battle:
        current_turn = battle.current_turn()
        if waiting_for_user:
            waiting_for_user = False
            current_turn.resolve_trigger('end_of_turn')
            battle.end_turn()
            battle.next_turn()
            if battle.battle_ends():
                end_current_battle()

        game_loop()
        socketio.emit('message', { 'type': 'initiative','message': {'index': battle.current_turn_index}})
        socketio.emit('message', { 'type': 'move', 'message': {'id': current_turn.entity_uid, 
                                                               'animation_log' : battle.get_animation_logs() }})
        socketio.emit('message', { 'type': 'turn', 'message': {}})
        battle.clear_animation_logs()

    with open('save.yml','w+') as f:
        f.write(yaml.dump(battle_map.to_dict()))
    return jsonify(status='ok')

@app.route('/update')
def update():
    global current_game
    enable_pov = request.args.get('pov', 'false') == 'true'
    x = int(request.args.get('x'))
    y = int(request.args.get('y'))
    battle_map = current_game.get_current_battle_map()
    battle = current_game.get_current_battle()
    renderer = JsonRenderer(battle_map, battle)

    pov_entities = None

    if enable_pov and 'dm' in user_role():
        entity = battle_map.entity_at(x, y)
        if entity:
            pov_entities = [entity]
    else:
        if 'dm' in user_role():
            pov_entities = None
        else:
            pov_entities = entities_controlled_by(session['username'], battle_map)
    my_2d_array = [renderer.render(entity_pov=pov_entities)]
    return render_template('map.html', tiles=my_2d_array, tile_size_px=TILE_PX, is_setup=(request.args.get('is_setup') == 'true'))

@app.route('/actions', methods=['GET'])
def get_actions():
    global current_game
    current_user = session['username']
    battle_map = current_game.get_current_battle_map()
    battle = current_game.get_current_battle()

    id = request.args.get('id')
    if id is None:
        return jsonify(error="No entity id provided"), 400

    entity = battle_map.entity_by_uid(id)
    if entity:
        if 'dm' in user_role() or current_user in entity_owners(entity.entity_uid):
            return render_template('actions.html', entity=entity, battle=battle, session=game_session)
        else:
            return jsonify(error="Forbidden"), 403
    return jsonify(error="Entity not found"), 404

@app.route("/hide", methods=['GET'])
def get_hiding_spots():
    global current_game
    battle_map = current_game.get_current_battle_map()
    battle = current_game.get_current_battle()
    entity_id = request.args.get('id')
    entity = battle_map.entity_by_uid(entity_id)
    if entity is None:
        return jsonify(error="Entity not found"), 404
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
    else:
        raise ValueError(f"Unknown action type {action_type}")

@app.route('/target', methods=['GET'])
def get_target():
    global current_game
    battle_map = current_game.get_current_battle_map()
    battle = current_game.get_current_battle()
    payload = json.loads(request.args.get('payload'))
    
    entity_id = payload.get('id')
    x = int(payload.get('x'))
    y = int(payload.get('y'))
    action_info = payload.get('action_info')
    opts = payload.get('opts', {})
    entity = battle_map.entity_by_uid(entity_id)
    target = battle_map.entity_at(x, y)

    if entity and target and action_info == 'AttackAction':
        action = AttackAction(game_session, entity, 'attack')
        action.using = opts.get('using')
        action.npc_action = opts.get('npc_action', None)
        action.thrown = opts.get('thrown', False)
        action.target = target

        adv_mod, adv_info, attack_mod = action.compute_advantage_info(battle)
        valid_target = True
        if battle:
            valid_targets = battle.valid_targets_for(entity, action)
            valid_target = target in valid_targets
        return jsonify(valid_target=valid_target, adv_mod=adv_mod, adv_info=adv_info, attack_mod=attack_mod)

    elif entity and target and action_info =='SpellAction':
        build_map = SpellAction.build(game_session, entity)
        spell_choice = (opts['spell'], opts['at_level'])
        build_map = build_map['next'](spell_choice)
        action = build_map['next'](target)

        adv_mod, adv_info, attack_mod = action.compute_advantage_info(battle)
        valid_target = True

        if battle:
            valid_targets = battle.valid_targets_for(entity, action)
            valid_target = target in valid_targets
        return jsonify(valid_target=valid_target, adv_mod=adv_mod, adv_info=adv_info, attack_mod=attack_mod)
    else:
        success_rate = None

    return jsonify(success_rate=success_rate)

@app.route('/spells', methods=['GET'])
def get_spell():
    global current_game
    battle_map = current_game.get_current_battle_map()
    battle = current_game.get_current_battle()

    entity_id = request.args.get('id')
    entity = battle_map.entity_by_uid(entity_id)
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


@app.route('/action', methods=['POST'])
def action():
    global current_game
    battle_map = current_game.get_current_battle_map()
    battle = current_game.get_current_battle()
    action_request = request.json
    entity_id = action_request['id']
    action_type = action_request['action']
    opts = action_request.get('opts', {})
    entity = battle_map.entity_by_uid(entity_id)
    action_info = {}
    action_hash = None
    target_coords = action_request.get('target', None)

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
                    battle_map.move_to(entity, *last_coords, battle)
                    if battle:
                        socketio.emit('message', {'type': 'move', 'message': {'from': move_path[0], 'to': move_path[-1],
                                                                            'animation_log': battle.get_animation_logs()}})
                        battle.clear_animation_logs()
                    return jsonify({'status': 'ok'})
        else:
            action_info['action'] = 'movement'
            action_info['type'] = 'select_path'
            build_map = action.build_map()
            action_info['param'] = build_map['param']
            return jsonify(action_info)
    elif action_type == 'SpellAction':
        action = SpellAction(game_session, entity, 'spell')
        selected_spell = opts.get('spell')
        at_level = opts.get('at_level')
        target = opts.get('target')

        if selected_spell:
            action.spell = game_session.load_spell(selected_spell)
            current_map = action.build_map()
            current_map = current_map['next']((selected_spell, at_level))
            if isinstance(current_map, Action):
                return jsonify(commit_and_update(current_map))
            else:
                if target_coords:
                    if isinstance(target_coords, list):
                        target = []
                        for entity_uids in target_coords:
                            target.append(battle_map.entity_by_uid(entity_uids))
                    else:
                        target = battle_map.entity_at(int(target_coords['x']), int(target_coords['y']))
                        if target is None:
                            raise ValueError(f"Invalid target {target_coords}")

                    current_map = current_map['next'](target)

                    if isinstance(current_map, Action):
                        validate_targets(current_map, entity, target, current_map, battle)
                        return jsonify(commit_and_update(current_map))
                    else:
                        raise ValueError(f"Invalid action map {current_map}")

                action_info["action"] = "spell"
                action_info["type"] = "select_target"
                action_info["param"] = current_map["param"]
                param_details = current_map["param"][0]
                action_info['total_targets'] = param_details.get('num', 1)
                action_info['target_types'] = param_details.get('target_types', ['enemies'])
                action_info['range'] = param_details.get('range', 5)
                action_info['range_max'] = param_details.get('range', 5)
                action_info['spell'] = selected_spell
                if param_details.get('num', 1) > 1:
                    target_hints = [ t.entity_uid for t in acquire_targets(param_details, entity, battle, battle_map)]
                    action_info['target_hints'] = target_hints
                    action_info['unique_targets'] = param_details.get('unique_targets', False)
        else:
            action_info["action"] = "spell"
            action_info["type"] = "select_spell"
            current_map = action.build_map()
            action_info["param"] = current_map["param"]



    elif action_type == 'AttackAction' or action_type == 'TwoWeaponAttackAction':
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

            build_map = action.build_map()

            action_info['param'] = build_map['param']
    else:
        action_class = action_type_to_class(action_type)
        opts = action_request.get('opts', {})
        action = action_class(game_session, entity, opts.get('action_type'))
        action = action.build_map()
        if isinstance(action, Action):
            return jsonify(commit_and_update(action))
        else:
            if len(action['param'])==1:
                param_details = action['param'][0]
                if param_details['type'] == 'select_target':
                    valid_targets = battle_map.valid_targets_for(entity, param_details)
                    valid_targets = {target.entity_uid: battle_map.entity_or_object_pos(target) for target in valid_targets}
                    if target_coords:
                        if isinstance(target_coords, list):
                            target = []
                            for entity_uids in target_coords:
                                target.append(battle_map.entity_by_uid(entity_uids))
                        else:
                            target = battle_map.entity_at(int(target_coords['x']), int(target_coords['y']))
                            if target is None:
                                raise ValueError(f"Invalid target {target_coords}")
                        current_map = action['next'](target)

                        if isinstance(current_map, Action):
                            return jsonify(commit_and_update(current_map))
                        else:
                            raise ValueError(f"Invalid action map {current_map}")
                    else:
                        action_info['action'] = action_type
                        action_info['type'] = 'select_target'
                        action_info['valid_targets'] = valid_targets
                        action_info['total_targets'] = param_details['num']
                        action_info['param'] = action['param']
                        action_info['range'] = param_details.get('range', 5)
                        action_info['range_max'] = param_details.get('max_range', param_details.get('range', 5))
            else:
                raise ValueError(f"Invalid action map {action}")

    return jsonify(action_info)

@app.route('/info', methods=['GET'])
def get_info():
    battle_map = current_game.get_current_battle_map()
    battle = current_game.get_current_battle
    info_id = request.args.get('id')
    # Fetch the necessary information based on the info_id
    entity = battle_map.entity_by_uid(info_id)
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
        if 'dm' in user_role() or controller_of(session['username'], battle.current_turn().entity_uid):
            return render_template('turn.jinja', battle=battle)
        else:
            return jsonify(error="Forbidden"), 403
    else:
        return jsonify(error="No battle in progress"), 400


@app.route('/add', methods=['GET'])
def add():
    global current_game
    battle_map = current_game.get_current_battle_map()
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
    tracks = []
    for index, track in enumerate(SOUNDTRACKS):
        track_data = {
            'id': index,
            'url': track['file'],
            'name': track['name']
        }
        tracks.append(track_data)
    return render_template('soundtrack.jinja', tracks=tracks, track_id=int(request.args.get('track_id', 0)))

@app.route('/sound', methods=['POST'])
def sound():
    global current_soundtrack
    track_id = int(request.form['track_id'])
    if track_id == -1:
        current_soundtrack = None
        socketio.emit('message', {'type': 'stoptrack', 'message': {}})
    else:
        url = SOUNDTRACKS[track_id]['file']
        current_soundtrack = {'url': url, 'id': track_id}
        socketio.emit('message', {'type': 'track', 'message': current_soundtrack})
    return jsonify(status='ok')

@app.route('/volume', methods=['POST'])
def set_volume():
    volume = int(request.json['volume'])
    socketio.emit('message', {'type': 'volume', 'message': {'volume': volume}})
    return jsonify(status='ok')


def ai_loop():
    global current_game
    battle = current_game.get_current_battle()
    entity = battle.current_turn()
    cycles = 0
    while True:
        cycles += 1
        action = battle.move_for(entity)
        if not action:
            print(f"{entity.name}: End turn.")
            break
        battle.action(action)
        battle.commit(action)
        if not action or entity.unconscious() or entity.dead():
            break

def end_current_battle():
    global current_game
    current_game.trigger_event('on_battle_end')
    current_game.set_current_battle(None)
    socketio.emit('message', {'type': 'console', 'message': 'TPK. Battle has ended.'})
    socketio.emit('message', {'type': 'stop', 'message': {}})

if __name__ == '__main__':
    socketio.run(app, debug=True)
