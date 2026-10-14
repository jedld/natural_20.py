"""Dice subtracted from d20 rolls by effects.

* ``targeted_attack_penalty`` on the *target*: the attacker subtracts the
  returned dice (``'1d4'``) from attack rolls against it (2024 Blade Ward).
* ``attack_roll_penalty`` on the *attacker*: it subtracts the dice from its
  own attack rolls (Synaptic Static's muddled thoughts).
* ``concentration_save_penalty`` on the *concentrating creature*: subtracted
  from Constitution saves made to keep concentration.

Every registered handler applies; each is called as
``handler.<effect_type>(entity, {'attacker': ..., 'battle': ..., 'effect': ...})``
and returns a dice string or ``None``.
"""

from __future__ import annotations

from natural20.die_roll import DieRoll


def penalty_dice(entity, effect_type, opts=None):
    """Dice strings from every active ``effect_type`` handler on ``entity``."""
    out = []
    if entity is None or not hasattr(entity, 'effects'):
        return out
    session = getattr(entity, 'session', None)
    for descriptor in list((entity.effects or {}).get(effect_type) or []):
        expiration = descriptor.get('expiration')
        if expiration is not None and session is not None and expiration <= session.game_time:
            continue
        handler = descriptor.get('handler')
        method = getattr(handler, descriptor.get('method') or effect_type, None)
        if method is None:
            continue
        dice = method(entity, dict(opts or {}, effect=descriptor.get('effect')))
        if dice:
            out.append(str(dice))
    return out


def subtract_dice(roll, dice_list, roller=None, battle=None, description='dice_roll.penalty'):
    for dice in dice_list:
        penalty = DieRoll.roll(dice, description=description, entity=roller, battle=battle)
        roll += DieRoll.roll(f"-{penalty.result()}", battle=battle, entity=roller)
    return roll


def apply_targeted_penalties(attack_roll, attacker, target, battle=None):
    """Return ``attack_roll`` minus the target's and the attacker's penalty dice."""
    opts = {'attacker': attacker, 'battle': battle}
    dice = penalty_dice(target, 'targeted_attack_penalty', opts)
    dice += penalty_dice(attacker, 'attack_roll_penalty', opts)
    return subtract_dice(attack_roll, dice, roller=attacker, battle=battle,
                         description='dice_roll.attack_penalty')
