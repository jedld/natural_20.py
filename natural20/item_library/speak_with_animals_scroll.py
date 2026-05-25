from natural20.item_library.object import Object
from natural20.utils.animal_communication import (
    DEFAULT_DURATION_SECONDS,
    grant_animal_communication,
)


class SpeakWithAnimalsScroll(Object):
    def __init__(self, session, map, properties):
        super().__init__(session, map, properties)
        self.properties = properties

    def consumable(self):
        return self.properties.get('consumable', True)

    def can_use(self, entity, battle):
        return True

    def build_map(self, action):
        def next_fn(target):
            action.target = target
            return action

        return {
            'param': [
                {
                    'type': 'select_target',
                    'num': 1,
                    'range': 0,
                    'target_types': ['self'],
                }
            ],
            'next': next_fn,
        }

    def resolve(self, entity, battle, action, _battle_map):
        duration_seconds = int(self.properties.get('duration_seconds', DEFAULT_DURATION_SECONDS))
        return {'duration_seconds': duration_seconds}

    def use(self, entity, result, session=None):
        session_obj = session or self.session
        expiration = grant_animal_communication(
            session_obj,
            entity=entity,
            duration_seconds=int(result.get('duration_seconds', self.properties.get('duration_seconds', DEFAULT_DURATION_SECONDS))),
        )

        if getattr(session_obj, 'event_manager', None) is not None:
            session_obj.event_manager.received_event(
                {
                    'event': 'message',
                    'source': entity,
                    'target': entity,
                    'message': f"You can understand beasts until game time {expiration}.",
                }
            )
