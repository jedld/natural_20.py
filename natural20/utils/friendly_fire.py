"""Keep AI combatants from harming their own side without a reason.

5e lets a creature attack or blast anyone (Magic Missile lists both
``enemies`` and ``allies``), so the action builders legitimately offer
hostile options aimed at allies. A human player chooses those on purpose;
an AI decision model only sees "cast Magic Missile on X" and, when X is a
downed ally at 0 HP, a "weakest target first" ranking makes it look like the
best finisher. AI option lists therefore drop harmful actions aimed at the
acting creature or its allies.

An action is *harmful* when it is:

* a weapon/natural attack, shove, or grapple;
* a spell with a ``damage_type``, an explicit ``hostile: true`` YAML flag, or
  a creature target restricted to enemies (``target_types: [enemies]``);
* a used item that deals damage or casts such a spell (spell scrolls).

``hostile: false`` on a spell or item marks it safe to aim at allies.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, List, Optional


def _props(obj) -> dict:
    props = getattr(obj, 'properties', None)
    return props if isinstance(props, dict) else {}


def _spell_props(action) -> dict:
    sa = getattr(action, 'spell_action', None)
    props = _props(sa)
    if props:
        return props
    sp = getattr(action, 'spell', None) or (getattr(action, 'opts', None) or {}).get('spell')
    return sp if isinstance(sp, dict) else {}


def _enemy_only_target(spell_action, action) -> bool:
    try:
        node = spell_action.build_map(action)
    except Exception:
        return False
    for _ in range(8):
        if not isinstance(node, dict):
            return False
        for p in node.get('param') or []:
            if p.get('type') == 'select_target':
                types = {str(t).lower() for t in (p.get('target_types') or ['enemies'])}
                return 'enemies' in types and not types & {'allies', 'self'}
        nxt = node.get('next')
        try:
            node = nxt() if callable(nxt) else None
        except Exception:
            return False
    return False


def _spell_is_harmful(props: dict, spell_action=None, action=None) -> bool:
    if 'hostile' in props:
        return bool(props.get('hostile'))
    if props.get('damage_type') or props.get('damage'):
        return True
    return spell_action is not None and _enemy_only_target(spell_action, action)


def _item_is_harmful(session, item) -> bool:
    props = _props(item)
    if 'hostile' in props:
        return bool(props.get('hostile'))
    if props.get('damage') or props.get('damage_type'):
        return True
    spell = props.get('spell')
    if spell and session is not None:
        try:
            return _spell_is_harmful(session.load_spell(spell) or {})
        except Exception:
            return False
    return False


def is_harmful(action, session=None) -> bool:
    from natural20.actions.attack_action import AttackAction
    from natural20.actions.spell_action import SpellAction
    try:
        from natural20.actions.attack_action import TwoWeaponAttackAction
    except ImportError:
        TwoWeaponAttackAction = AttackAction
    from natural20.actions.shove_action import ShoveAction
    from natural20.actions.grapple_action import GrappleAction
    from natural20.actions.use_item_action import UseItemAction

    if isinstance(action, (AttackAction, TwoWeaponAttackAction, ShoveAction, GrappleAction)):
        return True
    if isinstance(action, SpellAction):
        return _spell_is_harmful(_spell_props(action), getattr(action, 'spell_action', None), action)
    if isinstance(action, UseItemAction):
        item = getattr(action, 'target_item', None)
        return item is not None and _item_is_harmful(session or getattr(action, 'session', None), item)
    return False


def _creature_targets(action) -> List[Any]:
    t = getattr(action, 'target', None)
    members = t if isinstance(t, (list, tuple)) else [t]
    return [m for m in members if m is not None and hasattr(m, 'entity_uid')]


def harms_own_side(battle, entity, action) -> bool:
    """True when *action* is harmful and aimed at *entity* or one of its allies."""
    targets = _creature_targets(action)
    if not targets or battle is None:
        return False
    own = []
    for t in targets:
        if t is entity:
            own.append(t)
            continue
        try:
            if battle.allies(entity, t):
                own.append(t)
        except Exception:
            continue
    if not own:
        return False
    return is_harmful(action, getattr(battle, 'session', None))


def filter_actions(battle, entity, actions: Iterable[Any],
                   action_of: Optional[Callable[[Any], Any]] = None) -> List[Any]:
    """Drop options that would harm *entity*'s own side."""
    get = action_of or (lambda a: a)
    out = []
    for item in actions:
        try:
            if harms_own_side(battle, entity, get(item)):
                continue
        except Exception:
            pass
        out.append(item)
    return out
