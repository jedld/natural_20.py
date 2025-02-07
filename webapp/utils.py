from collections import deque
import time
import os
import yaml
from natural20.map import Map
from natural20.battle import Battle
from webapp.controller.web_controller import WebController, ManualControl
import uuid

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


class GameManagement:
    def __init__(self, game_session, map_location, socketio, output_logger, tile_px):
        self.map_location = map_location
        self.game_session = game_session
        self.socketio = socketio
        self.output_logger = output_logger
        self.tile_px = tile_px
        self.waiting_for_user = False
        self.waiting_for_reaction = False

        if os.path.exists('save.yml'):
            with open('save.yml','r') as f:
                map_dict = yaml.safe_load(f)
                self.battle_map = Map.from_dict(game_session, map_dict)
        else:
            self.battle_map = Map(game_session, self.map_location)
        self.battle = None
        self.trigger_handlers = {}
        self.callbacks = {}

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

    def loop_environment(self):
        # check all entities in the map if it would set off a battle
        entity_by_groups = {}

        for entity in self.battle_map.entities:
            if entity.group not in entity_by_groups:
                entity_by_groups[entity.group] = set()
            entity_by_groups[entity.group].add(entity)
        start_battle = False
        add_to_initiative = []
        for group1 in entity_by_groups.keys():
            for group2 in entity_by_groups.keys():
                if group1 == group2:
                    continue
                if self.game_session.opposing(group1, group2):
                    for entity1 in entity_by_groups[group1]:
                        for entity2 in entity_by_groups[group2]:
                            if self.battle_map.can_see(entity1, entity2):
                                add_to_initiative.append((entity1, group1))
                                add_to_initiative.append((entity2, group2))
                                start_battle = True

        if start_battle and len(add_to_initiative) > 0:
            battle = Battle(self.game_session, self.battle_map, animation_log_enabled=True)
            self.set_current_battle(battle)
            for entity, group in add_to_initiative:
                battle.add(entity, group)
            battle.start_turn()
            self.game_loop()


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