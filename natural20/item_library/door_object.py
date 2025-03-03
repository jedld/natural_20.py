from natural20.item_library.object import Object
from natural20.item_library.common import StoneWallDirectional
from natural20.event_manager import EventManager
import pdb

class DoorObject(Object):
    def __init__(self, session, map, properties):
        Object.__init__(self, session, map, properties)
        self.front_direction = self.properties.get("front_direction", "auto")
        self.privacy_lock = self.properties.get("privacy_lock", False)
        self.door_blocking = self.properties.get("door_blocking", False)
        self.state = self.properties.get("state", "closed")
        self.lockable = self.properties.get("lockable", 'key' in self.properties.keys())
        self.locked = self.properties.get("locked", False)
        self.key_name = self.properties.get("key")
        self.door_pos = self.properties.get("door_pos", None)

    def after_setup(self):
        if self.front_direction == "auto":
            # check for walls and auto determine the direction
            pos = self.map.position_of(self)

            if self.door_pos is not None:
                if self.door_pos == 0:
                    self.front_direction = "up"
                elif self.door_pos == 1:
                    self.front_direction = "right"
                elif self.door_pos == 2:
                    self.front_direction = "down"
                elif self.door_pos == 3:
                    self.front_direction = "left"
            else:
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

    def facing(self):
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
        self.resolve_trigger("open")

    def close(self):
        self.state = "closed"
        self.resolve_trigger("close")

    def token(self):
        if self.dead():
            return "`"

        if self.opened() and self.properties.get("token_open"):
            return self.properties.get("token_open")

        if self.closed() and self.properties.get("token_closed"):
            return self.properties.get("token_closed")

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

    def available_interactions(self, entity, battle=None, admin=False):
        if self.concealed():
            return {}

        def inside_range_for_locking():
            if admin:
                return True

            offsets = {
            "up": (0, -1),
            "down": (0, 1),
            "left": (-1, 0),
            "right": (1, 0)
            }
            ex, ey = self.map.position_of(entity)
            dx, dy = self.map.position_of(self)
            off = offsets.get(self.facing())
            return off and (ex, ey) == (dx + off[0], dy + off[1])

        def inside_range_for_opening():
            if admin:
                return True

            ex, ey = self.map.position_of(entity)
            dx, dy = self.map.position_of(self)

            if self.map.position_of(entity) == self.map.position_of(self):
                return True

            offsets = {
                "up": (0, -1),
                "down": (0, 1),
                "left": (-1, 0),
                "right": (1, 0)
            }

            offset_opposite = {
                "up": (0, 1),
                "down": (0, -1),
                "left": (1, 0),
                "right": (-1, 0)
            }

            off = offsets.get(self.facing())
            off_opposite = offset_opposite.get(self.facing())
            is_in_range = [(ex, ey) == (dx + off[0], dy + off[1]), (ex, ey) == (dx + off_opposite[0], dy + off_opposite[1])]
            return any(is_in_range) if off else False

        actions = super().available_interactions(entity, battle, admin)
        if entity:
            has_key = entity.item_count(self.key_name) > 0
        else:
            has_key = False

        if self.locked and not admin:
            if self.lockable:
                actions["unlock"] = {
                    "disabled": not has_key,
                    "disabled_text": "object.door.key_required"
                }
                if entity.item_count("thieves_tools") > 0 and entity.proficient("thieves_tools"):
                    if battle:
                        actions["lockpick"] = {
                            "disabled": entity.action(battle),
                            "disabled_text": "object.door.action_required"
                        }
                    else:
                        actions["lockpick"] = {}
                if self.privacy_lock and inside_range_for_locking():
                    actions["unlock"] = {}
            return actions

        if self.opened() and inside_range_for_opening():
            return {
                "close": {
                    "disabled": self.someone_blocking_the_doorway(),
                    "disabled_text": "object.door.door_blocked"
                }
            }

        if inside_range_for_opening():
            actions["open"] = {}

        if self.privacy_lock and self.lockable and inside_range_for_locking():
            actions["lock"] = {}
        elif self.lockable:
            actions["lock"] = {
                "disabled": not has_key and not admin,
                "disabled_text": "object.door.key_required"
            }
        return actions

    def interactable(self, entity=None):
        return True

    def resolve(self, entity, action, other_params, opts=None):
        results = super().resolve(entity, action, other_params, opts)
        if results:
            return results

        if opts is None:
            opts = {}

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
            lock_pick_roll = entity.lockpick(opts.get("battle"))

            if lock_pick_roll.result() >= self.lockpick_dc():
                return {
                        "action": "lockpick_success",
                        "roll": lock_pick_roll,
                        "dc" : self.lockpick_dc(),
                        "cost": "action"
                        }
            else:
                return {"action": "lockpick_fail", "roll": lock_pick_roll, "dc" : self.lockpick_dc(),
                         "cost": "action"}
        elif action == "unlock":
            return {"action": "unlock"} if entity.item_count(self.key_name) > 0 else {"action": "unlock_failed"}
        elif action == "lock":
            return {"action": "lock"} if not self.unlocked() else {"action": "lock_failed"}

    def use(self, entity, result, session=None):
        super().use(entity, result, session)
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
            if self.locked:
                self.unlock()
                session.event_manager.received_event( { "source": entity,
                                                        "target": self,
                                                        "event": "object_interaction",
                                                        "sub_type": "unlock",
                                                        "result": "success",
                                                        "lockpick": True,
                                                        "roll": result["roll"],
                                                        "reason": "Door unlocked using lockpick."})
        elif action == "lockpick_fail":
            entity.deduct_item("thieves_tools")
            if session:
                session.event_manager.received_event({ "source": entity,
                                            "target": self,
                                            "event": "object_interaction",
                                            "sub_type": "unlock",
                                            "result": "failed",
                                            "roll": result["roll"],
                                            "reason":"Lockpicking failed and the theives tools are now broken"})
        elif action == "unlock":
            if self.locked:
                self.unlock()
                if session:
                    session.event_manager.received_event({
                                                        "source": entity,
                                                        "target": entity,
                                                        "event": "object_interaction",
                                                        "sub_type": "unlock",
                                                        "result": "success",
                                                        "reason":"object.door.unlock"
                                                        })
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
        if not self.door_blocking:
            return False

        return bool(self.map.entity_at(*self.position()))

    def on_take_damage(self, battle, damage_params):
        pass

    def setup_other_attributes(self):
        self.state = self.properties.get("state", "closed")
        self.locked = self.properties.get("locked")
        self.key_name = self.properties.get("key")

    def update_state(self, state):
        if state == "opened":
            self.open()
        elif state == "closed":
            self.close()
        elif state == "unconcealed":
            self.is_concealed = False
        elif state == "concealed":
            self.is_concealed = True
        else:
            raise ValueError("Invalid state for door object: %s" % state)

class DoorObjectWall(DoorObject, StoneWallDirectional):
    def __init__(self, session, map, properties):
        DoorObject.__init__(self, session, map, properties)
        StoneWallDirectional.__init__(self, session, map, properties)
        self.door_pos = self.properties.get("door_pos", 0)
        self.window = self.properties.get("window", [0, 0, 0, 0])
        self.is_secret = self.properties.get("secret", False)

    def token(self):
        return StoneWallDirectional.token(self)

    def token_opened(self):
        return DoorObject.token_opened(self)

    def token_closed(self):
        return DoorObject.token_closed(self)

    def token_image_transform(self):
        return StoneWallDirectional.token_image_transform(self)

    def opaque(self, origin=None):
        pos_x, pos_y = self.map.position_of(self)

        def check_door_opaque():
            if self.opened():
                return False

            if self.door_pos == 0 and origin[1] < pos_y:
                return True
            if self.door_pos == 1 and origin[0] > pos_x:
                return True
            if self.door_pos == 2 and origin[1] > pos_y:
                return True
            if self.door_pos == 3 and origin[0] < pos_x:
                return True

            return False

        def check_window_opaque():
            if self.window[0] and origin[1] < pos_y:
                return False
            if self.window[1] and origin[0] > pos_x:
                return False
            if self.window[2] and origin[1] > pos_y:
                return False
            if self.window[3] and origin[0] < pos_x:
                return False
            return True

        wall_opaque = StoneWallDirectional.opaque(self, origin=origin)
        pos_x, pos_y = self.map.position_of(self)
        # handle windows
        window_opaque = check_window_opaque()
        door_opaque = check_door_opaque()

        if not window_opaque:
            return False

        if not wall_opaque and door_opaque:
            return True

        return wall_opaque

    def unlock(self):
        return DoorObject.unlock(self)

    def lock(self):
        return DoorObject.lock(self)

    def passable(self, origin_pos = None):
        wall_passable = StoneWallDirectional.passable(self, origin_pos)

        if origin_pos is None:
            return wall_passable

        if wall_passable:
            if self.opened():
                return True

            pos_x, pos_y = self.map.position_of(self)
            if self.door_pos == 0 and origin_pos[1] < pos_y:
                return False
            if self.door_pos == 1 and origin_pos[0] > pos_x:
                return False
            if self.door_pos == 2 and origin_pos[1] > pos_y:
                return False
            if self.door_pos == 3 and origin_pos[0] < pos_x:
                return False

            return True

        return False

    def closed(self):
        return DoorObject.closed(self)

    def opened(self):
        return DoorObject.opened(self)

    def open(self):
        return DoorObject.open(self)

    def close(self):
        return DoorObject.close(self)

    def available_interactions(self, entity, battle=None, admin=False):
        if self.is_secret:
            return {}
        return DoorObject.available_interactions(self, entity, battle, admin=admin)

    def interactable(self, entity=None):
        return DoorObject.interactable(self, entity)

    def resolve(self, entity, action, other_params, opts=None):
        return DoorObject.resolve(self, entity, action, other_params, opts)

    def use(self, entity, result, session=None):
        return DoorObject.use(self, entity, result, session)

    def lockpick_dc(self):
        return DoorObject.lockpick_dc(self)

    def someone_blocking_the_doorway(self):
        return DoorObject.someone_blocking_the_doorway(self)

    def on_take_damage(self, battle, damage_params):
        return DoorObject.on_take_damage(self, battle, damage_params)

    def setup_other_attributes(self):
        return DoorObject.setup_other_attributes(self)