from natural20.spell.spell import Spell


class MistyStepSpell(Spell):
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
        feet_per_grid = getattr(battle_map, 'feet_per_grid', 5)
        grid_distance = battle_map.distance_to_square(self.source, tx, ty)
        if grid_distance * feet_per_grid > self.properties.get('range', 30):
            self.errors.append('Target is out of range')

        if not battle_map.placeable(self.source, tx, ty):
            self.errors.append('Target must be empty space')

        if not battle_map.can_see_square(self.source, [tx, ty]):
            self.errors.append('Target is not visible')

        return len(self.errors) == 0

    def resolve(self, entity, battle, spell_action, battle_map):
        target = spell_action.target
        if battle_map is None or target is None:
            return []

        if not isinstance(target, (list, tuple)) or len(target) != 2:
            return []

        tx, ty = int(target[0]), int(target[1])
        origin = None
        try:
            origin = list(battle_map.position_of(entity))
        except ValueError:
            origin = None

        spell_action.misty_step_from = origin

        return [{
            'type': 'misty_step',
            'map': battle_map,
            'target': [tx, ty],
            'from': origin,
            'source': entity,
            'spell': self.properties,
            'refresh_map': True
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'misty_step':
            return

        if battle and session is None:
            session = battle.session

        battle_map = item.get('map')
        target = item.get('target')
        source = item.get('source')

        if battle_map is None or target is None or source is None:
            return

        tx, ty = int(target[0]), int(target[1])
        if battle_map.placeable(source, tx, ty, battle):
            battle_map.move_to(source, tx, ty, battle)

        if session:
            session.event_manager.received_event({
                'event': 'misty_step',
                'source': source,
                'position': [tx, ty],
                'from': item.get('from')
            })
