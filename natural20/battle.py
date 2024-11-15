import random
from natural20.generic_controller import GenericController
from natural20.action import Action
from natural20.actions.attack_action import AttackAction, TwoWeaponAttackAction
from natural20.weapons import compute_max_weapon_range
from natural20.utils.ac_utils import cover_calculation
from natural20.map import Map
from natural20.session import Session
from natural20.entity import Entity
import pdb
class Battle():
    def __init__(self, session: Session, map: Map, standard_controller = None, animation_log_enabled=False):
        self.map = map
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

    def add(self, entity, group, controller=None, position=None, token=None, add_to_initiative=False):
        if entity in self.entities:
            return

        if entity is None:
            raise ValueError('entity cannot be nil')

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
        }

        self.entities[entity] = state
        self.groups.setdefault(group, set()).add(entity)

        if add_to_initiative:
            self.combat_order.append(entity)

        if position is None or self.map is None:
            return

        if isinstance(position, list) or isinstance(position, tuple):
            self.map.place(position, entity, token, self)
        else:
            self.map.place_at_spawn_point(position, entity, token)

    # remove an entity from the battle and from the map
    def remove(self, entity):
        del self.entities[entity]
        if entity in self.late_comers:
            self.late_comers.remove(entity)
        if entity in self.combat_order:
            self.combat_order.remove(entity)
        if self.map:
            self.map.remove(entity, battle=self)

    def start(self, combat_order=None, custom_initiative=None):
        self.started = True
        self.current_turn_index = 0

        if combat_order:
            self.combat_order = combat_order
            return

        # roll for initiative
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
        if advantage or disadvantage:
            return [random.sample(range(1, die_type + 1), 2) for _ in range(number_of_times)]
        else:
            return [random.randint(1, die_type) for _ in range(number_of_times)]
        
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
        if self.current_turn_index >= len(self.combat_order):
            raise Exception(f'current_turn_index out of bounds {self.current_turn_index} >= {len(self.combat_order)}')
        return self.combat_order[self.current_turn_index]

    def check_combat(self):
        if not self.started and not self.battle_ends():
            self.start()

            # print(f"Combat starts with {self.combat_order[0].name}.")
            return True
        return False

    def start_turn(self):
        entity = self.current_turn()
        entity_pos = self.map.entity_or_object_pos(entity)

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

    def entity_state_for(self, entity):
        entity_state = self.entities.get(entity, None)
        if entity_state is None:
            _entity = self.map.entity_by_uid(entity.entity_uid)
            return self.entities.get(_entity, None)
        return entity_state

    def dismiss_help_actions_for(self, source):
        for entity in self.entities.values():
            if entity.get('target_effect') and source in entity['target_effect']:
                if entity['target_effect'][source] in ['help', 'help_ability_check']:
                    del entity['target_effect'][source]

    def has_controller_for(self, entity):
        if entity not in self.entities:
            raise Exception('unknown entity in battle')

        return self.entities[entity]['controller'] != 'manual'

    def move_for(self, entity):
        return self.entities[entity]['controller'].move_for(entity, self)

    def help_with(self, target):
        if target in self.entities:
            return 'help' in self.entities[target]['target_effect'].values()

        return False
    
    # Returns opponents of entity
    # @param entity [Natural20::Entity] target entity
    # @return [List<Natural20::Entity>]
    def opponents_of(self, entity):
        return [k for k in (list(self.entities.keys()) + self.late_comers) if not k.dead() and self.opposing(k, entity)]
    
    def allies_of(self, entity):
        return [k for k in (list(self.entities.keys()) + self.late_comers) if not k.dead() and self.allies(k, entity)]

    def enemy_in_melee_range(self, source, exclude=None, source_pos=None):
        objects_around_me = self.map.look(source)
        exclude = exclude or []
        for object in objects_around_me:
            if object in exclude:
                continue

            state = self.entity_state_for(object)
            if not state:
                continue
            if not object.conscious():
                continue

            if self.opposing(source, object) and (self.map.distance(source, object, entity_1_pos=source_pos) <= (object.melee_distance() / self.map.feet_per_grid)):
                return True

        return False

    def action(self, action):
        opts = {
            'battle': self
        }
        return action.resolve(self.session, self.map, opts)
    
    def resolve_action(self, source, action_type, opts=None):
        if opts is None:
            opts = {}
        action = next((act for act in source.available_actions(self.session, self) if act.action_type == action_type), None)
        opts['battle'] = self
        return action.resolve(self.session, self.map, opts) if action else None
    
    def commit(self, action):
        if action is None:
            print('action is None')
            return

        # check_action_serialization(action)
        for item in action.result:
            for klass in Action.__subclasses__():
                klass.apply(self, item)
        if action.action_type == 'move':
            self.trigger_event('movement', action.source, { 'move_path': action.move_path})
            if self.animation_log_enabled:
                if len(self.animation_log) == 0:
                    self.animation_log.append([action.source.entity_uid, [self.map.entity_or_object_pos(action.source)], None])
                self.animation_log.append([action.source.entity_uid, action.move_path, None])
        elif action.action_type == 'attack':
            if self.animation_log_enabled and len(self.animation_log) > 0:
                self.animation_log[-1][2] = { "target" : action.target.entity_uid, "type": "attack", "ranged" : action.ranged_attack(), "label": action.label() }
        elif action.action_type == 'spell':
            if self.animation_log_enabled and action.target and action.avg_damage(self) > 0:
                if len(self.animation_log) == 0:
                    self.animation_log.append([action.source.entity_uid, [self.map.entity_or_object_pos(action.source)], None])
                self.animation_log[-1][2] = { "target" : action.target.entity_uid, "type" : "spell", "label" : action.label() }
        elif action.action_type == 'interact':
            self.trigger_event('interact', action)

        self.battle_log.append(action)

    def get_animation_logs(self):
        return self.animation_log
    
    def clear_animation_logs(self):
        self.animation_log.clear()
        entity = self.current_turn()
        entity_pos = self.map.entity_or_object_pos(entity)
        self.animation_log.append([entity.entity_uid, [entity_pos], None])

    def entity_group_for(self, entity):
        if entity not in self.entities:
            _entity = self.map.entity_by_uid(entity.entity_uid)
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
    

    def dismiss_help_for(self, target):
        if target in self.entities:
            self.entities[target]['target_effect'] = {k: v for k, v in self.entities[target]['target_effect'].items() if v != 'help'}

    def active_perception_for(self, entity):
        return self.entities[entity].get('active_perception', 0)
    
    # Consumes an action resource
    # @param entity [Natural20::Entity]
    # @param resource [str]
    def consume(self, entity, resource, qty=1):
        valid_resources = ['action', 'reaction', 'bonus_action', 'movement']
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
        self.map.activate_map_triggers(event, source, {**opt, 'ui_controller': self.controller_for(source)})

    # Determines if an entity can see someone in battle
    # @param entity1 [Natural20::Entity] observer
    # @param entity2 [Natural20::Entity] entity being observed
    # @return [Boolean]
    def can_see(self, entity1, entity2, active_perception=0, entity_1_pos=None, entity_2_pos=None):
        if entity1 == entity2:
            return True
        if not self.map.can_see(entity1, entity2, entity_1_pos=entity_1_pos, entity_2_pos=entity_2_pos):
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
            entity = self.map.entity_by_uid(entity.entity_uid)

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
            if self.map and self.map.distance(k, entity) * self.map.feet_per_grid > attack_range:
                continue
            if filter and not k.eval_if(filter):
                continue

            action.validate(target=k)

            if not action.errors:
                targets.append(k)
            else:
                print(f'{k}: action.errors')
                print(action.errors)

        if include_objects:
            for object, _position in self.map.interactable_objects.items():
                if object.dead():
                    continue
                if 'ignore_los' not in target_types and not self.can_see(entity, object, active_perception=active_perception):
                    continue
                if self.map.distance(object, entity) * self.map.feet_per_grid > attack_range:
                    continue
                if filter and not k.eval_if(filter):
                    continue

                targets.append(object)

        return targets
    
        # @return [Boolean]
    def ally_within_enemy_melee_range(self, source, target, exclude=None, source_pos=None):
        objects_around_me = self.map.look(target)

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

            if self.allies(source, object) and (self.map.distance(target, object, entity_1_pos=source_pos) <= (object.melee_distance() / self.map.feet_per_grid)):
                return True

        return False

    def trigger_opportunity_attack(self, entity, target, cur_x, cur_y):
        event = {
            'target': target,
            'position': [cur_x, cur_y]
        }
        action = entity.trigger_event('opportunity_attack', self, self.session, self.map, event)
        if action:
            self.action(action)
            self.commit(action)
