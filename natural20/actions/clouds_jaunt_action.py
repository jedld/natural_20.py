"""Cloud's Jaunt (Goliath, cloud giant ancestry; SRD 5.2).

Bonus action: magically teleport up to 30 feet to an unoccupied space the
creature can see. Draws on the Giant Ancestry uses pool.
"""

from __future__ import annotations

from natural20.action import Action
from natural20.utils import giant_ancestry


class CloudsJauntAction(Action):
    RANGE_FT = 30
    FEATURE = 'clouds_jaunt'

    def __init__(self, session, source, action_type='clouds_jaunt', opts=None):
        super().__init__(session, source, action_type, opts)
        self.as_bonus_action = True
        self.target = None

    def label(self):
        return f"Cloud's Jaunt ({giant_ancestry.uses_remaining(self.source, self.FEATURE)} left)"

    def button_label(self):
        return self.label()

    def __str__(self):
        return "CloudsJaunt"

    __repr__ = __str__

    @staticmethod
    def can(entity, battle, options=None):
        if not giant_ancestry.has_use(entity, CloudsJauntAction.FEATURE):
            return False
        if battle is not None and battle.entity_state_for(entity) is not None:
            return entity.total_bonus_actions(battle) > 0
        return True

    def build_map(self):
        def set_target(target):
            action = CloudsJauntAction(self.session, self.source, self.action_type, self.opts)
            action.target = target
            return action

        return {
            'param': [{
                'type': 'select_empty_space',
                'num': 1,
                'range': self.RANGE_FT,
                'require_los': True,
            }],
            'next': set_target,
        }

    @classmethod
    def build(cls, session, source):
        return cls(session, source).build_map()

    def validate(self, battle_map, target=None, battle=None):
        super().validate(battle_map, target=target, battle=battle)
        target = target if target is not None else self.target
        self.errors = []
        if battle_map is None:
            return True
        if not isinstance(target, (list, tuple)) or len(target) != 2:
            self.errors.append('Invalid target type, should be a position')
            return False
        tx, ty = int(target[0]), int(target[1])
        if battle_map.distance_to_square(self.source, tx, ty) * battle_map.feet_per_grid > self.RANGE_FT:
            self.errors.append('Target is out of range')
        if not battle_map.placeable(self.source, tx, ty, battle, squeeze=False):
            self.errors.append('Target must be empty space')
        if not battle_map.can_see_square(self.source, [tx, ty]):
            self.errors.append('Target is not visible')
        return len(self.errors) == 0

    def resolve(self, session, map, opts=None):
        battle = (opts or {}).get('battle')
        battle_map = map or (battle.map_for(self.source) if battle else None)
        if battle_map is None or not isinstance(self.target, (list, tuple)) or len(self.target) != 2:
            self.result = []
            return self
        if not self.validate(battle_map, battle=battle):
            self.result = []
            return self
        tx, ty = int(self.target[0]), int(self.target[1])
        try:
            origin = list(battle_map.position_of(self.source))
        except Exception:
            origin = None
        self.result = [{
            'type': 'clouds_jaunt',
            'source': self.source,
            'map': battle_map,
            'battle': battle,
            'target': [tx, ty],
            'from': origin,
            'refresh_map': True,
        }]
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'clouds_jaunt':
            return None
        source = item['source']
        battle_map = item.get('map')
        if session is None:
            session = battle.session if battle else source.session
        tx, ty = item['target']
        if battle is not None:
            battle.consume(source, 'bonus_action')
        giant_ancestry.spend_use(source, CloudsJauntAction.FEATURE)
        if battle_map is not None and battle_map.placeable(source, tx, ty, battle, squeeze=False):
            battle_map.move_to(source, tx, ty, battle)
        session.event_manager.received_event({
            'event': 'clouds_jaunt',
            'source': source,
            'position': [tx, ty],
            'from': item.get('from'),
        })
        return item

    @staticmethod
    def ai_options(session, entity, battle, battle_map):
        """A few sensible destinations for AI controllers.

        Closes to melee with the nearest visible foe when none is adjacent, or
        breaks away from melee when below half HP. Enumerating every square
        within 30 ft would flood JEV/LLM option lists.
        """
        if battle is None or battle_map is None:
            return []
        try:
            cur_x, cur_y = battle_map.position_of(entity)
        except Exception:
            return []
        reach = CloudsJauntAction.RANGE_FT // battle_map.feet_per_grid
        enemies = [e for e in battle.opponents_of(entity)
                   if e.conscious() and battle_map.can_see(entity, e)]
        if not enemies:
            return []

        def candidates():
            for dx in range(-reach, reach + 1):
                for dy in range(-reach, reach + 1):
                    if dx == 0 and dy == 0:
                        continue
                    x, y = cur_x + dx, cur_y + dy
                    if x < 0 or y < 0 or x >= battle_map.size[0] or y >= battle_map.size[1]:
                        continue
                    if battle_map.distance_to_square(entity, x, y) > reach:
                        continue
                    if not battle_map.placeable(entity, x, y, battle, squeeze=False):
                        continue
                    if not battle_map.can_see_square(entity, (x, y)):
                        continue
                    yield x, y

        def nearest_enemy_distance(x, y):
            return min(max(abs(x - ex), abs(y - ey))
                       for ex, ey in (battle_map.position_of(e) for e in enemies))

        in_melee = battle.enemy_in_melee_range(entity)
        low_hp = entity.hp() <= entity.max_hp() // 2
        destination = None
        if in_melee and low_hp:
            scored = [(nearest_enemy_distance(x, y), (x, y)) for x, y in candidates()]
            if scored:
                destination = max(scored)[1]
        elif not in_melee and not low_hp:
            scored = [(abs(cur_x - x) + abs(cur_y - y), (x, y))
                      for x, y in candidates() if nearest_enemy_distance(x, y) == 1]
            if scored:
                destination = min(scored)[1]
        if destination is None:
            return []
        action = CloudsJauntAction(session, entity)
        action.target = list(destination)
        return [action]
