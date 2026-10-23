"""Targeting wards (Sanctuary and similar protections).

A warded creature registers a ``targeting_ward`` effect whose handler returns
a ward descriptor ``{'save_type': 'wisdom', 'dc': 13, 'label': 'Sanctuary'}``
(or ``None`` when the ward does not apply to this attacker). A creature that
targets it with an attack or a harmful spell must first pass that saving
throw; on a failure the attack or spell is lost:

* ``AttackAction.resolve`` calls :func:`attack_ward_items` before rolling.
  A blocked attack still spends the attack (``consume_attack`` on the item).
* ``SpellAction.resolve`` calls :func:`filter_spell_targets` before the spell
  resolves. Warded creatures that fail are dropped from a multi-target spell;
  if no target is left the spell (and its slot) is lost.

Area effects that don't target the creature are not affected. Every save is
logged through a ``targeting_ward`` result item (applied by
``AttackAction.apply``, which sees every committed item).
"""
from __future__ import annotations

WARD_EFFECT = 'targeting_ward'


def _ward_for(target, attacker, battle, kind):
    if target is None or attacker is None or target is attacker:
        return None
    if not hasattr(target, 'has_effect') or not target.has_effect(WARD_EFFECT):
        return None
    try:
        return target.eval_effect(WARD_EFFECT, {'attacker': attacker, 'battle': battle, 'kind': kind})
    except Exception:
        return None


def roll_ward_save(battle, attacker, target, kind='attack'):
    """Roll the attacker's save against ``target``'s ward.

    Returns ``(blocked, item)``; ``item`` is ``None`` when no ward applies.
    """
    ward = _ward_for(target, attacker, battle, kind)
    if not ward:
        return False, None
    save_type = ward.get('save_type', 'wisdom')
    dc = int(ward.get('dc') or 10)
    roll = attacker.save_throw(save_type, battle, {'is_magical': True, 'dc': dc})
    blocked = roll.result() < dc
    return blocked, {
        'type': 'targeting_ward',
        'source': attacker,
        'target': target,
        'label': ward.get('label', 'ward'),
        'save_type': save_type,
        'roll': roll,
        'dc': dc,
        'blocked': blocked,
        'kind': kind,
    }


def attack_ward_items(action, battle, target):
    """Ward check for a weapon/natural attack. Returns the items to append and
    whether the attack was lost."""
    blocked, item = roll_ward_save(battle, action.source, target, 'attack')
    if item is None:
        return False, []
    if blocked:
        try:
            attack_name = action.get_weapon_info({})[1]
        except Exception:
            attack_name = getattr(action, 'using', None)
        item.update({
            'consume_attack': True,
            'battle': battle,
            'weapon': action.using,
            'attack_name': attack_name,
            'npc_action': action.npc_action,
            'thrown': False,
            'ammo': None,
            'multiattack_clear': bool(action.npc_action and action.npc_action.get('multiattack_clear_on_miss')),
            'multiattack_hits': False,
            'as_reaction': bool(action.as_reaction),
            'as_bonus_action': bool(getattr(action, 'as_bonus_action', False)),
            'as_legendary_action': bool(getattr(action, 'legendary_action', False)),
            'second_hand': action.second_hand() if hasattr(action, 'second_hand') else False,
        })
    return blocked, [item]


def _creatures(target):
    members = target if isinstance(target, (list, tuple)) else [target]
    return [m for m in members if m is not None and hasattr(m, 'entity_uid')]


def filter_spell_targets(spell_action, battle):
    """Ward checks for a harmful spell. Returns ``(lost, items)``.

    Mutates ``spell_action.target`` to drop warded creatures that the caster
    failed to target.
    """
    target = spell_action.target
    creatures = _creatures(target)
    if not creatures:
        return False, []
    if not any(c.has_effect(WARD_EFFECT) for c in creatures if hasattr(c, 'has_effect')):
        return False, []
    from natural20.utils.friendly_fire import is_harmful
    if not is_harmful(spell_action, getattr(battle, 'session', None)):
        return False, []

    items, dropped, checked = [], [], []
    for creature in creatures:
        if creature in checked:
            continue
        checked.append(creature)
        blocked, item = roll_ward_save(battle, spell_action.source, creature, 'spell')
        if item is not None:
            items.append(item)
        if blocked:
            dropped.append(creature)
    if not dropped:
        return False, items
    if isinstance(target, (list, tuple)):
        remaining = [t for t in target if t not in dropped]
        if any(hasattr(t, 'entity_uid') for t in remaining):
            spell_action.target = remaining
            return False, items
    return True, items


def apply_ward_item(battle, item, session):
    session.event_manager.received_event({
        'event': 'targeting_ward',
        'source': item['source'],
        'target': item['target'],
        'label': item.get('label'),
        'save_type': item.get('save_type'),
        'roll': item.get('roll'),
        'dc': item.get('dc'),
        'blocked': item.get('blocked'),
        'kind': item.get('kind'),
    })
