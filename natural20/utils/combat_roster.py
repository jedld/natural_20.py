"""Combat log summaries at the start of a fight.

* DM roster (``visibility='dm'``): every combatant's full stats, plus each
  combatant's HP and condition at the start of its turn.
* Party briefing (scoped to the members of each team that has a player
  character): full stats for partymates and sidekicks, and a players'-eye
  description of the enemies the team can see (appearance, rough health,
  visible gear and conditions; never HP, AC or hidden traits).

Campaign switch in ``game.yml``::

    combat_log:
      dm_summary: true        # roster at start of combat (default true)
      dm_turn_status: true    # HP/AC/conditions at start of each turn (default true)
      party_briefing: true    # partymates + enemy descriptions for players (default true)
"""
from typing import Any, Dict, List, Optional

DEFAULT_SETTINGS = {'dm_summary': True, 'dm_turn_status': True, 'party_briefing': True}
DM_PREFIX = '[DM]'
PARTY_PREFIX = '[Party]'
FOE_PREFIX = '[Foes]'
_MAX_DESCRIPTION = 80
_NON_COMBAT_TYPES = {'container', 'gear', 'adventuring_gear', 'tool', 'tools',
                     'ammunition', 'consumable', 'food', 'trade_good', 'clothing'}


def settings_for(session) -> Dict[str, Any]:
    out = dict(DEFAULT_SETTINGS)
    props = getattr(session, 'game_properties', None) or {}
    raw = props.get('combat_log') if isinstance(props, dict) else None
    if isinstance(raw, bool):
        out = {k: raw for k in out}
    elif isinstance(raw, dict):
        out.update({k: bool(v) for k, v in raw.items() if k in DEFAULT_SETTINGS})
    return out


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def _name(entity) -> str:
    return _safe(entity.label, None) or getattr(entity, 'name', None) or '?'


def hp_text(entity) -> str:
    hp = _safe(entity.hp, 0) or 0
    max_hp = _safe(entity.max_hp, None)
    text = f"HP {hp}/{max_hp}" if max_hp else f"HP {hp}"
    temp = _safe(entity.temp_hp, 0) or 0
    if temp:
        text += f" (+{temp} temp)"
    return text


def _short(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    text = ' '.join(str(text).split())
    if len(text) > _MAX_DESCRIPTION:
        text = text[:_MAX_DESCRIPTION - 1].rstrip() + '…'
    return text


def item_summary(item: Dict[str, Any]) -> str:
    """``Longbow (1d8 piercing, range 150/600)``, ``Chain Mail (AC 16)``,
    ``Shield (+2 AC)``, or the label plus a short description."""
    label = item.get('label') or str(item.get('name') or '?').replace('_', ' ').title()
    bits: List[str] = []
    if item.get('damage'):
        dmg = f"{item['damage']} {item.get('damage_type') or ''}".strip()
        if item.get('damage_2'):
            dmg += f", versatile {item['damage_2']}"
        bits.append(dmg)
        if item.get('range_max'):
            bits.append(f"range {item.get('range')}/{item['range_max']}")
        elif item.get('range') and int(item.get('range') or 5) > 5:
            bits.append(f"reach {item['range']}")
    if item.get('ac'):
        bits.append(f"AC {item['ac']}")
    if item.get('bonus_ac'):
        bits.append(f"+{item['bonus_ac']} AC")
    if not bits:
        desc = _short(item.get('description'))
        if desc:
            bits.append(desc)
    return f"{label} ({'; '.join(bits)})" if bits else label


def _combat_relevant(item: Dict[str, Any]) -> bool:
    if item.get('damage') or item.get('ac') or item.get('bonus_ac'):
        return True
    return str(item.get('type') or '').lower() not in _NON_COMBAT_TYPES


def gear_summary(entity) -> List[str]:
    """Equipped weapons, armor and other combat-relevant items (packs and
    tools are left out)."""
    return [item_summary(i) for i in (_safe(entity.equipped_items, []) or [])
            if _combat_relevant(i)]


def attack_summary(entity) -> List[str]:
    """NPC stat-block actions (to-hit and damage) usable with current gear."""
    actions = getattr(entity, 'npc_actions', None) or []
    equipped = set((getattr(entity, 'properties', None) or {}).get('equipped') or [])
    out: List[str] = []
    for spec in actions:
        if not isinstance(spec, dict) or not spec.get('name'):
            continue
        cond = str(spec.get('if') or '')
        if cond.startswith('equipped:') and cond.split(':', 1)[1] not in equipped:
            continue
        bits = []
        if spec.get('attack') is not None:
            bits.append(f"+{spec['attack']}")
        die = spec.get('damage_die')
        if die:
            mod = spec.get('damage_mod')
            if mod and '+' not in str(die) and '-' not in str(die):
                die = f"{die}+{mod}"
            bits.append(f"{die} {spec.get('damage_type') or ''}".strip())
        name = str(spec.get('label') or spec['name']).replace('_', ' ')
        out.append(f"{name} ({', '.join(bits)})" if bits else name)
    return out


def condition_summary(battle, entity) -> List[str]:
    """Conditions, concentration, buffs, defenses and limited defensive
    resources (Legendary Resistance)."""
    parts: List[str] = []
    try:
        from natural20.utils.jev_decision import _active_buffs, _creature_details
        details = _creature_details(battle, entity)
        if details:
            parts.extend(p.strip() for p in details.split(',') if p.strip()
                         and 'temp hp' not in p)
        parts.extend(f"effect: {b}" for b in _active_buffs(entity))
    except Exception:
        pass
    try:
        from natural20.utils.monster_traits import legendary_resistance_max, legendary_resistance_remaining
        maximum = legendary_resistance_max(entity)
        if maximum:
            parts.append(f"legendary resistance {legendary_resistance_remaining(entity)}/{maximum}")
    except Exception:
        pass
    try:
        from natural20.utils import polymorph
        form = polymorph.current_form(entity)
        if form:
            parts.append(f"in beast form: {form}")
    except Exception:
        pass
    return list(dict.fromkeys(parts))


def _group(battle, entity) -> str:
    state = _safe(lambda: battle.entity_state_for(entity), None) or {}
    return str(state.get('group') or '?')


def combatant_line(battle, entity, prefix: str = DM_PREFIX) -> str:
    state = _safe(lambda: battle.entity_state_for(entity), None) or {}
    head = f"{prefix} {_name(entity)}"
    descriptor = _safe(entity.class_descriptor, None)
    meta = [f"team {_group(battle, entity)}"]
    if state.get('initiative') is not None:
        meta.append(f"initiative {int(state['initiative'])}")
    head += f" ({descriptor}; {', '.join(meta)})" if descriptor else f" ({', '.join(meta)})"
    stats = [f"starting {hp_text(entity)}", f"AC {_safe(entity.armor_class, '?')}"]
    speed = _safe(entity.speed, None)
    if speed:
        stats.append(f"speed {speed} ft")
    pp = _safe(entity.passive_perception, None)
    if pp:
        stats.append(f"passive Perception {pp}")
    sections = [f"{head}: {', '.join(stats)}"]
    gear = gear_summary(entity)
    if gear:
        sections.append("gear: " + ", ".join(gear))
    attacks = attack_summary(entity)
    if attacks:
        sections.append("attacks: " + ", ".join(attacks))
    conditions = condition_summary(battle, entity)
    sections.append("conditions: " + (", ".join(conditions) if conditions else "none"))
    return " | ".join(sections)


def team_totals_line(battle, entities, prefix: str = DM_PREFIX) -> str:
    totals: Dict[str, List[int]] = {}
    for e in entities:
        bucket = totals.setdefault(_group(battle, e), [0, 0, 0])
        bucket[0] += int(_safe(e.hp, 0) or 0)
        bucket[1] += int(_safe(e.max_hp, 0) or 0)
        bucket[2] += 1
    parts = [f"team {g}: {hp}/{mx} HP across {n} combatant{'s' if n != 1 else ''}"
             for g, (hp, mx, n) in sorted(totals.items())]
    return f"{prefix} HP totals — " + "; ".join(parts)


def start_of_combat_lines(battle, combat_order=None) -> List[str]:
    """Team HP totals followed by one line per combatant in initiative order."""
    if battle is None or not settings_for(battle.session).get('dm_summary'):
        return []
    entities = [e for e, _ in (combat_order or [])] or list(getattr(battle, 'combat_order', None) or [])
    entities = [e for e in entities if not _safe(e.dead, False)]
    if not entities:
        return []
    return [team_totals_line(battle, entities)] + [combatant_line(battle, e) for e in entities]


def turn_status_line(battle, entity) -> Optional[str]:
    """``[DM] Strahd starts the turn at HP 120/144, AC 16 | conditions: ...``"""
    if battle is None or entity is None or not settings_for(battle.session).get('dm_turn_status'):
        return None
    conditions = condition_summary(battle, entity)
    line = (f"{DM_PREFIX} {_name(entity)} starts the turn at {hp_text(entity)}, "
            f"AC {_safe(entity.armor_class, '?')}")
    if conditions:
        line += " | conditions: " + ", ".join(conditions)
    return line


# --------------------------------------------------------------------------- #
# Party briefing                                                              #
# --------------------------------------------------------------------------- #

def health_description(entity) -> str:
    """What onlookers can tell about a creature's health without numbers."""
    if _safe(entity.dead, False):
        return 'dead'
    if _safe(entity.unconscious, False):
        return 'down'
    hp = _safe(entity.hp, 0) or 0
    max_hp = _safe(entity.max_hp, 0) or 0
    if max_hp <= 0 or hp >= max_hp:
        return 'unhurt'
    ratio = hp / max_hp
    if ratio > 0.5:
        return 'lightly wounded'
    if ratio > 0.25:
        return 'bloodied'
    return 'badly wounded'


def _visible_conditions(entity) -> List[str]:
    return [str(c).lower() for c in (_safe(entity.sheet_conditions, []) or [])
            if str(c).lower() not in ('dead', 'hidden', 'invisible')]


def foe_line(battle, foe, observer=None) -> str:
    from natural20.utils.outward_appearance import resolve_outward_appearance
    appearance = _short_sentence(_safe(lambda: resolve_outward_appearance(
        foe, session=battle.session, observer=observer, include_notes=False), '') or '')
    line = f"{FOE_PREFIX} {_name(foe)}"
    size = _safe(foe.size, None)
    if size:
        line += f" ({size})"
    line += f": {appearance} " if appearance else ": "
    line += f"Appears {health_description(foe)}."
    gear = [i.get('label') or str(i.get('name') or '').replace('_', ' ').title()
            for i in (_safe(foe.equipped_items, []) or []) if _combat_relevant(i)]
    gear = [g for g in gear if g and g.lower() not in appearance.lower()]
    if gear:
        line += " Carrying: " + ", ".join(gear) + "."
    conditions = _visible_conditions(foe)
    if conditions:
        line += " Visibly " + ", ".join(conditions) + "."
    return line


def _short_sentence(text: str, limit: int = 200) -> str:
    text = ' '.join(str(text).split())
    if len(text) > limit:
        cut = text[:limit]
        stop = cut.rfind('. ')
        text = cut[:stop + 1] if stop > 40 else cut.rstrip() + '…'
    if text and text[-1] not in '.!?…':
        text += '.'
    return text


def _has_player_character(entities) -> bool:
    return any(not _safe(e.is_npc, True) for e in entities)


def party_briefings(battle, combat_order=None) -> List[Dict[str, Any]]:
    """One briefing per team that has a player character:
    ``{'entity_uids': [...], 'lines': [...]}``. Partymates (PCs and
    sidekicks) get full stats; enemies the team can see get a description."""
    if battle is None or not settings_for(battle.session).get('party_briefing'):
        return []
    entities = [e for e, _ in (combat_order or [])] or list(getattr(battle, 'combat_order', None) or [])
    entities = [e for e in entities if not _safe(e.dead, False)]
    groups: Dict[str, List[Any]] = {}
    for e in entities:
        groups.setdefault(_group(battle, e), []).append(e)
    briefings = []
    for group, members in sorted(groups.items()):
        if not _has_player_character(members):
            continue
        lines = [team_totals_line(battle, members, prefix=PARTY_PREFIX)]
        lines += [combatant_line(battle, m, prefix=PARTY_PREFIX) for m in members]
        foes = []
        for e in entities:
            if e in members or e in foes:
                continue
            if not any(_safe(lambda m=m: e in battle.opponents_of(m), False) for m in members):
                continue
            if any(_safe(lambda m=m: battle.can_see(m, e), False) for m in members):
                foes.append(e)
        if foes:
            lines += [foe_line(battle, f, observer=members[0]) for f in foes]
        else:
            lines.append(f"{FOE_PREFIX} No enemies are in sight.")
        uids = [str(m.entity_uid) for m in members if getattr(m, 'entity_uid', None)]
        briefings.append({'entity_uids': uids, 'lines': lines})
    return briefings
