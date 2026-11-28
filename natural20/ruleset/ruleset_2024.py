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

    def sacred_weapon_model(self) -> str:
        return self._override("sacred_weapon_model", "attack_action")

    def two_weapon_fighting_model(self) -> str:
        return self._override("two_weapon_fighting_model", "attack_action_light")

    def surprise_model(self) -> str:
        return self._override("surprise_model", "initiative_disadvantage")

    def counterspell_resolution(self) -> str:
        return self._override("counterspell_resolution", "caster_con_save")

    def mirror_image_model(self) -> str:
        return self._override("mirror_image_model", "d6_on_hit")

    def spells_per_turn_model(self) -> str:
        return self._override("spells_per_turn_model", "one_slot_per_turn")

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

    def stones_endurance_uses_model(self) -> str:
        return str(self._override("stones_endurance_uses_model", "proficiency_per_long_rest"))

    def phb_2024_grapple_move_cost(self) -> bool:
        return bool(self._override("phb_2024_grapple_move_cost", True))

    def grappled_attack_disadvantage(self) -> bool:
        return bool(self._override("grappled_attack_disadvantage", True))

    def squeeze_attack_modifiers(self) -> bool:
        return bool(self._override("squeeze_attack_modifiers", False))

    def shield_ac_bonus(self) -> int:
        return int(self._override("shield_ac_bonus", 2))

    # --- Wild Shape (Druid), PHB 2024 ---
    _MOON_WILD_SHAPE_CR_2024 = ((18, 6.0), (15, 5.0), (12, 4.0), (9, 3.0), (6, 2.0), (3, 1.0))

    def wild_shape_max_cr(self, druid_level: int, subclass: str | None = None) -> float:
        """PHB 2024 Beast Shapes: CR 1/4 at 2-3, 1/2 at 4-7, 1 at 8+.
        Circle of the Moon: CR 1 at 3, then +1 CR at 6/9/12/15/18 (max 6)."""
        moon = bool(subclass) and "moon" in str(subclass).lower()
        if moon:
            for level, cr in self._MOON_WILD_SHAPE_CR_2024:
                if druid_level >= level:
                    return cr
            return 0.25
        if druid_level >= 8:
            return 1.0
        if druid_level >= 4:
            return 0.5
        return 0.25

    def wild_shape_swim_level(self, subclass: str | None = None) -> int:
        """2024 Wild Shape has no swim-speed restriction."""
        return 2

    def wild_shape_uses(self, druid_level: int) -> int:
        """PHB 2024 Druid Features table: 2 uses at 2, 3 at 6, 4 at 17."""
        if druid_level >= 17:
            return 4
        if druid_level >= 6:
            return 3
        return 2 if druid_level >= 2 else 0

    def wild_shape_short_rest_recharge(self) -> str:
        """2024: regain one expended use per short rest (all on a long rest)."""
        return "one"
