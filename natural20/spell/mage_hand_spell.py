from natural20.spell.spell import Spell
from natural20.spell.objects.mage_hand import MageHand


class MageHandEffect:
    def __init__(self, source, mage_hand, battle_map, range_feet=30):
        self.source = source
        self.mage_hand = mage_hand
        self.battle_map = battle_map
        self.range_feet = range_feet
        self._active = True
        self._listeners_registered = False

    @property
    def id(self):
        return 'mage_hand'

    def dismiss(self, entity, effect, opts=None):
        if opts is None:
            opts = {}
        if not self._active:
            return
        self._active = False
        if self.battle_map:
            try:
                self.battle_map.remove(self.mage_hand)
            except Exception:
                pass
        if self.source and self.source.session:
            self.source.session.event_manager.received_event({
                'event': 'mage_hand_dismissed',
                'source': self.source,
                'target': self.mage_hand,
                'reason': opts.get('event', 'dismissed')
            })

    def register_listeners(self, event_manager):
        if self._listeners_registered:
            return

        def handler(event):
            if not self._active:
                return
            event_type = event.get('event')
            mover = event.get('source')
            if event_type == 'move' and mover not in (self.source, self.mage_hand):
                return
            if event_type == 'start_of_turn' and mover != self.source:
                return
            if event_type == 'mage_hand_command' and mover != self.source:
                return
            if event_type in {'move', 'misty_step', 'start_of_turn', 'mage_hand_command'}:
                self.ensure_within_range(event_manager.battle)

        event_manager.register_event_listener(['move', 'misty_step', 'start_of_turn', 'mage_hand_command'], handler)
        self._listeners_registered = True

    def ensure_within_range(self, battle=None):
        if not self._active or self.battle_map is None:
            return
        battle_map = self.battle_map
        try:
            hand_pos = battle_map.position_of(self.mage_hand)
            battle_map.position_of(self.source)
        except Exception:
            # If either entity is not on the map, end the effect.
            if self.source:
                self.source.remove_effect(self, opts={'event': 'invalid_position'})
            return

        feet_per_grid = getattr(battle_map, 'feet_per_grid', 5)
        distance = battle_map.distance_to_square(self.source, hand_pos[0], hand_pos[1]) * feet_per_grid
        if distance > self.range_feet:
            self.source.remove_effect(self, opts={'event': 'too_far'})


class MageHandSpell(Spell):
    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [
                {
                    'type': 'select_empty_space',
                    'num': 1,
                    'range': self.properties.get('range', 30),
                    'require_los': True
                }
            ],
            'next': set_target
        }

    def validate(self, battle_map, target=None):
        super().validate(battle_map, target)

        if target is None:
            target = self.target

        self.errors = []
        if battle_map is None:
            return True

        if not target:
            self.errors.append('Invalid target')
            return False

        if not isinstance(target, (list, tuple)) or len(target) != 2:
            self.errors.append('Invalid target type, should be a position')
            return False

        tx, ty = int(target[0]), int(target[1])
        if not battle_map.can_see_square(self.source, [tx, ty]):
            self.errors.append('Target is not visible')

        feet_per_grid = getattr(battle_map, 'feet_per_grid', 5)
        distance = battle_map.distance_to_square(self.source, tx, ty) * feet_per_grid
        if distance > self.properties.get('range', 30):
            self.errors.append('Target is out of range')

        if not battle_map.placeable(MageHand(self.session, self.source), tx, ty):
            self.errors.append('Target must be empty space')

        return len(self.errors) == 0

    def resolve(self, entity, battle, spell_action, battle_map):
        target = spell_action.target
        if target is None:
            return []

        tx, ty = int(target[0]), int(target[1])
        return [{
            'type': 'mage_hand',
            'map': battle_map,
            'target': [tx, ty],
            'source': entity,
            'spell': self.properties,
            'effect': self,
            'refresh_map': True
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if battle and session is None:
            session = battle.session

        if item['type'] != 'mage_hand':
            return

        source = item['source']
        battle_map = item['map']
        target = item['target']

        session = session or getattr(source, 'session', None)
        if session is None:
            return

        # Dismiss any existing mage hand for this caster before creating a new one.
        source.remove_effect('mage_hand')

        mage_hand = MageHand(session, source)
        if not battle_map.placeable(mage_hand, target[0], target[1]):
            return

        battle_map.place(target, mage_hand)

        effect = MageHandEffect(source, mage_hand, battle_map)
        effect.register_listeners(session.event_manager)

        source.add_casted_effect({
            'target': target,
            'effect': effect,
            'expiration': session.game_time + 60
        })

        session.event_manager.received_event({
            'event': 'mage_hand_created',
            'source': source,
            'target': mage_hand,
            'position': target
        })
