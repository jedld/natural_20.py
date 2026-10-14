from natural20.spell.spell import Spell


class MistyStepSpell(Spell):
    SPELL_ID = 'misty_step'

    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            action.spell_rider = getattr(orig_action, 'spell_rider', None)
            return action

        from natural20.utils.spell_riders import choice_param
        rider_param = choice_param(self.source, self.properties.get('id') or self.SPELL_ID)
        if rider_param and getattr(orig_action, 'spell_rider', None) is None:
            def set_rider(choice):
                action = orig_action.clone()
                action.spell_rider = choice
                return self.build_map(action)
            return {'param': [rider_param], 'next': set_rider}

        return {
            'param': [
                {
                    'type': 'select_empty_space',
                    'num': 1,
                    'range': self.properties.get('range', 30),
                    'require_los': self.properties.get('require_los', True),
                    'max_choices': self.properties.get('ai_max_destinations'),
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

        if (self.properties.get('require_los', True)
                and not battle_map.can_see_square(self.source, [tx, ty])):
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

        from natural20.utils.spell_riders import rider_by_id
        rider = rider_by_id(entity, self.properties.get('id') or self.SPELL_ID,
                            getattr(spell_action, 'spell_rider', None))
        dc = None
        if rider is not None:
            from natural20.spell.hold_person_spell import HoldPersonSpell
            dc = entity.spell_save_dc(HoldPersonSpell._caster_spell_ability(entity, spell_action))

        return [{
            'type': 'misty_step',
            'map': battle_map,
            'target': [tx, ty],
            'from': origin,
            'source': entity,
            'spell': self.properties,
            'rider': rider,
            'dc': dc,
            'battle': battle,
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

        if item.get('rider'):
            from natural20.utils.spell_riders import apply_rider
            apply_rider(item['rider'], source, battle or item.get('battle'), battle_map,
                        item.get('from') or [tx, ty], [tx, ty], int(item.get('dc') or 10))
