from natural20.action import Action
from natural20.spell.flaming_sphere_spell import active_sphere
from natural20.utils.class_feature_registry import register_class_feature


class FlamingSphereAction(Action):
    """Bonus action: move an active Flaming Sphere up to 30 feet, optionally ramming a creature."""

    MOVE_FEET = 30

    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.target = None

    def clone(self):
        action = FlamingSphereAction(self.session, self.source, self.action_type, self.opts)
        action.target = self.target
        return action

    def name(self):
        return 'Move Flaming Sphere'

    def label(self):
        return 'Move Flaming Sphere'

    @staticmethod
    def _turn_key(battle):
        return (battle.current_round(), getattr(battle, 'current_turn_index', 0))

    @staticmethod
    def can(entity, battle, options=None):
        handle = active_sphere(entity)
        if handle is None:
            return False
        if battle is None:
            return True
        if not entity.has_bonus_action(battle):
            return False
        return handle.last_move_turn != FlamingSphereAction._turn_key(battle)

    def available(self, battle):
        return FlamingSphereAction.can(self.source, battle)

    @staticmethod
    def build(session, source):
        return FlamingSphereAction(session, source, 'flaming_sphere_move').build_map()

    def build_map(self):
        handle = active_sphere(self.source)

        def set_target(target):
            action = self.clone()
            action.target = target
            return action

        param = {'type': 'select_radius', 'num': 1, 'range': self.MOVE_FEET, 'radius': 5}
        if handle is not None:
            param['origin'] = list(handle.zone.center)
        return {'action': self, 'param': [param], 'next': set_target}

    def _point(self, battle_map, target=None):
        target = target if target is not None else self.target
        if hasattr(target, 'entity_uid') and battle_map is not None:
            target = battle_map.position_of(target)
        if isinstance(target, (list, tuple)) and len(target) == 2:
            return (int(target[0]), int(target[1]))
        return None

    def validate(self, battle_map, target=None):
        self.errors = []
        handle = active_sphere(self.source)
        if handle is None:
            self.errors.append('You have no Flaming Sphere to move.')
            return
        point = self._point(battle_map, target)
        if point is None:
            self.errors.append('Choose a square for the sphere.')
            return
        reach = self.MOVE_FEET // battle_map.feet_per_grid
        cx, cy = handle.zone.center
        if max(abs(point[0] - cx), abs(point[1] - cy)) > reach:
            self.errors.append('The sphere can only move 30 feet.')

    @staticmethod
    def _ram_square(battle_map, zone, creature):
        """Empty square next to ``creature`` closest to the sphere (or the sphere's own square)."""
        squares = battle_map.entity_squares(creature) or [battle_map.position_of(creature)]
        if any(zone.contains(sq) for sq in squares):
            return zone.center
        cx, cy = zone.center
        best = None
        for sx, sy in squares:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    x, y = sx + dx, sy + dy
                    if (x, y) in [tuple(s) for s in squares]:
                        continue
                    if x < 0 or y < 0 or x >= battle_map.size[0] or y >= battle_map.size[1]:
                        continue
                    if battle_map.entity_at(x, y) is not None:
                        continue
                    dist = max(abs(x - cx), abs(y - cy))
                    if best is None or dist < best[0]:
                        best = (dist, (x, y))
        return best[1] if best else zone.center

    def resolve(self, session, map, opts=None):
        opts = opts or {}
        battle = opts.get('battle')
        self.result = []
        handle = active_sphere(self.source)
        battle_map = map or (battle.map_for(self.source) if battle else None)
        point = self._point(battle_map)
        if handle is None or point is None or battle_map is None:
            return self
        zone = handle.zone
        creature = battle_map.entity_at(point[0], point[1])
        if creature is not None and creature.dead():
            creature = None
        destination = self._ram_square(battle_map, zone, creature) if creature is not None else point
        self.result.append({
            'type': 'flaming_sphere_move',
            'source': self.source,
            'target': list(destination),
            'from': list(zone.center),
            'ram': creature,
            'sphere': handle,
        })
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'flaming_sphere_move':
            return
        if battle and session is None:
            session = battle.session
        source = item['source']
        handle = item.get('sphere')
        if battle is not None:
            battle.consume(source, 'bonus_action')
            if handle is not None:
                handle.last_move_turn = FlamingSphereAction._turn_key(battle)
        if handle is None or handle.zone is None:
            return
        zone = handle.zone
        zone.move_to(item['target'])
        if session is not None:
            session.event_manager.received_event({
                'event': 'flaming_sphere_move',
                'source': source,
                'target': item.get('target'),
                'ram': item.get('ram'),
            })
        if item.get('ram') is not None:
            zone.burn(item['ram'], reason='ram')


register_class_feature(
    feature_id='flaming_sphere_move',
    action_class=FlamingSphereAction,
    provides=lambda entity: active_sphere(entity) is not None,
    builder=lambda session, entity, feature_id: [FlamingSphereAction(session, entity, feature_id)],
)
