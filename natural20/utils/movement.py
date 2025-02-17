from natural20.entity import Entity
import json
import pdb

class Movement:
    def __init__(self, movement, original_budget, acrobatics_check_locations, athletics_check_locations, jump_locations, jump_start_locations, land_locations, jump_budget, budget, impediment):
        self.jump_start_locations = jump_start_locations
        self.athletics_check_locations = athletics_check_locations
        self.jump_locations = jump_locations
        self.land_locations = land_locations
        self.jump_budget = jump_budget
        self.movement = movement
        self.original_budget = original_budget
        self.acrobatics_check_locations = acrobatics_check_locations
        self.impediment = impediment
        self.budget = budget

    def __str__(self) -> str:
        return f"Movement: {self.movement} budget: {self.budget} jump_budget: {self.jump_budget} original_budget: {self.original_budget}"

    @staticmethod
    def empty():
        return Movement([], 0, [], [], [], [], [], 0, 0, None)

    @property
    def cost(self):
        return self.original_budget - self.budget

    def to_json(self):
        return json.dumps(self.__dict__)

    def to_dict(self):
        # Convert the object to a dictionary
        return {
            "jump_start_locations": self.jump_start_locations,
            "athletics_check_locations": self.athletics_check_locations,
            "jump_locations": self.jump_locations,
            "land_locations": self.land_locations,
            "jump_budget": self.jump_budget,
            "movement": self.movement,
            "original_budget": self.original_budget,
            "acrobatics_check_locations": self.acrobatics_check_locations,
            "impediment": self.impediment,
            "budget": self.budget
        }    

    @staticmethod
    def from_json(json_str):
        data = json.loads(json_str)
        return Movement(**data)

def valid_move_path(entity: Entity, path: list, battle, map, test_placement=True, manual_jump=None):
    return path == compute_actual_moves(entity, path, map, battle, entity.available_movement(battle) / map.feet_per_grid,
                                        test_placement=test_placement, manual_jump=manual_jump).movement

def requires_squeeze(entity: Entity, pos_x, pos_y, map, battle=None):
    return not map.passable(entity, pos_x, pos_y, battle, False) and map.passable(entity, pos_x, pos_y, battle, True)


def compute_actual_moves(entity: Entity, current_moves, map, battle, movement_budget, fixed_movement=False, test_placement=True, manual_jump=None):
    actual_moves = []
    provisional_moves = []
    jump_budget = int(entity.standing_jump_distance() / map.feet_per_grid)
    running_distance = 1
    jump_distance = 0
    jumped = False
    acrobatics_check_locations = []
    athletics_check_locations = []
    jump_start_locations = []
    land_locations = []
    jump_locations = []
    impediment = None
    original_budget = movement_budget

    for index, m in enumerate(current_moves):
        if len(m) != 2:
            raise Exception('invalid move coordinate')  # assert move correctness

        if index == 0:
            actual_moves.append(m)
            continue
        
        incorporeal_movement = False
        if not map.passable(entity, *m, battle):
            if entity.class_feature('incorporeal_movement') and map.passable(entity, *m, battle, True):
                incorporeal_movement = True
            else:
                impediment = 'path_blocked'
            break

        if fixed_movement:
            movement_budget -= 1
        else:
            if incorporeal_movement or (map.difficult_terrain(entity, *m, battle) and not entity.is_flying() and (not manual_jump or len(manual_jump)==0 or index not in manual_jump)):
                movement_budget -= 2
            else:
                movement_budget -= 1

            if requires_squeeze(entity, *m, map, battle):
                movement_budget -= 1
            if entity.prone():
                movement_budget -= 1 
            if entity.is_grappling():
                movement_budget -= 1

        if movement_budget < 0:
            impediment = 'movement_budget'
            break

        if not fixed_movement and (map.jump_required(entity, *m) or (manual_jump and index in manual_jump)):
            if entity.prone():  # can't jump if prone
                impediment = 'prone_need_to_jump'
                break

            if not jumped:
                jump_start_locations.append(m)

            jump_locations.append(m)
            jump_budget -= 1
            jump_distance += 1

            if not fixed_movement and jump_budget < 0:
                impediment = 'jump_distance_not_enough'
                break

            running_distance = 0
            jumped = True
            provisional_moves.append(m)

            entity_at_square = map.entity_at(*m)
            if entity_at_square and entity_at_square.conscious() and not entity_at_square.prone():
                athletics_check_locations.append(m)
        else:
            actual_moves += provisional_moves
            provisional_moves.clear()

            if jumped:
                land_locations.append(m)
            if jumped and map.difficult_terrain(entity, *m, battle):
                acrobatics_check_locations.append(m)
            running_distance += 1

            # if jump not required reset jump budgets
            if running_distance > 1:
                jump_budget = int(entity.long_jump_distance() / map.feet_per_grid)
            else:
                jump_budget = int(entity.standing_jump_distance() / map.feet_per_grid)
            jumped = False
            jump_distance = 0
            actual_moves.append(m)

    # handle case where end is a jump, in that case we land if this is possible
    if provisional_moves:
        actual_moves += provisional_moves
        m = actual_moves[-1]
        if jumped:
            land_locations.append(m)
        if jumped and map.difficult_terrain(entity, *m, battle):
            acrobatics_check_locations.append(m)
        jump_locations.remove(actual_moves[-1])

    while test_placement and not map.placeable(entity, *actual_moves[-1], battle):
        impediment = 'not_placeable'
        jump_locations.remove(actual_moves[-1])
        actual_moves.pop()

    return Movement(actual_moves, original_budget, acrobatics_check_locations, athletics_check_locations, jump_locations, jump_start_locations, land_locations, jump_budget,
                    movement_budget, impediment)


def retrieve_opportunity_attacks(entity, move_list, battle):
    if entity.disengage(battle):
        return []
    battle_map = battle.map_for(entity)
    if not battle_map:
        raise Exception('battle map not found')
    opportunity_attacks = opportunity_attack_list(entity, move_list, battle, battle_map)
    return [enemy_opportunity for enemy_opportunity in opportunity_attacks if enemy_opportunity['source'].has_reaction(battle) and enemy_opportunity['source'] not in entity.grappling_targets()]


def opportunity_attack_list(entity, current_moves, battle, map):
    opponents = battle.opponents_of(entity)
    entered_melee_range = set()
    left_melee_range = []
    for index, path in enumerate(current_moves):
        for enemy in opponents:
            if enemy not in map.entities:
                continue

            if battle:
                if not enemy.has_reaction(battle):
                    continue
            if enemy.entered_melee(map, entity, *path):
                entered_melee_range.add(enemy)
            elif enemy in entered_melee_range and not enemy.entered_melee(map, entity, *path) and not (entity.class_feature('flyby') and entity.flying):
                left_melee_range.append({'source': enemy, 'path': index})
    return left_melee_range
