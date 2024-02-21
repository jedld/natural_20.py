import dndice
import random
from natural20.generic_controller import GenericController

class Battle():
    def __init__(self, map):
        self.map = map
        self.combat_order = []
        self.current_turn_index = 0
        self.round = 0
        self.entities = {}
        self.groups = {}
        self.standard_controller = GenericController()

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

            self.map.place(position, entity, token, self)

    def start(self, combat_order=None):
        if combat_order:
            self.combat_order = combat_order
            return

        # roll for initiative
        _combat_order = [[entity,v] for entity, v in self.entities.items() if not entity.dead()]
        for entity, v in _combat_order:
            v['initiative'] = entity.initiative(self)

        self.combat_order = [entity for entity in self.combat_order]
        self.started = True
        self.current_turn_index = 0
        self.combat_order = sorted(self.combat_order, key=lambda a: self.entities[a]['initiative'], reverse=True)

    def roll_for(self, entity, die_type, number_of_times, description, advantage=False, disadvantage=False, controller=None):
        if advantage or disadvantage:
            return [random.sample(range(1, die_type + 1), 2) for _ in range(number_of_times)]
        else:
            return [random.randint(1, die_type) for _ in range(number_of_times)]
        

    def current_turn(self):
        return self.combat_order[self.current_turn_index]

    def check_combat(self):
        if not self.started and not self.battle_ends():
            self.start()
            # Natural20.EventManager.received_event(source=self, event='start_of_combat', target=self.current_turn,
            #                                       combat_order=[[e, self.entities[e]['initiative']] for e in self.combat_order])
            print(f"Combat starts with {self.combat_order[0].name}.")
            return True
        return False

    def start_turn(self):
        print(f"{self.current_turn().name} starts their turn.")

        if self.current_turn().unconscious() and not self.current_turn().stable():
            self.current_turn().death_saving_throw(self)

    def end_turn(self):
        pass
        # self.trigger_event!('end_of_round', self, target=self.current_turn())
    
    def battle_ends(self):
        # check if the entities that are alive are all in the same group
        groups = set()
        for entity in self.combat_order:
            if not entity.dead():
                groups.add(self.entities[entity]['group'])
        return len(groups) == 1                

    def next_turn(self, max_rounds=None):
        #  self.trigger_event!('end_of_round', self, target=self.current_turn())

        if self.started and self.battle_ends():
            # Natural20.EventManager.received_event(source=self, event='end_of_combat')
            self.started = False
            return 'tpk'

        self.current_turn_index += 1
        if self.current_turn_index < len(self.combat_order):
            self.current_turn_index = 0
            self.round += 1

            # Natural20.EventManager.received_event(source=self, event='top_of_the_round', round=self.round,
            #                                       target=self.current_turn())

            if max_rounds is not None and self.round > max_rounds:
                return True
        return False

    def while_active(self, max_rounds=None, block=None):
        while True:
            self.start_turn()

            if self.current_turn().conscious():
                self.current_turn().reset_turn(self)
                if block(self.current_turn()):
                    continue
            self.current_turn().resolve_trigger('end_of_turn')

            result = self.next_turn(max_rounds)
            if result == 'tpk':
                return 'tpk'
            if result:
                return result
            
    def entity_state_for(self, entity):
      return self.entities[entity]
    

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
        self.entities[entity]['controller'].move_for(entity, self)
