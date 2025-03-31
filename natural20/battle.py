import random
from natural20.generic_controller import GenericController
from natural20.action import Action
from natural20.actions.attack_action import AttackAction, TwoWeaponAttackAction
from natural20.weapons import compute_max_weapon_range
from natural20.utils.ac_utils import cover_calculation
from natural20.map import Map
from natural20.session import Session
from natural20.entity import Entity
from natural20.die_roll import DieRoll
import pdb
class Battle():
    def __init__(self, session: Session, maps: Map, standard_controller = None, animation_log_enabled=False):
        if isinstance(maps, list):
            self.maps = maps
        elif isinstance(maps, dict):
            self.maps = maps.values()
        elif maps:
            self.maps = [maps]
        else:
            self.maps = None
        self.session = session
        self.combat_order = []
        self.current_turn_index = 0
        self.battle_field_events = {}
        self.round = 0
        self.entities = {}
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
            'target_effect': {},
            'two_weapon': None,
            'positions_entered': {},
            'controller': controller,
            'help_with': {}
        }

        self.entities[entity] = state
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

        if isinstance(position, list) or isinstance(position, tuple):
            self.maps[index].place(position, entity, token, self)
        else:
            self.maps[index].place_at_spawn_point(position, entity, token)

    # remove an entity from the battle and from the map
    def remove(self, entity):
        if self.current_turn_index == len(self.combat_order) - 1:
            self.current_turn_index = 0

        del self.entities[entity]
        if entity in self.late_comers:
            self.late_comers.remove(entity)
        if entity in self.combat_order:
            self.combat_order.remove(entity)

        if self.map_for(entity):
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

        return self.entities[entity]['controller']


    def set_controller_for(self, entity, controller):
        if entity not in self.entities:
            return False

        self.entities[entity]['controller'] = controller
        return True

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

        if self.animation_log_enabled:
            self.animation_log.append([entity.entity_uid, [entity_pos], None])

        if entity.unconscious() and not entity.stable():
            entity.death_saving_throw(self)
        self.trigger_event('start_of_turn', self, { "target" : entity })

    def end_turn(self):
        self.current_turn().resolve_trigger('end_of_turn')
        self.trigger_event('end_of_turn', self,  { "target" : self.current_turn()})

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
            if self.current_turn().conscious():
                self.current_turn().reset_turn(self)
                if callback(self.current_turn()):
                    continue

            self.current_turn().resolve_trigger('end_of_turn')
            # print("Next turn")
            result = self.next_turn(max_rounds)
            # print(f"Result: {result}")
            if result == 'tpk':
                return 'tpk'
            if result:
                return result
            
    def entity_by_uid(self, entity_uid):
        for map in self.maps:
            entity = map.entity_by_uid(entity_uid)
            if entity:
                return entity
        return None

    def entity_state_for(self, entity):
        entity_state = self.entities.get(entity, None)
        if entity_state is None:
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
            if source in entity_state['help_with']:
                entity_state['help_with'].pop(source)

    def help_with(self, entity):
        if entity in self.entities:
            return self.entities[entity]['help_with']
        return {}

    def dismiss_help_for(self, entity):
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

            if self.opposing(source, object) and (map_for_source.distance(source, object, entity_1_pos=source_pos) <= (object.melee_distance() / map_for_source.feet_per_grid)):
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
        for item in action.result:
            for klass in Action.__subclasses__():
                klass.apply(self, item, self.session)

                if self.animation_log_enabled:
                    if item.get('perception_targets'):
                        perception_targets = item['perception_targets']
                        self.animation_log.append({"type": "perception", "targets": [p.entity_uid for p in perception_targets]})

        if action.action_type == 'move':
            self.trigger_event('movement', action.source, { 'move_path': action.move_path})
            if self.animation_log_enabled:
                if len(self.animation_log) == 0:
                    self.animation_log.append([action.source.entity_uid, [self.entity_or_object_pos(action.source)], None])
                self.animation_log.append([action.source.entity_uid, action.move_path, None])
        elif action.action_type == 'attack':
            if self.animation_log_enabled and len(self.animation_log) > 0:
                self.animation_log[-1][2] = { "target" : action.target.entity_uid, "type": "attack", "ranged" : action.ranged_attack(), "label": action.label() }
        elif action.action_type == 'spell':
            if self.animation_log_enabled and action.target and action.avg_damage(self) > 0:
                if len(self.animation_log) == 0:
                    self.animation_log.append([action.source.entity_uid, [self.entity_or_object_pos(action.source)], None])
                self.animation_log[-1][2] = { "target" : action.target.entity_uid, "type" : "spell", "label" : action.label() }
        elif action.action_type == 'interact':
            self.trigger_event('interact', action)

        self.battle_log.append(action)
        return None

    def get_animation_logs(self):
        return self.animation_log

    def clear_animation_logs(self):
        self.animation_log.clear()
        entity = self.current_turn()
        entity_pos = self.entity_or_object_pos(entity)
        self.animation_log.append([entity.entity_uid, [entity_pos], None])

    def entity_group_for(self, entity):
        if entity not in self.entities:
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
        valid_resources = ['action', 'reaction', 'bonus_action', 'movement', 'free_object_interaction']
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

    def trigger_event(self, event, source, opt=None):
        if opt is None:
            opt = {}
        if event in self.battle_field_events:
            for object, handler in self.battle_field_events[event].items():
                object.__getattribute__(handler)(self, source, {**opt, 'ui_controller': self.controller_for(source)})
        if self.maps and self.map_for(source):
            self.map_for(source).activate_map_triggers(event, source, {**opt, 'ui_controller': self.controller_for(source)})

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
        if not map1.can_see(entity1, entity2, entity_1_pos=entity_1_pos, entity_2_pos=entity_2_pos):
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
            self.action(action)
            self.commit(action)
        return None

    def to_dict(self):
        return {
            'combat_order': self.combat_order,
            'current_turn_index': self.current_turn_index,
            'round': self.round,
            'entities': self.entities,
            'groups': self.groups,
            'late_comers': self.late_comers,
            'battle_log': self.battle_log,
            'animation_log': self.animation_log,
            'session': self.session,
            'maps': self.maps
        }

    def from_dict(data):
        battle = Battle(data['session'], data['maps'])
        battle.combat_order = data['combat_order']
        battle.current_turn_index = data['current_turn_index']
        battle.round = data['round']
        battle.entities = data['entities']
        battle.groups = data['groups']
        battle.late_comers = data['late_comers']
        battle.battle_log = data['battle_log']
        battle.animation_log = data['animation_log']
        return battle
