"""Abstract ruleset interface — hooks only for verified 2014 vs 2024 divergences."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Ruleset(ABC):
    """Edition-specific behavior for a campaign.

    Defaults should match 2014 SRD. ``Ruleset2024`` overrides only what SRD 5.2
    actually changed. Content deltas (class YAML, weapons, spells) live in
    ``templates/rulesets/<id>/`` overlays, not in this class.
    """

    def __init__(self, overrides: dict[str, Any] | None = None):
        self._overrides = dict(overrides or {})

    @property
    @abstractmethod
    def name(self) -> str:
        """Ruleset identifier, e.g. ``5e-2014`` or ``5e-2024``."""

    def _override(self, key: str, default: Any) -> Any:
        if key in self._overrides:
            return self._overrides[key]
        return default

    # --- Character HP ---
    def hp_per_level_strategy(self) -> str:
        """``roll`` (2014 default) or ``average`` (2024 printed default)."""
        return self._override("hp_per_level_strategy", "roll")

    # --- Combat actions ---
    def standard_actions(self) -> list[str]:
        return self._override(
            "standard_actions",
            [
                "attack",
                "cast_spell",
                "dash",
                "disengage",
                "dodge",
                "help",
                "hide",
                "ready",
                "search",
                "use_object",
                "improvise",
            ],
        )

    def unarmed_strike_modes(self) -> list[str]:
        """2014: attack only. 2024: attack / grapple / shove."""
        return self._override("unarmed_strike_modes", ["attack"])

    def grapple_shove_resolution(self) -> str:
        """``contested_check`` (2014) or ``target_saving_throw`` (2024)."""
        return self._override("grapple_shove_resolution", "contested_check")

    def two_weapon_fighting_model(self) -> str:
        """``bonus_action`` (2014) or ``attack_action_light`` (2024)."""
        return self._override("two_weapon_fighting_model", "bonus_action")

    def surprise_model(self) -> str:
        """``lose_turn`` (2014) or ``initiative_disadvantage`` (2024)."""
        return self._override("surprise_model", "lose_turn")

    def help_action_requires_adjacent(self) -> bool:
        return bool(self._override("help_action_requires_adjacent", True))

    # --- Spells ---
    def counterspell_resolution(self) -> str:
        """``auto_at_or_above`` (2014) or ``caster_con_save`` (2024)."""
        return self._override("counterspell_resolution", "auto_at_or_above")

    def spell_grouping(self) -> str:
        """``per_class`` (2014) or ``arcane_divine_primal`` (2024)."""
        return self._override("spell_grouping", "per_class")

    # --- Species / Background ---
    def ability_bonus_source(self) -> str:
        """``species`` (2014) or ``background`` (2024)."""
        return self._override("ability_bonus_source", "species")

    # --- Conditions / resources ---
    def exhaustion_model(self) -> str:
        """``legacy`` (2014) or ``levels_1_to_6_minus_2_per_level`` (2024)."""
        return self._override("exhaustion_model", "legacy")

    def heroic_inspiration_enabled(self) -> bool:
        return bool(self._override("heroic_inspiration_enabled", False))

    def d20_test_exhaustion_penalty(self, exhaustion_level: int) -> int:
        """Modifier applied to attack rolls, checks, saves, and initiative."""
        if self.exhaustion_model() != "levels_1_to_6_minus_2_per_level":
            return 0
        level = max(0, int(exhaustion_level or 0))
        return -2 * level

    def alert_feat_model(self) -> str:
        """``plus_five`` (2014) or ``proficiency_bonus_and_swap`` (2024)."""
        return self._override("alert_feat_model", "plus_five")

    # --- Class feature dispatchers ---
    def paladin_smite_is_spell(self) -> bool:
        return bool(self._override("paladin_smite_is_spell", False))

    def cleric_channel_divinity_level(self) -> int:
        return int(self._override("cleric_channel_divinity_level", 2))

    def monk_resource_name(self) -> str:
        return str(self._override("monk_resource_name", "ki"))

    def weapon_mastery_enabled(self) -> bool:
        return bool(self._override("weapon_mastery_enabled", False))

    def phb_2024_grapple_move_cost(self) -> bool:
        """Size-based grappling movement cost from 2024 rules."""
        return bool(self._override("phb_2024_grapple_move_cost", False))
