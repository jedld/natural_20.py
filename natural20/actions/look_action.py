from collections import namedtuple
from natural20.die_roll import DieRoll
from natural20.action import Action
from natural20.event_manager import EventManager

class LookAction(Action):
    def __init__(self, session, source, action_type, opts={}):
        super().__init__(session, source, action_type, opts)
        self.ui_callback = None

    @staticmethod
    def can(entity, battle, options={}):
        return battle is None or (battle.ongoing and entity.total_actions(battle) > 0 and battle.entity_state_for(entity)["active_perception"] == 0)

    def __repr__(self) -> str:
        return "Look(perception check)"

    def build_map(self):
        pass

    @staticmethod
    def build(session, source):
        action = LookAction(session, source, "look")
        return action.build_map()

    def resolve(self, session, map, opts={}):
        perception_check = self.source.perception_check(opts["battle"])
        perception_check_2 = self.source.perception_check(opts["battle"])

        perception_check_disadvantage = min(perception_check, perception_check_2)
        self.result = [{
            "source": self.source,
            "type": "look",
            "die_roll": perception_check,
            "die_roll_disadvantage": perception_check_disadvantage,
            "battle": opts["battle"],
            "ui_callback": self.ui_callback
        }]
        return self

    @staticmethod
    def apply(battle, item):
        if item["type"] == "look":
            battle.entity_state_for(item["source"])["active_perception"] = item["die_roll"].result()
            battle.entity_state_for(item["source"])["active_perception_disadvantage"] = item["die_roll_disadvantage"].result
            battle.session.event_manager.received_event({
                "source": item["source"],
                "perception_roll": item["die_roll"],
                "event": "perception"
            })
            if item["ui_callback"]:
                item["ui_callback"].target_ui(item["source"], perception=item["die_roll"].result, look_mode=True)
            battle.consume(item['source'], 'action')
