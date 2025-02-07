from collections import namedtuple
from natural20.die_roll import DieRoll
from natural20.action import Action
from natural20.event_manager import EventManager
import pdb

class LookAction(Action):
    def __init__(self, session, source, action_type, opts={}):
        super().__init__(session, source, action_type, opts)
        self.ui_callback = None
        self.perception_targets = {}

    @staticmethod
    def can(entity, battle, options={}):
        return battle is None or (battle.ongoing and entity.total_actions(battle) > 0 and battle.entity_state_for(entity)["active_perception"] == 0)

    def __repr__(self) -> str:
        return "Look(perception check)"

    def build_map(self):
        return self

    @staticmethod
    def build(session, source):
        action = LookAction(session, source, "look")
        return action.build_map()

    def resolve(self, session, map, opts={}):
        perception_check = self.source.perception_check(opts.get("battle"))
        perception_check_2 = self.source.perception_check(opts.get("battle"))

        perception_check_disadvantage = min(perception_check, perception_check_2)
        self.result = [{
            "source": self.source,
            "type": "look",
            "die_roll": perception_check,
            "die_roll_disadvantage": perception_check_disadvantage,
            "map": map,
            "battle": opts.get("battle"),
            "ui_callback": self.ui_callback
        }]
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if item["type"] == "look":
            if battle:
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

            current_map = item["map"]
            # scan all visible objects in the map with a note
            item['perception_targets'] = {}
            for entity in list(current_map.entities.keys()) + list(current_map.interactable_objects.keys()):
                if entity != item["source"] and entity.has_notes() and current_map.can_see(item["source"], entity):
                    if session:
                        session.event_manager.received_event({
                            "source": item["source"],
                            "target": entity,
                            "die_roll": item["die_roll"],
                            "event": "look"
                        })

                    _, new_notes = entity.list_notes(entity=item["source"], perception=item["die_roll"].result())
                    for k in new_notes.keys():
                        item['perception_targets'][k] = new_notes[k]