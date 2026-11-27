from typing import NamedTuple
from natural20.action import Action

class ProneAction(Action):
    def __init__(self, session, source, action_type):
        super().__init__(session, source, action_type, {})
        
    @staticmethod
    def can(entity, battle):
        # Going prone is allowed out of combat too (5e "Move": falling
        # prone is always available); like StandAction, gate only on the
        # creature's own state so the VTT action bar offers it anywhere.
        return not entity.prone()

    def build_map(self):
        return self

    def label(self):
        return "Go Prone"

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
    def apply(battle, item, session=None):
        if item["type"] == "prone":
            if battle:
                battle.event_manager.received_event({'event': 'prone', 'source': item['source']})
            item["source"].do_prone()
