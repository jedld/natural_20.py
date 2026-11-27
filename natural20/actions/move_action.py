from typing import List, Tuple
from natural20.action import Action
from natural20.utils.movement import compute_actual_moves, retrieve_opportunity_attacks
from natural20.map_renderer import MapRenderer
from natural20.action import AsyncReactionHandler
import pdb


def reveal_if_exposed(battle, session, source):
    """SRD \"Hiding\" (p.183): you can't hide from a creature that can see
    you, and Hide ends when an enemy finds the creature. When a hidden
    creature finishes moving, break the hide if any conscious enemy now
    has unobstructed, unobscured line of sight to its new square — the
    automatic-discovery threshold the players' guide calls adjudication
    (issue #6 item 56). Hiding behind a wall, in darkness, or while
    invisible keeps working: stealth is only lost when the new square is
    plainly in an enemy's sight."""
    if battle is None or source is None or not source.hidden():
        return
    if not battle.map_for(source):
        return
    previous_stealth = source.hidden_stealth
    # Judge discovery with the hide already broken: can_see() consults the
    # creature's stealth while it is hidden, which would compare passive
    # perception against the old bonus instead of asking whether the
    # square itself is plainly visible.
    source.break_stealth()
    exposed = False
    for observer in list(battle.entities.keys()):
        if observer is source or not observer.conscious():
            # A dead *or unconscious* creature cannot be the observer that
            # finds the hider (a 0-HP enemy does not break Hide).
            continue
        if not battle.opposing(source, observer):
            continue
        if battle.can_see(observer, source):
            exposed = True
            break
    if not exposed and previous_stealth is not None:
        source.do_hide(previous_stealth)


def drag_square_free(map, target, grappler, pos, grappler_stay_squares=()):
    """Can the dragged ``target`` END its trail at ``pos``?

    SRD 5.2.1 never lets a move END in another creature's space, so a
    grappler may not leave its catch on an occupied square (issue #6:
    dragging a hero along a path that crosses an ally dropped the hero on
    the ally's token). Every trail square is a square the grappler itself
    moves through, so terrain/objects are already legal for the target;
    what can block is a creature token — except the grappler's, for the
    squares it is VACATING this very move. A Large grappler only partly
    vacates its old footprint, so the squares it keeps occupying
    (``grappler_stay_squares``, its footprint at the move's end) also
    block the target: a 2x2 grappler stepping west or north must not drop
    its catch inside its own body (issue #6 item 5).
    """
    x, y = pos
    for p_x, p_y in map.entity_squares_at_pos(target, x, y):
        if (p_x, p_y) in grappler_stay_squares:
            return False
        token = map.tokens[p_x][p_y]
        if token and token['entity'] is not target and token['entity'] is not grappler:
            return False
    return True


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
        self.stack_descent = opts.get('stack_descent')
        self.as_dash = False
        self.as_bonus_action = False
        # Out-of-combat exploration: when True the move budget is not
        # capped by the entity's speed. Only set this when there is no
        # active battle (or the entity is not a combatant) — the engine
        # still validates passability tile-by-tile.
        self.unlimited_movement = False
        # Legendary "Move" option: budget is the creature's full speed and
        # the cost is paid from the legendary action pool, not movement.
        self.legendary_cost = 1
        self.ignore_opportunity_attacks = False

    def to_dict(self):
        hash = super().to_dict()
        hash['move_path'] = self.move_path
        hash['jump_index'] = self.jump_index
        hash['as_dash'] = self.as_dash
        hash['as_bonus_action'] = self.as_bonus_action
        hash['unlimited_movement'] = self.unlimited_movement
        hash['stack_descent'] = self.stack_descent
        hash['legendary_action'] = self.legendary_action
        hash['legendary_cost'] = self.legendary_cost
        hash['ignore_opportunity_attacks'] = self.ignore_opportunity_attacks
        return hash
    
    @staticmethod
    def from_dict(hash):
        action = MoveAction(hash.get('session'), hash.get('source'), hash['action_type'])
        action.move_path = hash.get('move_path', [])
        action.jump_index = hash.get('jump_index', [])
        action.as_dash = hash.get('as_dash', False)
        action.as_bonus_action = hash.get('as_bonus_action', False)
        action.unlimited_movement = hash.get('unlimited_movement', False)
        action.stack_descent = hash.get('stack_descent')
        action.legendary_action = hash.get('legendary_action', False)
        action.legendary_cost = hash.get('legendary_cost', 1)
        action.ignore_opportunity_attacks = hash.get('ignore_opportunity_attacks', False)
        return action

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
        action = MoveAction(self.session, self.source, self.action_type, self.opts)
        action.legendary_action = self.legendary_action
        action.legendary_cost = self.legendary_cost
        action.ignore_opportunity_attacks = self.ignore_opportunity_attacks
        return action

    @staticmethod
    def can(entity, battle):
        # Out of combat, available_movement falls back to speed(); a 0-speed
        # state (shell defense, restrained, etc.) must still block movement.
        return entity.available_movement(battle) > 0

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

        if battle is not None and len(current_moves) > 1:
            # A deferred reaction can interrupt a move and then DISPLACE the
            # mover (a push rider, a knockback, a teleport).  Replaying the
            # stale path must never teleport the creature back onto it:
            # resume from the current square when it is still on the path,
            # otherwise drop the move (the movement budget was not spent, so
            # the creature can simply move again).
            where = map.position_of(self.source)
            if where is not None and list(current_moves[0]) != list(where):
                anchor = next(
                    (i for i, mv in enumerate(current_moves) if list(mv) == list(where)),
                    None)
                if anchor is None:
                    return self
                current_moves = current_moves[anchor:]
                jumps = []

        actual_moves = []
        additional_effects = []

        if self.unlimited_movement and battle is None:
            # Exploration mode: allow paths longer than the entity's speed,
            # but never when speed is currently 0 (shell, restrained, etc.).
            if self.source.speed() <= 0:
                movement_budget = 0
            else:
                # Cap at the map size so we still bound the loop.
                mx, my = map.size
                movement_budget = (mx + my) * 4
        elif self.legendary_action:
            movement_budget = (self.source.speed() // 5)
        elif self.as_dash:
            movement_budget = (self.source.speed // 5)
        else:
            movement_budget = (self.source.available_movement(battle) // 5)

        movement = compute_actual_moves(self.source, current_moves, map, battle, movement_budget, manual_jump=jumps)
        actual_moves = movement.movement

        while actual_moves and not map.placeable(self.source, *actual_moves[-1], battle):
            actual_moves.pop()

        # Frightened (SRD): the creature can't willingly move closer to the
        # source of its fear; the path stops before the first such step.
        from natural20.utils.fear import truncate_path_for_fear
        actual_moves = truncate_path_for_fear(self.source, actual_moves, map, battle)

        if not self.ignore_opportunity_attacks:
            actual_moves = self.check_opportunity_attacks(self.source, actual_moves, battle)

        # if acutal_moves is a generator just exit
        if actual_moves and hasattr(actual_moves, 'send'):
            return actual_moves

        actual_moves = self.check_movement_athletics(actual_moves, movement.athletics_check_locations, battle, map)

        actual_moves = self.check_movement_acrobatics(actual_moves, movement.acrobatics_check_locations, battle)

        if self.source.incapacitated():
            # Dead, unconscious, stunned, paralyzed, petrified or asleep: no
            # movement. This matters when an interrupted move is re-run
            # after a deferred reaction — the opportunity attack may have
            # killed or disabled the mover in the meantime (unconscious()
            # is False for the dead). Grappled and restrained movers are
            # handled through the zero movement budget instead: they are
            # not incapacitated, and a grappler may still drag its catch.
            if battle is not None:
                _state = battle.entity_state_for(self.source)
                if _state is not None:
                    _state['movement'] = 0
            return self

        # cutoff = False
        move_segments = []
        segment_effects = []  # list of lists: one group of trigger effects per segment boundary
        _safe_moves = []
        for index, move in enumerate(actual_moves):
            is_flying_or_jumping = self.source.flying or move in movement.jump_locations
            if index > 0:
                trigger_results = map.area_trigger(self.source, move, is_flying_or_jumping)
                if not trigger_results:
                    _safe_moves.append(move)
                else:
                    if index > 0:
                        _safe_moves.append(actual_moves[index - 1])
                    else:
                        assert False, "should not happen"
                    _safe_moves.append(move)
                    move_segments.append(_safe_moves)
                    _safe_moves = []

                    segment_effects.append(trigger_results)
                    additional_effects += trigger_results
                    if any(result['type'] == 'cancel_move' for result in trigger_results):
                        break
            else:
                _safe_moves.append(move)
        if len(_safe_moves) > 0:
            move_segments.append(_safe_moves)

        stack_descent = self.stack_descent

        for index, safe_moves in enumerate(move_segments):
            movement = compute_actual_moves(self.source, safe_moves, map, battle, movement_budget, manual_jump=jumps)

            movement_cost = movement_budget - movement.budget

            # Trim the grappler's own path first: the dragged targets trail
            # along the path it ACTUALLY takes, and their clamp must know
            # the grappler's final footprint. Ending a move squeezed (in a
            # space sized for the reduced footprint) is allowed, matching
            # the reachable-squares menu, which already pathfinds through
            # squeeze-only gaps (issue #6 item 2: the two used to disagree).
            for move in reversed(movement.movement):
                if map.placeable(self.source, *move, battle, squeeze=True):
                    break
                else:
                    movement.movement.remove(move)
                    movement_cost -= 1

            grapple_effects = []
            if self.source.is_grappling():
                # The source's full path is [start, step1, ..., dest]. Each
                # grappled target trails the source by one more step than the
                # previous one (the first lags 1, the next 2, ...). Slice the
                # trailing steps off instead of popping a shared list, so a
                # short path or several grappled targets can't underflow.
                source_path = movement.movement
                dest_x, dest_y = source_path[-1]
                grappler_stay = set(
                    tuple(sq) for sq in map.entity_squares_at_pos(
                        self.source, dest_x, dest_y))
                for i, grappling_target in enumerate(self.source.grappling_targets()):
                    start_pos = map.entity_or_object_pos(grappling_target)
                    lag = i + 1
                    lagged = source_path[:-lag] if len(source_path) > lag else []
                    grappled_entity_movement = [start_pos] + lagged

                    # A dragged creature can never END on an occupied
                    # square: drop trailing steps until its last square
                    # is free, so it stops at the last open square of
                    # the trail instead of overlapping a creature. If
                    # that leaves it out of reach, the out-of-reach
                    # rule in grappling.py releases the grapple at the
                    # next turn start.
                    while (len(grappled_entity_movement) > 1
                           and not drag_square_free(
                               map, grappling_target, self.source,
                               grappled_entity_movement[-1],
                               grappler_stay)):
                        grappled_entity_movement.pop()

                    grapple_effects.append({
                        'source': grappling_target,
                        'map': map,
                        'battle': battle,
                        'type': 'move',
                        'path': grappled_entity_movement,
                        'as_dash': self.as_dash,
                        'as_bonus_action': self.as_bonus_action,
                        'move_cost': 0,
                        'dragged_by': self.source,
                        'position': grappled_entity_movement[-1]
                    })
            self.result.append({
                'source': self.source,
                'map': map,
                'battle': battle,
                'as_dash': self.as_dash,
                'as_bonus_action': self.as_bonus_action,
                'as_legendary_action': bool(self.legendary_action),
                'legendary_cost': self.legendary_cost if (self.legendary_action and index == 0) else 0,
                'type': 'move',
                'path': movement.movement,
                'move_cost': movement_cost,
                'position': movement.movement[-1]
            })

            for effect in grapple_effects:
                self.result.append(effect)

            if stack_descent and index == len(move_segments) - 1 and stack_descent.get('base_path'):
                to_map_name = stack_descent.get('to_map')
                to_map = self.session.maps.get(to_map_name) if to_map_name else None
                if to_map is not None:
                    self.result.append({
                        'source': self.source,
                        'type': 'stack_descent',
                        'from_map': map,
                        'to_map': to_map,
                        'battle': battle,
                        'descent_info': stack_descent,
                    })
                    base_moves = stack_descent['base_path']
                    base_budget = movement.budget if movement.budget > 0 else 0
                    base_movement = compute_actual_moves(
                        self.source, base_moves, to_map, battle, base_budget, manual_jump=jumps,
                    )
                    base_cost = base_budget - base_movement.budget if base_budget else 0
                    self.result.append({
                        'source': self.source,
                        'map': to_map,
                        'battle': battle,
                        'as_dash': self.as_dash,
                        'as_bonus_action': self.as_bonus_action,
                        'type': 'move',
                        'path': base_movement.movement,
                        'move_cost': base_cost,
                        'position': base_movement.movement[-1] if base_movement.movement else base_moves[-1],
                    })

            if index < len(segment_effects):
                for effect in segment_effects[index]:
                    self.result.append(effect)
        return self

    def check_opportunity_attacks(self, entity, move_list, battle, grappled=False):
        if battle:
            for enemy_opportunity in retrieve_opportunity_attacks(entity, move_list, battle):
                original_location = move_list[:enemy_opportunity['path']]
                attack_location = original_location[-1]
                stored_reaction = self.has_async_reaction_for_source(enemy_opportunity['source'], 'opportunity_attack')

                # SRD: the opportunity attack happens "just before" the
                # creature leaves your reach — it interrupts the move. The
                # mover must physically stand on the square it is provoking
                # from while the attack resolves, or cover, sight, range
                # and the final board position all react to a stale square
                # (issue #6 item 58).
                mover_map = battle.map_for(entity)
                start_position = list(mover_map.position_of(entity)) \
                    if mover_map is not None else None
                if mover_map is not None and list(attack_location) != start_position:
                    mover_map.move_to(entity, attack_location[0], attack_location[1], battle)
                # Only a knock-down from THIS attack stops the move. A
                # creature that was already prone (crawling) before the
                # attack may keep crawling afterwards (SRD: the attack
                # interrupts the move, it does not end it; Nov-23 report
                # item 7).
                was_prone = entity.prone()
                try:
                    if stored_reaction is not False:
                        result = battle.trigger_opportunity_attack(enemy_opportunity['source'], entity, *attack_location, stored_reaction)
                    else:
                        result = battle.trigger_opportunity_attack(enemy_opportunity['source'], entity, *attack_location)
                        if hasattr(result, 'send'):
                            raise AsyncReactionHandler(enemy_opportunity['source'], result, self, 'opportunity_attack')
                except AsyncReactionHandler as exc:
                    # Deferred (player) reaction: the full path re-runs when
                    # resolve resumes, so snap the mover back for now.
                    if mover_map is not None and start_position is not None \
                            and entity in mover_map.entities \
                            and list(mover_map.entities[entity]) != start_position:
                        mover_map.move_to(entity, start_position[0], start_position[1], battle)
                    if exc.action is not self:
                        # A handler from deeper inside the attack (the
                        # mover's own Shield / Silvery Barbs window raised by
                        # the attack's own resolution) only carries the
                        # attack as its action. Without this back-reference
                        # the resumer replays the attack and the interrupted
                        # move is dropped, stranding the mover at its
                        # pre-move square even when the reaction deflected
                        # the attack (Nov-26 report: Crysania's Shield).
                        exc.interrupted_action = self
                    raise
                except GeneratorExit:
                    if mover_map is not None and start_position is not None \
                            and entity in mover_map.entities \
                            and list(mover_map.entities[entity]) != start_position:
                        mover_map.move_to(entity, start_position[0], start_position[1], battle)
                    raise

                if not grappled and not entity.conscious():
                    # Interrupted: the mover stops on the square where the
                    # attack caught it (it is already standing there), not
                    # back at its pre-move position.
                    return original_location

                if entity.prone() and not was_prone:
                    # This attack knocked the mover prone: standing up costs
                    # movement, so the rest of the path is not free. (An
                    # already-prone crawler keeps moving.)
                    return original_location

        return move_list

    @staticmethod
    def apply(battle, item, session=None):
        if session is None:
            session = battle.session

        item_type = item['type']
        if item_type == 'state':
            for k, v in item['params'].items():
                setattr(item['source'], k, v)

            results = item['source'].resolve_trigger(item['trigger'], { "target": item.get('target', None) })

            if results:
                for sub_item in results:
                    for klass in Action.__subclasses__():
                        klass.apply(battle, sub_item, session)

        elif item_type in ['acrobatics', 'athletics']:
            if item['success']:
                print(f"{item['source'].name} {item_type} check success")
                session.event_manager.received_event({
                    'source': item['source'],
                    'event': item_type,
                    'success': True,
                    'roll': item['roll']
                })
            else:
                print(f"{item['source'].name} {item_type} check failed and is now prone")
                session.event_manager.received_event({
                    'source': item['source'],
                    'event': item_type,
                    'success': False,
                    'roll': item['roll']
                })
                item['source'].prone()
        elif item_type == 'stack_descent':
            from natural20.map_stack_movement import apply_voluntary_stack_descent
            apply_voluntary_stack_descent(
                item['source'],
                item['from_map'],
                item['descent_info'],
                battle=battle,
                session=session,
            )
        elif item_type == 'move':
            if item['map'].move_to(item['source'], *item['position'], battle):
                if battle:
                    # SRD "Hiding": you can't hide from something that can
                    # see you. A hidden creature that steps into the clear
                    # line of sight of a hostile stops being hidden the
                    # moment it arrives there; the old stealth bonus only
                    # survives when nobody on the other side sees the new
                    # square (issue #6 item 56).
                    reveal_if_exposed(battle, session, item['source'])
                    path_taken = item['path']
                    positions_entered = battle.entity_state_for(item['source'])['positions_entered']
                    for p in path_taken:
                        p_key = tuple(p)
                        visit_count = positions_entered.get(p_key, 0)
                        positions_entered[p_key] = visit_count + 1

                # Broadcast per-step movement so persistent zones (Spike
                # Growth, Web, etc.) can react. Done here rather than in
                # ``Map.move_to`` so teleport-style move_to calls (Misty
                # Step, Teleporter objects) don't fire on every traversed
                # square. Zones living on the map's ``environment_zones``
                # (cast out of combat, or never promoted into the current
                # battle) fire through the same twin dispatcher so Spike
                # Growth damage works in and out of combat.
                from natural20.environment_zones import (
                    trigger_environment_movement_step,
                )
                prev = None
                for step in item['path']:
                    if battle and hasattr(battle, 'trigger_movement_step'):
                        battle.trigger_movement_step(item['source'], prev, step)
                    trigger_environment_movement_step(
                        item['map'], item['source'], prev, step,
                        event_manager=session.event_manager,
                    )
                    prev = tuple(step)

                if item.get('as_legendary_action'):
                    if battle and item.get('legendary_cost'):
                        battle.consume(item['source'], 'legendary_actions', item['legendary_cost'])
                elif item['as_dash'] and item['as_bonus_action']:
                    battle.entity_state_for(item['source'])['bonus_action'] -= 1
                elif item['as_dash']:
                    battle.entity_state_for(item['source'])['action'] -= 1
                elif battle:
                    battle.entity_state_for(item['source'])['movement'] -= item['move_cost'] * battle.map_for(item['source']).feet_per_grid

                battle_map = item.get('map', None)
                if battle_map is None:
                    battle_map = battle.map_for(item['source'])

                session.event_manager.received_event({
                    'event': 'move',
                    'source': item['source'],
                    'position': item['position'],
                    'path': item['path'],
                    'move_cost' : item['move_cost'],
                    'feet_per_grid': battle_map.feet_per_grid,
                    'as_dash': item['as_dash'],
                    'as_bonus': item['as_bonus_action'],
                    'as_legendary_action': bool(item.get('as_legendary_action')),
                    'dragged_by': item.get('dragged_by'),
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
