from natural20.action import Action
import pdb
class HelpAction(Action):
    target: any

    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.target = None

    @staticmethod
    def can(entity, battle):
        if battle:
            return entity.total_actions(battle) > 0
        return True

    def build_map(self):
        def set_target(target):
            self.target = target
            return self
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
            'next': set_target
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
            'battle': opts.get('battle')
        }]
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if item['type'] == 'help':
            
            if battle:
                battle.consume(item['source'], 'action')
                battle.event_manager.received_event({
                    'source': item['source'],
                    'target': item['target'],
                    'event': 'help'
                })
            else:
                session.event_manager.received_event({
                    'source': item['source'],
                    'target': item['target'],
                    'event': 'help'
                })

            item['source'].do_help(item['battle'], item['target'])
