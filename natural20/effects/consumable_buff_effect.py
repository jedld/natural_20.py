"""Timed buffs granted by drinking a consumable (``EffectConsumableItem``).

Supported buff keys (item YAML ``buffs``):

* ``speed_bonus``: added to walking speed (``speed_override``).
* ``fly_speed``: flying speed of at least this much (``fly_speed``).
* ``ac_bonus``: added to AC (``ac_bonus``).
* ``attack_die``: die added to attack rolls, e.g. ``1d4`` (``attack_roll_die``).
* ``save_die``: die added to saving throws (``save_modifier``).
"""

from __future__ import annotations

from natural20.die_roll import DieRoll

BUFF_EFFECT_TYPES = {
    'speed_bonus': 'speed_override',
    'fly_speed': 'fly_speed',
    'ac_bonus': 'ac_bonus',
    'attack_die': 'attack_roll_die',
    'save_die': 'save_modifier',
}


class ConsumableBuffEffect:
    def __init__(self, source, target, buffs, label='consumable_buff'):
        self.source = source
        self.target = target
        self.action = None
        self.buffs = dict(buffs or {})
        self.label = label
        self.id = f"{label}:{id(self)}"

    def __str__(self):
        # Tile icon slug (assets/effect/consumable_buff.png); the label names the item in logs.
        return 'consumable_buff'

    def apply_to(self, target, duration=None):
        for key, effect_type in BUFF_EFFECT_TYPES.items():
            if self.buffs.get(key):
                target.register_effect(effect_type, self, effect=self, source=self.source,
                                       duration=duration)

    @staticmethod
    def speed_override(entity, opt=None):
        opt = opt or {}
        return (opt.get('value') or 0) + int(opt['effect'].buffs.get('speed_bonus', 0) or 0)

    @staticmethod
    def fly_speed(entity, opt=None):
        opt = opt or {}
        return max(opt.get('value') or 0, int(opt['effect'].buffs.get('fly_speed', 0) or 0))

    @staticmethod
    def ac_bonus(entity, opt=None):
        opt = opt or {}
        return int(opt['effect'].buffs.get('ac_bonus', 0) or 0)

    @staticmethod
    def attack_roll_die(entity, opt=None):
        opt = opt or {}
        dice = list(opt.get('value') or [])
        die = opt['effect'].buffs.get('attack_die')
        if die:
            dice.append(die)
        return dice

    @staticmethod
    def save_modifier(entity, opt=None):
        opt = opt or {}
        value = opt.get('value') or 0
        die = opt['effect'].buffs.get('save_die')
        if not die:
            return value
        roll = DieRoll.roll(die, description=f"save_modifier:{opt['effect'].label}",
                            entity=entity, battle=opt.get('battle'))
        if hasattr(value, 'result'):
            return value + roll
        if value:
            return roll + DieRoll.roll(f"+{int(value)}" if int(value) >= 0 else str(int(value)),
                                       entity=entity, battle=opt.get('battle'))
        return roll


def attack_roll_dice(entity, battle=None):
    """Extra dice (``attack_roll_die`` effects) to add to an attack roll."""
    if not entity.has_effect('attack_roll_die'):
        return []
    dice = entity.eval_effect('attack_roll_die', {'stacked': True, 'value': []}) or []
    return [DieRoll.roll(die, description='dice_roll.attack_bonus_die', entity=entity, battle=battle)
            for die in dice]
