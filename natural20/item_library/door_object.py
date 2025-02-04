from natural20.item_library.object import Object
from natural20.event_manager import EventManager

class DoorObject(Object):
    def __init__(self, map, properties):
        super().__init__(map, properties)
        self.front_direction = self.properties.get("front_direction", "auto")
        self.privacy_lock = self.properties.get("privacy_lock", False)
        self.state = "closed"
        self.locked = False
        self.key_name = None

    def facing(self):
        if self.front_direction == "auto":
            # check for walls and auto determine the direction
            pos = self.map.position_of(self)

            if self.map.wall(pos[0] - 1, pos[1]):
                self.front_direction = "up"
            elif self.map.wall(pos[0] + 1, pos[1]):
                self.front_direction = "down"
            elif self.map.wall(pos[0], pos[1] - 1):
                self.front_direction = "left"
            elif self.map.wall(pos[0], pos[1] + 1):
                self.front_direction = "right"
            else:
                self.front_direction = "up"

        return self.front_direction

    def opaque(self, origin=None):
        return self.closed() and not self.dead()

    def unlock(self):
        self.locked = False

    def lock(self):
        self.locked = True

    def passable(self, origin=None):
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

        if self.facing() == "up":
            return "-" if self.opened() else "="
        elif self.facing() == "down":
            return "-" if self.opened() else "="
        elif self.facing() == "left":
            return ":" if self.opened() else "║"
        elif self.facing() == "right":
            return ":" if self.opened() else "║"

        pos_x, pos_y = self.position()
        if self.map.wall(pos_x - 1, pos_y) or self.map.wall(pos_x + 1, pos_y):
            return "-" if self.opened() else "="
        else:
            return "|" if self.opened() else "║"

    def token_opened(self):
        return self.properties.get("token_open", "-")

    def token_closed(self):
        return self.properties.get("token_closed", "=")
    
    def token_image_transform(self):
        # apply css style to rotate the image relative to the right hinge
        # depending on the direction of the door
        # Set transform-origin based on facing direction
        if self.facing() == "up":
            transform = "transform-origin: 100% 50%;"
        elif self.facing() == "down":
            transform = "transform-origin: 0% 50%;"
        else:
            transform = ""

        # Now apply rotation and translation
        if self.closed():
            if self.facing() == "up":
                transform += " transform: rotate(0deg);"
            elif self.facing() == "down":
                transform += " transform: rotate(180deg);"
            elif self.facing() == "left":
                transform += " transform: rotate(-90deg) translateX(-50%) translateY(120%);"
            elif self.facing() == "right":
                transform += " transform: rotate(90deg);"
        elif self.opened():
            if self.facing() == "up":
                transform += " transform: rotate(90deg);"
            elif self.facing() == "down":
                transform += " transform: rotate(-90deg);"
            elif self.facing() == "left":
                transform += " transform: rotate(0deg) translatey(50%);"
            elif self.facing() == "right":
                transform += " transform: rotate(180deg);"
        return transform

    def available_interactions(self, entity, battle=None):
        def inside_range():
            ex, ey = self.map.position_of(entity)
            dx, dy = self.map.position_of(self)
            facing = self.facing()
            if facing == "up":    return ex == dx and ey == dy - 1
            if facing == "down":  return ex == dx and ey == dy + 1
            if facing == "left":  return ex == dx - 1 and ey == dy
            if facing == "right": return ex == dx + 1 and ey == dy
            return False

        actions = {}
        if entity:
            has_key = entity.item_count(self.key_name) > 0
        else:
            has_key = False

        if self.locked:
            actions["unlock"] = {
                "disabled": not has_key,
                "disabled_text": "object.door.key_required"
            }
            if entity.item_count("thieves_tools") > 0 and entity.proficient("thieves_tools"):
                actions["lockpick"] = {
                    "disabled": entity.action(battle),
                    "disabled_text": "object.door.action_required"
                }
            if self.privacy_lock and inside_range():
                actions["unlock"] = {}
            return actions

        if self.opened():
            return {
                "close": {
                    "disabled": self.someone_blocking_the_doorway(),
                    "disabled_text": "object.door.door_blocked"
                }
            }

        actions["open"] = {}
        if self.privacy_lock and inside_range():
            actions["lock"] = {}
        else:
            actions["lock"] = {
                "disabled": not has_key,
                "disabled_text": "object.door.key_required"
            }
        return actions

    def interactable(self):
        return True

    def resolve(self, entity, action, other_params, opts=None):
        if action is None:
            return

        if action == "open":
            if not self.locked:
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


