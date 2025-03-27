from natural20.action import Action
import pdb
class ShoveAction(Action):
    def __init__(self, session, source, action_type):
        super().__init__(session, source, action_type, {})
        self.target = None
        self.knock_prone = None

    @staticmethod
    def can(entity, battle, options=None):
        return battle is None or entity.total_actions(battle) > 0

    def validate(self, battle_map, target=None):
        if target is None:
            target = self.target

        errors = []
        if target is None:
            errors.append("target is a required option for :attack")
        if (target.size_identifier() - self.source.size_identifier()) > 1:
            errors.append("validation.shove.invalid_target_size")
        return errors

    def __str__(self):
        return str(self.action_type).capitalize()

    def clone(self):
        return ShoveAction(self.session, self.source, self.action_type)

    def build_map(self):
        def set_target(target):
            action = self.clone()
            action.target = target
            return action

        return {
            "action": self,
            "param": [
                {
                    "type": "select_target",
                    "range": 5,
                    "target_types": ["enemies"],
                    "num": 1
                }
            ],
            "next": set_target
        }

    @staticmethod
    def build(session, source):
        action = ShoveAction(session, source, 'shove')
        return action.build_map()

    def resolve(self, session, map, opts=None):
        if not opts:
            opts = {}

        target = opts.get("target") or self.target
        battle = opts.get("battle")
        if target is None:
            raise Exception("target is a required option for :attack")
        if (target.size_identifier() - self.source.size_identifier()) > 1:
            return

        strength_roll = self.source.athletics_check(battle)
        athletics_stats = (self.target.athletics_proficient() * self.target.proficiency_bonus()) + self.target.str_mod()
        acrobatics_stats = (self.target.acrobatics_proficient() * self.target.proficiency_bonus()) + self.target.dex_mod()

        shove_success = False
        if self.target.incapacitated():
            shove_success = True
        else:
            if athletics_stats > acrobatics_stats:
                contested_roll = self.target.athletics_check(battle, description="die_roll.contest")
            else:
                contested_roll = self.target.acrobatics_check(battle, description="die_roll.contest")
            shove_success = strength_roll.result() >= contested_roll.result()

        shove_loc = None
        additional_effects = []
        if not self.knock_prone:
            shove_loc = self.target.push_from(map, *map.entity_or_object_pos(self.source))
            if shove_loc:
                trigger_results = map.area_trigger(self.target, shove_loc, False)
                additional_effects += trigger_results

        if shove_success:
            self.result = [{
                "source": self.source,
                "target": target,
                "type": "shove",
                "success": True,
                "battle": battle,
                "map": map,
                "shove_loc": shove_loc,
                "knock_prone": self.knock_prone,
                "source_roll": strength_roll,
                "target_roll": contested_roll
            }] + additional_effects
        else:
            self.result = [{
                "source": self.source,
                "target": target,
                "type": "shove",
                "success": False,
                "battle": battle,
                "knock_prone": self.knock_prone,
                "source_roll": strength_roll,
                "target_roll": contested_roll
            }]
        return self

    @staticmethod
    def apply(battle, item, session=None):
        event_manager = battle.event_manager if battle else session.event_manager
        if item["type"] == "shove":
            # if target entity is passive it is now active
            if item["target"].passive():
                item["target"].make_active()

            if item["success"]:
                if item["knock_prone"]:
                    item["target"].prone()
                elif item["shove_loc"]:
                    if item["map"].entity_at(*item["shove_loc"]):
                        item["target"].prone()
                    else:
                        item["map"].move_to(item["target"], *item["shove_loc"], battle)
                else:
                    raise Exception(f"Invalid shove action {item}")
                event_manager.received_event(
                    {
                        "event": "shove", "success": True, "target": item["target"], "source": item["source"],
                        "shove_loc": item["shove_loc"],
                        "source_roll": item["source_roll"], "target_roll": item["target_roll"]
                    }
                )
            else:
                event_manager.received_event(
                    {
                        "event": "shove", "success": False,
                        "target": item["target"], "source": item["source"],
                        "source_roll": item["source_roll"], "target_roll": item["target_roll"]
                    }
                )
            if battle:
                battle.consume(item["source"], 'action')


class PushAction(ShoveAction):
    pass
