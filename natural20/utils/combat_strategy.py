"""Strategic callout options derived from the current combat picture.

A decision-only model (JEV) cannot write speech, but it can pick *what* to
tell its allies from a short menu. ``strategy_options`` builds that menu from
what the speaker can perceive: wounded allies, the weakest or most dangerous
visible enemy, enemies pressing a downed or wounded ally, the side's overall
standing. Each option is a dict::

    {'kind': 'focus'|'heal'|'help'|'warn'|'retreat'|'protect'|'taunt'|'revive'|'regroup'|None,
     'target': <entity or None>,
     'intent': 'short reason in plain words',
     'desc': 'menu line shown to the decision model'}

``kind: None`` is "stay silent" and is always the first option. Options are
limited to callout kinds the speaker's wits allow (``combat_intelligence``)
and to targets it can see, so the menu never leaks hidden information.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from natural20.utils import combat_intelligence

SILENT = {'kind': None, 'target': None, 'intent': 'stay silent',
          'desc': 'stay silent (no callout this turn)'}

WOUNDED = 0.35
HURT = 0.5
DEFAULT_MAX_OPTIONS = 8


def _name(entity) -> str:
    try:
        label = entity.label() if callable(getattr(entity, 'label', None)) else None
    except Exception:
        label = None
    return str(label or getattr(entity, 'name', None) or entity)


def _hp_fraction(entity) -> float:
    try:
        mx = entity.max_hp() or 0
        return (entity.hp() or 0) / mx if mx else 1.0
    except Exception:
        return 1.0


def _pct(entity) -> str:
    return f"{int(round(_hp_fraction(entity) * 100))}% hp"


def _down(entity) -> bool:
    try:
        return bool(entity.dead() or entity.unconscious())
    except Exception:
        return False


def _fallen(entity) -> bool:
    """Unconscious but still alive, so healing or stabilizing can save them."""
    try:
        return bool(entity.unconscious() and not entity.dead())
    except Exception:
        return False


def _dist_ft(battle, a, b) -> Optional[float]:
    try:
        m = battle.map_for(a)
        return m.distance(a, b) * (m.feet_per_grid or 5)
    except Exception:
        return None


def _visible(battle, speaker, entity) -> bool:
    try:
        return bool(battle.can_see(speaker, entity))
    except Exception:
        return False


def _action_target(battle, speaker, action):
    if action is None:
        return None
    t = getattr(action, 'target', None)
    targets = list(t) if isinstance(t, (list, tuple)) else ([t] if t is not None else [])
    for e in targets:
        if not hasattr(e, 'entity_uid'):
            continue
        try:
            if battle.opposing(speaker, e):
                return e
        except Exception:
            continue
    return None


def _can_heal_others(battle, ally) -> bool:
    """A conscious ally with a healing spell it can still cast, Lay on Hands,
    or a healing potion to administer."""
    try:
        if _down(ally):
            return False
        if ally.class_feature('lay_on_hands'):
            return True
        # No battle: off-turn action economy shouldn't hide a healer.
        for details in (ally.spell_list(None) or {}).values():
            if not details.get('disabled') and str(details.get('type') or '').lower() == 'healing':
                return True
        session = getattr(ally, 'session', None)
        for item in ally.inventory_items(session) if hasattr(ally, 'inventory_items') else []:
            if 'healing' in str(item.get('name') or item.get('type') or '').lower():
                return True
    except Exception:
        return True
    return False


def _side_strength(group) -> float:
    return sum(_hp_fraction(e) for e in group if not _down(e))


def strategy_options(battle, speaker, action=None,
                     name_fn: Optional[Callable[[Any], str]] = None,
                     max_options: int = DEFAULT_MAX_OPTIONS) -> List[Dict[str, Any]]:
    """Callout options for *speaker* this turn (first option is always silence)."""
    name = name_fn or _name
    try:
        allies = [a for a in battle.allies_of(speaker) if a is not speaker]
        enemies = [e for e in battle.opponents_of(speaker) if not _down(e)]
    except Exception:
        return [dict(SILENT)]
    seen_enemies = [e for e in enemies if _visible(battle, speaker, e)]
    seen_allies = [a for a in allies if _visible(battle, speaker, a)]

    options: List[Dict[str, Any]] = []

    def add(kind, target, intent, desc):
        if not combat_intelligence.allowed_callout_kind(speaker, kind):
            return
        key = (kind, getattr(target, 'entity_uid', None))
        if any((o['kind'], getattr(o['target'], 'entity_uid', None)) == key for o in options):
            return
        options.append({'kind': kind, 'target': target, 'intent': intent, 'desc': desc})

    from natural20.utils.combat_comms import ally_focus_target
    called_focus = ally_focus_target(battle, speaker)

    my_hp = _hp_fraction(speaker)
    if my_hp <= HURT and any(_can_heal_others(battle, a) for a in allies):
        add('heal', None, f"I am badly hurt ({_pct(speaker)}) and need healing",
            f"call for healing (you are at {_pct(speaker)})")

    # Fallen allies come before damage calls: a downed ally is losing the fight.
    fallen = [a for a in seen_allies if _fallen(a)]
    for ally in fallen[:2]:
        add('revive', ally, f"get {name(ally)} back up before they die",
            f"urge allies to revive the fallen {name(ally)}")
    ours = _side_strength([speaker] + allies)
    theirs = _side_strength(enemies)
    outmatched = theirs > 0 and ours < theirs * 0.5
    if fallen and not outmatched:
        add('regroup', None, "regroup and cover the fallen",
            f"order allies to regroup around the fallen ({len(fallen)} down)")

    # With a single foe everyone is already fighting it; focus fire says nothing.
    many_foes = len(enemies) > 1

    attacking = _action_target(battle, speaker, action)
    if many_foes and attacking is not None and attacking is not called_focus:
        add('focus', attacking, f"everyone attack {name(attacking)}, the enemy I am attacking",
            f"call focus fire on {name(attacking)} ({_pct(attacking)}, your target this turn)")

    if seen_enemies and many_foes:
        weakest = min(seen_enemies, key=_hp_fraction)
        if weakest is not called_focus and _hp_fraction(weakest) <= HURT:
            add('focus', weakest, f"finish off {name(weakest)}, the most wounded enemy",
                f"call focus fire on {name(weakest)} (most wounded enemy, {_pct(weakest)})")

        threat_counts: Dict[int, int] = {}
        for ally in allies + [speaker]:
            attacker = combat_intelligence.last_attacker(battle, ally)
            if attacker is not None and any(attacker is e for e in seen_enemies):
                threat_counts[id(attacker)] = threat_counts.get(id(attacker), 0) + 1
        if threat_counts:
            threat = max(seen_enemies, key=lambda e: threat_counts.get(id(e), 0))
            hits = threat_counts.get(id(threat), 0)
            if hits >= 2 and many_foes and threat is not called_focus:
                add('focus', threat, f"take down {name(threat)}, who keeps hitting us",
                    f"call focus fire on {name(threat)} (attacked {hits} of your side)")

    wounded_allies = sorted((a for a in seen_allies if not _down(a) and _hp_fraction(a) <= WOUNDED),
                            key=_hp_fraction)
    for ally in wounded_allies[:2]:
        add('protect', ally, f"protect {name(ally)}, who is close to falling",
            f"tell allies to protect {name(ally)} ({_pct(ally)})")
        for enemy in seen_enemies:
            d = _dist_ft(battle, ally, enemy)
            if d is not None and d <= 5:
                add('warn', enemy, f"warn that {name(enemy)} is on the wounded {name(ally)}",
                    f"warn allies that {name(enemy)} is next to {name(ally)}")
                break
        if my_hp >= 0.6 and seen_enemies:
            nearest = min(seen_enemies, key=lambda e: _dist_ft(battle, ally, e) or 999)
            add('taunt', nearest, f"draw {name(nearest)}'s attacks away from {name(ally)}",
                f"taunt {name(nearest)} to draw it off {name(ally)}")

    if my_hp <= HURT:
        for enemy in seen_enemies:
            d = _dist_ft(battle, speaker, enemy)
            if d is not None and d <= 5:
                add('help', enemy, f"I need help against {name(enemy)}",
                    f"ask allies for help against {name(enemy)} (it is on you)")
                break

    if outmatched:
        add('retreat', None, "we are losing; fall back",
            f"order a retreat (your side is outmatched: {ours:.1f} vs {theirs:.1f} effective strength)")

    return [dict(SILENT)] + options[:max(0, max_options - 1)]


def default_choice(battle, speaker, options: List[Dict[str, Any]], action=None) -> Optional[Dict[str, Any]]:
    """Deterministic pick when no decision model is available.

    Calls for healing when nearly down, then for reviving a fallen ally,
    otherwise announces the enemy being attacked; anything else stays silent.
    """
    if _hp_fraction(speaker) <= 0.25:
        for o in options:
            if o['kind'] == 'heal':
                return o
    for o in options:
        if o['kind'] == 'revive':
            return o
    attacking = _action_target(battle, speaker, action)
    for o in options:
        if o['kind'] == 'focus' and attacking is not None and o['target'] is attacking:
            return o
    return None
