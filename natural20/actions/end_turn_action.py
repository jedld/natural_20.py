from natural20.action import Action


class EndTurnAction(Action):
    """Pass / end-turn action.

    Choosing this means the entity does nothing for the rest of its turn
    (wait, hold position, conserve resources). The JEV planner always offers
    it as a top-level option in the flattened action list; the controller
    maps a chosen EndTurnAction to ``None`` so the battle loop ends the turn.
    If one is ever committed anyway, ``apply`` is a harmless no-op that only
    emits an ``end_turn`` event (no resources are consumed).
    """

    def __init__(self, session, source, action_type):
        super().__init__(session, source, action_type)
        self.session = session
        self.source = source
        self.action_type = action_type

    @staticmethod
    def can(entity, battle):
        return True

    def build_map(self):
        return self

    @staticmethod
    def build(session, source):
        action = EndTurnAction(session, source, "end_turn")
        return action.build_map()

    def resolve(self, session, map_, opts=None):
        if not opts:
            opts = {}
        self.result = [{
            "source": self.source,
            "type": "end_turn",
            "battle": opts.get("battle")
        }]
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if item["type"] == "end_turn":
            if battle:
                battle.event_manager.received_event({'event': 'end_turn', 'source': item['source']})
        return []
