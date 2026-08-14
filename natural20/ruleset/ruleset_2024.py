"""D&D 5e 2024 rules (SRD 5.2) — overrides only verified divergences."""

from natural20.ruleset.ruleset_2014 import Ruleset2014


class Ruleset2024(Ruleset2014):
    """2024 / SRD 5.2 ruleset. Inherits 2014 and overrides changed hooks."""

    @property
    def name(self) -> str:
        return "5e-2024"

    def hp_per_level_strategy(self) -> str:
        return self._override("hp_per_level_strategy", "average")

    def standard_actions(self) -> list[str]:
        base = super().standard_actions()
        extras = ["influence", "study", "utilize", "magic"]
        merged = list(base)
        for name in extras:
            if name not in merged:
                merged.append(name)
        return self._override("standard_actions", merged)

    def unarmed_strike_modes(self) -> list[str]:
        return self._override("unarmed_strike_modes", ["attack", "grapple", "shove"])

    def grapple_shove_resolution(self) -> str:
        return self._override("grapple_shove_resolution", "target_saving_throw")

    def two_weapon_fighting_model(self) -> str:
        return self._override("two_weapon_fighting_model", "attack_action_light")

    def surprise_model(self) -> str:
        return self._override("surprise_model", "initiative_disadvantage")

    def counterspell_resolution(self) -> str:
        return self._override("counterspell_resolution", "caster_con_save")

    def spell_grouping(self) -> str:
        return self._override("spell_grouping", "arcane_divine_primal")

    def ability_bonus_source(self) -> str:
        return self._override("ability_bonus_source", "background")

    def exhaustion_model(self) -> str:
        return self._override("exhaustion_model", "levels_1_to_6_minus_2_per_level")

    def heroic_inspiration_enabled(self) -> bool:
        return bool(self._override("heroic_inspiration_enabled", True))

    def alert_feat_model(self) -> str:
        return self._override("alert_feat_model", "proficiency_bonus_and_swap")

    def paladin_smite_is_spell(self) -> bool:
        return bool(self._override("paladin_smite_is_spell", True))

    def cleric_channel_divinity_level(self) -> int:
        return int(self._override("cleric_channel_divinity_level", 1))

    def monk_resource_name(self) -> str:
        return str(self._override("monk_resource_name", "focus"))

    def weapon_mastery_enabled(self) -> bool:
        return bool(self._override("weapon_mastery_enabled", True))

    def phb_2024_grapple_move_cost(self) -> bool:
        return bool(self._override("phb_2024_grapple_move_cost", True))
