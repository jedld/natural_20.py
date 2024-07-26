from natural20.action import Action


class HideAction(Action):
    as_bonus_action: bool

    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.target = None
        self.as_bonus_action = False

    @staticmethod
    def can(entity, battle):
        return battle and entity.total_actions(battle) > 0

    def build_map(self):
        return {
            'param': None,
            'next': lambda: self
        }

    @staticmethod
    def build(session, source):
        action = HideAction(session, source, 'attack')
        return action.build_map()

    def resolve(self, session, map, opts=None):
        stealth_roll = self.source.stealth_check(opts['battle'])
        self.result = [{
            'source': self.source,
            'bonus_action': self.as_bonus_action,
            'type': 'hide',
            'roll': stealth_roll,
            'battle': opts['battle']
        }]
        return self

    @staticmethod
    def apply(battle, item):
        if item['type'] == 'hide':
            battle.event_manager.received_event({
                'source': item['source'],
                'roll': item['roll'],
                'event': 'hide'
            })
            item['source'].hiding(battle, item['roll'].result)
            if item['bonus_action']:
                battle.consume(item['source'], 'bonus_action')
            else:
                battle.consume(item['source'], 'action')

class HideBonusAction(HideAction):
    @staticmethod
    def can(entity, battle):
        return battle and entity.any_class_feature(['cunning_action', 'nimble_escape']) and entity.total_bonus_actions(battle) > 0

    @staticmethod
    def apply(battle, item):
        pass
