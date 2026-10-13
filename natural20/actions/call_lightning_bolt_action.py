from natural20.action import Action
from natural20.spell.call_lightning_spell import CallLightningEffect, CallLightningSpell


class CallLightningBoltAction(Action):
    """Use an action to call another bolt from an active Call Lightning cloud."""

    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.target = None

    def clone(self):
        action = CallLightningBoltAction(self.session, self.source, self.action_type, self.opts)
        action.target = self.target
        return action

    def name(self):
        return 'Call Lightning Bolt'

    def label(self):
        return 'Call Lightning Bolt'

    @staticmethod
    def active_storm(caster):
        storm = getattr(caster, 'concentration', None)
        return storm if isinstance(storm, CallLightningEffect) else None

    @staticmethod
    def _turn_key(battle):
        return (battle.current_round(), getattr(battle, 'current_turn_index', 0))

    @staticmethod
    def can(entity, battle, options=None):
        if battle is None or not entity.has_action(battle):
            return False
        storm = CallLightningBoltAction.active_storm(entity)
        if storm is None:
            return False
        return storm.last_bolt_turn != CallLightningBoltAction._turn_key(battle)

    @staticmethod
    def build(session, source):
        return CallLightningBoltAction(session, source, 'call_lightning_bolt').build_map()

    def build_map(self):
        storm = CallLightningBoltAction.active_storm(self.source)

        def set_target(target):
            action = self.clone()
            action.target = target
            return action

        param = {
            'type': 'select_radius',
            'num': 1,
            'range': storm.cloud_radius_ft() if storm else 60,
            'radius': int((storm.spell_properties if storm else {}).get('radius', 5)),
        }
        if storm is not None:
            param['origin'] = list(storm.center)
        return {'action': self, 'param': [param], 'next': set_target}

    def validate(self, battle_map, target=None):
        self.errors = []
        target = target if target is not None else self.target
        storm = CallLightningBoltAction.active_storm(self.source)
        if storm is None:
            self.errors.append('You are not concentrating on Call Lightning.')
            return
        if not isinstance(target, (list, tuple)) or len(target) != 2:
            self.errors.append('Choose a point under the storm cloud.')
            return
        reach = storm.cloud_radius_ft() // battle_map.feet_per_grid
        cx, cy = storm.center
        if max(abs(int(target[0]) - cx), abs(int(target[1]) - cy)) > reach:
            self.errors.append('That point is not under the storm cloud.')

    def resolve(self, session, map, opts=None):
        opts = opts or {}
        battle = opts.get('battle')
        self.result = []
        storm = CallLightningBoltAction.active_storm(self.source)
        if storm is None or self.target is None:
            return self
        battle_map = map or (battle.map_for(self.source) if battle else None)
        center = [int(self.target[0]), int(self.target[1])]
        spell = CallLightningSpell(session, self.source, 'CallLightningSpell', storm.spell_properties)
        self.result.extend(spell.bolt_items(self.source, battle, battle_map, center,
                                            storm.bolt_dice(), storm.dc))
        self.result.append({
            'type': 'call_lightning_bolt',
            'source': self.source,
            'target': center,
            'storm': storm,
        })
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'call_lightning_bolt':
            return
        if battle and session is None:
            session = battle.session
        source = item['source']
        storm = item.get('storm')
        if battle is not None:
            battle.consume(source, 'action')
            if storm is not None:
                storm.last_bolt_turn = CallLightningBoltAction._turn_key(battle)
        if session is not None:
            session.event_manager.received_event({
                'event': 'call_lightning_bolt',
                'source': source,
                'target': item.get('target'),
            })
