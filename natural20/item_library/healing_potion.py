from natural20.die_roll import DieRoll
from natural20.item_library.object import Object
from natural20.utils.healing import effective_heal_roll

class HealingPotion(Object):
    def __init__(self, session, map, properties):
        super().__init__(session, map, properties)
        self.properties = properties

    def consumable(self):
        return self.properties.get("consumable", False)

    def can_use(self, entity, battle):
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

    def resolve(self, entity, battle, action, _battle_map):
        hp_regain_roll = DieRoll.roll(
            self.properties.get("hp_regained", "1d4"),
            description="Healing Potion",
            entity=entity,
            battle=battle
        )
        target = getattr(action, 'target', None) or entity
        return { "hp_gain_roll": effective_heal_roll(target, hp_regain_roll) }

    def use(self, entity, result, session=None):
        entity.heal(effective_heal_roll(entity, result["hp_gain_roll"]).result())