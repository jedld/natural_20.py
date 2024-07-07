import dndice
import random
from natural20.generic_controller import GenericController
from natural20.action import Action
from natural20.weapons import compute_max_weapon_range
from natural20.map import Map
from natural20.utils.utils import Session
from natural20.entity import Entity
from natural20.event_manager import EventManager
import pdb
class Battle():
    def __init__(self, session: Session, map: Map,):
        self.map = map
        self.session = session
        self.combat_order = []
        self.current_turn_index = 0
        self.battle_field_events = {}
        self.round = 0
        self.entities = {}
        self.groups = {}
        self.late_comers = []
        self.battle_log = []
        self.standard_controller = GenericController
        self.event_manager = session.event_manager
        self.opposing_groups = {
        'a': ['b'],
        'b': ['a'],
        'c': ['c']
      }

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

    def start(self, combat_order=None):
        if combat_order:
            self.combat_order = combat_order
            return

        # roll for initiative
        _combat_order = [[entity,v] for entity, v in self.entities.items() if not entity.dead()]
        for entity, v in _combat_order:
            v['initiative'] = entity.initiative(self)

        self.combat_order = [entity for entity, _ in _combat_order]
        self.started = True
        self.current_turn_index = 0

        self.combat_order = sorted(self.combat_order, key=lambda a: self.entities[a]['initiative'], reverse=True)

    def roll_for(self, entity, die_type, number_of_times, description, advantage=False, disadvantage=False, controller=None):
        if advantage or disadvantage:
            return [random.sample(range(1, die_type + 1), 2) for _ in range(number_of_times)]
        else:
            return [random.randint(1, die_type) for _ in range(number_of_times)]
        
    def controller_for(self, entity):
        if entity not in self.entities:
            return None

        return self.entities[entity]['controller']


    def combat_ongoing(self):
        return True

    def current_turn(self) -> Entity:
        return self.combat_order[self.current_turn_index]

    def check_combat(self):
        if not self.started and not self.battle_ends():
            self.start()
            self.event_manager.received_event(source=self, event='start_of_combat', target=self.current_turn,
                                                  combat_order=[[e, self.entities[e]['initiative']] for e in self.combat_order])
            # print(f"Combat starts with {self.combat_order[0].name}.")
            return True
        return False

    def start_turn(self):
        if self.current_turn().unconscious() and not self.current_turn().stable():
            self.current_turn().death_saving_throw(self)

    def end_turn(self):
        self.trigger_event('end_of_round', self,  { "target" : self.current_turn()})
    
    def battle_ends(self):
        # check if the entities that are alive are all in the same group
        groups = set()
        for entity in self.combat_order:
            if entity.conscious():
                groups.add(self.entities[entity]['group'])
        return len(groups) == 1                

    def next_turn(self, max_rounds=None):
        self.trigger_event('end_of_round', self, { "target" : self.current_turn()})
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
      return self.entities.get(entity, None)
    

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
    
    def enemy_in_melee_range(self, source, exclude=[], source_pos=None):
        objects_around_me = self.map.look(source)

        for object in objects_around_me:
            if object in exclude:
                continue

            state = self.entity_state_for(object)
            if not state:
                continue
            if not object.conscious:
                continue

            if self.opposing(source, object) and (self.map.distance(source, object, entity_1_pos=source_pos) <= (object.melee_distance() / self.map.feet_per_grid)):
                return True

        return False

    def action(self, action):
        opts = {
            'battle': self
        }
        return action.resolve(self.session, self.map, opts)
    
    def resolve_action(self, source, action_type, opts={}):
        action = next((act for act in source.available_actions(self.session, self) if act.action_type == action_type), None)
        opts['battle'] = self
        return action.resolve(self.session, self.map, opts) if action else None
    
    def commit(self, action):
        if action is None:
            return

        # check_action_serialization(action)
        for item in action.result:
            for klass in Action.__subclasses__():
                klass.apply(self, item)

        if action.action_type == 'move':
            self.trigger_event('movement', action.source, { 'move_path': action.move_path})
        elif action.action_type == 'interact':
            self.trigger_event('interact', action)

        self.battle_log.append(action)


    def entity_group_for(self, entity):
        if entity not in self.entities:
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

        return source_group2 in self.opposing_groups.get(source_group1, [])
    
    def allies(self, entity1, entity2):
        source_state1 = self.entity_state_for(entity1)
        source_state2 = self.entity_state_for(entity2)
        if source_state1 is None or source_state2 is None:
            return False

        source_group1 = source_state1['group']
        source_group2 = source_state2['group']

        return source_group1 == source_group2

    def trigger_event(self, event, source, opt={}):
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
        if not entity2.hiding(self):
            return True

        cover_value = self.map.cover_calculation(self.map, entity1, entity2, entity_1_pos=entity_1_pos,
                                                 naturally_stealthy=entity2.class_feature('naturally_stealthy'))

        if cover_value > 0:
            entity_2_state = self.entity_state_for(entity2)
            if entity_2_state['stealth'] > max(active_perception, entity1.passive_perception):
                return False

        return True

    def valid_targets_for(self, entity, action, target_types=['enemies'], range=None, active_perception=None, include_objects=False, filter=None):
        if not isinstance(action, Action):
            raise Exception('not an action')

        active_perception = active_perception if active_perception is not None else self.active_perception_for(entity)
        target_types = [target_type.lower() for target_type in target_types] if target_types else ['enemies']
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
            if k.hp is None:
                continue
            if 'ignore_los' not in target_types and not self.can_see(entity, k, active_perception=active_perception):
                continue
            if self.map.distance(k, entity) * self.map.feet_per_grid > attack_range:
                continue
            if filter and not k.eval_if(filter):
                continue

            action.target = k
            action.validate()
            if not action.errors:
                targets.append(k)

        if include_objects:
            for object, _position in self.map.interactable_objects.items():
                if object.dead():
                    continue
                if not 'ignore_los' in target_types and not self.can_see(entity, object, active_perception=active_perception):
                    continue
                if self.map.distance(object, entity) * self.map.feet_per_grid > attack_range:
                    continue
                if filter and not k.eval_if(filter):
                    continue

                targets.append(object)

        return targets
    

    def trigger_opportunity_attack(self, entity, target, cur_x, cur_y):
        event = {
            'target': target,
            'position': [cur_x, cur_y]
        }
        action = entity.trigger_event('opportunity_attack', self, self.session, self.map, event)
        if action:
            self.action(action)
            self.commit(action)
