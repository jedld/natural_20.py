from natural20.die_roll import DieRoll
from natural20.item_library.object import Object

class HealingPotion(Object):
    def __init__(self, name, properties):
        super().__init__(None, properties)
        self.name = name
        self.properties = properties

    def consumable(self):
        return self.properties.get("consumable", False)

    def can_use(self, entity):
        return True
        # return entity.hp() < entity.max_hp()

    def build_map(self, action):
        def next_fn(target):
            action.target = target
            return action

        return {
            "param": [
                {
                    "type": "select_target",
                    "num": 1,
                    "range": 5,
                    "target_types": ["allies", "self"]
                }
            ],
            "next": next_fn
        }

    def resolve(self, entity, battle):
        hp_regain_roll = DieRoll.roll(
            self.properties.get("hp_regained", "1d4"),
            description="Healing Potion",
            entity=entity,
            battle=battle
        )
        return { "hp_gain_roll": hp_regain_roll }

    def use(self, entity, result):
        entity.heal(result["hp_gain_roll"].result())