"""Taunted: disadvantage on attacks against anyone but the taunter.

Used by Kender Taunt (race YAML ``taunt`` block, ``TauntAction``) and by
spell riders such as the Archfey's Taunting Step. A creature's taunts are kept
in ``entity.attributes['taunted_by']`` keyed by the taunter's UID::

    {'label': 'taunt'}

Taunts last until the start of the taunter's next turn
(``expire_taunts_by`` is called from ``Battle.start_turn``) or until the
taunter dies. ``taunt_disadvantage`` is read by
``weapons.compute_advantages_and_disadvantages`` (weapon and spell attacks).
"""

from __future__ import annotations

TAUNTED_KEY = 'taunted_by'


def _table(entity):
    attrs = getattr(entity, 'attributes', None)
    if not isinstance(attrs, dict):
        return {}
    table = attrs.get(TAUNTED_KEY)
    return table if isinstance(table, dict) else {}


def ability_dc(entity, abilities):
    """8 + proficiency bonus + the best modifier among ``abilities``."""
    from natural20.entity_class.data_driven import normalize_ability
    mods = []
    for ability in abilities or ['cha']:
        try:
            mods.append(int(entity.ability_mod(normalize_ability(ability)) or 0))
        except Exception:
            continue
    return 8 + int(entity.proficiency_bonus()) + (max(mods) if mods else 0)


def apply_taunt(target, taunter, label='taunt'):
    if target is None or taunter is None or target is taunter or target.dead():
        return False
    table = dict(_table(target))
    table[taunter.entity_uid] = {'label': label}
    target.attributes[TAUNTED_KEY] = table
    return True


def taunted_by(entity):
    return list(_table(entity).keys())


def taunt_disadvantage(attacker, target, battle=None):
    """``['taunted']`` when ``attacker`` is taunted by a living creature other than ``target``."""
    table = _table(attacker)
    if not table:
        return []
    session = getattr(attacker, 'session', None)
    target_uid = getattr(target, 'entity_uid', None)
    live = {}
    for uid, entry in table.items():
        source = session.entity_by_uid(uid) if session is not None and hasattr(session, 'entity_by_uid') else None
        if source is not None and source.dead():
            continue
        live[uid] = entry
    if live != table:
        attacker.attributes[TAUNTED_KEY] = live
    if any(uid != target_uid for uid in live):
        return ['taunted']
    return []


def expire_taunts_by(taunter, battle):
    """End every taunt ``taunter`` applied (start of the taunter's turn)."""
    uid = getattr(taunter, 'entity_uid', None)
    if uid is None or battle is None:
        return
    for entity in list(getattr(battle, 'entities', {}).keys()):
        table = _table(entity)
        if uid in table:
            table = dict(table)
            table.pop(uid, None)
            entity.attributes[TAUNTED_KEY] = table
