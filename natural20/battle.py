import random
import uuid
from natural20.generic_controller import GenericController
from natural20.action import Action
from natural20.actions.attack_action import AttackAction, TwoWeaponAttackAction, LinkedAttackAction
from natural20.weapons import compute_max_weapon_range
from natural20.utils.ac_utils import cover_calculation
from natural20.map import Map
from natural20.session import Session
from natural20.entity import Entity
from natural20.die_roll import DieRoll
from natural20.spell.effects.stench_effect import StenchEffect
import pdb
from natural20.uid_containers import EntitiesUIDMap


def _animation_uid(value):
    """Normalize ids in animator payloads (SocketIO JSON cannot encode uuid.UUID)."""
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, list):
        return [_animation_uid(v) for v in value]
    return value


def _attack_animation_missed(action):
    """True when the resolved attack result includes a miss (no damage dealt)."""
    for item in getattr(action, 'result', None) or []:
        if isinstance(item, dict) and item.get('type') == 'miss':
            return True
    return False


def _entity_grid_pos(battle, entity_or_uid):
    """Grid [x, y] for an entity at commit time (authoritative for client VFX)."""
    if battle is None or entity_or_uid is None:
        return None
    entity = entity_or_uid
    if not isinstance(entity, Entity):
        try:
            entity = battle.entity_by_uid(entity_or_uid)
        except Exception:
            entity = None
    if entity is None:
        return None
    pos = battle.entity_or_object_pos(entity)
    if pos is None:
        return None
    return [int(pos[0]), int(pos[1])]


def _target_grid_positions(battle, target):
    """Return (primary_target_pos, all_target_positions) for animation payloads."""
    if target is None:
        return None, None
    if isinstance(target, (list, tuple)):
        positions = []
        for t in target:
            p = _entity_grid_pos(battle, t)
            if p is not None:
                positions.append(p)
        return (positions[0] if positions else None), (positions or None)
    primary = _entity_grid_pos(battle, target)
    return primary, ([primary] if primary else None)


def action_animator(action, battle=None):
    def target_id(action):
        if hasattr(action, 'target') and action.target:
            if isinstance(action.target, list):
                return [
                    _animation_uid(t.entity_uid if isinstance(t, Entity) else t)
                    for t in action.target
                ]
            if isinstance(action.target, Entity):
                return _animation_uid(action.target.entity_uid)
            return _animation_uid(action.target)
        return None

    if action and action.action_type == 'attack':
        target_pos, target_positions = _target_grid_positions(battle, getattr(action, 'target', None))
        return {
            'type': 'attack',
            'message': {
                'target': target_id(action),
                'source': _animation_uid(action.source.entity_uid),
                'ranged': action.ranged_attack(),
                'type': 'attack',
                'label': action.label(),
                'miss': _attack_animation_missed(action),
                'source_pos': _entity_grid_pos(battle, action.source),
                'target_pos': target_pos,
                'target_positions': target_positions,
            }
        }
    elif action and action.action_type == 'move':
        return {
            'type': 'move',
            'token_image': action.source.token_image(),
            'token_size': action.source.token_size(),
            'transform': action.source.token_image_transform(),
        }
    elif action and action.action_type == 'spell':
        # Try to include the spell short name (e.g., 'bless') for client-side visuals
        try:
            spell_name = None
            if getattr(action, 'spell_action', None):
                spell_name = action.spell_action.short_name()
            elif getattr(action, 'spell_class', None):
                spell_name = getattr(action.spell_class, '__name__', None)
                if spell_name and spell_name.endswith('Spell'):
                    spell_name = spell_name[:-5]
            if isinstance(spell_name, str):
                spell_name = spell_name.lower().replace(' ', '_')
        except Exception:
            spell_name = None

        extra_message = {}
        if spell_name == 'misty_step':
            origin = getattr(action, 'misty_step_from', None)
            if origin is not None:
                extra_message['from'] = list(origin)

        return {
            'type': 'spell',
            'message': {
                'target': target_id(action),
                'source': _animation_uid(action.source.entity_uid),
                'type': 'spell',
                'label': action.label(),
                'spell': spell_name,
                **extra_message
            }
        }
    else:
        return {
            'type': 'spell',
            'message': {
                'target': target_id(action),
                'source': _animation_uid(action.source.entity_uid),
                'type': action.action_type,
                'label': action.label(),
                'spell': action.action_type
            }
        }

class Battle():
    def __init__(self, session: Session, maps: Map, standard_controller=None, animation_log_enabled=False):
        if isinstance(maps, list):
            self.maps = maps
        elif isinstance(maps, dict):
            self.maps = list(maps.values())
        elif maps:
            self.maps = [maps]
        else:
            self.maps = None

        self.session = session
        self.combat_order = []
        self.current_turn_index = 0
        self.battle_field_events = {}
        self.round = 0
        # Persistent area-of-effect zones (Spike Growth, Web, Spirit
        # Guardians, etc.). Spells append via ``register_zone`` and ticks
        # are driven by ``start_turn`` / ``end_turn`` and movement events.
        self.active_zones = []
        # Reaction trigger registry. Maps trigger name (e.g.
        # 'attack_hit', 'damage_taken') to a list of (handler, priority)
        # entries. Handlers are invoked by ``fire_reaction_window``.
        self.reaction_handlers = {}
        # Readied (Hold) actions: ``entity_uid`` -> ``ReadyActionState``.
        # Populated by ``ReadyAction.apply`` and consumed by
        # ``trigger_event`` when the readier's trigger fires.
        self.readied_actions = {}
        self._ready_action_resolver = None
        # Phase 4 summons registry: owner_uid (str) -> list[SummonedEntity].
        self.summons_by_owner = {}
        # Store entity states in a UID-backed map for robust serialization and lookups
        self.entities = EntitiesUIDMap(session)
        self.started = False
        self.groups = {}
        self.late_comers = []
        self.battle_log = []
        self.animation_log_enabled = animation_log_enabled
        self.animation_log = []

        if not standard_controller:
            self.standard_controller = GenericController
        else:
            self.standard_controller = standard_controller
        self.event_manager = session.event_manager
        self.opposing_groups = {
            'a': ['b'],
            'b': ['a'],
            'c': ['c']
        }
        # Bridge ``event_manager``-level lifecycle events (``unconscious``,
        # ``died``) into a battle-level ``goes_down`` trigger so readied
        # actions like "use a healing potion if my ally drops" can fire.
        # Listeners are gated on this battle being alive and having any
        # readied actions waiting on ``goes_down`` to avoid touching stale
        # state from prior battles that share the same session event_manager.
        self._goes_down_listener_installed = False
        self._object_interaction_listener_installed = False
        self._install_goes_down_bridge()
        self._install_object_interaction_bridge()
        self._install_concentration_break_bridge()

    def current_round(self):
        return self.round

    def map_for(self, entity):
        if not self.maps or len(self.maps) == 0:
            return None

        if isinstance(entity, str):
            for map in self.maps:
                if map.entity_by_uid(entity):
                    return map
            return None
        else:
            for map in self.maps:
                if entity in map.entities:
                    return map
                if entity in map.objects:
                    return map
        return None

    def add(self, entity, group, controller=None,
            position=None,
            index = 0,
            token=None, custom_initiative=None, add_to_initiative=False):
        if entity in self.entities:
            return

        if entity is None:
            raise ValueError('entity cannot be nil')

        if entity.properties.get('spiritual'):
            return

        state = {
            'group': group,
            'action': 0,
            'bonus_action': 0,
            'reaction': 0,
            'movement': 0,
            'stealth': 0,
            'statuses': set(),
            'active_perception': 0,
            'active_perception_disadvantage': 0,
            'free_object_interaction': 0,
            'legendary_actions': 0,
            'target_effect': {},
            'two_weapon': None,
            'martial_arts_pending': False,
            'positions_entered': {},
            'controller': controller,
            'help_with': {}
        }

        self.entities[entity] = state
        # Ensure entity is registered for UID-based operations
        self.session.register_entity(entity)
        self.groups.setdefault(group, set()).add(entity)

        if add_to_initiative:
            if custom_initiative:
                state['initiative'] = custom_initiative(self, entity)
            else:
                state['initiative'] = entity.initiative(self)
            self.combat_order.append(entity)

            # get current entity in current turn
            current_entity = self.current_turn()
            self.combat_order = sorted(self.combat_order, key=lambda a: self.entities[a]['initiative'], reverse=True)

            # retain current turn
            self.set_current_turn(current_entity)

        if position is None or self.maps is None:
            return

        if isinstance(position, (list, tuple)):
            self.maps[index].place(position, entity, token, self)
        else:
            self.maps[index].place_at_spawn_point(position, entity, token)

    # remove an entity from the battle and from the map
    def remove(self, entity, from_map=False):
        if self.current_turn_index == len(self.combat_order) - 1:
            self.current_turn_index = 0
        if entity in self.entities:
            del self.entities[entity]
        if entity in self.late_comers:
            self.late_comers.remove(entity)
        if entity in self.combat_order:
            self.combat_order.remove(entity)

        if from_map:
            self.map_for(entity).remove(entity, battle=self)

    def start(self, combat_order=None, custom_initiative=None):
        """
        Starts the combat

        :param combat_order: the order of combat
        :param custom_initiative: a custom function to determine initiative
        """
        self.started = True
        self.current_turn_index = 0

        if combat_order:
            self.combat_order = combat_order
            return

        # roll for initiative
        if isinstance(custom_initiative, list):
            self.combat_order = custom_initiative
        else:
            _combat_order = [[entity,v] for entity, v in self.entities.items() if not entity.dead()]
            for entity, v in _combat_order:
                if custom_initiative:
                    v['initiative'] = custom_initiative(self, entity)
                else:
                    v['initiative'] = entity.initiative(self)

            self.combat_order = [entity for entity, _ in _combat_order]
            self.combat_order = sorted(self.combat_order, key=lambda a: self.entities[a]['initiative'], reverse=True)
        self.event_manager.received_event({"event": 'start_of_combat',
                                           "target" : self.current_turn,
                                           "combat_order" : [[e, self.entities[e]['initiative']] for e in self.combat_order],
                                           "players" : self.entities })

    def roll_for(self, entity, die_type, number_of_times, description, advantage=False, disadvantage=False, controller=None):
        return DieRoll.roll_for(die_type, number_of_times, advantage, disadvantage)

    def controller_for(self, entity):
        if entity not in self.entities:
            return None
        if 'controller' not in self.entities[entity]:
            return self.entities[entity.owner]['controller']
        base = self.entities[entity]['controller']
        overrides = self.entities[entity].get('_control_overrides') or []
        if not overrides or base in (None, 'manual'):
            return base
        # Lazily build (and cache) a stack wrapper so that callers see
        # one stable wrapper instance per (entity, override-set).
        cache = self.entities[entity].get('_wrapped_controller')
        cache_key = tuple(id(o) for o in overrides)
        if cache and cache[0] == cache_key:
            return cache[1]
        from natural20.controllers.control_override import (
            ControlOverride,
            ControlOverrideStack,
        )
        if len(overrides) == 1 and isinstance(overrides[0], ControlOverride):
            wrapped = overrides[0]
            wrapped.base = base
        else:
            wrapped = ControlOverrideStack(base, overrides)
        self.entities[entity]['_wrapped_controller'] = (cache_key, wrapped)
        return wrapped


    def set_controller_for(self, entity, controller):
        if entity not in self.entities:
            return False

        self.entities[entity]['controller'] = controller
        # Invalidate any cached override wrapper so the new base controller
        # takes effect on the next ``controller_for`` lookup.
        self.entities[entity].pop('_wrapped_controller', None)
        return True

    # ------------------------------------------------------------------
    # Loss-of-control: pluggable controller overrides
    # ------------------------------------------------------------------

    def push_control_override(self, entity, override):
        """Attach a :class:`ControlOverride` to ``entity``.

        Multiple overrides stack — see
        :class:`natural20.controllers.control_override.ControlOverrideStack`.
        Returns ``True`` if the override was added.
        """
        state = self.entity_state_for(entity)
        if state is None:
            return False
        stack = state.setdefault('_control_overrides', [])
        if override not in stack:
            stack.append(override)
            state.pop('_wrapped_controller', None)
            self.event_manager.received_event({
                'event': 'control_override_added',
                'source': override.source if hasattr(override, 'source') else None,
                'target': entity,
                'condition': getattr(override, 'condition_id', 'control_override'),
            })
        return True

    def pop_control_override(self, entity, override=None, condition_id=None):
        """Remove an override (by reference or by ``condition_id``).

        Returns the removed override, or ``None`` if nothing matched.
        """
        state = self.entity_state_for(entity)
        if state is None:
            return None
        stack = state.get('_control_overrides') or []
        removed = None
        for candidate in list(stack):
            if override is not None and candidate is not override:
                continue
            if condition_id is not None and getattr(candidate, 'condition_id', None) != condition_id:
                continue
            stack.remove(candidate)
            removed = candidate
            break
        if removed is not None:
            state.pop('_wrapped_controller', None)
            self.event_manager.received_event({
                'event': 'control_override_removed',
                'source': removed.source if hasattr(removed, 'source') else None,
                'target': entity,
                'condition': getattr(removed, 'condition_id', 'control_override'),
            })
        return removed

    def active_overrides_for(self, entity):
        """Return the (possibly empty) list of overrides on ``entity``."""
        state = self.entity_state_for(entity)
        if state is None:
            return []
        return list(state.get('_control_overrides') or [])

    def clear_control_overrides(self, entity):
        """Drop every override attached to ``entity``."""
        state = self.entity_state_for(entity)
        if state is None:
            return
        if state.get('_control_overrides'):
            state['_control_overrides'] = []
            state.pop('_wrapped_controller', None)

    def combat_ongoing(self):
        return True

    def current_turn(self) -> Entity:
        if len(self.combat_order) == 0:
            return None

        if self.current_turn_index >= len(self.combat_order):
            raise Exception(f'current_turn_index out of bounds {self.current_turn_index} >= {len(self.combat_order)}')
        return self.combat_order[self.current_turn_index]

    def set_current_turn(self, entity):
        if entity not in self.combat_order:
            raise Exception('entity not in combat order')

        self.current_turn_index = self.combat_order.index(entity)

    def reorder_initiative(self, entity_uids):
        """
        Reorder the combat initiative based on a list of entity UIDs.
        
        :param entity_uids: List of entity UIDs in the desired order
        """
        if not entity_uids:
            return False
            
        # Get current turn entity to preserve it
        current_entity = self.current_turn() if self.combat_order else None
        
        # Create a mapping of UIDs to entities
        uid_to_entity = {entity.entity_uid: entity for entity in self.combat_order}
        
        # Validate that all provided UIDs exist in combat order
        for uid in entity_uids:
            if uid not in uid_to_entity:
                raise ValueError(f"Entity UID {uid} not found in combat order")
        
        # Validate that all entities in combat order are represented
        if len(entity_uids) != len(self.combat_order):
            raise ValueError("Number of entities in new order doesn't match combat order")
        
        # Reorder the combat order
        new_combat_order = [uid_to_entity[uid] for uid in entity_uids]
        self.combat_order = new_combat_order
        
        # Restore the current turn index if there was a current entity
        if current_entity:
            try:
                self.current_turn_index = self.combat_order.index(current_entity)
            except ValueError:
                # If the current entity is no longer in the order, reset to 0
                self.current_turn_index = 0
        
        return True

    def check_combat(self):
        if not self.started and not self.battle_ends():
            self.start()

            # print(f"Combat starts with {self.combat_order[0].name}.")
            return True
        return False

    def entity_or_object_pos(self, entity):
        if not self.map_for(entity):
            return None
        return self.map_for(entity).entity_or_object_pos(entity)

    def start_turn(self):
        entity = self.current_turn()
        entity_pos = self.entity_or_object_pos(entity)

        # if self.animation_log_enabled:
        #     self.animation_log.append([entity.entity_uid, [entity_pos], None])

        if entity.unconscious() and not entity.stable():
            entity.death_saving_throw(self)
        # Per RAW the Ready action ends at the start of the readier's next
        # turn, regardless of whether the trigger fired.
        if self.readied_actions and entity is not None:
            self.clear_ready_action(entity)
        self.trigger_event('start_of_turn', self, { "target" : entity })
        
        # check for the stench feature
        effects_list = [StenchEffect(self, entity)]
        for effect in effects_list:
            effect.start_of_turn(entity)

    def end_turn(self):
        self.current_turn().resolve_trigger('end_of_turn')
        self.trigger_event('end_of_turn', self,  { "target" : self.current_turn()})

        # reset legendary actions
        self.eval_legendary_action()

    def eval_legendary_action(self):
        for entity in self.combat_order:
            if entity == self.current_turn():
                continue

            if not entity.conscious():
                continue

            if entity.npc() and len(entity.legendary_actions) > 0:
                controller = self.controller_for(entity)
                if controller:
                    action = controller.legendary_action_listener(self, self.session, entity, self.map_for(entity), { "target" : self.current_turn() })
                    if action:
                        self.execute_action(action)

    def battle_ends(self):
        """
        Returns true if the battle has ended
        """
        groups = set()

        for entity in self.combat_order:
            if entity.conscious():
                groups.add(self.entities[entity]['group'])

        # get all groups and make sure there are no opposing groups
        for group in groups:
            for group2 in groups:
                if group == group2:
                    continue
                if group2 in self.opposing_groups.get(group, []):
                    return False

        return True

    def winning_groups(self):
        """
        Returns the winning groups in the battle. If the battle is not over, returns an empty set.
        """
        if not self.battle_ends():
            return set()

        groups = set()
        for entity in self.combat_order:
            if entity.conscious():
                groups.add(self.entities[entity]['group'])
        return groups

    def player_groups(self):
        """
        Returns the set of groups that contain player characters in this battle.
        Falls back to the session's default group (the one flagged ``default: true``
        in game.yml) when no PCs are registered.
        """
        groups = set()
        for entity in self.combat_order:
            try:
                is_npc = bool(entity.npc())
            except Exception:
                is_npc = True
            if not is_npc:
                groups.add(self.entities[entity]['group'])
        if not groups:
            try:
                for name, info in (self.session.groups() or {}).items():
                    if isinstance(info, dict) and info.get('default'):
                        groups.add(name)
                        break
            except Exception:
                pass
        return groups

    def tpk(self):
        """
        Total Party Kill: the battle has ended and no player-character group is
        among the winners. Returns ``False`` if combat is still ongoing or if at
        least one PC group is still standing.
        """
        if not self.battle_ends():
            return False
        winners = self.winning_groups()
        pc_groups = self.player_groups()
        if not pc_groups:
            return False
        return not (pc_groups & winners)

    def compute_movement_inefficiency(self, entity):
        positions_entered = self.entities[entity]['positions_entered']
        if not positions_entered:
            return 0
        inefficiency = 0
        for _, count in positions_entered.items():
            if count > 1:
                inefficiency += 1
        return inefficiency

    def next_turn(self, max_rounds=None):
        self.trigger_event('end_of_turn', self, { "target" : self.current_turn()})
        if self.started and self.battle_ends():
            self.session.event_manager.received_event({"source" : self, "event" : 'end_of_combat'})
            self.started = False
            # print('tpk')
            return 'tpk'

        self.current_turn_index += 1
        if self.current_turn_index >= len(self.combat_order):
            self.current_turn_index = 0
            self.round += 1
            self.session.increment_game_time()
            self.session.event_manager.received_event({ "source" : self,
                                          "event" : 'top_of_the_round',
                                          "round" : self.round,
                                          "target" : self.current_turn()})

            if max_rounds is not None and self.round > max_rounds:
                return True
        return False

    def while_active(self, max_rounds=None, callback=lambda x: x):
        while True:
            self.start_turn()
            if self.controller_for(self.current_turn()):
                self.controller_for(self.current_turn()).begin_turn(self.current_turn())
            current = self.current_turn()
            if current.conscious() and not current.incapacitated():
                current.reset_turn(self)
                if callback(current):
                    continue
            elif current.incapacitated() and not current.dead():
                # Stunned, paralyzed, sleep, petrified, or generic
                # ``incapacitated``: the entity uses up its turn slot but
                # takes no actions and has no movement. Emit a hook so
                # observers (UI, logs, AI) can react.
                self.event_manager.received_event({
                    'event': 'turn_skipped',
                    'target': current,
                    'reason': 'incapacitated',
                    'statuses': list(current.statuses),
                })

            current.resolve_trigger('end_of_turn')
            # print("Next turn")
            result = self.next_turn(max_rounds)
            # print(f"Result: {result}")
            if result == 'tpk':
                return 'tpk'
            if result:
                return result

    def entity_by_uid(self, entity_uid):
        # Prefer the session-level registry for O(1) lookup
        ent = self.session.entity_registry.get(entity_uid)
        if ent is not None:
            return ent
        # Fallback to checking maps for legacy states
        for map in self.maps:
            entity = map.entity_by_uid(entity_uid)
            if entity:
                return entity
        return None
    
    def register_map(self, map):
        if map not in self.maps:
            self.maps.append(map)

    def unregister_map(self, map):
        if map in self.maps:
            for entity in map.entities.keys():
                self.remove(entity, from_map=False)
            self.maps.remove(map)

    def entity_state_for(self, entity):
        entity_state = self.entities.get(entity, None)
        if entity_state is None:
            if entity is None or not hasattr(entity, 'entity_uid'):
                return None
            _entity = self.entity_by_uid(entity.entity_uid)
            return self.entities.get(_entity, None)
        return entity_state

    def has_controller_for(self, entity):
        if entity not in self.entities:
            raise Exception('unknown entity in battle')

        return self.entities[entity]['controller'] != 'manual'

    def move_for(self, entity):
        """
        Returns the move for the entity, calls AI or manual user control
        associated to the entity
        """
        if entity not in self.entities:
            raise Exception('unknown entity in battle')
        if not self.entities[entity]['controller']:
            raise Exception(f"no controller for entity {entity}")

        return self.entities[entity]['controller'].move_for(entity, self)

    def do_distract(self, source, target):
        self.entities[target]['help_with'][source] = 'distract'

    # dismiss all distractions for a source
    def dismiss_distract(self, source):
        for _, entity_state in self.entities.items():
            if source in entity_state.get('help_with', {}):
                entity_state['help_with'].pop(source)

    def help_with(self, entity):
        if entity in self.entities:
            return self.entities[entity].get('help_with', {})
        return {}

    def dismiss_help_for(self, entity):
        if entity in self.entities:
            self.entities[entity]['help_with'] = {}

    # Returns opponents of entity
    # @param entity [Natural20::Entity] target entity
    # @return [List<Natural20::Entity>]
    def opponents_of(self, entity):
        return [k for k in (list(self.entities.keys()) + self.late_comers) if not k.dead() and self.opposing(k, entity)]

    def allies_of(self, entity):
        return [k for k in (list(self.entities.keys()) + self.late_comers) if not k.dead() and self.allies(k, entity)]

    def enemy_in_melee_range(self, source, exclude=None, source_pos=None):
        map_for_source = self.map_for(source)
        objects_around_me = map_for_source.look(source)
        exclude = exclude or []
        for object in objects_around_me:
            if object in exclude:
                continue

            state = self.entity_state_for(object)
            if not state:
                continue
            if not object.conscious():
                continue

            melee_distance = object.melee_distance() if hasattr(object, 'melee_distance') else None
            if melee_distance is None or melee_distance <= 0 or map_for_source.feet_per_grid <= 0:
                continue

            if self.opposing(source, object) and (map_for_source.distance(source, object, entity_1_pos=source_pos) <= (melee_distance / map_for_source.feet_per_grid)):
                return True

        return False

    def action(self, action):
        opts = {
            'battle': self
        }
        # check if action is a generator due to a yield
        if hasattr(action, 'send'):
            return action
        else:
            return action.resolve(self.session, self.map_for(action.source), opts)
    
    def resolve_action(self, source, action_type, opts=None):
        if opts is None:
            opts = {}
        action = next((act for act in source.available_actions(self.session, self) if act.action_type == action_type), None)
        opts['battle'] = self
        return action.resolve(self.session, self.map_for(action.source), opts) if action else None

    def commit(self, action):
        if action is None:
            print('action is None')
            return

        # if action is a generator, just return it
        if hasattr(action, 'send'):
            return action

        if action.committed:
            return

        action.committed = True
        # check_action_serialization(action)
        other_results = []
        index = 0
        while index < len(action.result):
            item = action.result[index]
            for klass in Action.__subclasses__():
                other_results = klass.apply(self, item, self.session)
                if isinstance(other_results, list):
                    for result in other_results:
                        if result not in action.result:
                            action.result.append(result)
            if self.animation_log_enabled:
                if item.get('perception_targets'):
                    perception_targets = item['perception_targets']
                    self.animation_log.append({"type": "perception", "targets": [p.entity_uid for p in perception_targets]})
                if item["type"] == "message":
                    self.animation_log.append({"type": "message_toaster", "source": item["source"].entity_uid, "message": item["message"], "position": item["position"]})
            index += 1
        if action.action_type == 'move':
            self.trigger_event('movement', action.source, { 'move_path': action.move_path})
            if self.animation_log_enabled:
                # if len(self.animation_log) == 0:
                #     self.animation_log.append([action.source.entity_uid, [self.entity_or_object_pos(action.source)], None])
                self.animation_log.append([action.source.entity_uid, action.move_path, action_animator(action, self)])
        elif action.action_type == 'attack':
            if self.animation_log_enabled:
                self.animation_log.append(action_animator(action, self))
            # Fire the ``attacked`` event so any readied actions whose trigger
            # depends on the readier being attacked can react. Note this fires
            # after the attack resolves; the readied action is then executed
            # synchronously inside the trigger dispatch loop.
            try:
                target = getattr(action, 'target', None)
                # Some attacks have multi-target lists; emit one event per
                # target so triggers tied to a specific readier still fire.
                if isinstance(target, (list, tuple)):
                    targets = list(target)
                else:
                    targets = [target]
                for t in targets:
                    if t is None:
                        continue
                    self.trigger_event('attacked', action.source, {
                        'target': t,
                        'attack_name': getattr(action, 'using', None) or getattr(action, 'spell_class', None),
                        'as_reaction': bool(getattr(action, 'as_reaction', False)),
                    })
                    # Also fan out as ``ally_attacks`` so a readier with a
                    # "when my ally hits Y, I also attack Y" trigger fires.
                    # The readier-side filter (subject_filter='allies' + the
                    # owner-not-source guard in evaluate_trigger) keeps this
                    # from firing the attacker's own readied actions.
                    self.trigger_event('ally_attacks', action.source, {
                        'target': t,
                        'attack_name': getattr(action, 'using', None) or getattr(action, 'spell_class', None),
                        'as_reaction': bool(getattr(action, 'as_reaction', False)),
                    })
            except Exception:
                pass
        elif action.action_type == 'interact':
            self.trigger_event('interact', action)
        else:
            if self.animation_log_enabled:
                animation_payload = action_animator(action, self)
                self.animation_log.append(animation_payload)
            # Spells that target a creature also count as an "attack" for
            # readied-trigger purposes (e.g. holding a spell to fire when the
            # enemy casts at you).
            if action.action_type == 'spell':
                try:
                    target = getattr(action, 'target', None)
                    if isinstance(target, (list, tuple)):
                        targets = list(target)
                    else:
                        targets = [target]
                    for t in targets:
                        if t is None or not hasattr(t, 'entity_uid'):
                            continue
                        self.trigger_event('attacked', action.source, {
                            'target': t,
                            'attack_name': getattr(action, 'spell_class', None),
                            'as_reaction': bool(getattr(action, 'as_reaction', False)),
                        })
                        self.trigger_event('ally_attacks', action.source, {
                            'target': t,
                            'attack_name': getattr(action, 'spell_class', None),
                            'as_reaction': bool(getattr(action, 'as_reaction', False)),
                        })
                except Exception:
                    pass

        self.battle_log.append(action)
        return None

    def get_animation_logs(self):
        return self.animation_log

    def clear_animation_logs(self):
        self.animation_log.clear()
        entity = self.current_turn()
        entity_pos = self.entity_or_object_pos(entity)
        # self.animation_log.append([entity.entity_uid, [entity_pos], None])

    def group_for(self, entity):
        return self.entity_group_for(entity)

    def entity_group_for(self, entity):
        if entity not in self.entities:
            if entity is None or not hasattr(entity, 'entity_uid'):
                return 'none'
            _entity = self.entity_by_uid(entity.entity_uid)
            if _entity:
                if _entity not in self.entities:
                    return 'none'
                return self.entities[_entity]['group']
            return 'none'

        return self.entities[entity]['group']

    def ongoing(self):
      return self.started

    def first_hand_weapon(self, entity):
        return self.entity_state_for(entity)['two_weapon']

    def two_weapon_attack(self, entity):
        return bool(self.entity_state_for(entity)['two_weapon'])
    
    def active_perception_for(self, entity):
        if entity not in self.entities:
            return 0

        return self.entities[entity].get('active_perception', 0)
    
    # Consumes an action resource
    # @param entity [Natural20::Entity]
    # @param resource [str]
    def consume(self, entity, resource, qty=1):
        valid_resources = ['action', 'reaction', 'bonus_action', 'movement', 'free_object_interaction', 'legendary_actions']
        if resource not in valid_resources:
            raise Exception('invalid resource')

        if self.entity_state_for(entity):
            entity_state = self.entity_state_for(entity)
            entity_state[resource] = max(0, entity_state[resource] - qty)

    def opposing(self, entity1, entity2):
        source_state1 = self.entity_state_for(entity1)
        source_state2 = self.entity_state_for(entity2)
        if source_state1 is None or source_state2 is None:
            return False

        source_group1 = source_state1['group']
        source_group2 = source_state2['group']

        if source_group1 == source_group2:
            return False

        return source_group2 in self.opposing_groups.get(source_group1, [])
    
    def allies(self, entity1, entity2):
        source_state1 = self.entity_state_for(entity1)
        source_state2 = self.entity_state_for(entity2)
        if source_state1 is None or source_state2 is None:
            return False

        source_group1 = source_state1['group']
        source_group2 = source_state2['group']

        return source_group1 == source_group2

    def _install_goes_down_bridge(self):
        """Register a listener that maps event_manager 'unconscious'/'died'
        events into a battle-level 'goes_down' trigger.

        Idempotent and defensive: if EventManager lacks
        ``register_event_listener`` (older session/test stubs) the bridge is
        silently skipped -- readied ``goes_down`` actions then simply will
        not auto-fire, but no other behaviour is affected.
        """
        if self._goes_down_listener_installed:
            return
        em = getattr(self, 'event_manager', None)
        if em is None or not hasattr(em, 'register_event_listener'):
            return
        battle_ref = self

        def _on_goes_down(event):
            try:
                if not getattr(battle_ref, 'started', False):
                    return
                if not getattr(battle_ref, 'readied_actions', None):
                    return
                ent = event.get('source') if isinstance(event, dict) else None
                if ent is None:
                    return
                battle_ref.trigger_event('goes_down', ent, {'target': ent})
            except Exception:
                # Never let a downstream readied-action error propagate out
                # of an event_manager broadcast loop.
                pass

        try:
            em.register_event_listener(['unconscious', 'died'], _on_goes_down)
            self._goes_down_listener_installed = True
        except Exception:
            pass

    def _install_object_interaction_bridge(self):
        """Bridge event_manager 'object_interaction' events (door opens,
        chest unlocks, etc.) into the battle-level trigger pipeline so a
        readied action like "shoot whoever opens that door" can fire.

        Idempotent and defensive (see ``_install_goes_down_bridge``).
        """
        if self._object_interaction_listener_installed:
            return
        em = getattr(self, 'event_manager', None)
        if em is None or not hasattr(em, 'register_event_listener'):
            return
        battle_ref = self

        def _on_object_interaction(event):
            try:
                if not getattr(battle_ref, 'started', False):
                    return
                if not getattr(battle_ref, 'readied_actions', None):
                    return
                if not isinstance(event, dict):
                    return
                actor = event.get('source')
                obj = event.get('target')
                if actor is None and obj is None:
                    return
                battle_ref.trigger_event(
                    'object_interaction',
                    actor if actor is not None else obj,
                    {
                        'target': obj,
                        'sub_type': event.get('sub_type'),
                        'result': event.get('result'),
                    },
                )
            except Exception:
                pass

        try:
            em.register_event_listener(['object_interaction'], _on_object_interaction)
            self._object_interaction_listener_installed = True
        except Exception:
            pass

    def _install_concentration_break_bridge(self):
        """Expire any readied spell whose held-spell concentration just
        ended (e.g. a damage-induced CON save failed).

        Per RAW: *holding onto the spell's magic requires concentration. If
        your concentration is broken, the spell dissipates without taking
        effect.* The slot is **not** refunded -- the spell was already cast
        at ready time. We only mark the readied state expired so it cannot
        fire later, and emit ``ready_action_dissipated`` for the log.
        """
        if getattr(self, '_concentration_break_listener_installed', False):
            return
        em = getattr(self, 'event_manager', None)
        if em is None or not hasattr(em, 'register_event_listener'):
            return
        battle_ref = self

        def _on_concentration_end(event):
            try:
                if not isinstance(event, dict):
                    return
                effect = event.get('effect')
                if effect is None or not getattr(effect, 'is_held_spell', False):
                    return
                owner = event.get('source')
                if owner is None:
                    return
                state = battle_ref.ready_action_for(owner)
                if state is None or state.expired:
                    return
                spec = state.action_spec or {}
                if (spec.get('kind') or '').lower() != 'spell':
                    return
                if spec.get('spell') != getattr(effect, 'spell_slug', None):
                    return
                state.expired = True
                try:
                    setattr(state, 'last_fizzle_reason',
                            'concentration broken; the held spell dissipated')
                except Exception:
                    pass
                battle_ref.clear_ready_action(owner)
                try:
                    em.received_event({
                        'source': owner,
                        'event': 'ready_action_dissipated',
                        'description': state.description,
                        'spell': spec.get('spell'),
                        'reason': 'concentration broken',
                    })
                except Exception:
                    pass
            except Exception:
                pass

        try:
            em.register_event_listener(['concentration_end'], _on_concentration_end)
            self._concentration_break_listener_installed = True
        except Exception:
            pass

    def trigger_event(self, event, source, opt=None):
        if opt is None:
            opt = {}
        if event in self.battle_field_events:
            for object, handler in self.battle_field_events[event].items():
                object.__getattribute__(handler)(self, source, {**opt, 'ui_controller': self.controller_for(source)})
        if self.maps and self.map_for(source):
            self.map_for(source).activate_map_triggers(event, source, {**opt, 'ui_controller': self.controller_for(source)})

        # Persistent AoE zones: tick on per-turn boundaries; movement
        # steps are dispatched via ``trigger_movement_step`` instead.
        if event in ('start_of_turn', 'end_of_turn') and self.active_zones:
            target = opt.get('target') if isinstance(opt, dict) else None
            for zone in list(self.active_zones):
                if zone.expired():
                    zone.dismiss()
                    continue
                if target is None:
                    continue
                pos = self.entity_or_object_pos(target)
                if pos is None or not zone.contains(tuple(pos)):
                    continue
                try:
                    if event == 'start_of_turn':
                        zone.on_turn_start(target)
                    else:
                        zone.on_turn_end(target)
                except Exception as exc:  # pragma: no cover - defensive
                    self.event_manager.received_event({
                        'source': zone, 'event': 'zone_error',
                        'phase': event, 'error': str(exc),
                    })

        # Readied actions: walk every readied entity and dispatch matching
        # triggers. We snapshot the dict so resolvers may mutate it.
        if self.readied_actions:
            self._dispatch_readied_actions(event, source, opt)

    # ------------------------------------------------------------------
    # Ready / Hold action support
    # ------------------------------------------------------------------
    def register_ready_action(self, entity, state):
        """Store ``state`` (a ``ReadyActionState``) for ``entity``."""
        if entity is None or state is None:
            return
        uid = str(getattr(entity, 'entity_uid', '') or '')
        if not uid:
            return
        self.readied_actions[uid] = state

    def clear_ready_action(self, entity):
        if entity is None:
            return
        uid = str(getattr(entity, 'entity_uid', '') or '')
        self.readied_actions.pop(uid, None)

    def ready_action_for(self, entity):
        if entity is None:
            return None
        uid = str(getattr(entity, 'entity_uid', '') or '')
        return self.readied_actions.get(uid)

    def set_ready_action_resolver(self, resolver):
        """Register an LLM-backed resolver. ``resolver(state, event_name,
        event_payload, battle, owner) -> Action | None`` -- returning ``None``
        means do nothing (the trigger fizzled). The state is left in place
        unless the resolver also calls ``clear_ready_action``."""
        self._ready_action_resolver = resolver

    def _dispatch_readied_actions(self, event, source, opt):
        from natural20.ready_action import (
            evaluate_trigger,
            default_resolver,
        )
        # Build a minimal payload describing who triggered this event.
        payload = {'source': source}
        if isinstance(opt, dict):
            for key in ('target', 'move_path', 'message', 'targets',
                        'volume', 'sub_type', 'result'):
                if key in opt and key not in payload:
                    payload[key] = opt[key]
        # ``becomes_visible`` is synthesised: when ``source`` finishes a move,
        # we ask each readier whether ``source`` was hidden at the start of
        # the path and is now visible. If so, we re-dispatch as
        # ``becomes_visible`` for that readier in addition to the normal
        # ``movement`` event.
        synth_visibility_uids = set()
        if event == 'movement' and source is not None and isinstance(opt, dict):
            move_path = opt.get('move_path') or []
            start_pos = move_path[0] if move_path else None
            if start_pos is not None:
                for uid, state in list(self.readied_actions.items()):
                    if state is None or state.expired:
                        continue
                    if (state.trigger or {}).get('event') != 'becomes_visible':
                        continue
                    owner = self.session.entity_registry.get(uid)
                    if owner is None or owner is source:
                        continue
                    try:
                        map_obj = self.map_for(owner) or self.map_for(source)
                    except Exception:
                        map_obj = None
                    if map_obj is None:
                        continue
                    try:
                        was_visible = map_obj.can_see(owner, source, entity_2_pos=start_pos)
                        is_visible = map_obj.can_see(owner, source)
                    except Exception:
                        was_visible = is_visible = False
                    if (not was_visible) and is_visible:
                        synth_visibility_uids.add(uid)
        for uid, state in list(self.readied_actions.items()):
            if state is None or state.expired:
                continue
            owner = self.session.entity_registry.get(uid)
            if owner is None:
                continue
            # Avoid dispatching on the readier's own actions.
            if source is owner:
                continue
            if not owner.has_reaction(self):
                continue
            # Use the synthesised event name when this readier is waiting on a
            # visibility transition triggered by the current movement.
            effective_event = 'becomes_visible' if uid in synth_visibility_uids else event
            if not evaluate_trigger(state, effective_event, payload, self, owner):
                continue
            resolver = self._ready_action_resolver or default_resolver
            try:
                action = resolver(state, effective_event, payload, self, owner)
            except Exception as exc:  # pragma: no cover - defensive
                self.event_manager.received_event({
                    'source': owner, 'event': 'ready_action_error',
                    'error': str(exc), 'description': state.description,
                })
                action = None
            state.fire_count += 1
            state.expired = True
            self.clear_ready_action(owner)
            if action is None:
                self.event_manager.received_event({
                    'source': owner, 'event': 'ready_action_fizzled',
                    'description': state.description, 'trigger_event': effective_event,
                    'reason': getattr(state, 'last_fizzle_reason', None),
                })
                continue
            try:
                self.event_manager.received_event({
                    'source': owner, 'event': 'ready_action_fired',
                    'description': state.description,
                    'action_spec': dict(state.action_spec or {}),
                    'trigger_event': effective_event,
                })
                self.action(action)
                self.commit(action)
            except Exception as exc:  # pragma: no cover - defensive
                self.event_manager.received_event({
                    'source': owner, 'event': 'ready_action_error',
                    'error': str(exc), 'description': state.description,
                })

    def register_zone(self, zone):
        """Register a ``PersistentAoEZone`` so the battle ticks it.

        Returns ``zone`` so spells can chain ``self.battle.register_zone(...)``.
        """
        if zone is None:
            return None
        if zone not in self.active_zones:
            self.active_zones.append(zone)
        return zone

    def unregister_zone(self, zone):
        if zone in self.active_zones:
            self.active_zones.remove(zone)

    # --- Concentration tracker -------------------------------------------

    def start_concentration(self, entity, effect, *, save_dc=None, auto_break=True):
        """Begin concentration for ``entity`` on ``effect``.

        Wraps the legacy ``Entity.concentration_on``: stores ``save_dc`` on
        the effect, broadcasts a ``concentration_start`` event, and (per
        5e RAW) auto-drops any prior concentration. ``auto_break=False``
        disables damage-time concentration checks for unusual effects.
        """
        if entity is None or effect is None:
            return None
        if save_dc is not None:
            try:
                setattr(effect, 'concentration_save_dc', int(save_dc))
            except Exception:
                pass
        try:
            setattr(effect, 'concentration_auto_break', bool(auto_break))
        except Exception:
            pass
        entity.concentration_on(effect)
        try:
            self.event_manager.received_event({
                'source': entity, 'event': 'concentration_start',
                'effect': effect,
            })
        except Exception:
            pass
        return effect

    def end_concentration(self, entity):
        """End concentration for ``entity`` (no-op if none active)."""
        if entity is None:
            return
        if getattr(entity, 'concentration', None):
            entity.drop_concentration()

    def concentration_owner_for(self, effect):
        """Return the entity currently concentrating on ``effect`` or None."""
        if effect is None:
            return None
        for ent in list(self.entities.keys()):
            if getattr(ent, 'concentration', None) is effect:
                return ent
        return None

    # --- Reaction trigger registry ---------------------------------------

    def register_reaction_trigger(self, trigger_name, handler, *, priority=0):
        """Register ``handler(battle, context) -> list[event_dict] | None``.

        Higher ``priority`` runs first. Handlers are deduplicated by
        identity, so re-registering the same callable is a no-op.
        """
        if not trigger_name or handler is None:
            return
        bucket = self.reaction_handlers.setdefault(trigger_name, [])
        for existing, _ in bucket:
            if existing is handler:
                return
        bucket.append((handler, int(priority)))
        bucket.sort(key=lambda pair: -pair[1])

    def unregister_reaction_trigger(self, trigger_name, handler):
        bucket = self.reaction_handlers.get(trigger_name, [])
        self.reaction_handlers[trigger_name] = [(h, p) for (h, p) in bucket if h is not handler]

    def fire_reaction_window(self, trigger_name, context=None):
        """Invoke all registered handlers for ``trigger_name``.

        Returns the flat list of event dicts produced. Each handler may
        also mutate ``context`` (e.g. set ``context['force_miss'] = True``).
        Exceptions in handlers are logged via the event manager and do not
        abort the window.
        """
        events = []
        if context is None:
            context = {}
        bucket = self.reaction_handlers.get(trigger_name, ())
        for handler, _priority in list(bucket):
            try:
                result = handler(self, context)
            except Exception as exc:  # pragma: no cover - defensive
                try:
                    self.event_manager.received_event({
                        'source': handler, 'event': 'reaction_error',
                        'trigger': trigger_name, 'error': str(exc),
                    })
                except Exception:
                    pass
                continue
            if not result:
                continue
            if isinstance(result, dict):
                events.append(result)
            else:
                events.extend(result)
        return events

    # --- Phase 4 summon registry ---------------------------------------

    def register_summon(self, summon):
        """Register a SummonedEntity under its owner's UID."""
        owner_uid = getattr(summon, 'owner_uid', None)
        key = str(owner_uid) if owner_uid is not None else '__orphan__'
        bucket = self.summons_by_owner.setdefault(key, [])
        if summon not in bucket:
            bucket.append(summon)
        return summon

    def unregister_summon(self, summon):
        for key, bucket in list(self.summons_by_owner.items()):
            if summon in bucket:
                bucket.remove(summon)
                if not bucket:
                    self.summons_by_owner.pop(key, None)
                return True
        return False

    def summons_for(self, owner):
        owner_uid = getattr(owner, 'entity_uid', None)
        return list(self.summons_by_owner.get(str(owner_uid), ()))

    def all_summons(self):
        out = []
        for bucket in self.summons_by_owner.values():
            out.extend(bucket)
        return out

    def tick_summons(self):
        """Drop expired summons. Safe to call on every round/turn boundary."""
        for key, bucket in list(self.summons_by_owner.items()):
            keep = []
            for s in bucket:
                if s.is_expired(self):
                    s.dismiss()
                    try:
                        self.event_manager.received_event({
                            'source': s.entity, 'event': 'summon_expired',
                            'owner': s.owner, 'source_id': s.source_id,
                        })
                    except Exception:
                        pass
                else:
                    keep.append(s)
            if keep:
                self.summons_by_owner[key] = keep
            else:
                self.summons_by_owner.pop(key, None)

    def zones_at(self, pos):
        """Return active zones whose footprint contains ``pos``."""
        if not self.active_zones:
            return []
        target = tuple(pos)
        return [z for z in self.active_zones if not z.expired() and z.contains(target)]

    def trigger_movement_step(self, entity, from_pos, to_pos):
        """Dispatch a per-square movement event.

        Called by ``Map.move_to`` after the entity has actually moved one
        square. Persistent zones whose footprint contains the destination
        receive ``on_enter``. Future reaction-trigger work (Phase 3) will
        consume the same event for opportunity attacks and difficult
        terrain.
        """
        if not self.active_zones:
            return
        if to_pos is None:
            return
        target = tuple(to_pos)
        for zone in list(self.active_zones):
            if zone.expired():
                zone.dismiss()
                continue
            if not zone.contains(target):
                continue
            # Don't fire on_enter when the entity was already inside the
            # zone (e.g. caster centers a sphere on themselves).
            if from_pos is not None and zone.contains(tuple(from_pos)):
                continue
            try:
                zone.on_enter(entity)
            except Exception as exc:  # pragma: no cover - defensive
                self.event_manager.received_event({
                    'source': zone, 'event': 'zone_error',
                    'phase': 'on_enter', 'error': str(exc),
                })

    # Determines if an entity can see someone in battle
    # @param entity1 [Natural20::Entity] observer
    # @param entity2 [Natural20::Entity] entity being observed
    # @return [Boolean]
    def can_see(self, entity1, entity2, active_perception=0, entity_1_pos=None, entity_2_pos=None):
        map1 = self.map_for(entity1)
        map2 = self.map_for(entity2)
        if map1 != map2:
            return False
        if entity1 == entity2:
            return True
        if not map1.can_see(entity1, entity2, entity_1_pos=entity_1_pos, entity_2_pos=entity_2_pos, active_perception=active_perception):
            return False

        return True

    def valid_targets_for(self, entity, action, target_types=None, range=None, active_perception=None, include_objects=False, filter=None):
        if target_types is None:
            if isinstance(action, AttackAction) or isinstance(action, TwoWeaponAttackAction):
                target_types = ['enemies']
            else:
                target_types = ['enemies', 'self', 'allies']
        if not isinstance(action, Action):
            raise Exception('not an action')

        active_perception = active_perception if active_perception is not None else self.active_perception_for(entity)
        target_types = [target_type.lower() for target_type in target_types] if target_types else ['enemies']

        if entity not in self.entities:
            entity = self.entity_by_uid(entity.entity_uid)

        entity_group = self.entities[entity]['group']
 
        attack_range = compute_max_weapon_range(self.session, action, range)

        if attack_range is None:
            raise Exception('attack range cannot be None')

        targets = []
        for k, prop in self.entities.items():
            if not k.allow_targeting():
                continue
            if 'self' not in target_types and k == entity:
                continue
            if 'allies' not in target_types and prop['group'] == entity_group and k != entity:
                continue
            if 'enemies' not in target_types and self.opposing(entity, k):
                continue
            if k.dead():
                continue
            if k.hp() is None:
                continue
            if 'ignore_los' not in target_types and not entity==k and not self.can_see(entity, k, active_perception=active_perception):
                continue
            if self.maps and self.map_for(k).distance(k, entity) * self.map_for(k).feet_per_grid > attack_range:
                continue
            if filter and not k.eval_if(filter):
                continue

            action.validate(self.map_for(k), target=k)

            if not action.errors:
                targets.append(k)
            else:
                print(f'{k}: action.errors')
                print(action.errors)

        if include_objects:
            _map = self.map_for(entity)
            for object, _position in _map.interactable_objects.items():
                if object.dead():
                    continue
                if 'ignore_los' not in target_types and not self.can_see(entity, object, active_perception=active_perception):
                    continue
                if _map.distance(object, entity) * _map.feet_per_grid > attack_range:
                    continue
                if filter and not k.eval_if(filter):
                    continue

                targets.append(object)

        return targets
    
        # @return [Boolean]
    def ally_within_enemy_melee_range(self, source, target, exclude=None, source_pos=None):
        _map = self.map_for(source)
        objects_around_me = _map.look(target)

        if exclude is None:
            exclude = []

        for object, _ in objects_around_me.items():
            if object in exclude:
                continue
            if object == source:
                continue

            state = self.entity_state_for(object)

            if not state:
                continue

            if object.incapacitated():
                continue

            if self.allies(source, object) and (_map.distance(target, object, entity_1_pos=source_pos) <= (object.melee_distance() / _map.feet_per_grid)):
                return True

        return False

    def execute_action(self, action):
        self.action(action)
        self.commit(action)

    def trigger_opportunity_attack(self, entity, target, cur_x, cur_y, action=None):
        event = {
            'target': target,
            'position': [cur_x, cur_y]
        }
        if action is None:
            action = entity.trigger_event('opportunity_attack', self, self.session, self.map_for(entity), event)
            # check if action is a generator due to a yield
            if hasattr(action, 'send'):
                return action

        if action:
            self.execute_action(action)
        return None

    def to_dict(self):
        # Prefer UID-friendly serialization. Keep legacy keys for backward compatibility.
        try:
            entities_uid = self.entities.as_uid_dict()
        except Exception:
            entities_uid = {}

        def _uids_for_group_map(groups):
            out = {}
            for g, ents in (groups or {}).items():
                uids = []
                for e in list(ents):
                    uid = getattr(e, 'entity_uid', None) or self.session.uid_for(e)
                    if uid is not None:
                        uids.append(str(uid))
                out[g] = uids
            return out

        return {
            # New UID-first entries
            'combat_order_uid': [getattr(e, 'entity_uid', None) for e in self.combat_order],
            'entities_uid': entities_uid,
            'groups_uid': _uids_for_group_map(self.groups),
            'late_comers_uid': [getattr(e, 'entity_uid', None) for e in self.late_comers],
            # Legacy fields (object-bearing) kept for compatibility with older loaders
            'combat_order': self.combat_order,
            'current_turn_index': self.current_turn_index,
            'round': self.round,
            # Convert UID map to a normal dict for YAML
            'entities': {e: self.entities[e] for e in self.entities},
            'groups': self.groups,
            'late_comers': self.late_comers,
            'battle_log': self.battle_log,
            'animation_log': self.animation_log,
            'session': self.session,
            'maps': self.maps,
            'readied_actions': {
                uid: state.to_dict() if hasattr(state, 'to_dict') else dict(state)
                for uid, state in (self.readied_actions or {}).items()
            },
        }

    def from_dict(data):
        battle = Battle(data['session'], data['maps'])
        # Restore combat order (prefer UID-based if present)
        combat_order_uid = data.get('combat_order_uid')
        if combat_order_uid:
            battle.combat_order = [battle.session.entity_registry.get(uid) for uid in combat_order_uid if battle.session.entity_registry.get(uid)]
        else:
            battle.combat_order = data.get('combat_order', [])

        battle.current_turn_index = data['current_turn_index']
        battle.round = data['round']

        # Restore entities state via UID map when available
        entities_uid = data.get('entities_uid')
        if entities_uid:
            # entities_uid is mapping of uid -> state
            for uid, state in entities_uid.items():
                ent = battle.session.entity_registry.get(uid)
                if ent is not None:
                    battle.entities[ent] = state
        else:
            # Legacy path: may be a plain dict keyed by live objects
            legacy_entities = data.get('entities', {})
            try:
                for ent, state in legacy_entities.items():
                    if ent is not None:
                        battle.session.register_entity(ent)
                        battle.entities[ent] = state
            except Exception:
                pass

        # Restore groups
        groups_uid = data.get('groups_uid')
        if groups_uid:
            restored = {}
            for g, uids in groups_uid.items():
                ents = set()
                for uid in (uids or []):
                    ent = battle.session.entity_registry.get(uid)
                    if ent is not None:
                        ents.add(ent)
                restored[g] = ents
            battle.groups = restored
        else:
            battle.groups = data.get('groups', {})

        # Late comers
        late_uids = data.get('late_comers_uid')
        if late_uids:
            battle.late_comers = [battle.session.entity_registry.get(uid) for uid in late_uids if battle.session.entity_registry.get(uid)]
        else:
            battle.late_comers = data.get('late_comers', [])

        battle.battle_log = data.get('battle_log', [])
        battle.animation_log = data.get('animation_log', [])

        # Restore readied actions if present.
        readied = data.get('readied_actions') or {}
        if readied:
            from natural20.ready_action import ReadyActionState
            for uid, raw in readied.items():
                try:
                    state = (raw if isinstance(raw, ReadyActionState)
                             else ReadyActionState.from_dict(raw or {}))
                    battle.readied_actions[str(uid)] = state
                except Exception:
                    continue

        # Backfill entity registry for quick UID lookups
        try:
            for ent in list(battle.entities.keys()):
                battle.session.register_entity(ent)
            for ent in battle.combat_order:
                if ent is not None:
                    battle.session.register_entity(ent)
        except Exception:
            pass
        return battle
