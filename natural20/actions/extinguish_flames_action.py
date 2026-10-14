from natural20.action import Action
from natural20.effects.burning_effect import BurningEffect


class ExtinguishFlamesAction(Action):
    """Action: put out the flames on yourself or a burning creature within 5 feet.

    Succeeds on a Dexterity check against the effect's ``extinguish_dc``
    (DC 10 for Alchemist's Fire).
    """

    REACH_FT = 5

    def __init__(self, session, source, action_type='extinguish_flames', opts=None):
        super().__init__(session, source, action_type, opts)
        self.target = None

    def clone(self):
        action = ExtinguishFlamesAction(self.session, self.source, self.action_type, self.opts)
        action.target = self.target
        return action

    def name(self):
        return 'Extinguish Flames'

    def label(self):
        return 'Extinguish Flames'

    @staticmethod
    def burning_targets(entity, battle):
        """Burning creatures *entity* can reach: itself and allies within 5 ft."""
        candidates = [entity]
        if battle is not None:
            candidates += [e for e in battle.allies_of(entity) if e is not entity]
        battle_map = battle.map_for(entity) if battle is not None else None
        targets = []
        for creature in candidates:
            if BurningEffect.active_on(creature) is None:
                continue
            if creature is not entity and battle_map is not None:
                if battle.map_for(creature) is not battle_map:
                    continue
                distance = battle_map.distance(entity, creature) * battle_map.feet_per_grid
                if distance > ExtinguishFlamesAction.REACH_FT:
                    continue
            targets.append(creature)
        return targets

    @staticmethod
    def can(entity, battle, options=None):
        if battle is not None and entity.total_actions(battle) <= 0:
            return False
        return bool(ExtinguishFlamesAction.burning_targets(entity, battle))

    @staticmethod
    def build(session, source):
        return ExtinguishFlamesAction(session, source).build_map()

    @staticmethod
    def options_for(session, entity, battle):
        """One ready-to-run action per creature *entity* can put out."""
        options = []
        for target in ExtinguishFlamesAction.burning_targets(entity, battle):
            action = ExtinguishFlamesAction(session, entity)
            action.target = target
            options.append(action)
        return options

    def build_map(self):
        def set_target(target):
            action = self.clone()
            action.target = target
            return action

        return {
            'action': self,
            'param': [{
                'type': 'select_target',
                'num': 1,
                'range': self.REACH_FT,
                'target_types': ['self', 'allies'],
            }],
            'next': set_target,
        }

    def resolve(self, session, map, opts=None):
        opts = opts or {}
        battle = opts.get('battle')
        target = self.target
        if isinstance(target, (list, tuple)):
            target = target[0] if target else None
        target = target or self.source
        self.result = []
        effect = BurningEffect.active_on(target)
        if effect is None:
            return self
        roll = self.source.dexterity_check(battle=battle, description='dice_roll.extinguish_flames')
        self.result.append({
            'type': 'extinguish_flames',
            'source': self.source,
            'target': target,
            'roll': roll,
            'dc': effect.extinguish_dc,
            'success': roll.result() >= effect.extinguish_dc,
        })
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'extinguish_flames':
            return
        if session is None:
            session = battle.session if battle is not None else item['source'].session
        if item['success']:
            BurningEffect.extinguish(item['target'], by=item['source'], battle=battle)
        elif session is not None:
            session.event_manager.received_event({
                'event': 'extinguish_failed',
                'source': item['source'],
                'target': item['target'],
                'roll': item['roll'],
                'dc': item['dc'],
            })
        if battle is not None:
            battle.consume(item['source'], 'action')
