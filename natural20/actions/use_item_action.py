from dataclasses import dataclass
from natural20.action import Action
from natural20.item_library.healing_potion import HealingPotion
import pdb

@dataclass
class UseItemAction(Action):
    def __init__(self, session, source, action_type):
        super().__init__(session, source, action_type)
        self.session = session
        self.source = source
        self.action_type = action_type
        self.target = None
        self.target_item = None


    def __str__(self):
        if self.target_item:
            return f"UseItem: {self.target_item.name}"
        return "UseItem"
    
    def __repr__(self):
        return self.__str__()
    
    def clone(self):
        action = UseItemAction(self.session, self.source, self.action_type)
        action.target = self.target
        action.target_item = self.target_item
        return action
    
    @staticmethod
    def can(entity, battle):
        return battle is None or entity.total_actions(battle) > 0

    def can_use_on(self, entity):
        return self.target_item.can_use(entity)

    def usable_items(self):
        return self.source.usable_items()

    @staticmethod
    def build(session, source):
        action = UseItemAction(session, source, "use_item")
        return action.build_map()

    def build_map(self):
        def next_fn(item):
            action = self.clone()
            action.target_item = item
            return action.build_next(item)

        return {
            "action": self,
            "param": [
                {
                    "type": "select_item"
                }
            ],
            "next": next_fn
        }

    def build_next(self, item):
        item_details = self.session.load_equipment(item)
        if not item_details["usable"]:
            raise Exception(f"item {item_details['name']} not usable!")

        klass = UseItemAction.to_item_class(item_details['item_class'])
        self.target_item = klass(item, item_details)
        return self.target_item.build_map(self)

    def to_item_class(item_class):
        if item_class == 'HealingPotion':
            klass = HealingPotion
        else:
            raise Exception(f"item class {item_class} not found")
        return klass


    def resolve(self, session, map=None, opts=None):
        if opts is None:
            opts = {}
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
    def apply(battle, item, session=None):
        if item["type"] == "use_item":
            if session is None:
                session = battle.session
            if session:
                session.event_manager.received_event({"event": "use_item", "source": item["source"], "item": item["item"]})
            item["item"].use(item["target"], item)
            if item["item"].consumable():
                item["source"].deduct_item(item["item"].name, 1)
            if battle:
                battle.entity_state_for(item["source"])["action"] -= 1
