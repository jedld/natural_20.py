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
        'BurningHandsSpell': BurningHandsSpell
    }

    if spell_name not in spell_classes:
        raise Exception(f"spell class not found {spell_name}")

    return spell_classes[spell_name]
