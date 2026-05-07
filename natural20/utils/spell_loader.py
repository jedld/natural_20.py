def load_spell_class(spell_name):
    # Import all spell classes
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
    from natural20.spell.false_life_spell import FalseLifeSpell
    from natural20.spell.chromatic_orb_spell import ChromaticOrbSpell
    from natural20.spell.color_spray_spell import ColorSpraySpell
    from natural20.spell.witch_bolt_spell import WitchBoltSpell
    from natural20.spell.grease_spell import GreaseSpell
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
        'FalseLifeSpell': FalseLifeSpell,
        'ChromaticOrbSpell': ChromaticOrbSpell,
        'ColorSpraySpell': ColorSpraySpell,
        'WitchBoltSpell': WitchBoltSpell,
        'GreaseSpell': GreaseSpell,
    }

    if spell_name not in spell_classes:
        raise Exception(f"spell class not found {spell_name}")

    return spell_classes[spell_name]


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
