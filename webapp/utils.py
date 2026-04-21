from collections import deque
import time
import os
import yaml
from natural20.map import Map
from natural20.entity import Entity
from natural20.battle import Battle, action_animator
from natural20.generic_controller import GenericController
from natural20.llm_controller import LlmMcpController
from natural20.web.web_controller import WebController, ManualControl
from natural20.player_character import PlayerCharacter
import uuid
import pdb
from itertools import combinations
import logging
from mutagen.mp3 import MP3
from natural20.utils.serialization import Serialization
import gzip
import threading
import queue
from natural20.action import Action
from natural20.utils.conversation import audible_entities
from typing import Optional, Dict, Any
from natural20.session import Session
from webapp.game_management_components import GameControllerRegistry, GameEntityRegistry, ShortTermGoalManager

class SocketIOOutputLogger:
    """
    A simple logger that logs to stdout
    """
    def __init__(self, socketio):
        self.logging_queue = deque(maxlen=1000)
        self.socketio = socketio
        self._game_getter = None
        self._role_lookup = None
        self._controlled_entities_lookup = None
        self._event_context = None

    def configure_visibility(self, game_getter=None, role_lookup=None, controlled_entities_lookup=None):
        self._game_getter = game_getter
        self._role_lookup = role_lookup
        self._controlled_entities_lookup = controlled_entities_lookup

    def get_all_logs(self, username=None, roles=None):
        return [entry['message'] for entry in self.get_visible_entries(username=username, roles=roles)]

    def get_visible_entries(self, username=None, roles=None):
        if username is None and roles is None:
            return list(self.logging_queue)

        visible_entries = []
        for entry in self.logging_queue:
            if self._entry_visible_to_user(entry, username=username, roles=roles):
                visible_entries.append(entry)
        return visible_entries

    def get_visible_entries_for_entity(self, entity):
        return [entry for entry in self.logging_queue if self._entry_visible_to_entity(entry, entity)]

    def get_logs_for_entity(self, entity):
        return [entry['message'] for entry in self.get_visible_entries_for_entity(entity)]

    def clear_logs(self):
        self.logging_queue.clear()

    def get_log_snapshot(self):
        """Return a serializable list of all log entries for saving."""
        return list(self.logging_queue)

    def restore_log_snapshot(self, entries):
        """Restore log entries from a saved snapshot."""
        self.logging_queue.clear()
        for entry in (entries or []):
            self.logging_queue.append(entry)

    def set_event_context(self, event):
        self._event_context = event

    def clear_event_context(self):
        self._event_context = None

    def update(self):
        game = self._current_game()
        if not game or not getattr(game, 'username_to_sid', None):
            self.socketio.emit('message', {'type': 'console', 'messages': self.get_all_logs()})
            return

        for username, sids in game.username_to_sid.items():
            if not sids:
                continue
            messages = self.get_all_logs(username=username, roles=self._roles_for_username(username))
            for sid in sids:
                self.socketio.emit('message', {'type': 'console', 'messages': messages}, to=sid)

    def log(self, event_msg, event=None, visibility=None):
        # add time to the message
        current_time_str = time.strftime("%Y:%m:%d.%H:%M:%S", time.localtime())
        rendered_message = f"{current_time_str}: {event_msg}"
        effective_event = event if event is not None else self._event_context

        entry = {
            'timestamp': current_time_str,
            'message': rendered_message,
            'visibility': self._snapshot_visibility(event=effective_event, visibility=visibility),
        }

        self.logging_queue.append(entry)
        self._emit_entry(entry)

    def _emit_entry(self, entry):
        game = self._current_game()
        if not game or not getattr(game, 'username_to_sid', None):
            self.socketio.emit('message', {'type': 'console', 'message': entry['message']})
            return

        emitted = False
        for username, sids in game.username_to_sid.items():
            if not sids:
                continue
            if not self._entry_visible_to_user(entry, username=username):
                continue
            emitted = True
            for sid in sids:
                self.socketio.emit('message', {'type': 'console', 'message': entry['message']}, to=sid)

        if not emitted and entry['visibility'].get('public'):
            self.socketio.emit('message', {'type': 'console', 'message': entry['message']})

    def _snapshot_visibility(self, event=None, visibility=None):
        if visibility is None and event is None:
            return self._public_visibility()

        if visibility == 'public':
            return self._public_visibility()

        if visibility in ('dm', 'dm_only'):
            return self._dm_only_visibility()

        if isinstance(visibility, dict):
            kind = visibility.get('kind')
            if kind == 'combat':
                return self._scoped_visibility(entity_uids=self._combat_visible_entity_uids(visibility))
            if kind == 'conversation':
                return self._scoped_visibility(entity_uids=self._conversation_visible_entity_uids(visibility))
            if kind in ('entity_only', 'entities'):
                return self._scoped_visibility(
                    entity_uids=self._entity_uids_from_values(
                        visibility.get('entity_uids') or visibility.get('entities') or []
                    ),
                    usernames=visibility.get('usernames') or [],
                )
            if visibility.get('public'):
                return self._public_visibility()
            if visibility.get('dm_only'):
                return self._dm_only_visibility()
            if visibility.get('entity_uids') or visibility.get('usernames'):
                return self._scoped_visibility(
                    entity_uids=self._entity_uids_from_values(visibility.get('entity_uids') or []),
                    usernames=visibility.get('usernames') or [],
                )

        if event is not None:
            event_name = event.get('event')
            if event_name == 'conversation':
                return self._scoped_visibility(entity_uids=self._conversation_visible_entity_uids(event))
            if event_name == 'console':
                return self._public_visibility()
            return self._scoped_visibility(entity_uids=self._combat_visible_entity_uids(event))

        return self._public_visibility()

    def _public_visibility(self):
        return {
            'public': True,
            'dm_only': False,
            'entity_uids': [],
            'usernames': [],
        }

    def _dm_only_visibility(self):
        return {
            'public': False,
            'dm_only': True,
            'entity_uids': [],
            'usernames': [],
        }

    def _scoped_visibility(self, entity_uids=None, usernames=None):
        entity_uids = sorted(set(uid for uid in (entity_uids or []) if uid))
        usernames = sorted(set(name for name in (usernames or []) if name))
        if not entity_uids and not usernames:
            return self._public_visibility()
        return {
            'public': False,
            'dm_only': False,
            'entity_uids': entity_uids,
            'usernames': usernames,
        }

    def _entry_visible_to_user(self, entry, username=None, roles=None):
        if roles is None:
            roles = self._roles_for_username(username)

        if roles and 'dm' in roles:
            return True

        visibility = entry.get('visibility') or self._public_visibility()
        if visibility.get('public'):
            return True
        if visibility.get('dm_only'):
            return False
        if username and username in set(visibility.get('usernames') or []):
            return True

        visible_uids = set(visibility.get('entity_uids') or [])
        if not visible_uids:
            return False

        controlled_uids = set(self._controlled_entity_uids_for_username(username))
        return bool(controlled_uids.intersection(visible_uids))

    def _entry_visible_to_entity(self, entry, entity):
        if entity is None:
            return False

        try:
            if getattr(entity, 'is_admin', False):
                return True
        except Exception:
            pass

        visibility = entry.get('visibility') or self._public_visibility()
        if visibility.get('public'):
            return True
        if visibility.get('dm_only'):
            return False

        entity_uid = self._entity_uid(entity)
        if not entity_uid:
            return False

        visible_uids = set(visibility.get('entity_uids') or [])
        return entity_uid in visible_uids

    def _combat_visible_entity_uids(self, payload):
        source = payload.get('source')
        targets = self._collect_entities(payload)
        visible_entities = set(self._entity_uids_from_values(targets))
        if source is not None:
            source_uid = self._entity_uid(source)
            if source_uid:
                visible_entities.add(source_uid)

        if payload.get('players'):
            visible_entities.update(self._entity_uids_from_values(payload['players'].keys()))

        battle_map = self._map_for_payload(payload)
        if battle_map is None:
            return visible_entities

        seeds = []
        if source is not None:
            seeds.append(source)
        seeds.extend(targets)

        if not seeds:
            return visible_entities

        for viewer in self._map_entities(battle_map):
            viewer_uid = self._entity_uid(viewer)
            if not viewer_uid:
                continue
            for seed in seeds:
                try:
                    if battle_map.can_see(viewer, seed):
                        visible_entities.add(viewer_uid)
                        break
                except Exception:
                    continue

        return visible_entities

    def _conversation_visible_entity_uids(self, payload):
        source = payload.get('source')
        targets = self._collect_entities(payload)
        visible_entities = set(self._entity_uids_from_values(targets))

        if source is None:
            return visible_entities

        source_uid = self._entity_uid(source)
        if source_uid:
            visible_entities.add(source_uid)

        battle_map = self._map_for_payload(payload)
        if battle_map is None:
            return visible_entities

        try:
            listeners = audible_entities(
                source,
                battle_map,
                distance_ft=payload.get('distance_ft', 30),
                mode=payload.get('volume'),
            )
        except Exception:
            listeners = []

        for listener_entry in listeners:
            listener_uid = self._entity_uid(listener_entry.get('entity'))
            if not listener_uid:
                continue
            visible_entities.add(listener_uid)

        return visible_entities

    def _collect_entities(self, payload):
        entities = []
        if payload.get('target') is not None:
            entities.append(payload.get('target'))
        entities.extend(payload.get('targets') or [])
        return entities

    def _entity_uids_from_values(self, values):
        entity_uids = []
        for value in values:
            uid = self._entity_uid(value)
            if uid:
                entity_uids.append(uid)
        return entity_uids

    def _entity_uid(self, value):
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return getattr(value, 'entity_uid', None)

    def _map_for_payload(self, payload):
        source = payload.get('source')
        candidate_entities = [source] + self._collect_entities(payload)
        for entity in candidate_entities:
            battle_map = self._map_for_entity(entity)
            if battle_map is not None:
                return battle_map
        return None

    def _map_for_entity(self, entity):
        if entity is None:
            return None

        game = self._current_game()
        if game is not None:
            try:
                battle_map = game.get_map_for_entity(entity)
                if battle_map is not None:
                    return battle_map
            except Exception:
                pass

        session = getattr(entity, 'session', None)
        if session is not None:
            try:
                return session.map_for_entity(entity)
            except Exception:
                return None
        return None

    def _map_entities(self, battle_map):
        entities = getattr(battle_map, 'entities', None)
        if entities is None:
            return []
        try:
            return list(entities)
        except Exception:
            return []

    def _current_game(self):
        if self._game_getter is None:
            return None
        try:
            return self._game_getter()
        except Exception:
            return None

    def _roles_for_username(self, username):
        if not username or self._role_lookup is None:
            return []
        try:
            return self._role_lookup(username) or []
        except Exception:
            return []

    def _controlled_entity_uids_for_username(self, username):
        if not username or self._controlled_entities_lookup is None:
            return []
        try:
            entities = self._controlled_entities_lookup(username) or []
        except Exception:
            return []

        entity_uids = []
        for entity in entities:
            uid = self._entity_uid(entity)
            if uid:
                entity_uids.append(uid)
        return entity_uids

# Defines a class for high level game management
class GameManagement:
    def __init__(self, game_session: Session, map_location, other_maps, socketio, output_logger, tile_px, controllers,
                 npc_controller = None,
                 force_llm_npc_combat = False,
                 autosave = False,
                 auto_battle=True,
                 system_logger=None,  soundtrack=None,
                 defer_player_spawn=False):
        """
        Initialize the game management

        :param game_session: the game session
        :param map_location: the map location
        :param socketio: the socketio instance
        :param output_logger: the output logger
        :param tile_px: the tile pixel size
        :param controllers: the controllers
        :param auto_battle: whether to auto battle
        """
        self.map_location = map_location
        self.other_maps = other_maps
        self.game_session = game_session
        self.socketio = socketio
        self.output_logger = output_logger
        self.tile_px = tile_px
        self.waiting_for_user = False
        self.waiting_for_reaction = False
        self.end_turn_state = False
        self.controllers = controllers
        self.npc_controller = npc_controller
        self.force_llm_npc_combat = force_llm_npc_combat
        self.auto_battle = auto_battle
        self.web_controllers = {}
        self.maps = {}
        self.max_save_states = 10
        self.pov_entity_for_user = {}
        self.current_map_for_user = {}
        self.username_to_sid = {}
        self.save_states = []
        self.defer_player_spawn = defer_player_spawn
        self.deferred_players = {}  # entity_uid -> {entity, map_name, position}
        self.entity_registry = GameEntityRegistry(self)
        self.controller_registry = GameControllerRegistry(self)
        self.soundtracks = soundtrack
        self.current_soundtrack = None
        self.autosave = autosave
        self.gzip = False
        self.read_notes = set()
        self.game_state_lock = threading.Lock()
        # Per-map locks for non-battle actions to reduce contention across maps
        self.map_state_locks = {}
        self._map_state_locks_guard = threading.Lock()
        # Initialize logger as early as possible so subsequent setup can log safely
        if not system_logger:
            self.logger = logging.getLogger(__name__)
            self.logger.setLevel(logging.INFO)
        else:
            self.logger = system_logger
        # Initialize async save worker
        self._save_queue = queue.Queue(maxsize=50)
        # Sentinel object to signal orderly shutdown of the save worker
        self._SAVE_SENTINEL = object()
        self._save_thread = threading.Thread(target=self._save_worker, name="save-worker", daemon=True)
        self._save_thread.start()
        # Centralize save directory (writable in Docker). Can be absolute or relative.
        base_save_dir = os.environ.get('SAVE_DIR', os.path.join(os.getcwd(), 'saves'))

        # Namespace saves by game to avoid collisions when multiple games use the same SAVE_DIR.
        try:
            game_props = getattr(self.game_session, 'game_properties', {}) or {}
        except Exception:
            game_props = {}

        # Prefer an explicit game name/id from game properties, else fall back to the root_path folder name
        game_name_raw = game_props.get('name') or game_props.get('id') or os.path.basename(os.path.abspath(self.game_session.root_path)) or 'game'
        import re, tempfile
        game_ns = re.sub(r'[^a-zA-Z0-9_-]+', '-', str(game_name_raw)).strip('-_ ').lower() or 'game'

        self.save_dir = os.path.join(base_save_dir, game_ns)
        try:
            os.makedirs(self.save_dir, exist_ok=True)
        except Exception:
            # Fallback to a local namespaced saves dir inside CWD
            try:
                self.save_dir = os.path.join(os.getcwd(), 'saves', game_ns)
                os.makedirs(self.save_dir, exist_ok=True)
            except Exception:
                # Last resort: a tmp dir unique per process and game
                tmpdir = os.path.join(tempfile.gettempdir(), f"natural20_saves_{os.getpid()}_{game_ns}")
                os.makedirs(tmpdir, exist_ok=True)
                self.save_dir = tmpdir

        # If directory exists but is not writable, fallback to a tmp dir unique per process + game
        try:
            test_path = os.path.join(self.save_dir, '.write_test')
            with open(test_path, 'w') as _f:
                _f.write('ok')
            os.remove(test_path)
        except Exception:
            tmpdir = os.path.join(tempfile.gettempdir(), f"natural20_saves_{os.getpid()}_{game_ns}")
            os.makedirs(tmpdir, exist_ok=True)
            self.save_dir = tmpdir
            self.logger.warning(f"SAVE_DIR not writable. Falling back to {self.save_dir}")


        self.logger.info(f"Loading map from {self.map_location}")
        self.battle_map = Map(game_session, self.map_location, name='index')

        self.maps = self.game_session.maps
        self.battle = None
        self.trigger_handlers = {}
        self.callbacks = {}
        self.current_save_index = 0
        self.previous_time = 0
        self.player_character_game_times = {}
        self.short_term_goals: Dict[str, Dict[str, Any]] = {}
        self.goal_turn_seconds = max(1, int(os.environ.get('NPC_GOAL_TURN_SECONDS', '6')))
        self.goal_poll_interval = max(0.25, float(os.environ.get('NPC_GOAL_POLL_INTERVAL', '1.0')))
        self.goal_manager = ShortTermGoalManager(self)
        self._goal_thread_stop = threading.Event()
        self._goal_thread = threading.Thread(target=self.goal_manager.goal_worker, name='npc-goal-worker', daemon=True)
        self._goal_thread.start()

        if self.soundtracks:
            # load each soundtrack and determine its duration
            for track in self.soundtracks:
                track['duration'] = 0
                # strip leading and trailing spaces
                track['name'] = track['name'].strip()
                track['start_time'] = int(time.time())
                if 'volume' not in track or track['volume'] is None:
                    track['volume'] = 0
                # load mp3 file
                audio_path = self.game_session.root_path + '/assets/' + track['file']
                if not os.path.exists(audio_path):
                    self.logger.error(f"Soundtrack {track['name']} not found at {audio_path}")
                    raise Exception(f"Soundtrack {track['name']} not found at {audio_path}")
                    
                audio = MP3(audio_path)
                track['duration'] = int(audio.info.length)
                self.logger.info(f"Loaded soundtrack {track['name']} with duration {track['duration']}")
                if 'background' in track['name']:
                    self.current_soundtrack = track
        self._setup_controllers()
        if self.defer_player_spawn:
            self._defer_all_players()
        if autosave:
            # Build an initial save list from files present
            available_files = []
            try:
                for file in os.listdir(self.save_dir):
                    if file.startswith('save_') and (file.endswith('.yml') or file.endswith('.yml.gz')):
                        try:
                            index = int(file.split('_')[1].split('.')[0])
                            available_files.append((index, file))
                        except Exception:
                            # Named saves without numeric index
                            available_files.append((10**9, file))
            except FileNotFoundError:
                pass

            self.save_states = [file for index, file in sorted(available_files, key=lambda x: x[0])]
            # Attempt to autoload the last save if recorded
            last_save_path = os.path.join(self.save_dir, 'last_save.txt')
            if os.path.exists(last_save_path):
                with open(last_save_path, 'r') as f:
                    last_save = f.read().strip()
                    if last_save:
                        save_file, index = last_save.split(',')
                        try:
                            self.current_save_index = int(index)
                        except Exception:
                            self.current_save_index = 0
                        print(f"Loading save {save_file} {index}")
                        # Prefer loading by filename to avoid index/position ambiguity
                        self.load_save(filename=save_file)

    def _setup_controllers(self):
        self.controller_registry.setup_controllers()

    def _defer_all_players(self):
        self.entity_registry.defer_all_players()

    def spawn_player_for_user(self, username):
        return self.entity_registry.spawn_player_for_user(username)

    def get_pov_entity_for_user(self, username):
        return self.entity_registry.get_pov_entity_for_user(username)

    def set_pov_entity_for_user(self, username, entity):
        self.entity_registry.set_pov_entity_for_user(username, entity)

    def switch_map_for_user(self, username, map_name):
        self.entity_registry.switch_map_for_user(username, map_name)

    def get_map_for_user(self, username) -> Map:
        return self.entity_registry.get_map_for_user(username)

    def get_map_for_entity(self, entity) -> Map:
        return self.entity_registry.get_map_for_entity(entity)

    def get_entity_by_uid(self, entity_uid) -> Entity:
        return self.entity_registry.get_entity_by_uid(entity_uid)

    def get_background_image_for_user(self, username):
        return self.entity_registry.get_background_image_for_user(username)

    def waiting_for_user_input(self):
        return self.waiting_for_user

    def waiting_for_reaction_input(self):
        return self.waiting_for_reaction

    def clear_reaction_input(self):
        self.waiting_for_reaction = False

    def set_waiting_for_reaction_input(self, waiting):
        self.waiting_for_reaction = waiting

    def set_waiting_for_user_input(self, waiting):
        self.waiting_for_user = waiting

    def reset(self):
        self.battle_map = Map(self.game_session, self.map_location)
        self.battle = None
        self.socketio.emit('message', {'type': 'reset', 'message': {}})

    def reload_map_for_user(self,  username):
        map_name, _ = self.current_map_for_user.get(username, ('index', self.maps['index']))
        self.current_map_for_user[username] = (map_name, self.maps[map_name])
        self.maps[map_name] = Map(self.game_session, self.other_maps[map_name], name=map_name)

    def set_current_battle_map(self, battle_map):
        for k,v in self.current_map_for_user.items():
            self.current_map_for_user[k] = (battle_map.name, battle_map)

    def set_current_battle(self, battle):
        self.battle = battle

    def get_current_battle(self):
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
        self.socketio.emit('message', {'type': 'prompt', 'message': message, 'callback': callback_id})

    def push_animation(self):
        self.socketio.emit('message', {'type': 'move', 'message': {'animation_log': self.battle.get_animation_logs()}})
        self.battle.clear_animation_logs()

    def execute_game_loop(self):
        self.output_logger.log("Battle started.", visibility='public')
        self.game_loop()
        self.socketio.emit('message',{'type': 'initiative', 'message': {}})

        if self.battle:
            self.socketio.emit('message', {
                'type': 'move',
                'message': { 'animation_log' : self.battle.get_animation_logs() }
                })
            self.battle.clear_animation_logs()

        self.socketio.emit('message',{ 'type': 'turn', 'message': {}})

    def refresh_client_map(self):
        width, height = self.battle_map.size
        tiles_dimension_width = width * self.tile_px
        tiles_dimension_height = height * self.tile_px
        map_image_url = f"assets/{ self.battle_map.name + '.png'}"

        self.socketio.emit('message', {'type': 'map',
                                  'width': tiles_dimension_width,
                                  'height': tiles_dimension_height,
                                  'image_offset_px': self.battle_map.image_offset_px,
                                  'message': map_image_url})
        self.socketio.emit('message', {'type': 'initiative', 'message': {}})
        self.socketio.emit('message', {'type': 'turn', 'message': {}})

    def get_available_maps(self):
        return list(self.maps.keys())

    def effective_npc_combat_controller(self):
        return self.controller_registry.effective_npc_combat_controller()

    def build_combat_controller_for_entity(self, entity):
        return self.controller_registry.build_combat_controller_for_entity(entity)
    
    def update_group(self, entity, group):
        entity.group = group
        self.loop_environment()

    def loop_environment(self):
        if not self.auto_battle:
            return

        # check all entities in the map if it would set off a battle
        entity_by_groups = {}
        start_battle = False
        add_to_initiative_set = set()
        pc_groups = ['a']
        enemy_groups = ['b']

        for battle_map in self.maps.values():
            for entity in battle_map.entities:
                if entity.group not in entity_by_groups:
                    entity_by_groups[entity.group] = set()
                entity_by_groups[entity.group].add(entity)

        for battle_map in self.maps.values():
            for group1 in pc_groups:
                for group2 in enemy_groups:
                    if self.game_session.opposing(group1, group2):

                        if group1 not in entity_by_groups:
                            continue

                        for entity1 in entity_by_groups[group1]:
                            if not entity1.conscious():
                                continue
                            if group2 not in entity_by_groups:
                                continue
                            for entity2 in entity_by_groups[group2]:
                                if not entity2.conscious():
                                    continue

                                # Ignore if both entities already belong to an ongoing battle
                                if self.battle and (entity1 in self.battle.entities and entity2 in self.battle.entities):
                                    continue

                                if self.get_map_for_entity(entity1) != self.get_map_for_entity(entity2):
                                    continue

                                if entity2.passive():
                                    continue

                                # if it is only the player character that can see the enemy, skip it
                                if isinstance(entity2, PlayerCharacter):
                                    continue

                                if battle_map.can_see(entity2, entity1):
                                    add_to_initiative_set.add((entity1, group1))
                                    add_to_initiative_set.add((entity2, group2))

                                    # Add allies for entity1
                                    for ally in entity_by_groups[group1]:
                                        if ally != entity1 and (battle_map.can_see(ally, entity1) or ally.group=='a'):
                                            add_to_initiative_set.add((ally, group1))

                                    # Add allies for entity2
                                    for ally in entity_by_groups[group2]:
                                        if ally != entity2 and battle_map.can_see(ally, entity2) or ally.group=='a':
                                            add_to_initiative_set.add((ally, group2))

                                    start_battle = True
        add_to_initiative = list(add_to_initiative_set)

        if add_to_initiative:
            if start_battle:
                battle_music = 'battle'
                if not self.battle:
                    self.battle = Battle(self.game_session, self.maps, animation_log_enabled=True)
                    for entity, group in add_to_initiative:

                        # For bosses, use their battle music
                        if entity.battle_music:
                            battle_music = entity.battle_music
                            self.logger.info(f"Using battle music {battle_music} for {entity.name}")
                        controller = self.build_combat_controller_for_entity(entity)
                        if not controller:
                            self.logger.error(f"Controller not found for {entity}")
                            controller = GenericController(self.game_session)

                        controller.register_handlers_on(entity)
                        self.logger.info(f"Adding {entity.name} to battle with group {group}")
                        self.battle.add(entity, group, controller=controller)
                    self.output_logger.log("Battle started.", visibility='public')

                    # if battle sound is present, start playing it
                    for soundtrack in (self.soundtracks or []):
                        if battle_music.lower()==soundtrack['name'].lower():
                            self.play_soundtrack(soundtrack['name'])
                            break
                    self.battle.start()
                    self.execute_game_loop()
                else:
                    for entity, group in add_to_initiative:
                        controller = self.build_combat_controller_for_entity(entity)
                        if controller is None:
                            controller = GenericController(self.game_session)
                        controller.register_handlers_on(entity)
                        self.battle.add(entity, group, add_to_initiative=True, controller=controller)

                self.socketio.emit('message', { 'type': 'initiative','message': {'index': self.battle.current_turn_index}})
                self.socketio.emit('message', { 'type': 'turn', 'message': {}})


    def get_controller_for_entity(self, entity):
        return self.controller_registry.get_controller_for_entity(entity)

    def get_web_controllers_for_user(self, username, default_controller = None):
        return self.controller_registry.get_web_controllers_for_user(username, default_controller=default_controller)

    def entity_owners(self, entity):
        return self.controller_registry.entity_owners(entity)

    def entities_owned_by(self, entity):
        return self.controller_registry.entities_owned_by(entity)

    def game_loop(self):
        battle = self.get_current_battle()
        try:
            while True:
                # Start turn and prepare entity
                battle.start_turn()
                current_turn = battle.current_turn()
                current_turn.reset_turn(battle)

                if battle.battle_ends():
                    break

                # Skip turns for dead or unconscious entities
                while (current_turn.dead() or current_turn.unconscious()) and not battle.battle_ends():
                    current_turn.resolve_trigger('end_of_turn')
                    battle.end_turn()
                    battle.next_turn()

                    battle.start_turn()
                    current_turn = battle.current_turn()
                    current_turn.reset_turn(battle)

                if battle.battle_ends():
                    break

                # Process AI actions
                self.ai_loop()
                current_turn.resolve_trigger('end_of_turn')

                if battle.battle_ends():
                    break

                # End turn and update environment
                battle.end_turn()
                self.loop_environment()
                battle.next_turn()

            self.end_current_battle()
        except ManualControl:
            self.logger.info("waiting for user to end turn.")

    def ai_loop(self):
        battle = self.get_current_battle()
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

    def set_volume(self, volume):
        self.current_soundtrack['volume'] = volume
        self.socketio.emit('message', {'type': 'volume', 'message': { 'volume': volume } })
        self.logger.info(f"Setting volume to {volume}")
    """
    Play a soundtrack

    :param track_id: the track id

    :return: None
    """
    def play_soundtrack(self, track_id):
        if track_id == "-1":
            # Clear current soundtrack and notify clients to stop
            self.current_soundtrack = None
            self.socketio.emit('message', {'type': 'stoptrack', 'message': {}})
        else:
            for soundtrack in (self.soundtracks or []):
                url = soundtrack['file']

                if track_id != soundtrack['name']:
                    continue

                if self.current_soundtrack:
                    if self.current_soundtrack['name'] != soundtrack['name']:
                        current_time_in_seconds = int(time.time())
                        current_soundtrack = {'url': url, 'id': track_id, 'start_time': current_time_in_seconds, 'duration': soundtrack.get('duration', 0)}
                        soundtrack['time'] = 0
                        self.logger.info(f"Playing soundtrack {current_soundtrack}")
                        self.socketio.emit('message', { 'type': 'track', 'message': current_soundtrack })
                        self.current_soundtrack = soundtrack
                        break
                    else:
                        time_s = (time.time() - self.current_soundtrack['start_time']) % self.current_soundtrack['duration']
                        self.current_soundtrack['time'] = time_s
                        self.logger.info(f"Playing soundtrack {self.current_soundtrack}")
                        self.socketio.emit('message', { 'type': 'track', 'message': self.current_soundtrack})
                else:
                    current_soundtrack = {'url': url, 'id': track_id, 'start_time': time.time(), 'duration': soundtrack.get('duration', 0)}
                    self.logger.info(f"Playing soundtrack {current_soundtrack}")
                    self.socketio.emit('message', {'type': 'track', 'message': current_soundtrack})
                    self.current_soundtrack = soundtrack
                    break

    """
    Againt track_id, seek to a specific time
    :param track_id: the track id
    :param time_s: the time in seconds
    """
    def seek_soundtrack(self, time_s):
        if self.current_soundtrack:
            self.current_soundtrack['start_time'] = int(time.time()) - time_s
            self.current_soundtrack['time'] = time_s
            self.socketio.emit('message', {'type': 'track', 'message': self.current_soundtrack})
            self.logger.info(f"Seeking soundtrack {self.current_soundtrack['name']} to {time_s}")

    def list_states(self):
        return self.save_states

    def _get_map_lock(self, map_obj):
        """Return an RLock dedicated to the provided map object.
        This allows actions on different maps to proceed concurrently when safe (outside battle).
        """
        if map_obj is None:
            # Fallback to global lock if map is unknown
            return self.game_state_lock
        try:
            map_key = getattr(map_obj, 'name', None) or id(map_obj)
        except Exception:
            map_key = id(map_obj)
        with self._map_state_locks_guard:
            lock = self.map_state_locks.get(map_key)
            if lock is None:
                lock = threading.RLock()
                self.map_state_locks[map_key] = lock
            return lock

    def save_game(self, name: Optional[str] = None):
        # Snapshot state and determine filename under lock, then write outside the lock
        yaml_str, target_file, index_for_record, log_snapshot, read_notes_snapshot = self._prepare_save(name)
        self._write_save_file(yaml_str, target_file, index_for_record, log_snapshot, read_notes_snapshot)

    def save_game_async(self, name: Optional[str] = None):
        """Queue a save request to be processed by the background save worker."""
        try:
            # Coalesce: if queue is full, drop older requests
            if self._save_queue.full():
                try:
                    _ = self._save_queue.get_nowait()
                except Exception:
                    pass
            self._save_queue.put_nowait(name)
        except Exception as e:
            # Fallback to synchronous save if queueing fails
            self.logger.warning(f"Falling back to sync save due to queue error: {e}")
            self.save_game(name=name)

    def _save_worker(self):
        """Background worker that processes save requests, coalescing bursts."""
        while True:
            try:
                name = self._save_queue.get()  # block
                stop_after = False
                if name is self._SAVE_SENTINEL:
                    # Nothing pending before sentinel, exit immediately
                    break
                # Drain to last request to coalesce rapid bursts. If we encounter sentinel while
                # draining, process the last non-sentinel request and then stop.
                while not self._save_queue.empty():
                    try:
                        next_item = self._save_queue.get_nowait()
                        if next_item is self._SAVE_SENTINEL:
                            stop_after = True
                            break
                        name = next_item
                    except Exception:
                        break
                yaml_str, target_file, index_for_record, log_snapshot, read_notes_snapshot = self._prepare_save(name)
                self._write_save_file(yaml_str, target_file, index_for_record, log_snapshot, read_notes_snapshot)
                if stop_after:
                    break
            except Exception as e:
                try:
                    self.logger.error(f"Async save failed: {e}")
                except Exception:
                    pass

    def _prepare_save(self, name: Optional[str]):
        """Prepare YAML string and decide target filename/index under lock."""
        with self.game_state_lock:
            serializer = Serialization()
            yaml_str = serializer.serialize(self.game_session, self.battle, self.maps)
            log_snapshot = self.output_logger.get_log_snapshot()
            read_notes_snapshot = list(self.read_notes)

            # Determine filename
            if name:
                import re
                slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", name).strip("-_ ")
                ts = time.strftime('%Y%m%d-%H%M%S')
                base_name = f"save_{ts}_{slug}.yml" if slug else f"save_{ts}.yml"
                index_for_record = -1
            else:
                index = self.current_save_index % self.max_save_states
                base_name = f"save_{index}.yml"
                index_for_record = index
                # Advance index to avoid race while writing
                self.current_save_index += 1

            target_file = base_name + ('.gz' if self.gzip and not base_name.endswith('.gz') else '')
            return yaml_str, target_file, index_for_record, log_snapshot, read_notes_snapshot

    def _write_save_file(self, yaml_str: str, target_file: str, index_for_record: int, log_snapshot=None, read_notes_snapshot=None):
        """Write the given YAML string to disk atomically and update indices/state."""
        abs_target = os.path.join(self.save_dir, target_file)
        import tempfile
        tmp_dir = self.save_dir
        try:
            if abs_target.endswith('.gz'):
                fd, tmp_path = tempfile.mkstemp(prefix='.save_', suffix='.yml.gz', dir=tmp_dir)
                os.close(fd)
                with gzip.open(tmp_path, 'wb') as f:
                    f.write(yaml_str.encode('utf-8'))
            else:
                fd, tmp_path = tempfile.mkstemp(prefix='.save_', suffix='.yml', dir=tmp_dir)
                with os.fdopen(fd, 'w') as f:
                    f.write(yaml_str)
            os.replace(tmp_path, abs_target)
        except PermissionError:
            import tempfile as _tempfile
            fallback_dir = os.path.join(_tempfile.gettempdir(), f"natural20_saves_{os.getpid()}")
            os.makedirs(fallback_dir, exist_ok=True)
            self.logger.warning(f"Permission denied writing to {self.save_dir}. Falling back to {fallback_dir}")
            self.save_dir = fallback_dir
            abs_target = os.path.join(self.save_dir, target_file)
            if abs_target.endswith('.gz'):
                with gzip.open(abs_target, 'wb') as f:
                    f.write(yaml_str.encode('utf-8'))
            else:
                with open(abs_target, 'w') as f:
                    f.write(yaml_str)

        # Rebuild save list
        available_files = []
        try:
            for file in os.listdir(self.save_dir):
                if file.startswith('save_') and (file.endswith('.yml') or file.endswith('.yml.gz')):
                    try:
                        idx = int(file.split('_')[1].split('.')[0])
                        available_files.append((idx, file))
                    except Exception:
                        available_files.append((10**9, file))
        except FileNotFoundError:
            pass
        self.save_states = [file for idx, file in sorted(available_files, key=lambda x: x[0])]
        try:
            with open(os.path.join(self.save_dir, 'last_save.txt'), 'w') as f:
                f.write(f"{target_file},{index_for_record}")
        except Exception:
            # Non-fatal if we can't write last_save.txt
            pass

        # Save combat log alongside the game state
        if log_snapshot is not None:
            import json
            log_file = os.path.splitext(target_file.replace('.gz', ''))[0] + '.log.json'
            try:
                abs_log = os.path.join(self.save_dir, log_file)
                with open(abs_log, 'w') as f:
                    json.dump(log_snapshot, f)
            except Exception:
                pass

        # Save read notes alongside the game state
        if read_notes_snapshot is not None:
            import json
            notes_file = os.path.splitext(target_file.replace('.gz', ''))[0] + '.read_notes.json'
            try:
                abs_notes = os.path.join(self.save_dir, notes_file)
                with open(abs_notes, 'w') as f:
                    json.dump(read_notes_snapshot, f)
            except Exception:
                pass

    def load_save(self, index=None, filename=None):
        """
        Load a save by filename or identifier.
        - If filename is provided, load that file directly.
        - If index is provided, first try save_{index}.yml(.gz); otherwise treat as positional index into self.save_states.
        - If neither provided, load the latest (last in sorted list).
        """
        target_file = None
        if filename:
            # Trust provided filename as-is
            target_file = filename
        elif index is not None:
            # Try id-based file first
            candidate_yml = f"save_{index}.yml"
            candidate_gz = f"save_{index}.yml.gz"
            if os.path.exists(os.path.join(self.save_dir, candidate_yml)):
                target_file = candidate_yml
            elif os.path.exists(os.path.join(self.save_dir, candidate_gz)):
                target_file = candidate_gz
            else:
                # Fallback to positional within current list
                try:
                    target_file = self.save_states[index]
                except Exception:
                    return
        else:
            # Default to latest known
            if not self.save_states:
                return
            target_file = self.save_states[-1]

        # Read the state content
        # Resolve to absolute path under save_dir if not absolute
        abs_path = target_file
        if not os.path.isabs(abs_path):
            abs_path = os.path.join(self.save_dir, target_file)
        if abs_path.endswith('.gz'):
            with gzip.open(abs_path, 'rb') as f:
                state = f.read().decode('utf-8')
        else:
            with open(abs_path, 'r') as f:
                state = f.read()
        serializer = Serialization()
        new_session, new_battle, new_maps = serializer.deserialize(state)
        self.game_session = new_session
        self.battle = new_battle

        self.battle_map = new_maps['index']
        self.maps = new_maps
        # Do not mutate the save list on load; keep history intact

        # Restore combat log if a log file exists alongside the save
        import json
        log_file = os.path.splitext(target_file.replace('.gz', ''))[0] + '.log.json'
        abs_log = os.path.join(self.save_dir, log_file)
        try:
            if os.path.exists(abs_log):
                with open(abs_log, 'r') as f:
                    log_snapshot = json.load(f)
                self.output_logger.restore_log_snapshot(log_snapshot)
        except Exception:
            pass

        # Restore read notes if a file exists alongside the save
        notes_file = os.path.splitext(target_file.replace('.gz', ''))[0] + '.read_notes.json'
        abs_notes = os.path.join(self.save_dir, notes_file)
        try:
            if os.path.exists(abs_notes):
                with open(abs_notes, 'r') as f:
                    self.read_notes = set(json.load(f))
            else:
                self.read_notes = set()
        except Exception:
            pass


    def end_current_battle(self):
        self.trigger_event('on_battle_end')
        self.set_current_battle(None)
        # revert to background musing if present
        for soundtrack in (self.soundtracks or []):
            if 'background' in soundtrack['name']:
                self.play_soundtrack(soundtrack['name'])
        self.socketio.emit('message', {'type': 'console', 'message': 'Battle has ended.'})
        self.socketio.emit('message', {'type': 'stop', 'message': {}})

    def execute_command(self, command):
        """Execute a command string and return the result."""
        try:
            # Split the command into parts
            parts = command.strip().split()
            if not parts:
                return "Empty command"
                
            cmd = parts[0].lower()
            args = parts[1:]
            
            # Process different commands
            if cmd == "help":
                return "Available commands: help, status, list, move, attack, cast, use, give, take, say, whisper, shout"
            elif cmd == "status":
                return f"Current map: {self.current_map.name}, Battle in progress: {self.battle is not None}"
            elif cmd == "list":
                if len(args) > 0 and args[0] == "entities":
                    entities = self.current_map.get_entities()
                    return "\n".join([f"{e.name} ({e.entity_uid})" for e in entities])
                else:
                    return "Usage: list entities"
            else:
                return f"Unknown command: {cmd}. Type 'help' for available commands."
        except Exception as e:
            return f"Error executing command: {str(e)}"

    def increment_game_time(self, player_character: PlayerCharacter):
        # Update the game time for the player character
        if player_character not in self.player_character_game_times:
            self.player_character_game_times[player_character] = 0
        self.player_character_game_times[player_character] += 6

        max_player_time = max(self.player_character_game_times.values(), default=0)

        if max_player_time > self.previous_time:
            self.previous_time = max_player_time
            self.game_session.increment_game_time()

    def advance_world_time(self, seconds: int = 6, trigger_environment: bool = True):
        with self.game_state_lock:
            self.game_session.increment_game_time(seconds)
            if trigger_environment and not self.get_current_battle():
                self.loop_environment()
        self.socketio.emit('message', {'type': 'turn', 'message': {'game_time': self.game_session.game_time}})
        if self.autosave:
            self.save_game_async()

    def schedule_short_term_goal(self, entity, goal_text, speaker=None):
        return self.goal_manager.schedule_short_term_goal(entity, goal_text, speaker=speaker)

    def get_short_term_goal(self, entity):
        return self.goal_manager.get_short_term_goal(entity)

    def record_short_term_goal_history(self, entity, entry):
        return self.goal_manager.record_short_term_goal_history(entity, entry)

    def complete_short_term_goal(self, entity, status='completed', reason=None):
        return self.goal_manager.complete_short_term_goal(entity, status=status, reason=reason)

    def _goal_worker(self):
        self.goal_manager.goal_worker()

    def commit_and_update(self, username, action, pov_entities):
        """Commit an action and update clients.

        Locking policy:
        - During an active battle, use the global game_state_lock to preserve strict ordering.
        - Outside battle, use a per-map lock for the map containing the acting entity
          so actions on different maps don't block each other.
        """
        # Snapshot basic references without holding locks for long
        battle = self.get_current_battle()
        pov_entity = self.get_pov_entity_for_user(username) or (pov_entities[0] if pov_entities else None)
        pov_map = self.get_map_for_entity(pov_entity)

        if battle:
            # Strict global locking while in battle
            with self.game_state_lock:
                battle.action(action)
                battle.commit(action)
                if battle.battle_ends():
                    self.end_current_battle()
        else:
            # More forgiving: lock only the acting entity's map
            action_battle_map = self.get_map_for_entity(action.source)
            map_lock = self._get_map_lock(action_battle_map)
            # Try a short timeout first to avoid long waits; then block if needed
            acquired = False
            try:
                acquired = map_lock.acquire(timeout=0.2)
            except Exception:
                # Fallback to blocking acquire if timeout not supported
                acquired = False
            if not acquired:
                map_lock.acquire()
            try:
                action.resolve(self.game_session, action_battle_map)
                for item in list(action.result):
                    for klass in Action.__subclasses__():
                        other_results = klass.apply(None, item, session=self.game_session)
                        if isinstance(other_results, list):
                            action.result.extend(other_results)
                # handle game time for out of battle actions
                if isinstance(action.source, PlayerCharacter):
                    self.increment_game_time(action.source)
            finally:
                try:
                    map_lock.release()
                except Exception:
                    pass
        # did the map change for the current pov?
        self.check_and_notify_map_change(pov_map, pov_entity, username)

        if battle:
            self.socketio.emit('message', {'type': 'move', 'message': { 'animation_log': battle.get_animation_logs()}})
            battle.clear_animation_logs()
            # Lighting or visibility may have changed (e.g. fire damage lighting a fireplace)
            self.socketio.emit('message', {'type': 'refresh_map'})
        else:
            self.socketio.emit('message', {'type': 'move', 'message': {'animation_log': []}})
            # check if spell and send animation log
            self.socketio.emit('message',action_animator(action))
            # Check if the action affects visibility (doors, lighting, etc.) and emit refresh_map
            request_map_refresh = False
            if hasattr(action, 'result') and action.result:
                for result_item in action.result:
                    if (result_item.get('type') == 'interact' and
                        result_item.get('action') in ['open', 'close']):
                        # Door open/close affects line of sight, refresh the map
                        request_map_refresh = True
                    elif result_item.get('type') == 'look':
                        # Look action can reveal notes and concealed entities, refresh the map
                        request_map_refresh = True
                    elif result_item.get("type") == "message":
                        self.socketio.emit('message', {"type": "message_toaster", "source": result_item["source"].entity_uid, "message": result_item["message"], "position": result_item["position"]})
                    elif result_item.get('refresh_map'):
                        request_map_refresh = True
            if request_map_refresh:
                self.socketio.emit('message', {'type': 'refresh_map'})
            self.loop_environment()
        self.socketio.emit('message', {'type': 'turn', 'message': { 'game_time': self.game_session.game_time }})

        if self.autosave:
            self.save_game_async()
        return True

    def shutdown_save_worker(self, timeout: float = 5.0):
        """Request the background save worker to flush any pending saves and stop.
        Blocks up to `timeout` seconds waiting for the thread to exit.
        Safe to call multiple times.
        """
        try:
            # If thread already not alive, nothing to do
            if not getattr(self, "_save_thread", None) or not self._save_thread.is_alive():
                return
            # Enqueue sentinel; block if needed to preserve ordering
            self._save_queue.put(self._SAVE_SENTINEL)
            self._save_thread.join(timeout)
            if self._save_thread.is_alive():
                try:
                    self.logger.warning("Save worker did not stop within timeout; proceeding with shutdown.")
                except Exception:
                    pass
        except Exception:
            # Best-effort shutdown; never raise during app teardown
            pass
        try:
            self._goal_thread_stop.set()
            if getattr(self, '_goal_thread', None) and self._goal_thread.is_alive():
                self._goal_thread.join(timeout)
        except Exception:
            pass
    
    def check_and_notify_map_change(self, pov_map, pov_entity, username):
        # Use the lock to make the operation atomic
        with self.game_state_lock:
            new_battle_map = self.get_map_for_entity(pov_entity)
            if pov_map is None:
                return
            if new_battle_map is None:
                return
            self.logger.info(f"pov_map: {pov_map.name} new_battle_map: {new_battle_map.name}")

            if new_battle_map != pov_map:
                self.switch_map_for_user(username, new_battle_map.name)
                sids = self.username_to_sid.get(username, [])
                for sid in sids:
                    self.socketio.emit('message', {'type': 'switch_map', 'message': {'map': new_battle_map.name}}, to=sid)
