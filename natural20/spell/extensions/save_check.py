"""SaveCheck — uniform "target makes a save vs DC" helper for spells.

Wraps :py:meth:`natural20.entity.Entity.save_throw` and DC comparison so
spell authors stop re-implementing the same `save_result < dc` pattern.

Also exposes a hook point: any effect registered with ``eval_effect`` key
``save_modifier`` is consulted from inside ``Entity.save_throw`` and may
return a numeric bonus / penalty applied to the rolled result.  See
:py:meth:`natural20.entity.Entity.save_throw`.
"""

from typing import Optional, Any

__all__ = ["SaveCheck", "SaveResult"]


class SaveResult:
    """Outcome of a saving throw."""

    __slots__ = ("passed", "roll", "dc", "ability", "auto_failed")

    def __init__(self, passed: bool, roll, dc: int, ability: str,
                 auto_failed: bool = False):
        self.passed = passed
        self.roll = roll
        self.dc = dc
        self.ability = ability
        self.auto_failed = auto_failed

    def __bool__(self) -> bool:  # ``if result:`` reads as "saved"
        return self.passed

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (f"SaveResult(passed={self.passed}, roll={self.roll}, "
                f"dc={self.dc}, ability={self.ability!r})")


class SaveCheck:
    """Static helper — call :py:meth:`make` to roll a save."""

    @staticmethod
    def make(entity, ability: str, dc: int, battle=None,
             opts: Optional[dict] = None,
             auto_fail_if_unconscious: bool = True) -> SaveResult:
        """Roll ``ability`` save for ``entity`` and compare to ``dc``.

        Parameters mirror the existing :py:meth:`Entity.save_throw` API.
        ``auto_fail_if_unconscious`` mirrors 5e RAW (incapacitated/
        unconscious creatures auto-fail Str/Dex saves; downstream callers
        already pre-check this for many spells, so the default keeps
        existing behavior for callers that hand off the decision).
        """
        if opts is None:
            opts = {}

        # Auto-fail on Str/Dex while unconscious; other ability saves still
        # roll (so that, e.g., Wisdom saves vs. Hold Person aren't bypassed
        # by a downed target — but in practice Hold Person already requires
        # an in-progress effect to matter).
        if (auto_fail_if_unconscious
                and ability in ('strength', 'dexterity')
                and hasattr(entity, 'conscious')
                and not entity.conscious()):
            return SaveResult(passed=False, roll=None, dc=dc,
                              ability=ability, auto_failed=True)

        roll = entity.save_throw(ability, battle, opts)
        passed = not (roll < dc)
        return SaveResult(passed=passed, roll=roll, dc=dc, ability=ability)
