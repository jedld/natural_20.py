from natural20.action import Action
from collections import namedtuple

class EscapeGrappleAction(Action):
    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.ui_callback = None

    @staticmethod
    def can(entity, battle, options=None):
        return entity.grappled() and (battle is None or entity.total_actions(battle) > 0)

    def __str__(self):
        return self.action_type.value.replace("_", " ").capitalize()

    def build_map(self):
        ActionParam = namedtuple("ActionParam", ["type", "targets", "num"])
        action_param = ActionParam(type="select_target", targets=self.source.grapples, num=1)

        return {
            "action": self,
            "param": [action_param],
            "next": lambda target: self.set_target(target)
        }

    @classmethod
    def build(cls, session, source):
        action = cls(session, source, "escape_grapple")
        return action.build_map()

    def resolve(self, session, map, opts=None):
        battle = opts.get("battle")
        target = self.source.grapples[0]

        strength_roll = target.athletics_check(battle)
        athletics_stats = (self.source.proficiency_bonus if self.source.athletics_proficient else 0) + self.source.str_mod
        acrobatics_stats = (self.source.proficiency_bonus if self.source.acrobatics_proficient else 0) + self.source.dex_mod

        contested_roll = self.source.athletics_check(battle) if athletics_stats > acrobatics_stats else self.source.acrobatics_check(battle)
        grapple_success = strength_roll.result >= contested_roll.result

        if grapple_success:
            result = [{
                "source": self.source,
                "target": target,
                "type": "grapple_escape",
                "success": True,
                "battle": battle,
                "source_roll": contested_roll,
                "target_roll": strength_roll
            }]
        else:
            result = [{
                "source": self.source,
                "target": target,
                "type": "grapple_escape",
                "success": False,
                "battle": battle,
                "source_roll": contested_roll,
                "target_roll": strength_roll
            }]

        self.result = result

    @staticmethod
    def apply(battle, item):
        if item["type"] == "grapple_escape":
            if item["success"]:
                item["source"].escape_grapple_from(item["target"])
                battle.event_manager.received_event( { "event" : "escape_grapple_success",
                                                       "target": item["target"],
                                                       "source": item["source"],
                                                       "source_roll" : item["source_roll"],
                                                       "target_roll" : item["target_roll"]})
            else:
                battle.event_manager.received_event( { "event": "escape_grapple_failure",
                                                       "target" : item["target"],
                                                       "source" : item["source"],
                                                       "source_roll": item["source_roll"],
                                                       "target_roll" :item["target_roll"]})

            battle.consume(item["source"], "action")
