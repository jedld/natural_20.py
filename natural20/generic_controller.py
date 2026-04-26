from natural20.actions.look_action import LookAction
from natural20.actions.stand_action import StandAction
from natural20.actions.attack_action import AttackAction
from natural20.actions.spell_action import SpellAction
from natural20.actions.dodge_action import DodgeAction
# from natural20.actions.prone_action import ProneAction
from natural20.actions.move_action import MoveAction
from natural20.actions.second_wind_action import SecondWindAction
from natural20.actions.use_item_action import UseItemAction
from natural20.actions.first_aid_action import FirstAidAction
from natural20.actions.lay_on_hands_action import LayOnHandsAction
from natural20.actions.help_action import HelpAction
from natural20.actions.shove_action import ShoveAction
from natural20.actions.grapple_action import GrappleAction
from natural20.gym.types import EnvObject, Environment
from natural20.entity import Entity
from natural20.action import Action
from natural20.controller import Controller
from natural20.ai.path_compute import PathCompute
from natural20.utils.movement import retrieve_opportunity_attacks, simplify_path
from natural20.utils.action_builder import autobuild
from natural20.item_library.door_object import DoorObject
from natural20.item_library.trap_door import TrapDoor
import math
import copy
import pdb
from typing import Optional

class GenericController(Controller):
    # Consider a broader set so AI can open doors, reposition, or defend
    VALID_AI_MOVE_TYPES = [
        "attack",
        "spell",
        "move",
        "interact",
        "use_item",
        "first_aid",
        "lay_on_hands",
        "second_wind",
        "dash",
        "dash_bonus",
        "disengage",
        "disengage_bonus",
        "dodge",
        "hide",
        "hide_bonus",
        "help",
        "shove",
        "grapple",
        "drop_grapple",
        "escape_grapple",
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

    def select_action(self, battle, entity, available_actions = None) -> Optional[Action]:
        if available_actions is None:
            available_actions = []
        if len(available_actions) > 0:
            action = self._sort_actions(entity, battle, available_actions)
            if len(action) > 0:
                return action[0]
        # no action, end turn
        return None

    def select_reaction(self, entity, battle, map, valid_actions, event) -> Optional[Action]:
        if len(valid_actions) == 0:
            return None
        action = self._sort_actions(entity, battle, valid_actions)[0]
        return action

    def move_for(self, entity: Entity, battle) -> Optional[Action]:
        # choose available moves at random and return it
        available_actions = self._compute_available_moves(entity, battle)
        # environment, entity = self._build_environment(battle, entity)
        scored = self._sort_actions_with_scores(entity, battle, available_actions)
        if not scored:
            return None
        selected_action, selected_score = scored[0]
        if isinstance(selected_action, MoveAction):
            # If the best available move actively makes the situation worse
            # (negative score) AND the entity is already engaged in melee,
            # forfeit the remaining movement instead of wandering. This
            # avoids NPCs that have exhausted their attacks walking away
            # from adjacent melee targets and provoking opportunity attacks.
            # We deliberately *do* allow negative-scored moves when not in
            # melee, so out-of-combat exploration still works.
            if selected_score < 0 and battle.enemy_in_melee_range(entity):
                return None
            # Remove backtracking/oscillation from move paths
            if selected_action.move_path:
                selected_action.move_path = simplify_path(selected_action.move_path)
            if not selected_action.move_path or len(selected_action.move_path) < 2:
                return None
            battle_data = self._battle_data(battle, entity)
            for p in selected_action.move_path:
                battle_data['visited_location'][tuple(p)] = True
            destination = tuple(selected_action.move_path[-1])
            recent_destinations = battle_data['recent_destinations']
            recent_destinations.append(destination)
            if len(recent_destinations) > 4:
                recent_destinations.pop(0)
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
                else:
                    # Enemy crossed onto a linked map (e.g. through stairs/portal).
                    # Seed the teleporter tile leading toward them so the NPC can
                    # chase across maps.
                    other_map = battle.map_for(e)
                    if other_map is None:
                        continue
                    try:
                        ex, ey = other_map.position_of(e)
                    except Exception:
                        continue
                    plan = PathCompute(battle, current_map, entity, ignore_opposing=True) \
                        .compute_cross_map_path(current_map, entity_x, entity_y,
                                                other_map, ex, ey)
                    if not plan:
                        continue
                    first_seg = plan[0]
                    if first_seg.get('teleporter') is None:
                        continue
                    portal_tile = tuple(first_seg['path'][-1])
                    investigate_location.setdefault(portal_tile,
                                                    {"priority": 1.5, "age": 0})
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
                'visited_location': {},
                'recent_destinations': []
            }

    def _compute_available_moves(self, entity, battle):
        self._initialize_battle_data(battle, entity)

        battle_data = self._battle_data(battle, entity)
        investigate_location = battle_data['investigate_location']

        enemy_positions = {}
        self._observe_enemies(battle, entity, enemy_positions)
        available_actions = entity.available_actions(self.session, battle)
        current_map = battle.map_for(entity)
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
                if getattr(action, 'disabled', False):
                    continue
                if getattr(action, 'target', None) is None and isinstance(action, (FirstAidAction, LayOnHandsAction, HelpAction, ShoveAction, GrappleAction)):
                    built_actions = autobuild(self.session, action.__class__, entity, battle, map=current_map)
                    if built_actions:
                        valid_actions.extend([built_action for built_action in built_actions if not getattr(built_action, 'disabled', False)])
                        continue
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
                'visited_location': {},
                'recent_destinations': []
            }
        return self.battle_data[battle][entity]

    # Sort actions based on success rate and damage
    def _sort_actions(self, entity, battle, available_actions):
        return [a for a, _ in self._sort_actions_with_scores(entity, battle, available_actions)]

    def _sort_actions_with_scores(self, entity, battle, available_actions):
        """
        Simple rules for performing combat actions:
        - Attack if available
        - Move towards the closest enemy

        Returns a list of ``(action, score)`` tuples sorted by score descending.
        """

        current_map = battle.map_for(entity)
        enemy_positions = self._get_enemy_positions(battle, entity)
        battle_data = self._battle_data(battle, entity)
        investigate_location = battle_data['investigate_location']
        visited_location = battle_data['visited_location']
        recent_destinations = battle_data['recent_destinations']

        def action_targets(action):
            target = getattr(action, 'target', None)
            if target is None:
                return []
            if isinstance(target, list):
                return [candidate for candidate in target if isinstance(candidate, Entity)]
            if isinstance(target, Entity):
                return [target]
            return []

        def has_melee_pressure(target):
            return bool(target) and target.conscious() and battle.enemy_in_melee_range(target)

        def missing_hp(target):
            return max(0, target.max_hp() - target.hp()) if target else 0

        def score_heal_target(target, expected_heal, prefer_bonus_action=False):
            if target is None:
                return 0

            target_missing_hp = missing_hp(target)
            if target_missing_hp <= 0 and not target.unconscious():
                return -0.5

            restored_hp = max(1, min(target_missing_hp if target_missing_hp > 0 else expected_heal, expected_heal))
            urgency = 1.0
            if target.unconscious():
                urgency += 3.5
            else:
                hp_ratio = target.hp() / max(1, target.max_hp())
                if hp_ratio <= 0.25:
                    urgency += 2.0
                elif hp_ratio <= 0.5:
                    urgency += 1.0

            if has_melee_pressure(target):
                urgency += 0.5
            if prefer_bonus_action:
                urgency += 0.5

            return (restored_hp / 3.0) * urgency

        def score_support_spell(action):
            spell = getattr(action, 'spell_action', None)
            if spell is None:
                return 0

            spell_name = spell.short_name()
            targets = action_targets(action)

            if action.avg_damage(battle) < 0:
                expected_heal = -action.avg_damage(battle)
                return max(score_heal_target(target, expected_heal, prefer_bonus_action=action.casting_time == 'bonus_action') for target in targets)

            if spell_name in ('bless', 'guidance', 'resistance', 'shield_of_faith', 'protection_from_poison'):
                score = 0
                for target in targets:
                    if battle.allies(entity, target):
                        if spell_name == 'protection_from_poison' and getattr(target, 'poisoned', lambda: False)():
                            score += 2.5
                            continue
                        if hasattr(target, 'has_effect') and target.has_effect(spell_name):
                            score -= 0.25
                        else:
                            score += 1.0
                            if has_melee_pressure(target):
                                score += 0.5
                if len(enemy_positions) > 0:
                    score -= 0.3
                return score

            return 0

        def score_use_item(action):
            if not isinstance(action, UseItemAction) or action.target_item is None:
                return 0

            item_name = getattr(action.target_item, 'name', None)
            if item_name == 'healing_potion':
                targets = action_targets(action) or [entity]
                return max(score_heal_target(target, expected_heal=7.0) for target in targets) - 0.35
            return 0

        def score_second_wind(action):
            if not isinstance(action, SecondWindAction):
                return 0
            fighter_level = getattr(entity, 'fighter_level', 1)
            expected_heal = 5.5 + fighter_level
            return score_heal_target(entity, expected_heal, prefer_bonus_action=True) + 0.75

        def score_first_aid(action):
            if not isinstance(action, FirstAidAction):
                return 0
            targets = action_targets(action)
            if not targets:
                return 0
            target = targets[0]
            if not battle.allies(entity, target):
                return -2.0
            if target.unconscious() and not target.stable():
                return 5.0
            return -0.5

        def score_lay_on_hands(action):
            if not isinstance(action, LayOnHandsAction):
                return 0
            target = getattr(action, 'target', None)
            if target is None:
                return 0
            if action.mode == 'cure':
                return 3.0 if action.cure_targets else 0
            expected_heal = action.heal_amt or 1
            return score_heal_target(target, expected_heal)

        def score_help(action):
            if not isinstance(action, HelpAction):
                return 0
            targets = action_targets(action)
            if not targets:
                return 0
            target = targets[0]
            if not target.conscious():
                return -1.0
            if battle.allies(entity, target):
                return 1.25 if has_melee_pressure(target) else 0.5
            # Distracting an enemy (Help against an opponent) only matters if
            # an ally is in melee range of that enemy and could capitalize on
            # the granted advantage. A lone NPC distracting a foe wastes its
            # action because no one else attacks the target.
            try:
                target_map = battle.map_for(target)
                allies_in_melee = False
                for nearby in target_map.look(target):
                    if nearby is entity or nearby is target:
                        continue
                    if not getattr(nearby, 'conscious', lambda: False)():
                        continue
                    if not battle.allies(entity, nearby):
                        continue
                    reach = max(5, nearby.melee_distance() if hasattr(nearby, 'melee_distance') else 5)
                    if target_map.distance(nearby, target) <= (reach / target_map.feet_per_grid):
                        allies_in_melee = True
                        break
                if not allies_in_melee:
                    return -0.5
            except Exception:
                return 0
            return 0.9

        def score_control_action(action):
            target = getattr(action, 'target', None)
            if target is None or not battle.opposing(entity, target):
                return 0

            base_score = 0.8
            if isinstance(action, ShoveAction):
                if target.prone():
                    base_score -= 0.5
                elif has_melee_pressure(target):
                    base_score += 0.35
            elif isinstance(action, GrappleAction):
                if target.grappled():
                    base_score -= 0.4
                elif has_melee_pressure(entity):
                    base_score += 0.35
            return base_score

        # Build target-driven movement scores
        def build_move_scores():
            scores = {}
            targets = []
            target_kind = None
            # Visible enemies first
            for _, (loc, path) in enemy_positions.items():
                if path is None or len(path) < 2:
                    continue
                targets.append(tuple(loc))
            if targets:
                target_kind = 'enemy'
            # Then investigation spots if no visible enemies
            if not targets and len(investigate_location) > 0:
                targets = list(investigate_location.keys())
                target_kind = 'investigate'
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
                if door_adjacents:
                    targets = list({t for t in door_adjacents})
                    target_kind = 'door'

            # Precompute path to each target and score the first step towards the closest one
            if not targets:
                return scores, targets, target_kind

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
            return scores, targets, target_kind

        move_square_score, move_targets, move_target_kind = build_move_scores()

        def progress_score_for(position_key):
            if not move_targets:
                return 0

            ex, ey = current_map.position_of(entity)
            path_compute = PathCompute(battle, current_map, entity, ignore_opposing=True)
            current_paths = path_compute.compute_paths_to_multiple_destinations(ex, ey, move_targets)
            destination_paths = path_compute.compute_paths_to_multiple_destinations(position_key[0], position_key[1], move_targets)

            current_lengths = [len(path) - 1 for path in current_paths.values() if path]
            destination_lengths = [len(path) - 1 for path in destination_paths.values() if path]
            if not current_lengths or not destination_lengths:
                return 0

            progress = min(current_lengths) - min(destination_lengths)
            score = progress * 0.45
            if move_target_kind == 'investigate':
                score += progress * 0.1
            elif move_target_kind == 'door':
                score += progress * 0.05
            elif progress <= 0:
                score -= 0.2
            return score

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
            else:
                # Non-door interactions (loot, etc.) are low priority during active combat
                if len(enemy_positions) > 0:
                    score = -1.0  # strongly deprioritize when enemies are visible
            return score

        sorted_actions = []
        for action in available_actions:
            if isinstance(action, AttackAction) or isinstance(action, SpellAction):
                if isinstance(action, SpellAction):
                    support_score = score_support_spell(action)
                    if support_score != 0:
                        sorted_actions.append((action, support_score))
                        continue
                base_score = action.compute_hit_probability(battle) * action.avg_damage(battle)
                sorted_actions.append((action, base_score))
            elif isinstance(action, MoveAction):
                if not action.move_path or len(action.move_path) < 2:
                    sorted_actions.append((action, -2.0))
                    continue
                new_position = action.move_path[-1]
                position_key = (new_position[0], new_position[1])
                score = move_square_score.get(position_key, 0)
                score += progress_score_for(position_key)

                if position_key in recent_destinations:
                    recency = len(recent_destinations) - recent_destinations.index(position_key)
                    score -= 0.75 + (0.2 * recency)

                if position_key in visited_location:
                    score -= 0.15

                # avoid opportunity attacks
                opportunity_list = retrieve_opportunity_attacks(entity, action.move_path, battle)
                if len(opportunity_list) > 0:
                    # Strongly deprioritize; keep as last resort if truly stuck
                    score -= 1.0

                sorted_actions.append((action, score))
            elif isinstance(action, SecondWindAction):
                sorted_actions.append((action, score_second_wind(action)))
            elif isinstance(action, UseItemAction):
                sorted_actions.append((action, score_use_item(action)))
            elif isinstance(action, FirstAidAction):
                sorted_actions.append((action, score_first_aid(action)))
            elif isinstance(action, LayOnHandsAction):
                sorted_actions.append((action, score_lay_on_hands(action)))
            elif isinstance(action, HelpAction):
                sorted_actions.append((action, score_help(action)))
            elif isinstance(action, (ShoveAction, GrappleAction)):
                sorted_actions.append((action, score_control_action(action)))
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
        return sorted_actions