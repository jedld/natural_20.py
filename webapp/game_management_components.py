import sys
import time

from natural20.generic_controller import GenericController
from natural20.llm_controller import LlmMcpController
from natural20.player_character import PlayerCharacter
from natural20.web.web_controller import WebController


class GameEntityRegistry:
    def __init__(self, manager):
        self.manager = manager

    def defer_all_players(self):
        deferred_ids = set()
        for entity_map in self.manager.maps.values():
            for entity in list(entity_map.entities.keys()):
                if not isinstance(entity, PlayerCharacter):
                    continue

                entity_uid = str(getattr(entity, 'entity_uid', '') or '')
                if not entity_uid or entity_uid in deferred_ids:
                    continue

                position = list(entity_map.position_of(entity))
                entity_map.remove(entity)
                self.manager.deferred_players[entity_uid] = {
                    'entity': entity,
                    'map_name': entity_map.name,
                    'position': position,
                }
                deferred_ids.add(entity_uid)
                self.manager.logger.info(f"Deferred spawn for {entity_uid} at {position} on map {entity_map.name}")

    def spawn_player_for_user(self, username):
        spawned = []
        for controller in self.manager.controllers:
            if username not in controller['controllers']:
                continue
            entity_uid = str(controller['entity_uid'])
            deferred = self.manager.deferred_players.get(entity_uid)
            if deferred is None:
                continue
            entity = deferred['entity']
            map_name = deferred['map_name']
            position = deferred['position']
            target_map = self.manager.maps.get(map_name)
            if target_map is None:
                continue
            pos_x, pos_y = position
            if not target_map.placeable(entity, pos_x, pos_y):
                pos_x, pos_y = target_map.find_empty_placeable_position(entity, pos_x, pos_y)
                self.manager.logger.info(f"Original position {position} occupied, using {pos_x},{pos_y} for {entity_uid}")
            target_map.place((pos_x, pos_y), entity)
            del self.manager.deferred_players[entity_uid]
            spawned.append(entity)
            self.manager.logger.info(f"Spawned {entity_uid} at ({pos_x},{pos_y}) on map {map_name} for user {username}")
        return spawned

    def get_pov_entity_for_user(self, username):
        # Reduced logging verbosity - info-level logging on every lookup was causing I/O overhead
        # self.manager.logger.debug(f"Getting POV entity for {username}")
        return self.manager.pov_entity_for_user.get(username, None)

    def set_pov_entity_for_user(self, username, entity):
        if entity:
            self.manager.logger.info(f"Setting POV entity for {username} to {entity.name}")
        self.manager.pov_entity_for_user[username] = entity

    def switch_map_for_user(self, username, map_name):
        self.manager.logger.info(f"Switching map for {username} to {map_name}")
        self.manager.current_map_for_user[username] = (map_name, self.manager.maps[map_name])
        try:
            from natural20.companion import sync_companions_on_map_switch
            game_properties = getattr(self.manager.game_session, 'game_properties', None)
            if game_properties:
                sync_companions_on_map_switch(self.manager.game_session, game_properties, username, map_name)
        except Exception:
            pass

    def get_map_for_user(self, username):
        if 'index' not in self.manager.maps:
            return list(self.manager.maps.values())[0]
        _name, battle_map = self.manager.current_map_for_user.get(username, ('index', self.manager.maps['index']))
        return battle_map

    def get_map_for_entity(self, entity):
        for _name, map_obj in self.manager.maps.items():
            if isinstance(entity, str):
                mapped_entity = map_obj.get_entity_by_uid(entity)
            else:
                mapped_entity = entity

            if mapped_entity in map_obj.entities:
                return map_obj
        return None

    def get_entity_by_uid(self, entity_uid):
        for _name, map_obj in self.manager.maps.items():
            entity = map_obj.entity_by_uid(entity_uid)
            if entity:
                return entity
        deferred = self.manager.deferred_players.get(str(entity_uid))
        if deferred:
            return deferred['entity']
        return None

    def get_background_image_for_user(self, username):
        name, battle_map = self.manager.current_map_for_user.get(username, ('index', self.manager.maps['index']))
        if battle_map.background_image():
            return 'maps/' + battle_map.background_image()
        return 'maps/' + name + '.png'


class GameControllerRegistry:
    def __init__(self, manager):
        self.manager = manager

    def setup_controllers(self):
        for controller in self.manager.controllers:
            entity_uid = controller['entity_uid']
            self.manager.logger.info(f"Setting up controller for {entity_uid}")
            entity = self.manager.get_entity_by_uid(entity_uid)
            if entity not in self.manager.controllers:
                self.manager.web_controllers[entity] = WebController(self.manager.game_session, None)
                self.manager.web_controllers[entity].add_user('dm')

            for username in controller['controllers']:
                self.manager.web_controllers[entity].add_user(username)

    def effective_npc_combat_controller(self):
        if self.manager.force_llm_npc_combat:
            return 'llm'
        return self.manager.npc_controller

    def build_combat_controller_for_entity(self, entity):
        if isinstance(entity, PlayerCharacter):
            return self.manager.get_controller_for_entity(entity)
        if entity.familiar():
            return self.manager.get_controller_for_entity(entity.owner)

        npc_controller = self.effective_npc_combat_controller()

        if npc_controller == 'manual':
            web_controllers = WebController(self.manager.game_session, None)
            web_controllers.add_user('dm')
            return web_controllers

        if npc_controller == 'llm':
            try:
                from webapp.app import llm_handler as current_llm_handler  # type: ignore
                provider = getattr(current_llm_handler, 'current_provider', None)
            except Exception:
                provider = None
            controller_class = LlmMcpController
            utils_module = sys.modules.get('webapp.utils')
            if utils_module is not None:
                controller_class = getattr(utils_module, 'LlmMcpController', controller_class)
            return controller_class(self.manager.game_session, llm_provider=provider)

        return GenericController(self.manager.game_session)

    def get_controller_for_entity(self, entity):
        return self.manager.web_controllers.get(entity, None)

    def get_web_controllers_for_user(self, username, default_controller=None):
        controller_list = []
        for _entity, controller in self.manager.web_controllers.items():
            if username in controller.get_users():
                controller_list.append(controller)
        return controller_list

    def entity_owners(self, entity):
        owner = getattr(entity, 'owner', None)
        if owner is not None and getattr(owner, 'entity_uid', None) is not None:
            entity_uid = owner.entity_uid
        else:
            entity_uid = entity.entity_uid

        ctrl_info = next((controller for controller in self.manager.controllers if controller['entity_uid'] == entity_uid), None)
        return [] if not ctrl_info else ctrl_info['controllers']

    def entities_owned_by(self, entity):
        entities = []
        for _name, map_obj in self.manager.maps.items():
            for candidate in map_obj.entities:
                if candidate.owner == entity:
                    entities.append(candidate)
        return entities


class ShortTermGoalManager:
    def __init__(self, manager):
        self.manager = manager

    def schedule_short_term_goal(self, entity, goal_text, speaker=None):
        if entity is None:
            return None

        goal_text = (goal_text or '').strip()
        if not goal_text:
            return None

        goal_id = str(entity.entity_uid)
        requester_uid = getattr(speaker, 'entity_uid', None) if speaker is not None else None
        goal_record = {
            'entity_uid': goal_id,
            'goal': goal_text,
            'status': 'active',
            'created_at_game_time': self.manager.game_session.game_time,
            'updated_at_game_time': self.manager.game_session.game_time,
            'next_run_at': time.time() + self.manager.goal_turn_seconds,
            'attempts': 0,
            'history': [],
            'requester_uid': requester_uid,
            'last_error': None,
            'running': False,
        }
        with self.manager.game_state_lock:
            self.manager.short_term_goals[goal_id] = goal_record
        return goal_record

    def get_short_term_goal(self, entity):
        if entity is None:
            return None
        return self.manager.short_term_goals.get(str(entity.entity_uid))

    def record_short_term_goal_history(self, entity, entry):
        if entity is None:
            return None
        goal = self.manager.short_term_goals.get(str(entity.entity_uid))
        if goal is None:
            return None
        goal['history'].append(entry)
        goal['history'] = goal['history'][-12:]
        goal['updated_at_game_time'] = self.manager.game_session.game_time
        return goal

    def complete_short_term_goal(self, entity, status='completed', reason=None):
        if entity is None:
            return None
        goal = self.manager.short_term_goals.get(str(entity.entity_uid))
        if goal is None:
            return None
        goal['status'] = status
        goal['running'] = False
        goal['next_run_at'] = None
        goal['last_error'] = reason
        goal['updated_at_game_time'] = self.manager.game_session.game_time
        if reason:
            goal['history'].append({
                'time': self.manager.game_session.game_time,
                'event': status,
                'reason': reason,
            })
            goal['history'] = goal['history'][-12:]
        return goal

    def goal_worker(self):
        while not self.manager._goal_thread_stop.is_set():
            if self.manager.get_current_battle() or not self.manager.short_term_goals:
                self.manager._goal_thread_stop.wait(self.manager.goal_poll_interval)
                continue

            due_goal_ids = []
            now = time.time()
            with self.manager.game_state_lock:
                for goal_id, goal in self.manager.short_term_goals.items():
                    if goal.get('status') != 'active':
                        continue
                    if goal.get('running'):
                        continue
                    next_run_at = goal.get('next_run_at')
                    if next_run_at is None or next_run_at > now:
                        continue
                    goal['running'] = True
                    due_goal_ids.append(goal_id)

            for goal_id in due_goal_ids:
                try:
                    from webapp import app as app_module
                    app_module.entity_rag_handler.execute_scheduled_goal(goal_id, app_module.llm_conversation_handler)
                except Exception as exc:
                    self.manager.logger.error(f"Failed to execute short-term goal for {goal_id}: {exc}")
                    entity = self.manager.get_entity_by_uid(goal_id)
                    if entity is not None:
                        self.record_short_term_goal_history(entity, {
                            'time': self.manager.game_session.game_time,
                            'event': 'error',
                            'reason': str(exc),
                        })
                finally:
                    with self.manager.game_state_lock:
                        goal = self.manager.short_term_goals.get(goal_id)
                        if goal is not None:
                            goal['running'] = False
                            if goal.get('status') == 'active':
                                goal['attempts'] = goal.get('attempts', 0) + 1
                                goal['next_run_at'] = time.time() + self.manager.goal_turn_seconds
                                goal['updated_at_game_time'] = self.manager.game_session.game_time

            self.manager._goal_thread_stop.wait(self.manager.goal_poll_interval)