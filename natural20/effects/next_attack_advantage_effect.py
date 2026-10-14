"""One-shot advantage (or disadvantage) on the bearer's next attack roll.

Granted by item YAML ``on_use: [next_attack_advantage]`` and by attack options
such as "the target has disadvantage on its next attack roll". The effect ends
after one attack roll, at the end of the bearer's turn, or when its duration
runs out, whichever comes first.
"""


class NextAttackAdvantageEffect:
    def __init__(self, source, target=None, label='next_attack_advantage', mode='advantage'):
        self.source = source
        self.target = target if target is not None else source
        self.action = None
        self.label = label
        self.mode = mode
        self.id = f"next_attack_{mode}:{id(self)}"

    def __str__(self):
        return self.label

    @staticmethod
    def attack_advantage_modifier(entity, opt=None):
        effect = (opt or {}).get('effect')
        label = str(effect) if effect is not None else 'next_attack_advantage'
        if effect is not None and effect.mode == 'disadvantage':
            return [[], [label]]
        return [[label], []]

    @staticmethod
    def _end(entity, opt=None):
        effect = (opt or {}).get('effect')
        if effect is None:
            return []
        try:
            entity.dismiss_effect(effect)
        except Exception:
            pass
        return []

    @staticmethod
    def attack_resolved(entity, opt=None):
        return NextAttackAdvantageEffect._end(entity, opt)

    @staticmethod
    def end_of_turn(entity, opt=None):
        effect = (opt or {}).get('effect')
        if effect is not None and effect.mode == 'disadvantage':
            return []
        return NextAttackAdvantageEffect._end(entity, opt)

    @classmethod
    def grant(cls, entity, source=None, label='next_attack_advantage', duration=6, mode='advantage'):
        """``advantage`` lasts until the end of the bearer's turn; ``disadvantage`` until ``duration`` runs out."""
        source = source or entity
        effect = cls(source, entity, label=label, mode=mode)
        entity.register_effect('attack_advantage_modifier', cls, effect=effect,
                               source=source, duration=duration)
        entity.register_event_hook('attack_resolved', cls, effect=effect,
                                   source=source, duration=duration)
        entity.register_event_hook('end_of_turn', cls, effect=effect,
                                   source=source, duration=duration)
        return effect
