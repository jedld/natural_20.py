"""Hostile persistent-zone context for battle AI prompts."""

from __future__ import annotations

from typing import List

_ZONE_SAVES = {
    "cloud_of_daggers": "dexterity",
    "flaming_sphere": "dexterity",
    "grease": "dexterity",
    "hunger_of_hadar": "constitution",
    "sleet_storm": "dexterity",
    "spike_growth": "wisdom",
    "spirit_guardians": "wisdom",
    "stinking_cloud": "constitution",
    "web": "dexterity",
}

_ZONE_EFFECTS = {
    "cloud_of_daggers": "damage on failed save",
    "flaming_sphere": "damage when ending a turn nearby",
    "grease": "prone on failed save",
    "hunger_of_hadar": "damage and blinded on failed save",
    "silence": "blocks speech and verbal spells",
    "sleet_storm": "prone on failed save",
    "spike_growth": "damage per step moved",
    "spirit_guardians": "damage on entering or starting a turn",
    "stinking_cloud": "loses an action on failed save",
    "web": "restrained on failed save",
}


def _props(zone) -> dict:
    spell = getattr(zone, "spell", None)
    if isinstance(spell, dict):
        return spell
    props = getattr(spell, "properties", None)
    return props if isinstance(props, dict) else {}


def _label(zone) -> str:
    props = _props(zone)
    label = props.get("label") or props.get("name") or getattr(zone, "name", None) or "hazard"
    label = str(label)
    if "_" in label:
        label = label.replace("_", " ").strip()
        if label and label[0].islower():
            label = label.title()
    return label


def _squares(zone) -> List[tuple]:
    squares = list(getattr(zone, "squares", None) or [])
    if squares:
        return [tuple(s) for s in squares]

    area = getattr(zone, "area", None)
    if callable(area):
        try:
            squares = [tuple(s) for s in list(area() or [])]
            if squares:
                return squares
        except Exception:
            pass

    center = getattr(zone, "center", None)
    if center is not None:
        try:
            return [tuple(center)]
        except Exception:
            pass
    return []


def _extent_text(zone) -> str:
    props = _props(zone)
    radius_ft = getattr(zone, "radius_ft", None)
    if radius_ft:
        return f"{radius_ft} ft radius"

    name = str(getattr(zone, "name", ""))
    if name == "flaming_sphere":
        return "5 ft threat"

    radius = props.get("radius")
    if radius:
        shape = str(getattr(zone, "shape", "radius"))
        if shape in ("radius", "sphere", "emanation"):
            return f"{radius} ft radius"

    area_size = props.get("area_size")
    if area_size:
        shape = str(getattr(zone, "shape", ""))
        if shape in ("square", "cube"):
            return f"{area_size} ft {shape}"
    return ""


def _details(zone) -> str:
    props = _props(zone)
    name = str(getattr(zone, "name", ""))
    parts = []

    extent = _extent_text(zone)
    if extent:
        parts.append(extent)

    dice = getattr(zone, "dice", None) or getattr(zone, "damage_dice", None)
    damage_type = getattr(zone, "damage_type", None) or props.get("damage_type")
    if dice and damage_type:
        parts.append(f"{dice} {damage_type}")
    elif dice:
        parts.append(str(dice))

    dc = getattr(zone, "dc", None)
    save = props.get("save_type") or props.get("save") or _ZONE_SAVES.get(name)
    if dc is not None:
        parts.append(f"DC{dc} {save} save" if save else f"DC{dc} save")

    effect = _ZONE_EFFECTS.get(name)
    if effect:
        parts.append(effect)

    return ", ".join(parts)


def _inside_names(zone, battle, entity, m) -> List[str]:
    try:
        allies = list(battle.allies_of(entity))
    except Exception:
        allies = []

    names = []
    for other in [entity] + allies:
        if other is None:
            continue
        try:
            dead = getattr(other, "dead", None)
            if callable(dead) and dead():
                continue
            if hasattr(zone, "entity_within_reach"):
                inside = bool(zone.entity_within_reach(other))
            else:
                squares = []
                if m is not None:
                    try:
                        squares = m.entity_squares(other)
                    except Exception:
                        squares = []
                if not squares:
                    pos = getattr(m, "position_of", None)
                    if callable(pos):
                        try:
                            p = pos(other)
                            squares = [tuple(p)] if p else []
                        except Exception:
                            squares = []
                inside = any(zone.contains(s) for s in squares)
            if inside:
                names.append(other.name)
        except Exception:
            continue
    return names


def _is_visible(m, entity, squares) -> bool:
    if m is None:
        return True
    for s in squares[:6]:
        try:
            if m.can_see_square(entity, s):
                return True
        except Exception:
            continue
    return False


def hostile_hazard_lines(battle, entity, map_=None, limit: int = 4) -> List[str]:
    """Return short lines describing hostile persistent zones the entity can see."""
    if battle is None or entity is None:
        return []

    m = map_
    if m is None:
        try:
            m = battle.map_for(entity)
        except Exception:
            m = None

    zones = list(getattr(battle, "active_zones", None) or [])
    if not zones and m is not None:
        zones.extend(list(getattr(m, "environment_zones", None) or []))

    lines = []
    for zone in zones:
        try:
            if getattr(zone, "_dismissed", False):
                continue
            expired = getattr(zone, "expired", None)
            if callable(expired) and expired():
                continue

            owner = getattr(zone, "owner", None)
            if owner is None:
                owner = getattr(zone, "source", None)
            if owner is None or owner is entity:
                continue
            if not battle.opposing(owner, entity):
                continue

            squares = _squares(zone)
            if not squares:
                continue
            if not _is_visible(m, entity, squares):
                continue

            pos = getattr(zone, "center", None) or squares[0]
            pos = tuple(pos)
            text = f"{_label(zone)} at {pos}"

            parts = []
            if m is not None:
                try:
                    feet = int(
                        m.distance_to_square(entity, pos[0], pos[1])
                        * (getattr(m, "feet_per_grid", 5) or 5)
                    )
                    parts.append(f"{feet} ft")
                except Exception:
                    pass

            details = _details(zone)
            if details:
                parts.append(details)

            inside = _inside_names(zone, battle, entity, m)
            if inside:
                parts.append("inside: " + ", ".join(inside))

            if parts:
                text += " (" + ", ".join(parts) + ")"
            lines.append(text)
            if len(lines) >= limit:
                break
        except Exception:
            continue

    return lines
