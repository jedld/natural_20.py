"""Battle statistics collected from the battle log, reported at combat end.

Everything is computed from ``battle.battle_log`` (committed actions and
their ``result`` items), so there is no new state to serialize: the numbers
survive save/load for free, and ``_applied_damage`` annotations (written by
``Entity.take_damage``) make damage totals reflect resistances, immunity and
damage reduction rather than raw rolls.

The report covers:

* per combatant: damage dealt (by damage type), hits / crits / misses,
  healing done, saving throws, damage taken;
* per source-to-target pair: totals and type breakdown;
* team aggregates (party vs foes) and per-round counts;
* kills and downings with attribution from ``death_info``.

Campaign switch in ``game.yml``::

    battle_statistics:
      enabled: true           # emit the report at combat end (default true)
      visibility: dm          # 'dm' (default) or 'all' to also show players

The engine emits one ``battle_statistics`` event (DM combat log) whose
``lines`` carry the human-readable report; ``collect_statistics(battle)``
returns the same data as a JSON-safe dict for MCP / UI use.
"""

from typing import Any, Dict, List, Optional

DEFAULT_SETTINGS = {'enabled': True, 'visibility': 'dm'}
DM_PREFIX = '[DM]'

_DAMAGE_TYPES_ORDER = 12


def settings_for(session) -> Dict[str, Any]:
    out = dict(DEFAULT_SETTINGS)
    props = getattr(session, 'game_properties', None) or {}
    raw = props.get('battle_statistics') if isinstance(props, dict) else None
    if isinstance(raw, bool):
        out['enabled'] = raw
    elif isinstance(raw, dict):
        if 'enabled' in raw:
            out['enabled'] = bool(raw['enabled'])
        vis = raw.get('visibility')
        if isinstance(vis, str) and vis.strip():
            out['visibility'] = vis.strip().lower()
    return out


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def _name(entity) -> str:
    if entity is None:
        return '?'
    return _safe(entity.label, None) or getattr(entity, 'name', None) or '?'


def _roll_value(obj) -> Optional[int]:
    """Numeric value of a DieRoll / int / None."""
    if obj is None:
        return None
    if isinstance(obj, bool):
        return None
    if isinstance(obj, (int, float)):
        return int(obj)
    result = _safe(obj.result, None)
    if result is None:
        return None
    try:
        return int(result)
    except Exception:
        return None


def _applied(item: Dict[str, Any]) -> int:
    """Damage actually dealt by a log item (post resistance/reduction)."""
    applied = item.get('_applied_damage')
    if isinstance(applied, (int, float)):
        return max(0, int(applied))
    value = _roll_value(item.get('damage'))
    return max(0, value) if value is not None else 0


def _is_critical(item: Dict[str, Any]) -> bool:
    if item.get('critical'):
        return True
    roll = item.get('attack_roll')
    if roll is None:
        return False
    return bool(_safe(roll.nat_20, False))


def _pair(stats: Dict[str, Any], src: str, tgt: str) -> Dict[str, Any]:
    key = f"{src} -> {tgt}"
    return stats['pairs'].setdefault(key, {
        'damage': 0, 'hits': 0, 'crits': 0, 'misses': 0, 'by_type': {},
    })


def _side(stats: Dict[str, Any], name: str) -> Dict[str, Any]:
    return stats['combatants'].setdefault(name, {
        'dealt': 0, 'taken': 0, 'hits': 0, 'misses': 0, 'crits': 0,
        'healing': 0, 'saves': 0, 'saves_passed': 0, 'spells_cast': set(),
    })


def _group(battle, entity) -> str:
    state = _safe(lambda: battle.entity_state_for(entity), None) or {}
    return str(state.get('group') or '?')


def collect_statistics(battle) -> Dict[str, Any]:
    """JSON-safe statistics for a battle (ended or still running)."""
    stats: Dict[str, Any] = {
        'rounds': int(getattr(battle, 'round', 0) or 0),
        'combatants': {},
        'pairs': {},
        'damage_types': {},
        'teams': {},
        'totals': {'damage': 0, 'healing': 0, 'hits': 0, 'misses': 0,
                   'crits': 0, 'saves': 0, 'saves_passed': 0},
        'kills': [],
    }

    for action in (getattr(battle, 'battle_log', None) or []):
        results = getattr(action, 'result', None) or []
        for item in results:
            if not isinstance(item, dict):
                continue
            itype = item.get('type')
            src = _name(item.get('source'))
            tgt = _name(item.get('target')) if item.get('target') is not None else None

            if itype in ('damage', 'spell_damage', 'additional_damage'):
                if tgt is None:
                    continue
                dmg = _applied(item)
                dtype = str(item.get('damage_type') or 'untyped')
                pair = _pair(stats, src, tgt)
                pair['damage'] += dmg
                pair['by_type'][dtype] = pair['by_type'].get(dtype, 0) + dmg
                stats['damage_types'][dtype] = stats['damage_types'].get(dtype, 0) + dmg
                stats['totals']['damage'] += dmg
                _side(stats, src)['dealt'] += dmg
                _side(stats, tgt)['taken'] += dmg
                is_attack = item.get('attack_roll') is not None or \
                    (itype == 'damage' and 'hit?' in item)
                if is_attack:
                    pair['hits'] += 1
                    stats['totals']['hits'] += 1
                    _side(stats, src)['hits'] += 1
                    if item.get('critical'):
                        pair['crits'] += 1
                        stats['totals']['crits'] += 1
                        _side(stats, src)['crits'] += 1
                if itype == 'spell_damage' and 'save_failed' in item:
                    stats['totals']['saves'] += 1
                    _side(stats, tgt)['saves'] += 1
                    if not item.get('save_failed'):
                        stats['totals']['saves_passed'] += 1
                        _side(stats, tgt)['saves_passed'] += 1
                if itype == 'spell_damage':
                    spell = item.get('spell')
                    sp_name = None
                    if isinstance(spell, dict):
                        sp_name = spell.get('label') or spell.get('name')
                    elif spell is not None:
                        sp_name = _safe(spell.label, None) or getattr(spell, 'name', None)
                    if sp_name:
                        _side(stats, src)['spells_cast'].add(str(sp_name))
            elif itype in ('miss', 'blind_miss'):
                pair = _pair(stats, src, tgt or 'a guessed square')
                pair['misses'] += 1
                stats['totals']['misses'] += 1
                _side(stats, src)['misses'] += 1
            elif itype in ('spell_heal', 'heal'):
                heal = _roll_value(item.get('heal_roll')) or _roll_value(item.get('healing')) or 0
                if tgt and heal:
                    _side(stats, src)['healing'] += heal
                    stats['totals']['healing'] += heal
                    stats.setdefault('heals', []).append(
                        {'from': src, 'to': tgt, 'amount': heal})
            elif itype == 'use_item':
                heal = _roll_value(item.get('hp_gain_roll'))
                if tgt and heal:
                    _side(stats, src)['healing'] += heal
                    stats['totals']['healing'] += heal
                    stats.setdefault('heals', []).append(
                        {'from': src, 'to': tgt, 'amount': heal})

    # set of str -> sorted list for JSON safety
    for side in stats['combatants'].values():
        side['spells_cast'] = sorted(side['spells_cast'])

    # team aggregates + fates + kills
    entities = list(getattr(battle, 'combat_order', None) or [])
    if not entities:
        try:
            entities = list(battle.entities.keys())
        except Exception:
            entities = []
    for entity in entities:
        name = _name(entity)
        side = _side(stats, name)
        team = _group(battle, entity)
        team_bucket = stats['teams'].setdefault(team, {'dealt': 0, 'taken': 0})
        team_bucket['dealt'] += side['dealt']
        team_bucket['taken'] += side['taken']
        fate = {'name': name, 'team': team}
        if _safe(entity.dead, False):
            fate['fate'] = 'dead'
            info = getattr(entity, 'attributes', {}).get('death_info') \
                if isinstance(getattr(entity, 'attributes', None), dict) else None
            if isinstance(info, dict):
                stats['kills'].append({
                    'victim': name,
                    'by': info.get('killer_name') or 'unknown',
                    'cause': info.get('cause') or 'unknown',
                    'attack': info.get('attack_name'),
                })
        elif _safe(entity.unconscious, False):
            fate['fate'] = 'downed'
        else:
            fate['fate'] = 'standing'
        fate['hp'] = _safe(entity.hp, 0) or 0
        fate['max_hp'] = _safe(entity.max_hp, 0) or 0
        side['fate'] = fate['fate']
        stats['fates'] = stats.get('fates', [])
        stats['fates'].append(fate)
    return stats


# --------------------------------------------------------------------------- #
# Human-readable report                                                       #
# --------------------------------------------------------------------------- #

def format_statistics_lines(battle, stats: Optional[Dict[str, Any]] = None,
                            prefix: str = DM_PREFIX) -> List[str]:
    """Compact multi-line report used by the combat log."""
    if battle is None:
        return []
    stats = stats if stats is not None else collect_statistics(battle)
    totals = stats['totals']
    if not (totals['damage'] or totals['healing'] or totals['hits'] or totals['misses']):
        return []
    head = f"{prefix} " if prefix else ''
    sub = f"{prefix}   " if prefix else '   '
    lines: List[str] = [
        f"{head}Battle statistics after {stats['rounds']} round"
        f"{'s' if stats['rounds'] != 1 else ''}:"
    ]

    lines.append(f"{head}Combatants — damage dealt / taken / hits-crits-misses / healing / saves passed:")
    for name, side in sorted(stats['combatants'].items(),
                             key=lambda kv: -kv[1]['dealt']):
        line = (f"{sub}{name}: {side['dealt']} dealt, {side['taken']} taken, "
                f"{side['hits']}-{side['crits']}-{side['misses']} hits/crits/misses")
        if side['healing']:
            line += f", {side['healing']} healed"
        if side['saves']:
            line += f", {side['saves_passed']}/{side['saves']} saves passed"
        fate = side.get('fate')
        if fate and fate != 'standing':
            line += f" [{fate}]"
        lines.append(line)

    pairs = [(k, v) for k, v in stats['pairs'].items()
             if v['damage'] or v['misses'] or v['hits']]
    if pairs:
        lines.append(f"{head}Damage by matchup:")
        for key, v in sorted(pairs, key=lambda kv: -kv[1]['damage']):
            if not (v['damage'] or v['misses'] or v['hits']):
                continue
            part = f"{key}: {v['damage']}"
            detail = []
            if v['hits']:
                detail.append(f"{v['hits']} hit" + ('s' if v['hits'] != 1 else ''))
            if v['crits']:
                detail.append(f"{v['crits']} crit")
            if v['misses']:
                detail.append(f"{v['misses']} miss" + ('es' if v['misses'] != 1 else ''))
            if detail:
                part += " (" + ", ".join(detail) + ")"
            if v['by_type']:
                types = ", ".join(f"{amt} {t}" for t, amt in
                                  sorted(v['by_type'].items(), key=lambda kv: -kv[1])
                                  [:_DAMAGE_TYPES_ORDER])
                part += f" [{types}]"
            lines.append(f"{sub}{part}")

    if stats['damage_types']:
        types = ", ".join(f"{t} {amt}" for t, amt in
                          sorted(stats['damage_types'].items(), key=lambda kv: -kv[1])
                          [:_DAMAGE_TYPES_ORDER])
        lines.append(f"{head}Damage types: {types}")

    if stats['teams']:
        teams = "; ".join(f"team {g}: dealt {v['dealt']}, taken {v['taken']}"
                          for g, v in sorted(stats['teams'].items()))
        lines.append(f"{head}Team totals: {teams}")

    if stats.get('kills'):
        lines.append(f"{head}Kills:")
        for kill in stats['kills']:
            how = f" with {kill['attack']}" if kill.get('attack') else ''
            cause = f" ({kill['cause']})" if kill.get('cause') and kill['cause'] != 'killed' else ''
            lines.append(f"{sub}{kill['victim']} killed by {kill['by']}{how}{cause}")
    downed = [f for f in stats.get('fates', []) if f['fate'] == 'downed']
    if downed:
        lines.append(f"{head}Downed at combat end: " +
                     ", ".join(f"{f['name']} ({f['hp']}/{f['max_hp']})" for f in downed))

    lines.append(f"{head}Totals: {totals['damage']} damage dealt, "
                 f"{totals['hits']} hits ({totals['crits']} critical), "
                 f"{totals['misses']} misses, {totals['healing']} healing, "
                 f"{totals['saves_passed']}/{totals['saves']} saves passed")
    return lines


def emit_battle_statistics(battle) -> None:
    """Compute and log the combat-end report (gated by game.yml)."""
    try:
        settings = settings_for(getattr(battle, 'session', None))
        if not settings['enabled']:
            return
        visibility = 'dm' if settings['visibility'] != 'all' else None
        lines = format_statistics_lines(
            battle, prefix=DM_PREFIX if visibility else '')
        if not lines:
            return
        battle.session.event_manager.received_event({
            'source': battle,
            'event': 'battle_statistics',
            'battle': battle,
            'lines': lines,
            'visibility': visibility,
        })
    except Exception:
        # statistics are best-effort; never break the combat-end path
        import logging
        logging.getLogger(__name__).debug('battle statistics report failed',
                                          exc_info=True)
