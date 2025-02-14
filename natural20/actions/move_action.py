from typing import List, Tuple
from natural20.action import Action
from natural20.utils.movement import compute_actual_moves, retrieve_opportunity_attacks
from natural20.map_renderer import MapRenderer
from natural20.action import AsyncReactionHandler
import pdb
class MoveAction(Action):
    """
    Move action
    """
    move_path: List[Tuple[int, int]]
    jump_index: List[int]
    as_dash: bool
    as_bonus_action: bool

    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        if opts is None:
            opts = {}
        self.move_path = opts.get('move_path', [])
        self.jump_index = []
        self.as_dash = False
        self.as_bonus_action = False

    def __str__(self):
        if len(self.move_path) > 0:
            return f"move to {self.move_path[-1]}"
        else:
            return "move"
    
    def __repr__(self):
        if self.move_path:
            return f"move to {self.move_path[-1]}"
        return "move"
    
    def clone(self):
        return MoveAction(self.session, self.source, self.action_type, self.opts)

    @staticmethod
    def can(entity, battle):
        return battle is None or entity.available_movement(battle) > 0

    def build_map(self):
        def set_path(path_and_jump_index):
            action = self.clone()
            path, jump_index = path_and_jump_index
            action.move_path = path
            action.jump_index = jump_index
            return action

        return {
            'action': self,
            'param': [{
            'type': 'movement'
            }],
            'next': set_path
        }

    @staticmethod
    def build(session, source):
        action = MoveAction(session, source, 'move')
        return action.build_map()

    def resolve(self, _session, map, opts=None):
        if opts is None:
            opts = {}

        if self.move_path is None or len(self.move_path) == 0:
            if opts.get('move_path') is None:
                raise ValueError('no path specified')
        # print("move path", self.move_path)
        # renderer = MapRenderer(map)
        # print(renderer.render())
        self.result = []
        battle = opts.get('battle')

        current_moves = self.move_path or opts.get('move_path')
        jumps = self.jump_index or []

        actual_moves = []
        additional_effects = []

        if self.as_dash:
            movement_budget = (self.source.speed // 5)
        else:
            movement_budget = (self.source.available_movement(battle) // 5)

        movement = compute_actual_moves(self.source, current_moves, map, battle, movement_budget, manual_jump=jumps)
        actual_moves = movement.movement

        while actual_moves and not map.placeable(self.source, *actual_moves[-1], battle):
            actual_moves.pop()

        actual_moves = self.check_opportunity_attacks(self.source, actual_moves, battle)

        # if acutal_moves is a generator just exit
        if actual_moves and hasattr(actual_moves, 'send'):
            return actual_moves

        actual_moves = self.check_movement_athletics(actual_moves, movement.athletics_check_locations, battle, map)

        actual_moves = self.check_movement_acrobatics(actual_moves, movement.acrobatics_check_locations, battle)

        if self.source.unconscious():
            battle.entity_state_for(self.source)['movement'] = 0
            return self

        # cutoff = False

        safe_moves = []
        for move in actual_moves:
            is_flying_or_jumping = self.source.flying or move in movement.jump_locations
            trigger_results = map.area_trigger(self.source, move, is_flying_or_jumping)
            if not trigger_results:
                safe_moves.append(move)
            else:
                safe_moves.append(move)
                additional_effects += trigger_results
                break

        movement = compute_actual_moves(self.source, safe_moves, map, battle, movement_budget, manual_jump=jumps)

        if self.source.is_grappling():
            grappled_movement = movement.movement.copy()
            grappled_movement.pop()

            for grappling_target in self.source.grappling_targets():
                start_pos = map.entity_or_object_pos(grappling_target)
                grappled_entity_movement = [start_pos] + grappled_movement

                additional_effects.append({
                    'source': grappling_target,
                    'map': map,
                    'battle': battle,
                    'type': 'move',
                    'path': grappled_entity_movement,
                    'as_dash': self.as_dash,
                    'as_bonus_action': self.as_bonus_action,
                    'move_cost': 0,
                    'position': grappled_entity_movement[-1]
                })

                grappled_movement.pop()
        # print(f"budget: {movement_budget}  {movement.budget}")
        movement_cost = movement_budget - movement.budget

        self.result.append({
            'source': self.source,
            'map': map,
            'battle': battle,
            'as_dash': self.as_dash,
            'as_bonus_action': self.as_bonus_action,
            'type': 'move',
            'path': movement.movement,
            'move_cost': movement_cost,
            'position': movement.movement[-1]
        })
        self.result += additional_effects

        return self

    def check_opportunity_attacks(self, entity, move_list, battle, grappled=False):
        if battle:
            for enemy_opportunity in retrieve_opportunity_attacks(entity, move_list, battle):
                original_location = move_list[:enemy_opportunity['path']]
                attack_location = original_location[-1]
                stored_reaction = self.has_async_reaction_for_source(enemy_opportunity['source'], 'opportunity_attack')

                if stored_reaction is not False:
                    result = battle.trigger_opportunity_attack(enemy_opportunity['source'], entity, *attack_location, stored_reaction)
                else:
                    result = battle.trigger_opportunity_attack(enemy_opportunity['source'], entity, *attack_location)
                    if hasattr(result, 'send'):
                        raise AsyncReactionHandler(enemy_opportunity['source'], result, self, 'opportunity_attack')

                if not grappled and not entity.conscious():
                    return original_location

                if entity.prone():
                    return original_location

        return move_list

    @staticmethod
    def apply(battle, item, session=None):
        item_type = item['type']
        if item_type == 'state':
            for k, v in item['params'].items():
                setattr(item['source'], k, v)
        elif item_type in ['acrobatics', 'athletics']:
            if item['success']:
                print(f"{item['source'].name} {item_type} check success")
                battle.session.event_manager.received_event(source=item['source'], event=item_type, success=True,
                                                     roll=item['roll'])
            else:
                print(f"{item['source'].name} {item_type} check failed and is now prone")
                battle.session.event_manager.received_event(source=item['source'], event=item_type, success=False,
                                                     roll=item['roll'])
                item['source'].prone()
        elif item_type == 'drop_grapple':
            item['target'].escape_grapple_from(item['source'])
            print(f"{item['source'].name} dropped grapple on {item['target'].name}")
            battle.session.event_manager.received_event(event='drop_grapple',
                                                  target=item['target'], source=item['source'],
                                                  source_roll=item['source_roll'],
                                                  target_roll=item['target_roll'])
        elif item_type == 'move':
            item['map'].move_to(item['source'], *item['position'], battle)

            # mark path
            if battle:
                path_taken = item['path']
                positions_entered = battle.entity_state_for(item['source'])['positions_entered']
                for p in path_taken:
                    p_key = tuple(p)
                    visit_count = positions_entered.get(p_key, 0)
                    positions_entered[p_key] = visit_count + 1

            if item['as_dash'] and item['as_bonus_action']:
                battle.entity_state_for(item['source'])['bonus_action'] -= 1
            elif item['as_dash']:
                battle.entity_state_for(item['source'])['action'] -= 1
            elif battle:
                battle.entity_state_for(item['source'])['movement'] -= item['move_cost'] * battle.map_for(item['source']).feet_per_grid

            battle.session.event_manager.received_event({
                'event': 'move',
                'source': item['source'],
                'position': item['position'],
                'path': item['path'],
                'move_cost' : item['move_cost'],
                'feet_per_grid': battle.map_for(item['source']).feet_per_grid if battle.map_for(item['source']) else None,
                'as_dash': item['as_dash'],
                'as_bonus': item['as_bonus_action']
            })

    def check_movement_acrobatics(self, actual_moves, dexterity_checks, battle):
        cutoff = len(actual_moves) - 1
        for index, m in enumerate(actual_moves):
            if m not in dexterity_checks:
                continue

            acrobatics_roll = self.source.acrobatics_check(battle)
            if acrobatics_roll.result() >= 10:
                self.result.append({
                    'source': self.source,
                    'type': 'acrobatics',
                    'success': True,
                    'roll': acrobatics_roll,
                    'location': m
                })
            else:
                self.result.append({
                    'source': self.source,
                    'type': 'acrobatics',
                    'success': False,
                    'roll': acrobatics_roll,
                    'location': m
                })
                cutoff = index
                break

        return actual_moves[:cutoff + 1]

    def check_movement_athletics(self, actual_moves, athletics_checks, battle, map):
        cutoff = len(actual_moves) - 1
        for index, m in enumerate(actual_moves):
            if m not in athletics_checks:
                continue

            athletics_roll = self.source.athletics_check(battle)
            if athletics_roll.result() >= 10:
                self.result.append({
                    'source': self.source,
                    'type': 'athletics',
                    'success': True,
                    'roll': athletics_roll,
                    'location': m
                })
            else:
                self.result.append({
                    'source': self.source,
                    'type': 'athletics',
                    'success': False,
                    'roll': athletics_roll,
                    'location': m
                })
                cutoff = index - 1
                while cutoff >= 0 and not map.placeable(self.source, *actual_moves[cutoff], battle):
                    cutoff -= 1
                break

        return actual_moves[:cutoff + 1]
