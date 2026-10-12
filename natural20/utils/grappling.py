"""Shared grappler-side grapple rules (PHB 2014 / 2024).

* Dragging or carrying a grappled creature halves the grappler's speed (each
  square costs one extra square) unless the creature is two or more sizes
  smaller (2024 also exempts Tiny creatures).
* The grappler may release a grapple whenever it likes (no action required).
* The grapple ends when the grappler is incapacitated, the grappled creature
  dies, or the creature ends up out of the grappler's reach.
"""

from __future__ import annotations

from typing import List, Optional


def _phb_2024(entity) -> bool:
    session = getattr(entity, 'session', None)
    ruleset = getattr(session, 'ruleset', None) if session is not None else None
    try:
        return bool(ruleset.phb_2024_grapple_move_cost()) if ruleset is not None else False
    except Exception:
        return False


def drag_slows(grappler, target, phb_2024_rules: Optional[bool] = None) -> bool:
    """True when moving with ``target`` in tow costs the grappler extra movement."""
    if phb_2024_rules is None:
        phb_2024_rules = _phb_2024(grappler)
    try:
        if phb_2024_rules and target.size() == 'tiny':
            return False
        return target.size_identifier() - grappler.size_identifier() >= -1
    except Exception:
        return True


def dragged_targets_slowing(grappler, phb_2024_rules: Optional[bool] = None) -> List:
    if not grappler.is_grappling():
        return []
    return [t for t in grappler.grappling_targets() if drag_slows(grappler, t, phb_2024_rules)]


def drag_penalty(grappler, phb_2024_rules: Optional[bool] = None) -> bool:
    """True when the grappler's speed is halved by what it is holding."""
    return bool(dragged_targets_slowing(grappler, phb_2024_rules))


def drag_cost_multiplier(grappler) -> int:
    """Movement cost multiplier per square (2 while dragging, else 1)."""
    try:
        return 2 if drag_penalty(grappler) else 1
    except Exception:
        return 1


def release(grappler, target, battle=None, reason: Optional[str] = None) -> None:
    """Free release of ``target`` (no action) with a combat-log event."""
    if target not in grappler.grappling_targets() and grappler not in getattr(target, 'grapples', []):
        return
    if hasattr(target, 'escape_grapple_from'):
        target.escape_grapple_from(grappler)
    else:
        grappler.ungrapple(target)
    session = getattr(grappler, 'session', None) or getattr(battle, 'session', None)
    em = getattr(grappler, 'event_manager', None) or getattr(session, 'event_manager', None)
    if em is not None:
        event = {'event': 'drop_grapple', 'source': grappler, 'target': target}
        if reason:
            event['reason'] = reason
        try:
            em.received_event(event)
        except Exception:
            pass


def _out_of_reach(grappler, target, battle) -> bool:
    if battle is None:
        return False
    try:
        m_src = battle.map_for(grappler)
        m_tgt = battle.map_for(target)
        if m_src is None or m_tgt is None:
            return False
        if m_src is not m_tgt:
            return True
        reach_ft = max(5, int(grappler.melee_distance() or 5))
        return m_src.distance(grappler, target) * m_src.feet_per_grid > reach_ft
    except Exception:
        return False


def prune_invalid_grapples(entity, battle=None) -> List:
    """Release grapples the rules say have ended. Returns released targets."""
    released = []
    if not entity.is_grappling():
        return released
    incapacitated = False
    try:
        incapacitated = entity.incapacitated()
    except Exception:
        pass
    for target in list(entity.grappling_targets()):
        reason = None
        if incapacitated:
            reason = 'grappler incapacitated'
        elif target.dead():
            reason = 'target died'
        elif _out_of_reach(entity, target, battle):
            reason = 'out of reach'
        if reason:
            release(entity, target, battle, reason=reason)
            released.append(target)
    return released


def ai_release_candidates(entity, battle) -> List:
    """Held creatures a combat AI has no reason to keep holding.

    Holding a dead, unconscious, or non-hostile creature only halves our speed.
    """
    out = []
    if not entity.is_grappling():
        return out
    for target in list(entity.grappling_targets()):
        try:
            if target.dead() or target.unconscious():
                out.append(target)
                continue
            if battle is not None and not battle.opposing(entity, target):
                out.append(target)
        except Exception:
            continue
    return out


def grapple_status_text(entity) -> str:
    """One-line description for AI prompts (empty when not grappling/grappled)."""
    parts = []
    if entity.is_grappling():
        names = [getattr(t, 'name', '?') for t in entity.grappling_targets()]
        slowed = drag_penalty(entity)
        txt = f"grappling {', '.join(names)}"
        if slowed:
            txt += (" (moving drags them along: speed halved, each 5 ft costs 10 ft;"
                    " you may release the grapple for free, no action)")
        else:
            txt += " (small enough to carry at full speed; release is free)"
        parts.append(txt)
    grapplers = getattr(entity, 'grapples', None) or []
    if grapplers:
        names = [getattr(g, 'name', '?') for g in grapplers]
        parts.append(f"grappled by {', '.join(names)} (speed 0; escape uses your action)")
    return '; '.join(parts)
