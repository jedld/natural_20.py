from typing import Callable
from dataclasses import dataclass
from types import SimpleNamespace
from natural20.action import Action
from natural20.entity import Entity

class StandAction(Action):
    def __init__(self, session, source, action_type):
        self.session = session
        self.source = source
        self.action_type = action_type

    @staticmethod
    def can(entity, battle):
        return battle and entity.prone() and entity.speed() > 0 and entity.available_movement(battle) >= StandAction.required_movement(entity)

    def build_map(self):
        return SimpleNamespace(param=None, next=lambda: self)

    @staticmethod
    def build(session, source):
        action = StandAction(session, source, "attack")
        return action.build_map()

    def resolve(self, session, map_, opts=None):
        self.result = [{
            "source": self.source,
            "type": "stand",
            "battle": opts.get("battle")
        }]
        return self

    @staticmethod
    def apply(battle, item):
        if item["type"] == "stand":
            print(f"{item['source'].name} stands up.")
            item["source"].stand()
            battle.consume(item["source"], "movement", (item["source"].speed() // 2))

    @staticmethod
    def required_movement(entity: Entity):
        return entity.speed() // 2
