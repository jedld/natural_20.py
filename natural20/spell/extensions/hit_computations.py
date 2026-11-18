
from natural20.utils.spell_attack_util import evaluate_spell_attack
from natural20.weapons import damage_modifier, target_advantage_condition
from natural20.utils.ac_utils import effective_ac
from natural20.spell.spell import Spell

class AttackSpell(Spell):
    """
    A spell that requires an attack roll. This class provides the default implementation for computing hit probability
    and average damage.

    Mainly used for spells like Firebolt, Ray of Frost, etc.

    Useful for building spells that require attack rolls and allows for a
    statistical analysis of the spell's effectiveness that can be used
    for AI and as assistive information for human players.
    """

    def compute_hit_probability(self, battle, opts = None):
        """
        Compute the hit probability of the spell

        Args:
            battle: The battle context
            opts: Additional options

        Returns:
            The hit probability of the spell
        """
        if opts is None:
            opts = {}

        target = self._primary_target()
        if target is None:
            return 0.0
        # Estimate analytically: scoring must not roll game dice or run the
        # full attack pipeline (luck windows, one-shot effects).
        from natural20.die_roll import DieRoll
        advantage_mod, adv_info = target_advantage_condition(
            self.session, self.source, target, self.properties, battle=battle, overrides=opts)
        caster = self.source
        if getattr(caster, 'familiar', None) and caster.familiar():
            caster = caster.owner
        attack_mod = caster.spell_attack_modifier_for(self.properties)
        target_ac, _cover_ac = effective_ac(battle, self.source, target, spell_attack=True)
        return DieRoll.estimate(DieRoll.d20(attack_mod),
                                advantage=advantage_mod > 0,
                                disadvantage=advantage_mod < 0).prob(target_ac)

    def _primary_target(self):
        """Multi-target selections (e.g. Scorching Ray rays) arrive as a list or tuple."""
        target = self.action.target if self.action else None
        if isinstance(target, (list, tuple)):
            return next((t for t in target if hasattr(t, 'entity_uid')), None)
        return target

    def compute_advantage_info(self, battle, opts=None):
        target = self._primary_target()
        if target is None:
            return 0, [[], []], 0
        advantage_mod, adv_info = target_advantage_condition(self.session, self.source, target, self.properties, battle=battle, overrides=opts)
        return advantage_mod, adv_info, 0

    def avg_damage(self, battle, opts=None):
        """
        Compute the average damage of the spell. This should be overridden by subclasses.

        Args:
            battle: The battle context
            opts: Additional options

        return 0
        """
        return 0