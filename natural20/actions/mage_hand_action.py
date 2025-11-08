from natural20.action import Action
from natural20.spell.mage_hand_spell import MageHandEffect


def _resolve_caster(entity):
    owner = getattr(entity, 'owner', None)
    return owner if owner is not None else entity


class MageHandAction(Action):
    """Control an existing Mage Hand to move and manipulate objects."""

    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.destination = None
        self.interaction = 'none'

    def clone(self):
        action = MageHandAction(self.session, self.source, self.action_type, self.opts)
        action.destination = list(self.destination) if isinstance(self.destination, list) else self.destination
        action.interaction = self.interaction
        return action

    def name(self):
        return 'Command Mage Hand'

    def label(self):
        return 'Command Mage Hand'

    @staticmethod
    def build(session, source):
        action = MageHandAction(session, source, 'mage_hand_command')
        return action.build_map()

    def build_map(self):
        def set_destination(target):
            action = self.clone()
            if isinstance(target, (list, tuple)) and len(target) == 2:
                action.destination = [int(target[0]), int(target[1])]
            else:
                action.destination = target
            return action._build_interaction_step()

        return {
            'param': [
                {
                    'type': 'select_empty_space',
                    'num': 1,
                    'range': 30,
                    'require_los': False
                }
            ],
            'next': set_destination
        }

    def _build_interaction_step(self):
        def set_interaction(choice):
            action = self.clone()
            if isinstance(choice, list):
                action.interaction = choice[1]
            else:
                action.interaction = choice
            return action

        return {
            'param': [
                {
                    'type': 'select_choice',
                    'choices': [
                        ['No additional interaction', 'none'],
                        ['Manipulate or press an object', 'manipulate'],
                        ['Open or close an unlocked container', 'open'],
                        ['Pick up or drop a small object', 'pick_up_drop'],
                        ['Stow or retrieve a small object', 'stow_retrieve'],
                        ['Pour out the contents of a vial', 'pour']
                    ],
                    'num': 1
                }
            ],
            'next': set_interaction
        }

    @staticmethod
    def can(entity, battle, options=None):
        caster = _resolve_caster(entity)
        if caster is None:
            return False
        if battle and not caster.has_action(battle):
            return False
        return caster.has_casted_effect('mage_hand')

    @staticmethod
    def _grid_distance(start, end):
        if start is None or end is None:
            return 0
        return max(abs(int(start[0]) - int(end[0])), abs(int(start[1]) - int(end[1])))

    def validate(self, battle_map, target=None):
        self.errors = []
        if battle_map is None:
            self.errors.append('No battle map available')
            return False

        effect_entry = self._effect_entry()
        if not effect_entry:
            self.errors.append('No active mage hand to command')
            return False

        mage_hand = effect_entry['effect'].mage_hand
        try:
            current = battle_map.position_of(mage_hand)
        except Exception:
            self.errors.append('Mage hand is not present on the map')
            return False

        destination = self.destination or current
        if not isinstance(destination, (list, tuple)) or len(destination) != 2:
            self.errors.append('Invalid destination')
            return False

        dx, dy = int(destination[0]), int(destination[1])
        if not battle_map.placeable(mage_hand, dx, dy):
            self.errors.append('Destination must be empty space')

        feet_per_grid = getattr(battle_map, 'feet_per_grid', 5)
        caster = _resolve_caster(self.source)
        distance_from_caster = battle_map.distance_to_square(caster, dx, dy) * feet_per_grid
        if distance_from_caster > 30:
            self.errors.append('Destination is beyond the 30-foot limit from the caster')

        travel_distance = self._grid_distance(current, destination) * feet_per_grid
        if travel_distance > 30:
            self.errors.append('Mage hand can move at most 30 feet as part of this action')

        return len(self.errors) == 0

    def resolve(self, session, map, opts=None):
        if opts is None:
            opts = {}
        self.result.clear()

        effect_entry = self._effect_entry()
        if not effect_entry:
            return self

        mage_hand_effect = effect_entry['effect']
        mage_hand = mage_hand_effect.mage_hand
        try:
            current = map.position_of(mage_hand)
        except Exception:
            return self

        if not self.validate(map):
            return self

        destination = self.destination or current
        dx, dy = int(destination[0]), int(destination[1])

        path = [list(current), [dx, dy]] if [dx, dy] != list(current) else [list(current)]
        move_cost = self._grid_distance(current, [dx, dy])

        caster = _resolve_caster(self.source)

        self.result.append({
            'type': 'mage_hand_command',
            'source': caster,
            'effect': mage_hand_effect,
            'mage_hand': mage_hand,
            'map': map,
            'destination': [dx, dy],
            'path': path,
            'move_cost': move_cost,
            'interaction': self.interaction
        })

        return self

    @staticmethod
    def apply(battle, item, session=None):
        if battle and session is None:
            session = battle.session

        if item['type'] != 'mage_hand_command':
            return

        source = item['source']
        effect = item['effect']
        mage_hand = item['mage_hand']
        map_obj = item['map']
        destination = item['destination']

        if session is None:
            session = getattr(source, 'session', None)
        if session is None:
            return

        moved = False
        try:
            current = map_obj.position_of(mage_hand)
        except Exception:
            current = None

        if destination and current != destination:
            moved = map_obj.move_to(mage_hand, destination[0], destination[1], battle)
        else:
            moved = True

        if battle and source:
            battle.consume(source, 'action')

        session.event_manager.received_event({
            'event': 'mage_hand_command',
            'source': source,
            'target': mage_hand,
            'position': destination,
            'interaction': item['interaction'],
            'moved': moved,
            'path': item['path']
        })

        effect.ensure_within_range(battle)

    def to_dict(self):
        return {
            'action_type': self.action_type,
            'source': self.source.entity_uid if self.source else None,
            'destination': self.destination,
            'interaction': self.interaction
        }

    def _effect_entry(self):
        caster = _resolve_caster(self.source)
        if caster is None:
            return None
        for effect_entry in getattr(caster, 'casted_effects', []):
            effect = effect_entry.get('effect')
            if not isinstance(effect, MageHandEffect):
                continue
            if effect.mage_hand is self.source or caster is self.source:
                return effect_entry
        return None
