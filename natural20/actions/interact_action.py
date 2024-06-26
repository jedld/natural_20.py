from typing import Callable
from natural20.action import Action

class InteractAction(Action):
    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.target = None
        self.object_action = None
        self.other_params = None

    @staticmethod
    def can(entity, battle):
        return battle is None or not battle.ongoing or entity.total_actions(battle) > 0 or entity.free_object_interaction(battle)

    @staticmethod
    def build(session, source):
        action = InteractAction()
        action.build_map()
        return action

    def build_map(self):
        return {
            'action': self,
            'param': [
                {
                    'type': 'select_object'
                }
            ],
            'next': lambda object: self.build_next(object)
        }

    def build_next(self, object):
        self.target = object
        return {
            'param': [
                {
                    'type': 'interact',
                    'target': object
                }
            ],
            'next': lambda action: self.build_custom_action(action, object)
        }

    def build_custom_action(self, action, object):
        self.object_action = action
        custom_action = object.build_map(action, self) if object else None

        if custom_action is None:
            return {
                'param': None,
                'next': lambda: self
            }
        else:
            return custom_action

    def resolve(self, session, map=None, opts=None):
        battle = opts.get('battle') if opts else None

        result = self.target.resolve(self.source, self.object_action, self.other_params, opts)

        if result is None:
            return []

        result_payload = {
            'source': self.source,
            'target': self.target,
            'object_action': self.object_action,
            'map': map,
            'battle': battle,
            'type': 'interact'
        }
        result_payload.update(result)
        self.result = [result_payload]
        return self

    @staticmethod
    def apply(battle, item):
        entity = item['source']
        item_type = item['type']

        if item_type == 'interact':
            item['target'].use(entity, item)
            if item['cost'] == 'action':
                battle.consume(entity, 'action', 1)
            else:
                battle.consume(entity, 'free_object_interaction', 1) or battle.consume(entity, 'action', 1)

            battle.event_manager.received_event(event='interact', source=entity, target=item['target'],
                                                  object_action=item['object_action'])
