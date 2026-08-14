"""Factory for campaign ruleset instances."""

from __future__ import annotations

from typing import Any

from natural20.ruleset.base import Ruleset
from natural20.ruleset.ruleset_2014 import Ruleset2014
from natural20.ruleset.ruleset_2024 import Ruleset2024

RULESET_IDS = ("5e-2014", "5e-2024")

_REGISTRY: dict[str, type[Ruleset]] = {
    "5e-2014": Ruleset2014,
    "5e-2024": Ruleset2024,
    # Aliases
    "2014": Ruleset2014,
    "2024": Ruleset2024,
    "srd-5.1": Ruleset2014,
    "srd-5.2": Ruleset2024,
}


def normalize_ruleset_id(ruleset_id: str | None) -> str:
    if not ruleset_id:
        return "5e-2014"
    key = str(ruleset_id).strip().lower()
    aliases = {
        "5e-2014": "5e-2014",
        "2014": "5e-2014",
        "srd-5.1": "5e-2014",
        "srd5.1": "5e-2014",
        "5e-2024": "5e-2024",
        "2024": "5e-2024",
        "srd-5.2": "5e-2024",
        "srd5.2": "5e-2024",
        "srd-5.2.1": "5e-2024",
    }
    return aliases.get(key, "5e-2014" if key not in _REGISTRY else key)


def get_ruleset(
    ruleset: str | Ruleset | None = None,
    *,
    overrides: dict[str, Any] | None = None,
) -> Ruleset:
    """Return a Ruleset instance for *ruleset* id or pass through an instance."""
    if isinstance(ruleset, Ruleset):
        if overrides:
            # Re-wrap with overrides if a bare instance was passed without them.
            return type(ruleset)(overrides=overrides)
        return ruleset

    ruleset_id = normalize_ruleset_id(ruleset)
    cls = _REGISTRY.get(ruleset_id, Ruleset2014)
    # Prefer canonical class for normalized id
    if ruleset_id == "5e-2024":
        cls = Ruleset2024
    elif ruleset_id == "5e-2014":
        cls = Ruleset2014
    return cls(overrides=overrides)
