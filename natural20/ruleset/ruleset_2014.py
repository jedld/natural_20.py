"""D&D 5e 2014 SRD (SRD 5.1) — default campaign ruleset."""

from natural20.ruleset.base import Ruleset


class Ruleset2014(Ruleset):
    """Mirrors current engine behavior (implicit 2014 SRD)."""

    @property
    def name(self) -> str:
        return "5e-2014"
