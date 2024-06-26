from typing import Callable
from dataclasses import dataclass
from natural20.action import Action

@dataclass
class UseItemAction(Action):
    target: any
    target_item: any

    def __init__(self, session, source, action_type):
        self.session = session
        self.source = source
        self.action_type = action_type


    @staticmethod
    def can(entity, battle):
        return battle is None or entity.total_actions(battle) > 0

    @staticmethod
    def build(session, source):
        action = UseItemAction(session, source, "attack")
        action.build_map()

    def build_map(self):
        return {
            "action": self,
            "param": [
                {
                    "type": "select_item"
                }
            ],
            "next": lambda item: self.build_next(item)
        }

    def build_next(self, item):
        item_details = self.session.load_equipment(item)
        if not item_details["usable"]:
            raise Exception(f"item {item_details['name']} not usable!")

        self.target_item = item_details["item_class"](item, item_details)
        self.target_item.build_map(self)

    def resolve(self, session, map=None, opts=None):
        battle = opts.get("battle")
        result_payload = {
            "source": self.source,
            "target": self.target,
            "map": map,
            "battle": battle,
            "type": "use_item",
            "item": self.target_item
        }
        result_payload.update(self.target_item.resolve(self.source, battle))
        self.result = [result_payload]
        return self

    @staticmethod
    def apply(battle, item):
        if item["type"] == "use_item":
            battle.event_manager.received_event({"event": "use_item", "source": item["source"], "item": item["item"]})
            item["item"].use(item["target"], item)
            if item["item"].consumable():
                item["source"].deduct_item(item["item"].name, 1)
            if battle:
                battle.entity_state_for(item["source"])["action"] -= 1
