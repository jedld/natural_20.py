from natural20.action import Action

class HelpAction(Action):
    target: any

    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.target = None

    @staticmethod
    def can(entity, battle):
        return battle and entity.total_actions(battle) > 0

    def build_map(self):
        return {
            'action': self,
            'param': [
                {
                    'type': 'select_target',
                    'target_types': ['allies', 'enemies'],
                    'range': 5,
                    'num': 1
                }
            ],
            'next': lambda target: {
                'param': None,
                'next': lambda: self
            }
        }

    @staticmethod
    def build(session, source):
        action = HelpAction(session, source, 'help')
        return action.build_map()

    def resolve(self, session, map, opts=None):
        self.result = [{
            'source': self.source,
            'target': self.target,
            'type': 'help',
            'battle': opts['battle']
        }]
        return self

    @staticmethod
    def apply(battle, item):
        if item['type'] == 'help':
            battle.event_manager.received_event({
                'source': item['source'],
                'target': item['target'],
                'event': 'help'
            })
            item['source'].help(item['battle'], item['target'])
            battle.consume(item['source'], 'action')
