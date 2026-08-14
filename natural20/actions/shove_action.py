from natural20.action import Action
from natural20.utils.target_validation import clear_validation, has_validation_failures

# Unarmed / natural reach. Weapon Reach does not extend shove (Sage Advice).
SHOVE_REACH_FT = 5


def _skill_mod(entity, skill):
    getter = getattr(entity, f"{skill}_mod", None)
    if callable(getter):
        return int(getter() or 0)
    return 0


def _shove_reach_ft(entity):
    props = getattr(entity, "properties", None) or {}
    for key in ("natural_reach", "shove_reach"):
        value = props.get(key)
        if value is not None:
            try:
                return max(5, int(value))
            except (TypeError, ValueError):
                pass
    return SHOVE_REACH_FT


def _target_contest_check(target, battle):
    """Target chooses Athletics or Acrobatics; pick the better modifier (optimal RAW)."""
    if _skill_mod(target, "athletics") >= _skill_mod(target, "acrobatics"):
        return target.athletics_check(battle, description="die_roll.contest")
    return target.acrobatics_check(battle, description="die_roll.contest")


def _target_save(target, battle):
    """2024: target chooses Strength or Dexterity save; pick the better modifier."""
    str_mod = target.saving_throw_mod("strength")
    dex_mod = target.saving_throw_mod("dexterity")
    save_type = "strength" if str_mod >= dex_mod else "dexterity"
    return target.save_throw(save_type, battle)


def _grapple_shove_resolution(session):
    ruleset = getattr(session, "ruleset", None) if session else None
    if ruleset is None:
        return "contested_check"
    return ruleset.grapple_shove_resolution()


def _unarmed_save_dc(source):
    return 8 + int(source.str_mod()) + int(source.proficiency_bonus())


def _distance_ft(battle_map, source, target):
    if battle_map is None or source is None or target is None:
        return 0
    try:
        squares = battle_map.distance(source, target)
    except Exception:
        return 0
    feet_per_grid = getattr(battle_map, "feet_per_grid", 5) or 5
    return squares * feet_per_grid


class ShoveAction(Action):
    def __init__(self, session, source, action_type):
        super().__init__(session, source, action_type, {})
        self.target = None
        # Default matches the action button: shove = knock prone, push = 5 ft away.
        self.knock_prone = action_type != "push"

    @staticmethod
    def can(entity, battle, options=None):
        return battle is None or entity.total_actions(battle) > 0

    def label(self):
        return self.t(f"action.{self.action_type}")

    def validate(self, battle_map, target=None):
        clear_validation(self)
        if target is None:
            target = self.target

        if target is None:
            self.add_validation_issue("validation.targeting.required")
            return not has_validation_failures(self)
        if target is self.source:
            self.add_validation_issue("validation.targeting.self")
        if (target.size_identifier() - self.source.size_identifier()) > 1:
            self.add_validation_issue("validation.shove.invalid_target_size")
        reach_ft = _shove_reach_ft(self.source)
        distance_ft = _distance_ft(battle_map, self.source, target)
        if distance_ft > reach_ft:
            self.add_validation_issue(
                "validation.targeting.out_of_range",
                distance_ft=distance_ft,
                range_ft=reach_ft,
            )
        return not has_validation_failures(self)

    def __str__(self):
        return str(self.action_type).capitalize()

    def clone(self):
        action = type(self)(self.session, self.source, self.action_type)
        action.target = self.target
        action.knock_prone = self.knock_prone
        return action

    def to_h(self):
        data = super().to_h()
        data["knock_prone"] = bool(self.knock_prone)
        if self.target is not None:
            data["target"] = getattr(self.target, "entity_uid", self.target)
        return data

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
                    "range": _shove_reach_ft(self.source),
                    "target_types": ["enemies", "allies"],
                    "exclude_self": True,
                    "num": 1,
                }
            ],
            "next": set_target,
        }

    @staticmethod
    def build(session, source):
        action = ShoveAction(session, source, "shove")
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

        reach_ft = _shove_reach_ft(self.source)
        if map is not None and _distance_ft(map, self.source, target) > reach_ft:
            return

        source_roll = None
        target_roll = None
        save_dc = None
        shove_success = False
        resolution = _grapple_shove_resolution(session)

        if target.incapacitated():
            shove_success = True
        elif resolution == "target_saving_throw":
            save_dc = _unarmed_save_dc(self.source)
            target_roll = _target_save(target, battle)
            shove_success = target_roll.result() < save_dc
        else:
            source_roll = self.source.athletics_check(battle)
            target_roll = _target_contest_check(target, battle)
            # Contests: a tie leaves the situation unchanged (defender wins).
            shove_success = source_roll.result() > target_roll.result()

        shove_loc = None
        additional_effects = []
        if shove_success and map is not None and not self.knock_prone:
            source_pos = map.entity_or_object_pos(self.source) if self.source else None
            target_pos = map.entity_or_object_pos(target) if target else None
            if source_pos is not None and target_pos is not None:
                try:
                    shove_loc = target.push_from(map, *source_pos)
                except (ValueError, TypeError):
                    shove_loc = None
                if shove_loc == tuple(target_pos) or shove_loc == list(target_pos):
                    shove_loc = None
            if shove_loc:
                trigger_results = map.area_trigger(target, shove_loc, False)
                additional_effects += trigger_results

        if shove_success:
            self.result = [{
                "source": self.source,
                "target": target,
                "type": "shove",
                "success": True,
                "battle": battle,
                "refresh_map": True,
                "map": map,
                "shove_loc": shove_loc,
                "knock_prone": self.knock_prone,
                "source_roll": source_roll,
                "target_roll": target_roll,
                "save_dc": save_dc,
            }] + additional_effects
        else:
            self.result = [{
                "source": self.source,
                "target": target,
                "type": "shove",
                "success": False,
                "battle": battle,
                "knock_prone": self.knock_prone,
                "source_roll": source_roll,
                "target_roll": target_roll,
                "save_dc": save_dc,
            }]
        return self

    @staticmethod
    def apply(battle, item, session=None):
        event_manager = battle.event_manager if battle else session.event_manager
        if item["type"] != "shove":
            return

        if item["target"].passive():
            item["target"].make_active()

        if item["success"]:
            if item["knock_prone"]:
                item["target"].do_prone()
            elif item.get("shove_loc"):
                target_map = item.get("map")
                dest = item["shove_loc"]
                if target_map is not None and dest:
                    occupied = target_map.entity_at(*dest)
                    if occupied is None or occupied is item["target"]:
                        still_on_map = False
                        try:
                            still_on_map = target_map.entity_or_object_pos(item["target"]) is not None
                        except Exception:
                            still_on_map = False
                        if still_on_map:
                            target_map.move_to(item["target"], *dest, battle)
            event_manager.received_event(
                {
                    "event": "shove",
                    "success": True,
                    "target": item["target"],
                    "source": item["source"],
                    "shove_loc": item.get("shove_loc"),
                    "knock_prone": item.get("knock_prone"),
                    "source_roll": item.get("source_roll"),
                    "target_roll": item.get("target_roll"),
                    "save_dc": item.get("save_dc"),
                }
            )
        else:
            event_manager.received_event(
                {
                    "event": "shove",
                    "success": False,
                    "target": item["target"],
                    "source": item["source"],
                    "knock_prone": item.get("knock_prone"),
                    "source_roll": item.get("source_roll"),
                    "target_roll": item.get("target_roll"),
                    "save_dc": item.get("save_dc"),
                }
            )
        if battle:
            battle.consume(item["source"], "action")


class PushAction(ShoveAction):
    def __init__(self, session, source, action_type="push"):
        super().__init__(session, source, action_type or "push")
        self.knock_prone = False

    @staticmethod
    def build(session, source):
        action = PushAction(session, source, "push")
        return action.build_map()
