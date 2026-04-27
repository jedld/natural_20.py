"""DamageScalingMixin — eliminates per-spell ``at_level`` arithmetic.

Many leveled-spell classes copy/paste the same pattern::

    at_level = opts.get('at_level', getattr(self.action, 'at_level', None))
    if not at_level or at_level < 1:
        at_level = self.properties.get('level', 1) or 1
    dice = base + max(0, at_level - base_level)

This mixin centralizes that computation so a spell becomes::

    class MySpell(DamageScalingMixin, Spell):
        BASE_DAMAGE = "3d6"
        PER_SLOT_DAMAGE = "1d6"

        def _damage(self, battle, **kw):
            return self._scaled_damage_roll(battle, **kw)

…or, for callers that want the dice expression string:

    expr = self._scaled_damage_dice("3d6", "1d6", at_level)
"""

from natural20.die_roll import DieRoll

__all__ = ["DamageScalingMixin"]


def _parse_dice(expr: str):
    """Parse a simple ``NdM`` expression into ``(N, M)``."""
    expr = expr.strip().lower()
    if 'd' not in expr:
        raise ValueError(f"unsupported dice expression: {expr!r}")
    n_str, m_str = expr.split('d', 1)
    n = int(n_str) if n_str else 1
    m = int(m_str)
    return n, m


class DamageScalingMixin:
    """Mixin providing slot-level damage helpers.

    Spells inheriting from :class:`Spell` get four small utilities; none
    is required, all are opt-in.
    """

    # ---- slot-level resolution -----------------------------------------

    def _resolve_at_level(self, opts=None) -> int:
        """Return the effective slot level used to cast this spell.

        Resolution order: explicit ``opts['at_level']`` → spell action's
        ``at_level`` attribute → the spell's base ``level`` from YAML
        (minimum 1 for leveled spells, 0 for cantrips).
        """
        if opts and opts.get('at_level') is not None:
            return int(opts['at_level'])
        action_level = getattr(getattr(self, 'action', None), 'at_level', None)
        if action_level is not None and action_level >= 1:
            return int(action_level)
        base = self.properties.get('level', 1) if hasattr(self, 'properties') else 1
        if base is None:
            base = 1
        return int(base) if base >= 1 else 0

    # ---- dice expression / DieRoll helpers -----------------------------

    @staticmethod
    def _scaled_damage_dice(base_dice: str, per_slot_dice: str,
                            at_level: int, base_level: int = 1) -> str:
        """Return the dice expression scaled for ``at_level``.

        ``base_dice`` is rolled once. For each slot level above
        ``base_level`` an additional ``per_slot_dice`` worth of dice are
        added (same die size required).
        """
        base_n, base_m = _parse_dice(base_dice)
        per_n, per_m = _parse_dice(per_slot_dice)
        if base_m != per_m:
            raise ValueError(
                f"die size mismatch: base={base_dice} per_slot={per_slot_dice}")
        extra_levels = max(0, int(at_level) - int(base_level))
        total_n = base_n + per_n * extra_levels
        return f"{total_n}d{base_m}"

    def _scaled_damage_roll(self, battle, base_dice: str, per_slot_dice: str,
                            *, at_level=None, opts=None,
                            crit: bool = False, description: str = "",
                            base_level: int = 1):
        """Roll ``base_dice + (slot - base_level) * per_slot_dice``.

        ``at_level`` may be supplied explicitly; otherwise resolved via
        :py:meth:`_resolve_at_level` from ``opts`` / spell action.
        """
        if at_level is None:
            at_level = self._resolve_at_level(opts)
        expr = self._scaled_damage_dice(base_dice, per_slot_dice,
                                        at_level, base_level=base_level)
        return DieRoll.roll(expr, crit=crit, battle=battle,
                            entity=getattr(self, 'source', None),
                            description=description)
