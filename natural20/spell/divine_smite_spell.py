from natural20.spell.spell import Spell


class DivineSmiteSpell(Spell):
    """Placeholder spell class for Divine Smite reactions."""

    def build_map(self, orig_action):
        return orig_action

    def compute_hit_probability(self, battle, opts=None):
        # Triggered after a hit, so treated as guaranteed.
        return 1.0

    def avg_damage(self, battle, opts=None):
        at_level = None
        if opts and 'slot_level' in opts:
            at_level = opts['slot_level']
        if at_level is None and self.action is not None:
            at_level = getattr(self.action, 'at_level', self.properties.get('level', 1))
        if at_level is None:
            at_level = self.properties.get('level', 1)
        dice = 2 + max(0, at_level - 1)
        # Average of d8 is 4.5; undead/fiend bonus handled at runtime.
        return dice * 4.5

    def resolve(self, entity, battle, spell_action, battle_map):
        # Divine Smite resolution is handled via DivineSmiteAction.
        return []
