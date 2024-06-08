from natural20.item_library.object import Object
from natural20.event_manager import EventManager

class DoorObject(Object):
    def __init__(self, map, properties):
        super().__init__(map, properties)
        self.state = "closed"
        self.locked = False
        self.key_name = None

    def opaque(self):
        return self.closed() and not self.dead()

    def unlock(self):
        self.locked = False

    def lock(self):
        self.locked = True

    def locked(self):
        return self.locked

    def passable(self):
        return self.opened() or self.dead()

    def closed(self):
        return self.state == "closed"

    def opened(self):
        return self.state == "opened"

    def open(self):
        self.state = "opened"

    def close(self):
        self.state = "closed"

    def token(self):
        if self.dead():
            return "`"

        pos_x, pos_y = self.position()
        if self.map.wall(pos_x - 1, pos_y) or self.map.wall(pos_x + 1, pos_y):
            return "-" if self.opened() else "="
        else:
            return "|" if self.opened() else "║"

    def token_opened(self):
        return self.properties.get("token_open", "-")

    def token_closed(self):
        return self.properties.get("token_closed", "=")

    def available_interactions(self, entity, battle=None):
        interaction_actions = {}
        if self.locked():
            interaction_actions["unlock"] = {
                "disabled": not entity.item_count(self.key_name) > 0,
                "disabled_text": "object.door.key_required"
            }
            if entity.item_count("thieves_tools") > 0 and entity.proficient("thieves_tools"):
                interaction_actions["lockpick"] = {
                    "disabled": entity.action(battle),
                    "disabled_text": "object.door.action_required"
                }
            return interaction_actions

        if self.opened():
            return {"close": {"disabled": self.someone_blocking_the_doorway(), "disabled_text": "object.door.door_blocked"}}
        else:
            return {"open": {}, "lock": {"disabled": not entity.item_count(self.key_name) > 0, "disabled_text": "object.door.key_required"}}

    def interactable(self):
        return True

    def resolve(self, entity, action, other_params, opts=None):
        if action is None:
            return

        if action == "open":
            if not self.locked():
                return {"action": action}
            else:
                return {"action": "door_locked"}
        elif action == "close":
            return {"action": action}
        elif action == "lockpick":
            lock_pick_roll = entity.lockpick(opts["battle"])

            if lock_pick_roll.result() >= self.lockpick_dc():
                return {"action": "lockpick_success", "roll": lock_pick_roll, "cost": "action"}
            else:
                return {"action": "lockpick_fail", "roll": lock_pick_roll, "cost": "action"}
        elif action == "unlock":
            return {"action": "unlock"} if entity.item_count(self.key_name) > 0 else {"action": "unlock_failed"}
        elif action == "lock":
            return {"action": "lock"} if not self.unlocked() else {"action": "lock_failed"}

    def use(self, entity, result):
        action = result["action"]
        if action == "open":
            if self.closed():
                self.open()
        elif action == "close":
            if self.opened():
                if self.someone_blocking_the_doorway():
                    EventManager.received_event(source=self, user=entity, event="object_interaction",
                                                          sub_type="close_failed", result="failed",
                                                          reason="Cannot close door since something is in the doorway")
                self.close()
        elif action == "lockpick_success":
            if self.locked():
                self.unlock()
                EventManager.received_event(source=self, user=entity, event="object_interaction",
                                                      sub_type="unlock", result="success", lockpick=True,
                                                      roll=result["roll"], reason="Door unlocked using lockpick.")
        elif action == "lockpick_fail":
            entity.deduct_item("thieves_tools")
            EventManager.received_event(source=self, user=entity, event="object_interaction",
                                                  sub_type="unlock", result="failed", roll=result["roll"],
                                                  reason="Lockpicking failed and the theives tools are now broken")
        elif action == "unlock":
            if self.locked():
                self.unlock()
                EventManager.received_event(source=self, user=entity, event="object_interaction",
                                                      sub_type="unlock", result="success", reason="object.door.unlock")
        elif action == "lock":
            if self.unlocked():
                self.lock()
                EventManager.received_event(source=self, user=entity, event="object_interaction",
                                                      sub_type="lock", result="success", reason="object.door.lock")
        elif action == "door_locked":
            EventManager.received_event(source=self, user=entity, event="object_interaction",
                                                  sub_type="open_failed", result="failed", reason="Cannot open door since door is locked.")
        elif action == "unlock_failed":
            EventManager.received_event(source=self, user=entity, event="object_interaction",
                                                  sub_type="unlock_failed", result="failed", reason="Correct Key missing.")

    def lockpick_dc(self):
        return self.properties.get("lockpick_dc", 10)

    def someone_blocking_the_doorway(self):
        return bool(self.map.entity_at(*self.position()))

    def on_take_damage(self, battle, damage_params):
        pass

    def setup_other_attributes(self):
        self.state = self.properties.get("state", "closed")
        self.locked = self.properties.get("locked")
        self.key_name = self.properties.get("key")
