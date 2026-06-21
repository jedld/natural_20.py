"""D&D 5e 2014 experience and level progression helpers."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable, Mapping, Sequence


XP_THRESHOLDS_BY_LEVEL = {
    1: 0,
    2: 300,
    3: 900,
    4: 2700,
    5: 6500,
    6: 14000,
    7: 23000,
    8: 34000,
    9: 48000,
    10: 64000,
    11: 85000,
    12: 100000,
    13: 120000,
    14: 140000,
    15: 165000,
    16: 195000,
    17: 225000,
    18: 265000,
    19: 305000,
    20: 355000,
}

PROFICIENCY_BONUS_BY_LEVEL = {
    1: 2,
    2: 2,
    3: 2,
    4: 2,
    5: 3,
    6: 3,
    7: 3,
    8: 3,
    9: 4,
    10: 4,
    11: 4,
    12: 4,
    13: 5,
    14: 5,
    15: 5,
    16: 5,
    17: 6,
    18: 6,
    19: 6,
    20: 6,
}

CR_XP = {
    Fraction(0, 1): 10,
    Fraction(1, 8): 25,
    Fraction(1, 4): 50,
    Fraction(1, 2): 100,
    Fraction(1, 1): 200,
    Fraction(2, 1): 450,
    Fraction(3, 1): 700,
    Fraction(4, 1): 1100,
    Fraction(5, 1): 1800,
    Fraction(6, 1): 2300,
    Fraction(7, 1): 2900,
    Fraction(8, 1): 3900,
    Fraction(9, 1): 5000,
    Fraction(10, 1): 5900,
    Fraction(11, 1): 7200,
    Fraction(12, 1): 8400,
    Fraction(13, 1): 10000,
    Fraction(14, 1): 11500,
    Fraction(15, 1): 13000,
    Fraction(16, 1): 15000,
    Fraction(17, 1): 18000,
    Fraction(18, 1): 20000,
    Fraction(19, 1): 22000,
    Fraction(20, 1): 25000,
    Fraction(21, 1): 33000,
    Fraction(22, 1): 41000,
    Fraction(23, 1): 50000,
    Fraction(24, 1): 62000,
    Fraction(25, 1): 75000,
    Fraction(26, 1): 90000,
    Fraction(27, 1): 105000,
    Fraction(28, 1): 120000,
    Fraction(29, 1): 135000,
    Fraction(30, 1): 155000,
}

ENCOUNTER_XP_MULTIPLIERS = (
    (1, 1.0),
    (2, 1.5),
    (6, 2.0),
    (10, 2.5),
    (14, 3.0),
    (float("inf"), 4.0),
)

ENCOUNTER_DIFFICULTY_THRESHOLDS = {
    1: {"easy": 25, "medium": 50, "hard": 75, "deadly": 100},
    2: {"easy": 50, "medium": 100, "hard": 150, "deadly": 200},
    3: {"easy": 75, "medium": 150, "hard": 225, "deadly": 400},
    4: {"easy": 125, "medium": 250, "hard": 375, "deadly": 500},
    5: {"easy": 250, "medium": 500, "hard": 750, "deadly": 1100},
    6: {"easy": 300, "medium": 600, "hard": 900, "deadly": 1400},
    7: {"easy": 350, "medium": 750, "hard": 1100, "deadly": 1700},
    8: {"easy": 450, "medium": 900, "hard": 1400, "deadly": 2100},
    9: {"easy": 550, "medium": 1100, "hard": 1600, "deadly": 2400},
    10: {"easy": 600, "medium": 1200, "hard": 1900, "deadly": 2800},
    11: {"easy": 800, "medium": 1600, "hard": 2400, "deadly": 3600},
    12: {"easy": 1000, "medium": 2000, "hard": 3000, "deadly": 4500},
    13: {"easy": 1100, "medium": 2200, "hard": 3400, "deadly": 5100},
    14: {"easy": 1250, "medium": 2500, "hard": 3800, "deadly": 5700},
    15: {"easy": 1400, "medium": 2800, "hard": 4300, "deadly": 6400},
    16: {"easy": 1600, "medium": 3200, "hard": 4800, "deadly": 7200},
    17: {"easy": 2000, "medium": 3900, "hard": 5900, "deadly": 8800},
    18: {"easy": 2100, "medium": 4200, "hard": 6300, "deadly": 9500},
    19: {"easy": 2400, "medium": 4900, "hard": 7300, "deadly": 10900},
    20: {"easy": 2800, "medium": 5700, "hard": 8500, "deadly": 12700},
}

PROGRESSION_MODE_XP = "xp"
PROGRESSION_MODE_DM = "dm"
PROGRESSION_MODE_EVENT = "event"
PROGRESSION_MODES = {
    PROGRESSION_MODE_XP,
    PROGRESSION_MODE_DM,
    PROGRESSION_MODE_EVENT,
}

DEFAULT_PROGRESSION_SETTINGS = {
    "mode": PROGRESSION_MODE_XP,
    "events": {},
}


@dataclass(frozen=True)
class XPAward:
    entity_uid: str
    old_xp: int
    new_xp: int
    amount: int
    old_level: int
    eligible_level: int

    @property
    def levels_available(self) -> int:
        return max(0, self.eligible_level - self.old_level)


def normalize_cr(cr) -> Fraction:
    if isinstance(cr, Fraction):
        return cr
    if isinstance(cr, str):
        raw = cr.strip()
        if "/" in raw:
            numerator, denominator = raw.split("/", 1)
            return Fraction(int(numerator), int(denominator))
        return Fraction(raw)
    return Fraction(cr).limit_denominator()


def xp_for_cr(cr) -> int:
    return CR_XP[normalize_cr(cr)]


def level_for_xp(xp: int) -> int:
    xp = max(0, int(xp or 0))
    level = 1
    for candidate, threshold in XP_THRESHOLDS_BY_LEVEL.items():
        if xp >= threshold:
            level = candidate
    return level


def xp_to_next_level(xp: int, current_level: int | None = None) -> int | None:
    level = current_level or level_for_xp(xp)
    if level >= 20:
        return None
    return max(0, XP_THRESHOLDS_BY_LEVEL[level + 1] - int(xp or 0))


def proficiency_bonus_for_level(level: int) -> int:
    return PROFICIENCY_BONUS_BY_LEVEL[max(1, min(20, int(level)))]


def hit_die_average(hit_die_sides: int) -> int:
    return int(hit_die_sides // 2 + 1)


def normalize_progression_settings(settings: Mapping | None) -> dict:
    """Return campaign progression settings with conservative defaults.

    Supported `game.yml` forms:

    progression:
      mode: xp      # default, D&D XP thresholds
      mode: dm      # DM grants level-up permissions
      mode: event   # named event grants level-up permissions
      events:
        goblin_king_defeated:
          levels: 1
          label: Defeated the Goblin King
    """
    normalized = dict(DEFAULT_PROGRESSION_SETTINGS)
    if isinstance(settings, str):
        normalized["mode"] = settings
        return normalized
    if isinstance(settings, Mapping):
        normalized.update(settings)
    mode = str(normalized.get("mode") or PROGRESSION_MODE_XP).strip().lower()
    normalized["mode"] = mode if mode in PROGRESSION_MODES else PROGRESSION_MODE_XP
    events = normalized.get("events") or normalized.get("level_up_events") or {}
    if isinstance(events, Sequence) and not isinstance(events, (str, bytes, dict)):
        events = {str(event): {"levels": 1, "label": str(event)} for event in events}
    normalized["events"] = events if isinstance(events, Mapping) else {}
    return normalized


def monster_xp(monster) -> int:
    props = getattr(monster, "properties", None) or {}
    if props.get("xp") is not None:
        return int(props.get("xp") or 0)
    if props.get("cr") is not None:
        return xp_for_cr(props.get("cr"))
    return 0


def encounter_xp(monsters: Iterable) -> int:
    return sum(monster_xp(monster) for monster in monsters)


def encounter_multiplier(monster_count: int, party_size: int | None = None) -> float:
    monster_count = max(0, int(monster_count or 0))
    if monster_count <= 0:
        return 0.0
    multiplier = 1.0
    for limit, value in ENCOUNTER_XP_MULTIPLIERS:
        if monster_count <= limit:
            multiplier = value
            break
    if party_size is not None:
        party_size = int(party_size or 0)
        if party_size < 3:
            multiplier = next_higher_multiplier(multiplier)
        elif party_size >= 6:
            multiplier = next_lower_multiplier(multiplier)
    return multiplier


def next_higher_multiplier(multiplier: float) -> float:
    values = [value for _, value in ENCOUNTER_XP_MULTIPLIERS]
    for value in values:
        if value > multiplier:
            return value
    return values[-1]


def next_lower_multiplier(multiplier: float) -> float:
    values = [value for _, value in ENCOUNTER_XP_MULTIPLIERS]
    previous = values[0]
    for value in values:
        if value >= multiplier:
            return previous
        previous = value
    return previous


def adjusted_encounter_xp(monsters: Sequence, party_size: int | None = None) -> int:
    base = encounter_xp(monsters)
    return int(base * encounter_multiplier(len(monsters), party_size))


def split_xp(total_xp: int, recipients: Sequence, split: bool = True) -> dict[str, int]:
    if not recipients:
        return {}
    total_xp = max(0, int(total_xp or 0))
    if not split:
        return {recipient.entity_uid: total_xp for recipient in recipients}
    share, remainder = divmod(total_xp, len(recipients))
    awards = {}
    for index, recipient in enumerate(recipients):
        awards[recipient.entity_uid] = share + (1 if index < remainder else 0)
    return awards


def party_difficulty_thresholds(levels: Iterable[int]) -> dict[str, int]:
    totals = {"easy": 0, "medium": 0, "hard": 0, "deadly": 0}
    for level in levels:
        thresholds = ENCOUNTER_DIFFICULTY_THRESHOLDS[max(1, min(20, int(level)))]
        for key, value in thresholds.items():
            totals[key] += value
    return totals


def encounter_difficulty(adjusted_xp: int, levels: Iterable[int]) -> str:
    thresholds = party_difficulty_thresholds(levels)
    adjusted_xp = int(adjusted_xp or 0)
    if adjusted_xp >= thresholds["deadly"]:
        return "deadly"
    if adjusted_xp >= thresholds["hard"]:
        return "hard"
    if adjusted_xp >= thresholds["medium"]:
        return "medium"
    if adjusted_xp >= thresholds["easy"]:
        return "easy"
    return "trivial"


def award_xp_to_character(character, amount: int, source: str = "manual",
                          reason: str | None = None) -> XPAward:
    old_xp = character.experience()
    old_level = character.level()
    character.add_experience(amount, source=source, reason=reason)
    new_xp = character.experience()
    return XPAward(
        entity_uid=character.entity_uid,
        old_xp=old_xp,
        new_xp=new_xp,
        amount=max(0, int(amount or 0)),
        old_level=old_level,
        eligible_level=level_for_xp(new_xp),
    )


def validate_npc_xp(npc_props: Mapping) -> dict | None:
    if not npc_props or npc_props.get("cr") is None or npc_props.get("xp") is None:
        return None
    expected = xp_for_cr(npc_props["cr"])
    actual = int(npc_props["xp"])
    if expected == actual:
        return None
    return {"cr": npc_props["cr"], "expected_xp": expected, "actual_xp": actual}
