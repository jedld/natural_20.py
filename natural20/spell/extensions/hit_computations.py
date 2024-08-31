
from natural20.utils.spell_attack_util import evaluate_spell_attack
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

        _, attack_roll, _, _, _ = evaluate_spell_attack(battle, self.source, self.action.target, self.properties)
        target_ac, _cover_ac = effective_ac(battle, self.source, self.action.target)
        return attack_roll.prob(target_ac)

    def avg_damage(self, battle, opts=None):
        """
        Compute the average damage of the spell. This should be overridden by subclasses.

        Args:
            battle: The battle context
            opts: Additional options

        return 0
        """