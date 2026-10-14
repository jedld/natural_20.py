"""The bearer can't regain hit points until the start of the source's next turn.

Applied by NPC action YAML ``on_hit: [{fail: effect:no_healing}]`` (no
``save_dc`` means it always applies on a hit). Every healing path goes
through ``Entity.heal`` and its ``heal_override`` effect, so potions, spells,
regeneration and Lay on Hands are all blocked while it lasts.
"""


class NoHealingEffect:
    def __init__(self, source, target, label='no_healing'):
        self.source = source
        self.target = target
        self.action = None
        self.label = label
        self.id = f"no_healing:{id(self)}"

    def __str__(self):
        return self.label

    @staticmethod
    def heal_override(entity, opt=None):
        return 0

    @staticmethod
    def start_of_turn(entity, opt=None):
        effect = (opt or {}).get('effect')
        if effect is None:
            return []
        for holder in (effect.target, effect.source):
            if holder is None:
                continue
            try:
                holder.remove_effect(effect)
            except Exception:
                pass
        return []

    @classmethod
    def apply_to(cls, target, source, duration=6):
        effect = cls(source, target)
        target.register_effect('heal_override', cls, effect=effect, source=source, duration=duration)
        if source is not None and source is not target:
            source.register_event_hook('start_of_turn', cls, effect=effect, source=source, duration=duration)
        return effect
