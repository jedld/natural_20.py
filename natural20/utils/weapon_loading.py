"""The Loading weapon property (SRD 5.1 / 5.2).

A Loading weapon fires only one piece of ammunition when you use an action,
bonus action or reaction to fire it, whatever the number of attacks you can
normally make. With Extra Attack, a crossbow shot therefore uses up the rest of
that Attack action for Loading weapons; the remaining attacks can still use a
different weapon.

Tracking: ``AttackAction.consume_resource`` stamps ``loading_fired`` (the turn
marker) on the attacker's battle state when a Loading weapon is fired as part
of the Attack action, and a fresh Attack action clears it. Bonus action,
reaction and legendary attacks are single attacks, so they are never blocked.
Feats may waive the property (``weapon_attack_rules`` ``ignore_properties:
[loading]``, e.g. Crossbow Expert). NPC stat-block attacks are not checked:
their Multiattack already reflects the creature's weapons.
"""

from __future__ import annotations

STATE_KEY = 'loading_fired'


def _turn_marker(battle):
    return [getattr(battle, 'round', 0), getattr(battle, 'current_turn_index', 0)]


def _load_weapon(entity, weapon):
    if isinstance(weapon, dict):
        return weapon
    if not weapon:
        return None
    try:
        return entity.session.load_weapon(weapon)
    except Exception:
        return None


def has_loading(entity, weapon):
    """True when firing ``weapon`` is limited by its Loading property."""
    weapon = _load_weapon(entity, weapon)
    if not isinstance(weapon, dict) or 'loading' not in (weapon.get('properties') or []):
        return False
    npc = getattr(entity, 'npc', None)
    if callable(npc) and npc():
        return False
    from natural20.utils.feat_mechanics import ignores_weapon_property
    return not ignores_weapon_property(entity, weapon, 'loading')


def loading_blocked(entity, battle, weapon, *, as_reaction=False, as_bonus_action=False,
                    second_hand=False, legendary=False):
    """True when the current Attack action already fired a Loading weapon."""
    if battle is None or entity is None:
        return False
    if as_reaction or as_bonus_action or second_hand or legendary:
        return False
    if not has_loading(entity, weapon):
        return False
    state = battle.entity_state_for(entity) or {}
    if state.get(STATE_KEY) != _turn_marker(battle):
        return False
    try:
        return int(state.get('extra_attacks_remaining') or 0) > 0
    except (TypeError, ValueError):
        return False


def action_blocked(action, battle):
    """``loading_blocked`` for an ``AttackAction``."""
    if getattr(action, 'npc_action', None) or not getattr(action, 'using', None):
        return False
    return loading_blocked(
        action.source, battle, action.using,
        as_reaction=bool(getattr(action, 'as_reaction', False)),
        as_bonus_action=bool(getattr(action, 'as_bonus_action', False)),
        second_hand=bool(action.second_hand()) if callable(getattr(action, 'second_hand', None)) else False,
        legendary=bool(getattr(action, 'legendary_action', False)),
    )


def record_attack(battle, item, new_action):
    """Update the Loading stamp after an Attack-action attack is paid for.

    ``new_action`` is True when this attack spent a fresh action (not a
    remaining Extra Attack).
    """
    state = battle.entity_state_for(item['source']) if battle is not None else None
    if state is None:
        return
    if new_action:
        state[STATE_KEY] = None
    if item.get('npc_action') or not item.get('weapon'):
        return
    if has_loading(item['source'], item['weapon']):
        state[STATE_KEY] = _turn_marker(battle)
