def load_spell_class(spell_name):
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

  if spell_name == 'ShockingGraspSpell':
      spell_class = ShockingGraspSpell
  elif spell_name == 'FireboltSpell':
      spell_class = FireboltSpell
  elif spell_name == 'MageArmorSpell':
      spell_class = MageArmorSpell
  elif spell_name == 'ChillTouchSpell':
      spell_class = ChillTouchSpell
  elif spell_name == 'ExpeditiousRetreatSpell':
      spell_class = ExpeditiousRetreatSpell
  elif spell_name == 'MagicMissileSpell':
      spell_class = MagicMissileSpell
  elif spell_name == 'RayOfFrostSpell':
      spell_class = RayOfFrostSpell
  elif spell_name == 'ShieldSpell':
      spell_class = ShieldSpell
  elif spell_name == 'SacredFlameSpell':
      spell_class = SacredFlameSpell
  elif spell_name == 'CureWoundsSpell':
      spell_class = CureWoundsSpell
  elif spell_name == 'GuidingBoltSpell':
      spell_class = GuidingBoltSpell
  elif spell_name == 'BlessSpell':
      spell_class = BlessSpell
  elif spell_name == 'TollTheDeadSpell':
      spell_class = TollTheDeadSpell
  elif spell_name == 'InflictWoundsSpell':
      spell_class = InflictWoundsSpell
  elif spell_name == 'HealingWordSpell':
      spell_class = HealingWordSpell
  elif spell_name == 'SpareTheDyingSpell':
      spell_class = SpareTheDyingSpell
  elif spell_name == 'IceKnifeSpell':
      spell_class = IceKnifeSpell
  elif spell_name == 'ShieldOfFaithSpell':
      spell_class = ShieldOfFaithSpell
  elif spell_name == 'SpiritualWeaponSpell':
      spell_class = SpiritualWeaponSpell
  elif spell_name == 'ProtectionFromPoisonSpell':
      spell_class = ProtectionFromPoisonSpell
  else:
      raise Exception(f"spell class not found {spell_name}")
  
  return spell_class
