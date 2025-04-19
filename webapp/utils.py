from collections import deque
import time
import os
import yaml
from natural20.map import Map
from natural20.battle import Battle
from natural20.generic_controller import GenericController
from natural20.web.web_controller import WebController, ManualControl
from natural20.player_character import PlayerCharacter
import uuid
import pdb
from itertools import combinations
import logging
from mutagen.mp3 import MP3
from natural20.utils.serialization import Serialization
import gzip

class SocketIOOutputLogger:
    """
    A simple logger that logs to stdout
    """
    def __init__(self, socketio):
        self.logging_queue = deque(maxlen=1000)
        self.socketio = socketio

    def get_all_logs(self):
        return self.logging_queue

    def clear_logs(self):
        self.logging_queue.clear()

    def update(self):
        self.socketio.emit('message', {'type': 'console', 'messages': self.get_all_logs()})

    def log(self, event_msg):
        # add time to the message
        current_time_str = time.strftime("%Y:%m:%d.%H:%M:%S", time.localtime())
        event_msg = f"{current_time_str}: {event_msg}"

        self.logging_queue.append(event_msg)
        self.socketio.emit('message', {'type': 'console', 'message': event_msg})



# Defines a class for high level game management
class GameManagement:
    def __init__(self, game_session, map_location, other_maps, socketio, output_logger, tile_px, controllers,
                 npc_controller = None,
                 autosave = False,
                 auto_battle=True, system_logger=None,  soundtrack=None):
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
        self.auto_battle = auto_battle
        self.web_controllers = {}
        self.maps = {}
        self.max_save_states = 10
        self.pov_entity_for_user = {}
        self.current_map_for_user = {}
        self.save_states = []
        self.soundtracks = soundtrack
        self.current_soundtrack = None
        self.autosave = autosave
        self.gzip = False

        if not system_logger:
            self.logger = logging.getLogger(__name__)
            self.logger.setLevel(logging.INFO)
        else:
            self.logger = system_logger


        self.logger.info(f"Loading map from {self.map_location}")
        self.battle_map = Map(game_session, self.map_location, name='index')

        self.maps = self.game_session.maps
        self.battle = None
        self.trigger_handlers = {}
        self.callbacks = {}
        self.current_save_index = 0

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
        if autosave:
           available_files = []
           for file in os.listdir('.'):
               if file.startswith('save_'):
                   index = file.split('_')[1].split('.')[0]
                   available_files.append((int(index), file))

           self.save_states = [file for index, file in sorted(available_files, key=lambda x: x[0])]
           if os.path.exists('last_save.txt'):
               with open('last_save.txt', 'r') as f:
                   last_save = f.read().strip()
                   if last_save:
                       save_file, index = last_save.split(',')
                       print(f"Loading save {save_file} {index}")
                       self.current_save_index = int(index)
                       self.load_save(int(index))

    def _setup_controllers(self):
        for controller in self.controllers:
            entity_uid =  controller['entity_uid']
            self.logger.info(f"Setting up controller for {entity_uid}")
            entity = self.get_entity_by_uid(entity_uid)
            if entity not in self.controllers:
                self.web_controllers[entity] = WebController(self.game_session, None)
                self.web_controllers[entity].add_user("dm")

            for _controller in controller['controllers']:
                self.web_controllers[entity].add_user(_controller)

    def get_pov_entity_for_user(self, username):
        self.logger.info(f"Getting POV entity for {username}")
        return self.pov_entity_for_user.get(username, None)

    def set_pov_entity_for_user(self, username, entity):
        if entity:
            self.logger.info(f"Setting POV entity for {username} to {entity.name}")
        self.pov_entity_for_user[username] = entity

    def switch_map_for_user(self, username, map_name):
        self.logger.info(f"Switching map for {username} to {map_name}")
        self.current_map_for_user[username] = (map_name, self.maps[map_name])

    def get_map_for_user(self, username):
        if 'index' not in self.maps:
             return self.maps.values()[0]
        name, _map = self.current_map_for_user.get(username, ('index', self.maps['index']))
        return _map

    def get_map_for_entity(self, entity):
        for _, map_obj in self.maps.items():
            if isinstance(entity, str):
                _entity = map_obj.get_entity_by_uid(entity)
            else:
                _entity = entity

            if _entity in map_obj.entities:
                return map_obj
        return None

    def get_entity_by_uid(self, entity_uid):
        for _, map_obj in self.maps.items():
            entity = map_obj.entity_by_uid(entity_uid)
            if entity:
                return entity
        return None

    def get_background_image_for_user(self, username):
        name, _ = self.current_map_for_user.get(username, ('index', self.maps['index']))
        return 'maps/' + name + '.png'

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
        self.output_logger.log("Battle started.")
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
                                  'message': map_image_url})
        self.socketio.emit('message', {'type': 'initiative', 'message': {}})
        self.socketio.emit('message', {'type': 'turn', 'message': {}})

    def get_available_maps(self):
        return list(self.maps.keys())

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

        if start_battle and add_to_initiative:
            # Helper to select the correct controller for an entity
            def get_controller(entity):
                if isinstance(entity, PlayerCharacter):
                    return self.get_controller_for_entity(entity)
                if entity.familiar():
                    return self.get_controller_for_entity(entity.owner)
                elif self.npc_controller == 'manual':
                        web_controllers = WebController(self.game_session, None)
                        web_controllers.add_user("dm")
                        return web_controllers
                return GenericController(self.game_session)
            battle_music = 'battle'
            if not self.battle:
                self.battle = Battle(self.game_session, self.maps, animation_log_enabled=True)
                for entity, group in add_to_initiative:

                    # For bosses, use their battle music
                    if entity.battle_music:
                        battle_music = entity.battle_music
                        self.logger.info(f"Using battle music {battle_music} for {entity.name}")
                    controller = get_controller(entity)
                    if not controller:
                        self.logger.error(f"Controller not found for {entity}")
                        controller = GenericController(self.game_session)

                    controller.register_handlers_on(entity)
                    self.battle.add(entity, group, controller=controller)
                self.output_logger.log("Battle started.")

                # if battle sound is present, start playing it
                for soundtrack in self.soundtracks:
                    if battle_music.lower()==soundtrack['name'].lower():
                        self.play_soundtrack(soundtrack['name'])
                        break

                self.battle.start()
                self.execute_game_loop()
            else:
                for entity, group in add_to_initiative:
                    controller = get_controller(entity)
                    controller.register_handlers_on(entity)
                    self.battle.add(entity, group, add_to_initiative=True, controller=controller)

            self.socketio.emit('message', { 'type': 'initiative','message': {'index': self.battle.current_turn_index}})
            self.socketio.emit('message', { 'type': 'turn', 'message': {}})


    def get_controller_for_entity(self, entity):
        return self.web_controllers.get(entity, None)

    def get_web_controllers_for_user(self, username, default_controller = None):
        controller_list = []
        for k, _controller in self.web_controllers.items():
            if username in _controller.get_users():
                controller_list.append(_controller)
        return controller_list

    def entity_owners(self, entity):
        if hasattr(entity, 'owner'):
            entity_uid = entity.owner.entity_uid
        else:
            entity_uid = entity.entity_uid

        ctrl_info = next((controller for controller in self.controllers if controller['entity_uid'] == entity_uid), None)
        return [] if not ctrl_info else ctrl_info['controllers']

    def entities_owned_by(self, entity):
        entities = []
        for _, map_obj in self.maps.items():
            for e in map_obj.entities:
                if e.owner == entity:
                    entities.append(e)
        return entities

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
            current_soundtrack = None
            self.socketio.emit('message', {'type': 'stoptrack', 'message': {}})
        else:
            for soundtrack in self.soundtracks:
                url = soundtrack['file']

                if track_id != soundtrack['name']:
                    continue

                if self.current_soundtrack:
                    if self.current_soundtrack['name'] != soundtrack['name']:
                        current_time_in_seconds = int(time.time())
                        current_soundtrack = {'url': url, 'id': track_id, 'start_time': current_time_in_seconds}
                        soundtrack['time'] = 0
                        self.logger.info(f"Playing soundtrack {current_soundtrack}")
                        self.socketio.emit('message', { 'type': 'track', 'message': current_soundtrack })
                        self.current_soundtrack = soundtrack
                        break
                    else:
                        time_s = (time.time() - self.current_soundtrack
                        ['start_time']) % self.current_soundtrack['duration']
                        self.current_soundtrack['time'] = time_s
                        self.logger.info(f"Playing soundtrack {self.current_soundtrack}")
                        self.socketio.emit('message', { 'type': 'track', 'message': self.current_soundtrack})
                else:
                    current_soundtrack = {'url': url, 'id': track_id, 'start_time': time.time()}
                    self.logger.info(f"Playing soundtrack {current_soundtrack}")
                    self.socketio.emit('message', {'type': 'track', 'message': current_soundtrack})
                    self.current_soundtrack = soundtrack
                    break

    def list_states(self):
        return self.save_states

    def save_game(self):
        index = self.current_save_index % self.max_save_states
        file_name = f"save_{index}.yml"
        serializer = Serialization()
        yaml_str = serializer.serialize(self.game_session, self.battle, self.maps)
        if self.gzip:
            with gzip.open(f"{file_name}.gz", 'wb') as f:
                f.write(yaml_str.encode('utf-8'))
        else:
            with open(file_name, 'w') as f:
                f.write(yaml_str)

        self.save_states.append(file_name)
        with open('last_save.txt', 'w') as f:
            f.write(f"{file_name},{index}")
        self.current_save_index += 1

    def load_save(self, index=None):
        if index is None:
            index = len(self.save_states) - 1
            if index < 0:
                return

        save_state = self.save_states[index]
        if self.gzip:
            with gzip.open(f"{save_state}.gz", 'rb') as f:
                state = f.read().decode('utf-8')
        else:
            with open(save_state, 'r') as f:
                state = f.read()
        serializer = Serialization()
        new_session, new_battle, new_maps = serializer.deserialize(state)
        self.game_session = new_session
        self.battle = new_battle

        self.battle_map = new_maps['index']
        self.maps = new_maps
        self.save_states.pop(index)


    def end_current_battle(self):
        self.trigger_event('on_battle_end')
        self.set_current_battle(None)
        # revert to background musing if present
        for soundtrack in self.soundtracks:
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
