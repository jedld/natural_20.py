from collections import deque
import time
import os
import yaml
from natural20.map import Map
from natural20.battle import Battle
from natural20.generic_controller import GenericController
from webapp.controller.web_controller import WebController, ManualControl
from natural20.player_character import PlayerCharacter
import uuid
import pdb
from itertools import combinations
import logging

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
                 auto_battle=True, system_logger=None):
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
        self.controllers = controllers
        self.auto_battle = auto_battle
        self.web_controllers = {}
        self.maps = {}
        self.pov_entity_for_user = {}
        self.current_map_for_user = {}
        if not system_logger:
            self.logger = logging.getLogger(__name__)
            self.logger.setLevel(logging.INFO)
        else:
            self.logger = system_logger

        if os.path.exists('save.yml'):
            with open('save.yml','r') as f:
                map_dict = yaml.safe_load(f)
                self.battle_map = Map.from_dict(game_session, map_dict)
        else:
            self.logger.info(f"Loading map from {self.map_location}")
            self.battle_map = Map(game_session, self.map_location, name='index')

        self.maps['index'] = self.battle_map

        if other_maps:
            for name, map_location in other_maps.items():
                self.logger.info(f"Loading map {name} from {map_location}")
                self.maps[name] = Map(game_session, map_location, name=name)

        # add links to the other maps
        for _, map_obj in self.maps.items():
            for name, linked_map in self.maps.items():
                if map_obj!=linked_map:
                    map_obj.add_linked_map(name, linked_map)

        self.battle = None
        self.trigger_handlers = {}
        self.callbacks = {}

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
        self.battle_map = battle_map

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

        for battle_map in self.maps.values():
            for entity in battle_map.entities:
                if entity.group not in entity_by_groups:
                    entity_by_groups[entity.group] = set()
                entity_by_groups[entity.group].add(entity)


            for group1, group2 in combinations(entity_by_groups.keys(), 2):
                if self.game_session.opposing(group1, group2):
                    for entity1 in entity_by_groups[group1]:
                        if not entity1.conscious():
                            continue

                        for entity2 in entity_by_groups[group2]:
                            if not entity2.conscious():
                                continue

                            # Ignore if both entities already belong to an ongoing battle
                            if self.battle and (entity1 in self.battle.entities and entity2 in self.battle.entities):
                                continue

                            if battle_map.can_see(entity1, entity2):
                                add_to_initiative_set.add((entity1, group1))
                                add_to_initiative_set.add((entity2, group2))

                                # Add allies for entity1
                                for ally in entity_by_groups[group1]:
                                    if ally != entity1 and battle_map.can_see(ally, entity1):
                                        add_to_initiative_set.add((ally, group1))

                                # Add allies for entity2
                                for ally in entity_by_groups[group2]:
                                    if ally != entity2 and battle_map.can_see(ally, entity2):
                                        add_to_initiative_set.add((ally, group2))

                                start_battle = True
        add_to_initiative = list(add_to_initiative_set)

        if start_battle and add_to_initiative:
            # Helper to select the correct controller for an entity
            def get_controller(entity, default_controller):
                if isinstance(entity, PlayerCharacter):
                    usernames = self.entity_owners(entity)
                    return default_controller if not usernames else self.get_web_controller_user(usernames[0], default_controller)
                return GenericController(self.game_session)

            dm_controller = self.get_web_controller_user("dm", GenericController(self.game_session))

            if not self.battle:
                self.battle = Battle(self.game_session, self.maps, animation_log_enabled=True)
                for entity, group in add_to_initiative:
                    controller = get_controller(entity, dm_controller)
                    controller.register_handlers_on(entity)
                    self.battle.add(entity, group, controller=controller)
                self.output_logger.log("Battle started.")
                self.battle.start()
                self.execute_game_loop()
            else:
                for entity, group in add_to_initiative:
                    controller = get_controller(entity, dm_controller)
                    controller.register_handlers_on(entity)
                    self.battle.add(entity, group, add_to_initiative=True, controller=controller)

            self.socketio.emit('message', { 'type': 'initiative','message': {'index': self.battle.current_turn_index}})
            self.socketio.emit('message', { 'type': 'turn', 'message': {}})


    def get_controllers(self, entity):
        # [{'entity_uid': 'gomerin', 'controllers': ['gomerin', 'shorvalu', 'leandro']}, {'entity_uid': 'crysania', 'controllers': ['crysania', 'shorvalu']}, {'entity_uid': 'shorvalu', 'controllers': ['shorvalu', 'keo']}, {'entity_uid': 'rumblebelly', 'controllers': ['rumblebelly', 'gomerin', 'shorvalu', 'jm']}]
        for entity_info in self.controllers:
            if entity_info['entity_uid'] == entity.entity_uid:
                for controller_name in entity_info['controllers']:
                    if controller_name in self.controllers:
                        return self.controllers[controller_name]
        return self.controllers

    def get_web_controller_user(self, username, default_controller = None):
        if username in self.web_controllers:
            return self.web_controllers[username]
        else:
            self.web_controllers[username] = default_controller
        return self.web_controllers[username]

    def entity_owners(self, entity):
        if hasattr(entity, 'owner'):
            entity_uid = entity.owner.entity_uid
        else:
            entity_uid = entity.entity_uid

        ctrl_info = next((controller for controller in self.controllers if controller['entity_uid'] == entity_uid), None)
        return [] if not ctrl_info else ctrl_info['controllers']

    def game_loop(self):
        battle = self.get_current_battle()
        try:
            while True:
                battle.start_turn()
                current_turn = self.get_current_battle().current_turn()
                current_turn.reset_turn(battle)

                if battle.battle_ends():
                    self.end_current_battle()
                    return

                while current_turn.dead() or current_turn.unconscious():
                    current_turn.resolve_trigger('end_of_turn')
                    battle.end_turn()
                    battle.next_turn()
                    current_turn = battle.current_turn()
                    battle.start_turn()
                    current_turn.reset_turn(battle)

                    if battle.battle_ends():
                        self.end_current_battle()
                        return


                self.ai_loop()
                current_turn.resolve_trigger('end_of_turn')

                if battle.battle_ends():
                    self.end_current_battle()
                    break

                battle.end_turn()
                self.loop_environment()
                battle.next_turn()

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

    def end_current_battle(self):
        self.trigger_event('on_battle_end')
        self.set_current_battle(None)
        self.socketio.emit('message', {'type': 'console', 'message': 'Battle has ended.'})
        self.socketio.emit('message', {'type': 'stop', 'message': {}})