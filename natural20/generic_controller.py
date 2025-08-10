from natural20.actions.look_action import LookAction
from natural20.actions.stand_action import StandAction
from natural20.actions.attack_action import AttackAction
from natural20.actions.spell_action import SpellAction
from natural20.actions.dodge_action import DodgeAction
# from natural20.actions.prone_action import ProneAction
from natural20.actions.move_action import MoveAction
from natural20.gym.types import EnvObject, Environment
from natural20.entity import Entity
from natural20.action import Action
from natural20.controller import Controller
from natural20.ai.path_compute import PathCompute
from natural20.utils.movement import retrieve_opportunity_attacks
from natural20.item_library.door_object import DoorObject
from natural20.item_library.trap_door import TrapDoor
import math
import copy
import pdb

class GenericController(Controller):
    # Consider a broader set so AI can open doors, reposition, or defend
    VALID_AI_MOVE_TYPES = [
        "attack",
        "spell",
        "move",
        "interact",
        "dash",
        "disengage",
        "dodge",
        "hide",
        "look"
    ]

    def __init__(self, session, valid_move_types=None):
        self.state = {}
        self.session = session
        self.battle_data = {}
        self.valid_moves_types = valid_move_types or self.VALID_AI_MOVE_TYPES

    def to_dict(self):
        return {
            "session": self.session,
            "state": self.state,
            "battle_data": self.battle_data
        }
    
    @staticmethod
    def from_dict(data):
        controller = GenericController(data['session'])
        controller.battle_data = data['battle_data']
        return controller

    # @param entity [Natural20::Entity]
    def register_handlers_on(self, entity):
        entity.attach_handler("opportunity_attack", self.opportunity_attack_listener)

    def begin_turn(self, entity):
        # print(f"{entity.name} begins turn")
        pass

    def roll_for(self, entity, stat, advantage=False, disadvantage=False):
        return None

    def legendary_action_listener(self, battle, session, entity, map, event):
        valid_actions = []
        if entity.total_legendary_actions(battle) > 0:
            actions = [s for s in entity.available_actions(session, battle, legendary_actions=True)]
            for action in actions:
                    valid_targets = battle.valid_targets_for(entity, action)
                    if event['target'] in valid_targets:
                        action.target = event['target']
                        action.legendary_action = True
                        valid_actions.append(action)
            selected_action = self.select_action(battle, entity, valid_actions )
            return selected_action
        return None


    def opportunity_attack_listener(self, battle, session, entity, map, event):
        actions = [s for s in entity.available_actions(session, battle, opportunity_attack=True)]
        print(f"Opportunity attack: {actions}")
        valid_actions = []
        for action in actions:
            valid_targets = battle.valid_targets_for(entity, action)
            if event['target'] in valid_targets:
                action.target = event['target']
                action.as_reaction = True
                valid_actions.append(action)
        selected_action = self.select_action(battle, entity, valid_actions )

        return selected_action

    def select_action(self, battle, entity, available_actions = None) -> Action:
        if available_actions is None:
            available_actions = []
        if len(available_actions) > 0:
            action = self._sort_actions(entity, battle, available_actions)
            if len(action) > 0:
                return action[0]
        # no action, end turn
        return None

    def select_reaction(self, entity, battle, map, valid_actions, event):
        if len(valid_actions) == 0:
            return None
        action = self._sort_actions(entity, battle, valid_actions)[0]
        return action

    def move_for(self, entity: Entity, battle):
        # choose available moves at random and return it
        available_actions = self._compute_available_moves(entity, battle)
        # environment, entity = self._build_environment(battle, entity)
        selected_action = self.select_action(battle, entity, available_actions)
        if isinstance(selected_action, MoveAction):
            battle_data = self._battle_data(battle, entity)
            for p in selected_action.move_path:
                battle_data['visited_location'][tuple(p)] = True
        return selected_action

    # Build a suitable environment for Reinforcement Learning
    def _build_environment(self, battle, entity):
        enemy_positions = {}
        self._observe_enemies(battle, entity, enemy_positions)
        objects = []

        for enemy, location in enemy_positions.items():
            equipped_items = []
            for item in enemy.equipped_items():
                equipped_items.append(item['name'])
            is_enemy = enemy in battle.opponents_of(entity)
            env_object = EnvObject(enemy.name, 'pc', enemy.hp()/enemy.max_hp(), location, equipped_items, is_enemy=is_enemy)
            objects.append(env_object)
        environment = Environment(battle.map, objects, {
            "available_movement" : entity.available_movement(battle),
            "available_actions" : entity.total_actions(battle),
            "available_reactions" : entity.total_reactions(battle),
            "available_bonus_actions" : entity.total_bonus_actions(battle)
        })
        # clone a copy of entity
        entity = copy.deepcopy(entity)
        return environment, entity

    # gain information about enemies in a fair and realistic way (e.g. using line of sight)
    # @param battle [Natural20::Battle]
    # @param entity [Natural20::Entity]
    def _observe_enemies(self, battle, entity, enemy_positions=None):
        if enemy_positions is None:
            enemy_positions = {}
        current_map = battle.map_for(entity)
        objects_around_me = current_map.look(entity)

        entity_x, entity_y = current_map.position_of(entity)

        for object, location in objects_around_me.items():
            group = battle.entity_group_for(object)
            if group == "none":
                continue
            if not group:
                continue
            if not object.conscious():
                continue
            if battle.opposing(entity, object):
                path = PathCompute(battle, current_map, entity, ignore_opposing=True).compute_path(
                    entity_x, entity_y, location[0], location[1]
                )
                enemy_positions[object] = (location, path)

        # Update memory: track last known enemy locations and investigation targets
        battle_data = self._battle_data(battle, entity)
        known_positions = battle_data['known_enemy_positions']
        investigate_location = battle_data['investigate_location']

        # Record current sightings
        for enemy, (loc, _path) in enemy_positions.items():
            known_positions[enemy] = tuple(loc)
            # Seeing an enemy clears any investigate marker at that exact location
            if tuple(loc) in investigate_location:
                investigate_location.pop(tuple(loc), None)

        # If we previously saw enemies that are no longer visible, mark their last known
        # position as an investigation target (if still reachable on this map)
        invisible_known = [e for e in list(known_positions.keys()) if e not in enemy_positions]
        for e in invisible_known:
            try:
                last_loc = known_positions.get(e)
                if last_loc is None:
                    continue
                # Only keep markers on same map
                if battle.map_for(e) == current_map:
                    investigate_location.setdefault(tuple(last_loc), {"priority": 1.0, "age": 0})
            except Exception:
                # If entity e no longer exists on map, discard
                known_positions.pop(e, None)

    def _initialize_battle_data(self, battle, entity):
        if battle not in self.battle_data:
            self.battle_data[battle] = {}
        if entity not in self.battle_data[battle]:
            self.battle_data[battle][entity] = {
                'known_enemy_positions': {},
                'hiding_spots': {},
                'investigate_location': {},
                'visited_location': {}
            }

    def _compute_available_moves(self, entity, battle):
        self._initialize_battle_data(battle, entity)

        battle_data = self._battle_data(battle, entity)
        investigate_location = battle_data['investigate_location']

        enemy_positions = {}
        self._observe_enemies(battle, entity, enemy_positions)
        available_actions = entity.available_actions(self.session, battle)
        available_movement = entity.available_movement(battle)
        # generate available targets
        valid_actions = []

        # Proactive look when we can't see enemies
        # - If we have no targets in sight and no investigation leads and can't move, use Look
        look_added = False
        if len(enemy_positions.keys()) == 0 and len(investigate_location) == 0 and \
            available_movement == 0 and LookAction.can(entity, battle):
            valid_actions.append(LookAction(self.session, entity, "look"))
            look_added = True

        # If we have no visible enemies but we can move, also allow Look as an option
        if len(enemy_positions.keys()) == 0 and LookAction.can(entity, battle) and not look_added:
            valid_actions.append(LookAction(self.session, entity, "look"))
            look_added = True

        if len(enemy_positions.keys()) == 0 and entity.available_movement(battle) == 0 and DodgeAction.can(entity, battle):
            valid_actions.append(DodgeAction(None, entity, "dodge"))

        # try to stand if prone
        if entity.prone() and StandAction.can(entity, battle):
            valid_actions.append(StandAction(None, entity, "stand"))

        for action in available_actions:
            if action.action_type in self.valid_moves_types:
                # Avoid appending duplicate LookActions
                if isinstance(action, LookAction) and look_added:
                    continue
                if isinstance(action, LookAction):
                    look_added = True
                valid_actions.append(action)

        return valid_actions

    def _get_enemy_positions(self, battle, entity):
        enemy_positions = {}
        self._observe_enemies(battle, entity, enemy_positions)
        return enemy_positions

    def _battle_data(self, battle, entity):
        if battle not in self.battle_data:
            self.battle_data[battle] = {}
        if entity not in self.battle_data[battle]:
            self.battle_data[battle][entity] = {
                'known_enemy_positions': {},
                'hiding_spots': {},
                'investigate_location': {},
                'visited_location': {}
            }
        return self.battle_data[battle][entity]

    # Sort actions based on success rate and damage
    def _sort_actions(self, entity, battle, available_actions):
        """
        Simple rules for performing combat actions:
        - Attack if available
        - Move towards the closest enemy
        """

        current_map = battle.map_for(entity)
        enemy_positions = self._get_enemy_positions(battle, entity)
        battle_data = self._battle_data(battle, entity)
        investigate_location = battle_data['investigate_location']
        visited_location = battle_data['visited_location']

        # Build target-driven movement scores
        def build_move_scores():
            scores = {}
            targets = []
            # Visible enemies first
            for _, (loc, path) in enemy_positions.items():
                if path is None or len(path) < 2:
                    continue
                targets.append(tuple(loc))
            # Then investigation spots if no visible enemies
            if not targets and len(investigate_location) > 0:
                targets = list(investigate_location.keys())
            # If still nothing to go on, head to doors we can potentially open
            if not targets:
                door_adjacents = []
                for obj, pos in current_map.interactable_objects.items():
                    if not isinstance(obj, (DoorObject, TrapDoor)):
                        continue
                    # Consider only closed, visible doors
                    try:
                        is_closed = hasattr(obj, 'closed') and obj.closed()
                    except Exception:
                        is_closed = False
                    if not is_closed:
                        continue
                    if not current_map.can_see(entity, obj):
                        continue
                    dx, dy = pos
                    # Candidate squares where inside_range_for_opening would be true
                    facing = getattr(obj, 'facing', lambda: 'up')()
                    offsets = {
                        'up': [(0, -1), (0, 1)],
                        'down': [(0, 1), (0, -1)],
                        'left': [(-1, 0), (1, 0)],
                        'right': [(1, 0), (-1, 0)]
                    }.get(facing, [(0, -1), (0, 1), (-1, 0), (1, 0)])
                    for ox, oy in offsets:
                        tx, ty = dx + ox, dy + oy
                        # Only consider tiles on the map, passable and placeable
                        if 0 <= tx < current_map.size[0] and 0 <= ty < current_map.size[1]:
                            if current_map.bidirectionally_passable(entity, tx, ty, (dx, dy), battle, allow_squeeze=False) and \
                               current_map.placeable(entity, tx, ty, battle, squeeze=False):
                                door_adjacents.append((tx, ty))
                # Deduplicate
                targets = list({t for t in door_adjacents}) if door_adjacents else targets

            # Precompute path to each target and score the first step towards the closest one
            if not targets:
                return scores

            ex, ey = current_map.position_of(entity)
            path_compute = PathCompute(battle, current_map, entity, ignore_opposing=True)
            # Compute to multiple destinations
            paths = path_compute.compute_paths_to_multiple_destinations(ex, ey, targets)
            for dest, path in paths.items():
                if not path or len(path) < 2:
                    continue
                first_step = tuple(path[1])
                distance = len(path)
                # Prefer shorter paths
                base = 1.0 / max(1, distance)
                # Exploration bonus: prefer unvisited squares
                if first_step not in visited_location:
                    base += 0.1
                # Age-based investigate boost
                if dest in investigate_location:
                    base += 0.2 + 0.05 * investigate_location[dest].get('age', 0)
                scores[first_step] = max(scores.get(first_step, 0), base)
            return scores

        move_square_score = build_move_scores()

        def score_interact(action):
            # Favor opening doors when no enemies are visible or target investigation requires it
            if not hasattr(action, 'target') or action.target is None:
                return 0
            target = action.target
            act_name = action.object_action_name() if hasattr(action, 'object_action_name') else None
            score = 0
            if isinstance(target, (DoorObject, TrapDoor)):
                # Opening a closed door is valuable for exploration or chasing last-known positions
                if act_name == 'open' or act_name == 'unlock' or act_name == 'lockpick':
                    score = 0.6
                    # If we have investigate targets on the other side (rough heuristic: door blocks LOS now)
                    if len(enemy_positions) == 0 and len(investigate_location) > 0:
                        score += 0.3
            return score

        sorted_actions = []
        for action in available_actions:
            if isinstance(action, AttackAction) or isinstance(action, SpellAction):
                base_score = action.compute_hit_probability(battle) * action.avg_damage(battle)
                sorted_actions.append((action, base_score))
            elif isinstance(action, MoveAction):
                new_position = action.move_path[-1]
                position_key = (new_position[0], new_position[1])
                score = move_square_score.get(position_key, 0)

                # avoid opportunity attacks
                opportunity_list = retrieve_opportunity_attacks(entity, action.move_path, battle)
                if len(opportunity_list) > 0:
                    # Strongly deprioritize; keep as last resort if truly stuck
                    score -= 1.0

                sorted_actions.append((action, score))
            elif action.action_type == 'interact':
                sorted_actions.append((action, score_interact(action)))
            elif action.action_type == 'look':
                # Look is useful when we can't see anyone
                score = 0.3 if len(enemy_positions) == 0 else 0.0
                sorted_actions.append((action, score))
            elif action.action_type in ('dash', 'disengage', 'dodge', 'hide'):
                # Mild default value; will be preferred only when other options are poor
                sorted_actions.append((action, 0.1))
            else:
                sorted_actions.append((action, 0))

        # Sort by score desc
        sorted_actions.sort(key=lambda a: a[1], reverse=True)
        # Age investigation markers to decay/boost choices over time
        for k in list(investigate_location.keys()):
            investigate_location[k]['age'] = investigate_location[k].get('age', 0) + 1
        return [a[0] for a in sorted_actions]