def resolve_spell_class_key(spell_slug: str, spell_meta: dict | None = None) -> str:
    """Resolve the spell-loader class name for a YAML spell entry."""
    from natural20.utils.string_utils import classify

    meta = spell_meta or {}
    spell_class_name = meta.get("spell_class")
    if spell_class_name:
        spell_class_key = str(spell_class_name).replace("Natural20::", "")
        if not spell_class_key.endswith("Spell"):
            spell_class_key = f"{spell_class_key}Spell"
        return spell_class_key
    return f"{classify(spell_slug)}Spell"


def spell_is_implemented(spell_slug: str, spell_meta: dict | None = None) -> bool:
    """True when the spell has a loadable class beyond the generic wizard stub."""
    try:
        spell_class = load_spell_class(resolve_spell_class_key(spell_slug, spell_meta))
    except Exception:
        return False
    from natural20.spell.wizard_spells import UtilityWizardSpell

    if spell_class.__module__ == "natural20.spell.wizard_spells":
        return spell_class.resolve is not UtilityWizardSpell.resolve
    return True


_SPELL_CLASSES_CACHE = None


def load_spell_class(spell_name):
    global _SPELL_CLASSES_CACHE
    if _SPELL_CLASSES_CACHE is None:
        _SPELL_CLASSES_CACHE = _build_spell_class_registry()

    if spell_name not in _SPELL_CLASSES_CACHE:
        raise Exception(f"spell class not found {spell_name}")

    return _SPELL_CLASSES_CACHE[spell_name]


def _build_spell_class_registry():
    # Import all spell classes once; registry is reused for every lookup.
    from natural20.spell.shocking_grasp_spell import ShockingGraspSpell
    from natural20.spell.firebolt_spell import FireboltSpell
    from natural20.spell.mage_armor_spell import MageArmorSpell
    from natural20.spell.chill_touch_spell import ChillTouchSpell
    from natural20.spell.expeditious_retreat_spell import ExpeditiousRetreatSpell
    from natural20.spell.magic_missile_spell import MagicMissileSpell
    from natural20.spell.ray_of_frost_spell import RayOfFrostSpell
    from natural20.spell.sacred_flame_spell import SacredFlameSpell
    from natural20.spell.cure_wounds_spell import CureWoundsSpell
    from natural20.spell.guiding_bolt_spell import GuidingBoltSpell
    from natural20.spell.shield_spell import ShieldSpell
    from natural20.spell.bless_spell import BlessSpell
    from natural20.spell.protection_from_poison_spell import ProtectionFromPoisonSpell
    from natural20.spell.toll_the_dead_spell import TollTheDeadSpell
    from natural20.spell.inflict_wounds_spell import InflictWoundsSpell
    from natural20.spell.healing_word_spell import HealingWordSpell
    from natural20.spell.spare_the_dying_spell import SpareTheDyingSpell
    from natural20.spell.ice_knife_spell import IceKnifeSpell
    from natural20.spell.shield_of_faith_spell import ShieldOfFaithSpell
    from natural20.spell.spiritual_weapon_spell import SpiritualWeaponSpell
    from natural20.spell.find_familiar_spell import FindFamiliarSpell
    from natural20.spell.true_strike_spell import TrueStrikeSpell
    from natural20.spell.poison_spray_spell import PoisonSpraySpell
    from natural20.spell.burning_hands_spell import BurningHandsSpell
    from natural20.spell.bane_spell import BaneSpell
    from natural20.spell.resistance_spell import ResistanceSpell
    from natural20.spell.thunderwave_spell import ThunderwaveSpell
    from natural20.spell.eldritch_blast_spell import EldritchBlastSpell
    from natural20.spell.misty_step_spell import MistyStepSpell
    from natural20.spell.mage_hand_spell import MageHandSpell
    from natural20.spell.divine_smite_spell import DivineSmiteSpell
    from natural20.spell.armor_of_agathys_spell import ArmorOfAgathysSpell
    from natural20.spell.guidance_spell import GuidanceSpell
    from natural20.spell.hellish_rebuke_spell import HellishRebukeSpell
    from natural20.spell.darkness_spell import DarknessSpell
    from natural20.spell.silvery_barbs_spell import SilveryBarbsSpell
    from natural20.spell.light_spell import LightSpell
    from natural20.spell.acid_splash_spell import AcidSplashSpell
    from natural20.spell.vicious_mockery_spell import ViciousMockerySpell
    from natural20.spell.divine_favor_spell import DivineFavorSpell
    from natural20.spell.hunters_mark_spell import HuntersMarkSpell
    from natural20.spell.hex_spell import HexSpell
    from natural20.spell.searing_smite_spell import SearingSmiteSpell
    from natural20.spell.false_life_spell import FalseLifeSpell
    from natural20.spell.chromatic_orb_spell import ChromaticOrbSpell
    from natural20.spell.color_spray_spell import ColorSpraySpell
    from natural20.spell.witch_bolt_spell import WitchBoltSpell
    from natural20.spell.grease_spell import GreaseSpell
    from natural20.spell.enlarge_reduce_spell import EnlargeReduceSpell
    from natural20.spell.haste_spell import HasteSpell
    from natural20.spell.slow_spell import SlowSpell
    from natural20.spell.sleep_spell import SleepSpell
    from natural20.spell.polymorph_spell import PolymorphSpell
    from natural20.spell.booming_blade_spell import BoomingBladeSpell
    from natural20.spell.green_flame_blade_spell import GreenFlameBladeSpell
    from natural20.spell.absorb_elements_spell import AbsorbElementsSpell
    from natural20.spell.web_spell import WebSpell
    from natural20.spell.mirror_image_spell import MirrorImageSpell
    from natural20.spell.protection_from_evil_and_good_spell import ProtectionFromEvilAndGoodSpell
    from natural20.spell.hold_person_spell import HoldPersonSpell
    from natural20.spell.blight_spell import BlightSpell
    from natural20.spell.invisibility_spell import InvisibilitySpell, GreaterInvisibilitySpell
    from natural20.spell.wall_of_fire_spell import WallOfFireSpell
    from natural20.spell.tongues_spell import TonguesSpell
    from natural20.spell.detect_magic_spell import DetectMagicSpell
    from natural20.spell.leomunds_tiny_hut_spell import LeomundsTinyHutSpell
    from natural20.spell.message_spell import MessageSpell
    from natural20.spell.stinking_cloud_spell import StinkingCloudSpell
    from natural20.spell.animate_dead_spell import AnimateDeadSpell
    from natural20.spell.spirit_guardians_spell import SpiritGuardiansSpell
    from natural20.spell.revivify_spell import RevivifySpell
    from natural20.spell.mass_healing_word_spell import MassHealingWordSpell
    from natural20.spell.call_lightning_spell import CallLightningSpell
    from natural20.spell.sleet_storm_spell import SleetStormSpell
    from natural20.spell.shining_smite_spell import ShiningSmiteSpell
    from natural20.spell.beacon_of_hope_spell import BeaconOfHopeSpell
    from natural20.spell.daylight_spell import DaylightSpell
    from natural20.spell.remove_curse_spell import RemoveCurseSpell
    from natural20.spell.aura_of_vitality_spell import AuraOfVitalitySpell
    from natural20.spell.faerie_fire_spell import FaerieFireSpell
    from natural20.spell.sanctuary_spell import SanctuarySpell
    from natural20.spell.lesser_restoration_spell import LesserRestorationSpell
    from natural20.spell.ray_of_sickness_spell import RayOfSicknessSpell
    from natural20.spell.melfs_acid_arrow_spell import MelfsAcidArrowSpell
    from natural20.spell.flaming_sphere_spell import FlamingSphereSpell
    import natural20.actions.flaming_sphere_action  # noqa: F401  (registers the bonus-action follow-up)
    from natural20.spell.gaseous_form_spell import GaseousFormSpell
    from natural20.spell.ensnaring_strike_spell import EnsnaringStrikeSpell
    from natural20.spell.hail_of_thorns_spell import HailOfThornsSpell
    from natural20.spell.spike_growth_spell import SpikeGrowthSpell
    from natural20.spell.silence_spell import SilenceSpell
    from natural20.spell.magic_weapon_spell import MagicWeaponSpell
    from natural20.spell.pass_without_trace_spell import PassWithoutTraceSpell
    from natural20.spell.disguise_self_spell import DisguiseSelfSpell
    from natural20.spell.rope_trick_spell import RopeTrickSpell
    from natural20.spell.fear_spell import FearSpell
    from natural20.spell.strike_surge_spell import StrikeSurgeSpell
    from natural20.spell.push_creature_spell import PushCreatureSpell
    import natural20.spell.extensions.weapon_hit_spell  # noqa: F401  (WeaponHitSpellCastAction.apply)
    import natural20.actions.break_free_action  # noqa: F401  (escapable restraints)
    import natural20.actions.attack_surge_action  # noqa: F401  (strike surge follow-up)
    from natural20.spell.condition_spells import ConditionSaveSpell
    from natural20.spell.blink_spell import BlinkSpell
    from natural20.spell.blade_ward_spell import BladeWardSpell
    from natural20.spell.plant_growth_spell import PlantGrowthSpell
    from natural20.spell.detection_spells import ContactOtherPlaneSpell, SenseCreaturesSpell
    from natural20.spell.thunder_step_spell import ThunderStepSpell
    from natural20.spell.sending_spell import SendingSpell
    import natural20.actions.npc_area_action  # noqa: F401  (NpcAreaAction.apply)
    from natural20.spell.synaptic_static_spell import SynapticStaticSpell
    from natural20.spell.seeming_spell import SeemingSpell
    from natural20.spell.summon_spirit_spell import SummonSpiritSpell
    from natural20.spell.utility_spells import (
        FeatherFallSpell,
        IdentifySpell,
        MendingSpell,
        PrestidigitationSpell,
    )
    from natural20.spell.wizard_spells import (
        AganazzarsScorcherSpell,
        BigbysHandSpell,
        ChainLightningSpell,
        CloudkillSpell,
        ComprehendLanguagesSpell,
        ConeOfColdSpell,
        CounterspellSpell,
        DisintegrateSpell,
        DispelMagicSpell,
        FlySpell,
        FireballSpell,
        GustOfWindSpell,
        KnockSpell,
        HideousLaughterSpell,
        BlindnessDeafnessSpell,
        LightningBoltSpell,
        MazeSpell,
        MinorIllusionSpell,
        OtilukesResilientSphereSpell,
        ProtectionFromEnergySpell,
        ScorchingRaySpell,
        SunbeamSpell,
        SunburstSpell,
        TeleportSpell,
        WallOfForceSpell,
    )
    # Create a mapping of spell names to spell classes
    spell_classes = {
        'ShockingGraspSpell': ShockingGraspSpell,
        'FireboltSpell': FireboltSpell,
        'MageArmorSpell': MageArmorSpell,
        'ChillTouchSpell': ChillTouchSpell,
        'ExpeditiousRetreatSpell': ExpeditiousRetreatSpell,
        'MagicMissileSpell': MagicMissileSpell,
        'RayOfFrostSpell': RayOfFrostSpell,
        'ShieldSpell': ShieldSpell,
        'SacredFlameSpell': SacredFlameSpell,
        'CureWoundsSpell': CureWoundsSpell,
        'GuidingBoltSpell': GuidingBoltSpell,
        'BlessSpell': BlessSpell,
        'TollTheDeadSpell': TollTheDeadSpell,
        'InflictWoundsSpell': InflictWoundsSpell,
        'HealingWordSpell': HealingWordSpell,
        'SpareTheDyingSpell': SpareTheDyingSpell,
        'IceKnifeSpell': IceKnifeSpell,
        'ShieldOfFaithSpell': ShieldOfFaithSpell,
        'SpiritualWeaponSpell': SpiritualWeaponSpell,
        'ProtectionFromPoisonSpell': ProtectionFromPoisonSpell,
        'FindFamiliarSpell': FindFamiliarSpell,
        'TrueStrikeSpell': TrueStrikeSpell,
        'PoisonSpraySpell': PoisonSpraySpell,
        'BurningHandsSpell': BurningHandsSpell,
        'BaneSpell': BaneSpell,
        'ResistanceSpell': ResistanceSpell,
        'ThunderwaveSpell': ThunderwaveSpell,
        'EldritchBlastSpell': EldritchBlastSpell,
        'MistyStepSpell': MistyStepSpell,
        'MageHandSpell': MageHandSpell,
        'DivineSmiteSpell': DivineSmiteSpell,
        'ArmorOfAgathysSpell': ArmorOfAgathysSpell,
        'GuidanceSpell': GuidanceSpell,
        'HellishRebukeSpell': HellishRebukeSpell,
        'DarknessSpell': DarknessSpell,
        'SilveryBarbsSpell': SilveryBarbsSpell,
        'LightSpell': LightSpell,
        'AcidSplashSpell': AcidSplashSpell,
        'ViciousMockerySpell': ViciousMockerySpell,
        'DivineFavorSpell': DivineFavorSpell,
        'HuntersMarkSpell': HuntersMarkSpell,
        'HexSpell': HexSpell,
        'SearingSmiteSpell': SearingSmiteSpell,
        'FalseLifeSpell': FalseLifeSpell,
        'ChromaticOrbSpell': ChromaticOrbSpell,
        'ColorSpraySpell': ColorSpraySpell,
        'WitchBoltSpell': WitchBoltSpell,
        'GreaseSpell': GreaseSpell,
        'EnlargeReduceSpell': EnlargeReduceSpell,
        'HasteSpell': HasteSpell,
        'SlowSpell': SlowSpell,
        'SleepSpell': SleepSpell,
        'PolymorphSpell': PolymorphSpell,
        'BoomingBladeSpell': BoomingBladeSpell,
        'GreenFlameBladeSpell': GreenFlameBladeSpell,
        'AbsorbElementsSpell': AbsorbElementsSpell,
        'WebSpell': WebSpell,
        'MirrorImageSpell': MirrorImageSpell,
        'ProtectionFromEvilAndGoodSpell': ProtectionFromEvilAndGoodSpell,
        'HoldPersonSpell': HoldPersonSpell,
        'BlightSpell': BlightSpell,
        'InvisibilitySpell': InvisibilitySpell,
        'GreaterInvisibilitySpell': GreaterInvisibilitySpell,
        'WallOfFireSpell': WallOfFireSpell,
        'TonguesSpell': TonguesSpell,
        'AganazzarsScorcherSpell': AganazzarsScorcherSpell,
        'AnimateDeadSpell': AnimateDeadSpell,
        'BanishmentSpell': ConditionSaveSpell,
        'BigbysHandSpell': BigbysHandSpell,
        'ChainLightningSpell': ChainLightningSpell,
        'CloudkillSpell': CloudkillSpell,
        'ComprehendLanguagesSpell': ComprehendLanguagesSpell,
        'ConeOfColdSpell': ConeOfColdSpell,
        'CounterspellSpell': CounterspellSpell,
        'DetectMagicSpell': DetectMagicSpell,
        'DisintegrateSpell': DisintegrateSpell,
        'DispelMagicSpell': DispelMagicSpell,
        'FeatherFallSpell': FeatherFallSpell,
        'FlySpell': FlySpell,
        'FireballSpell': FireballSpell,
        'GustOfWindSpell': GustOfWindSpell,
        'KnockSpell': KnockSpell,
        'HideousLaughterSpell': HideousLaughterSpell,
        'BlindnessDeafnessSpell': BlindnessDeafnessSpell,
        'LeomundsTinyHutSpell': LeomundsTinyHutSpell,
        'LightningBoltSpell': LightningBoltSpell,
        'MazeSpell': MazeSpell,
        'MelfsAcidArrowSpell': MelfsAcidArrowSpell,
        'MessageSpell': MessageSpell,
        'MinorIllusionSpell': MinorIllusionSpell,
        'OtilukesResilientSphereSpell': OtilukesResilientSphereSpell,
        'PrestidigitationSpell': PrestidigitationSpell,
        'ProtectionFromEnergySpell': ProtectionFromEnergySpell,
        'ScorchingRaySpell': ScorchingRaySpell,
        'StinkingCloudSpell': StinkingCloudSpell,
        'SunbeamSpell': SunbeamSpell,
        'SunburstSpell': SunburstSpell,
        'TeleportSpell': TeleportSpell,
        'WallOfForceSpell': WallOfForceSpell,
        'SpiritGuardiansSpell': SpiritGuardiansSpell,
        'RevivifySpell': RevivifySpell,
        'MassHealingWordSpell': MassHealingWordSpell,
        'CallLightningSpell': CallLightningSpell,
        'SleetStormSpell': SleetStormSpell,
        'ShiningSmiteSpell': ShiningSmiteSpell,
        'BeaconOfHopeSpell': BeaconOfHopeSpell,
        'DaylightSpell': DaylightSpell,
        'RemoveCurseSpell': RemoveCurseSpell,
        'AuraOfVitalitySpell': AuraOfVitalitySpell,
        'FaerieFireSpell': FaerieFireSpell,
        'SanctuarySpell': SanctuarySpell,
        'LesserRestorationSpell': LesserRestorationSpell,
        'RayOfSicknessSpell': RayOfSicknessSpell,
        'FlamingSphereSpell': FlamingSphereSpell,
        'GaseousFormSpell': GaseousFormSpell,
        'IdentifySpell': IdentifySpell,
        'MendingSpell': MendingSpell,
        'EnsnaringStrikeSpell': EnsnaringStrikeSpell,
        'HailOfThornsSpell': HailOfThornsSpell,
        'SpikeGrowthSpell': SpikeGrowthSpell,
        'SilenceSpell': SilenceSpell,
        'MagicWeaponSpell': MagicWeaponSpell,
        'PassWithoutTraceSpell': PassWithoutTraceSpell,
        'DisguiseSelfSpell': DisguiseSelfSpell,
        'RopeTrickSpell': RopeTrickSpell,
        'FearSpell': FearSpell,
        'StrikeSurgeSpell': StrikeSurgeSpell,
        'PushCreatureSpell': PushCreatureSpell,
        'ConditionSaveSpell': ConditionSaveSpell,
        'HoldMonsterSpell': ConditionSaveSpell,
        'HypnoticPatternSpell': ConditionSaveSpell,
        'DominateBeastSpell': ConditionSaveSpell,
        'DominatePersonSpell': ConditionSaveSpell,
        'DominateMonsterSpell': ConditionSaveSpell,
        'PhantasmalForceSpell': ConditionSaveSpell,
        'CalmEmotionsSpell': ConditionSaveSpell,
        'BlinkSpell': BlinkSpell,
        'BladeWardSpell': BladeWardSpell,
        'PlantGrowthSpell': PlantGrowthSpell,
        'SenseCreaturesSpell': SenseCreaturesSpell,
        'DetectEvilAndGoodSpell': SenseCreaturesSpell,
        'DetectPoisonAndDiseaseSpell': SenseCreaturesSpell,
        'ContactOtherPlaneSpell': ContactOtherPlaneSpell,
        'ThunderStepSpell': ThunderStepSpell,
        'DimensionDoorSpell': MistyStepSpell,
        'SendingSpell': SendingSpell,
        'SynapticStaticSpell': SynapticStaticSpell,
        'SeemingSpell': SeemingSpell,
        'SummonSpiritSpell': SummonSpiritSpell,
        'SummonFiendSpell': SummonSpiritSpell,
    }
    return spell_classes


def register_serializable_effects():
    """Phase 4: register a curated set of effect classes with the
    serialization registry. Idempotent — safe to call multiple times.

    Only effects that already implement ``to_dict``/``from_dict`` are
    registered. Other spells keep using their existing serialization
    paths untouched.
    """
    from natural20.utils.effect_registry import register_effect
    # Lazy imports so the registry stays self-contained.
    from natural20.spell.bless_spell import BlessSpell
    from natural20.spell.bane_spell import BaneSpell
    from natural20.spell.mage_armor_spell import MageArmorSpell
    from natural20.spell.resistance_spell import ResistanceSpell
    from natural20.spell.guidance_spell import GuidanceSpell
    from natural20.spell.spell import Spell

    register_effect('bless', BlessSpell)
    register_effect('bane', BaneSpell)
    register_effect('mage_armor', MageArmorSpell)
    register_effect('resistance', ResistanceSpell)
    register_effect('guidance', GuidanceSpell)
    register_effect('spell', Spell)


# Note: not auto-registered on import to avoid eager spell-module loads
# (some spell modules import from natural20.battle/entity which import
# spell_loader transitively). Callers (Session/tests) opt in by calling
# ``register_serializable_effects()`` explicitly.
