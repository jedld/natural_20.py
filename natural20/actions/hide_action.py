from natural20.action import Action

class HideAction(Action):
    as_bonus_action: bool

    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.target = None
        self.as_bonus_action = False

    @staticmethod
    def can(entity, battle, options=None):
        if options is None:
            options = {}

        return battle and battle.maps and entity.total_actions(battle) > 0

    def build_map(self):
        return self

    @staticmethod
    def build(session, source):
        action = HideAction(session, source, 'attack')
        return action.build_map()

    def resolve(self, session, map, opts=None):
        if opts is None:
            opts = {}
        stealth_roll = self.source.stealth_check(opts.get('battle', None))

        source_map = self.session.map_for_entity(self.source)

        if opts['battle']:
            opponents = [opp for opp in opts['battle'].opponents_of(self.source) if opp.conscious()]
        else:
            opponents = []

        hide_failed_reasons = []
        if source_map:
            heavily_obscured = source_map.is_heavily_obscured(self.source)
        else:
            heavily_obscured = False

        opponent_passive_perception = 0

        for opp in opponents:
            opponent_map = self.session.map_for_entity(opp)
            if source_map != opponent_map:
                continue
            if source_map and source_map.can_see(opp, self.source):
                opponent_passive_perception = opp.passive_perception()
                if heavily_obscured:
                    opponent_passive_perception -= 5
                if opp.class_feature('keen_sight_and_smell'):
                    opponent_passive_perception += 5
                if stealth_roll < opponent_passive_perception:
                    hide_failed_reasons.append(f"{opp.name} can see {self.source.name}")

        if hide_failed_reasons:
            self.result = [{
                'source': self.source,
                'type': 'hide',
                'bonus_action': self.as_bonus_action,
                'result': 'failed',
                'roll': stealth_roll,
                'battle': opts['battle'],
                'reason': hide_failed_reasons
            }]
        else:
            self.result = [{
                'source': self.source,
                'bonus_action': self.as_bonus_action,
                'type': 'hide',
                'result': 'success',
                'roll': stealth_roll,
                'battle': opts['battle']
            }]
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if item['type'] == 'hide':
            if item['result'] == 'success':
                battle.event_manager.received_event({
                    'source': item['source'],
                    'roll': item['roll'],
                    'result' : 'success',
                    'event': 'hide'
                })
                item['source'].do_hide(item['roll'].result())
            else:
                battle.event_manager.received_event({
                    'source': item['source'],
                    'roll': item['roll'],
                    'result' : 'failed',
                    'event': 'hide',
                    'reason': item['reason']
                })

            if item.get('bonus_action'):
                battle.consume(item['source'], 'bonus_action')
            else:
                battle.consume(item['source'], 'action')

class HideBonusAction(HideAction):
    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.as_bonus_action = True

    @staticmethod
    def can(entity, battle):
        if not battle or entity.total_bonus_actions(battle) <= 0:
            return False

        if entity.any_class_feature(['cunning_action', 'nimble_escape']):
            return True

        if entity.any_class_feature(["shadow_stealth"]):
            map_entity = battle.map_for(entity)
            return map_entity.light_at(map_entity.position_of(entity)) <= 0.5

        return False
