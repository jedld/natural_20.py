from dataclasses import dataclass
from natural20.action import Action

@dataclass
class DisengageAction(Action):
    as_bonus_action: bool

    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.as_bonus_action = False

    def __repr__(self):
        if self.as_bonus_action:
            return "disengage as a bonus action"
        else:
            return "disengage"

    @staticmethod
    def can(entity, battle):
        return battle and battle.combat_ongoing() and entity.total_actions(battle) > 0

    def build_map(self):
        return self

    @staticmethod
    def build(session, source):
        action = DisengageAction(session, source, 'attack')
        return action.build_map()

    def resolve(self, session, map, opts=None):
        self.result = [{
            'source': self.source,
            'type': 'disengage',
            'as_bonus_action': self.as_bonus_action,
            'battle': opts.get('battle')
        }]
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if item['type'] == 'disengage':
            # print(f"{item['source'].name} disengages")
            battle.session.event_manager.received_event({'source': item['source'], 'event': 'disengage'})
            item['source'].do_disengage(battle)
            if item['as_bonus_action']:
                battle.consume(item['source'], 'bonus_action')
            else:
                battle.consume(item['source'], 'action')

@dataclass
class DisengageBonusAction(DisengageAction):
    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.as_bonus_action = True

    @staticmethod
    def can(entity, battle):
        return battle and entity.any_class_feature(['cunning_action', 'nimble_escape']) and entity.total_bonus_actions(battle) > 0
