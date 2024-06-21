from typing import NamedTuple
from natural20.action import Action

class ProneAction(Action):
    def __init__(self, session, source, action_type):
        super().__init__(session, source, action_type, {})
        
    @staticmethod
    def can(entity, battle):
        return battle and not entity.prone()

    def build_map(self):
        return NamedTuple(param=None, next=lambda: self)

    @staticmethod
    def build(session, source):
        action = ProneAction(session, source, "prone")
        return action.build_map()

    def resolve(self, session, _map, opts=None):
        opts = opts or {}
        self.result = [{
            "source": self.source,
            "type": "prone",
            "battle": opts.get("battle")
        }]
        return self

    @staticmethod
    def apply(battle, item):
        if item["type"] == "prone":
            battle.event_manager.received_event({'event': 'prone', 'source': item['source']})
            item["source"].do_prone()
