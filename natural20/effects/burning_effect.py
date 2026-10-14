"""A creature on fire: damage at the start of each of its turns until put out.

Applied by thrown items with a YAML ``burning`` block (Alchemist's Fire) via
``BurningEffect.apply_to``. The flames have no duration: they last until a
creature within reach uses an action and passes a Dexterity check against
``extinguish_dc`` (``ExtinguishFlamesAction``). A creature already burning
is not set alight twice; the stronger damage roll is kept.
"""

from natural20.die_roll import DieRoll


class BurningEffect:
    EFFECT_TYPE = 'burning'

    def __init__(self, source, target, damage='1d4', damage_type='fire',
                 extinguish_dc=10, label='Burning'):
        self.source = source
        self.target = target
        self.action = None
        self.damage = str(damage or '1d4')
        self.damage_type = str(damage_type or 'fire')
        self.extinguish_dc = int(extinguish_dc or 10)
        self.label = label or 'Burning'
        self.id = f"burning:{id(self)}"

    def __str__(self):
        return self.label

    @staticmethod
    def active_on(entity):
        """The ``BurningEffect`` currently on *entity*, or ``None``."""
        for descriptor in (getattr(entity, 'effects', None) or {}).get(BurningEffect.EFFECT_TYPE, []):
            effect = descriptor.get('effect')
            if isinstance(effect, BurningEffect):
                return effect
        return None

    @classmethod
    def apply_to(cls, target, source, damage='1d4', damage_type='fire',
                 extinguish_dc=10, label='Burning'):
        current = cls.active_on(target)
        if current is not None:
            if DieRoll.roll(str(damage)).expected() > DieRoll.roll(current.damage).expected():
                current.damage = str(damage)
                current.damage_type = str(damage_type or 'fire')
            current.extinguish_dc = max(current.extinguish_dc, int(extinguish_dc or 10))
            return current
        effect = cls(source, target, damage, damage_type, extinguish_dc, label)
        target.register_effect(cls.EFFECT_TYPE, cls, effect=effect, source=source)
        target.register_event_hook('start_of_turn', cls, effect=effect, source=source)
        return effect

    @staticmethod
    def burning(entity, opt=None):
        """Effect-registry marker; burning changes no stat by itself."""
        return None

    @staticmethod
    def start_of_turn(entity, opt=None):
        opt = opt or {}
        effect = opt.get('effect')
        if not isinstance(effect, BurningEffect) or entity.dead():
            return []
        battle = opt.get('battle')
        session = getattr(entity, 'session', None)
        roll = DieRoll.roll(effect.damage, battle=battle, entity=entity,
                            description='dice_roll.burning')
        amount = roll.result()
        if session is not None:
            session.event_manager.received_event({
                'event': 'burning_damage',
                'source': entity,
                'target': entity,
                'roll': roll,
                'value': amount,
                'damage_type': effect.damage_type,
            })
        entity.take_damage(amount, battle=battle, damage_type=effect.damage_type,
                           session=session, roll_info=roll)
        return []

    @staticmethod
    def extinguish(entity, by=None, battle=None):
        """Put out the flames on *entity*. Returns ``True`` if it was burning."""
        effect = BurningEffect.active_on(entity)
        if effect is None:
            return False
        entity.remove_effect(effect)
        session = getattr(entity, 'session', None)
        if session is not None:
            session.event_manager.received_event({
                'event': 'burning_extinguished',
                'source': by or entity,
                'target': entity,
            })
        return True
