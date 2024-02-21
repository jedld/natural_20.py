import dndice
import random
from natural20.generic_controller import GenericController

class Battle():
    def __init__(self, map):
        self.map = map
        self.combat_order = []
        self.current_turn_index = 0
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
