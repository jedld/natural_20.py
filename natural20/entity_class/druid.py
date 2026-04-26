# Druid class mixin (D&D 5e SRD 2014, levels 1-2 only)
#
# Implements:
#   * Level 1 - Druidic (secret nature language; flag only)
#   * Level 1 - Spellcasting (Wisdom; full caster slot table)
#   * Level 2 - Wild Shape (2 uses, recharges on short or long rest;
#     this engine tracks the resource but does not perform the actual
#     beast-form transformation)
#   * Level 2 - Druid Circle (subclass marker; flag only)
from collections import OrderedDict


DRUID_SPELL_SLOT_TABLE = [
  # cantrips, 1st, 2nd, 3rd ... etc
  [2, 2],  # 1
  [2, 3],  # 2
  [2, 4, 2],  # 3
  [3, 4, 3],  # 4
  [3, 4, 3, 2],  # 5
  [3, 4, 3, 3],  # 6
  [3, 4, 3, 3, 1],  # 7
  [3, 4, 3, 3, 2],  # 8
  [3, 4, 3, 3, 3, 1],  # 9
  [4, 4, 3, 3, 3, 2],  # 10
  [4, 4, 3, 3, 3, 2, 1],  # 11
  [4, 4, 3, 3, 3, 2, 1],  # 12
  [4, 4, 3, 3, 3, 2, 1, 1],  # 13
  [4, 4, 3, 3, 3, 2, 1, 1],  # 14
  [4, 4, 3, 3, 3, 2, 1, 1, 1],  # 15
  [4, 4, 3, 3, 3, 2, 1, 1, 1],  # 16
  [4, 4, 3, 3, 3, 2, 1, 1, 1, 1],  # 17
  [4, 4, 3, 3, 3, 3, 1, 1, 1, 1],  # 18
  [4, 4, 3, 3, 3, 3, 2, 1, 1, 1],  # 19
  [4, 4, 3, 3, 3, 3, 2, 2, 1, 1],  # 20
]


WILD_SHAPE_USES = 2  # 2 / short or long rest from L2 onward


class Druid:
  def initialize_druid(self):
    self.spell_slots['druid'] = self.reset_druid_spell_slots()
    if getattr(self, 'wild_shape_count', None) is None:
      self.wild_shape_count = self._wild_shape_max()
    self.wild_shape_max = self._wild_shape_max()

  # ---------------- Spellcasting ----------------

  def druid_spell_attack_modifier(self):
    return self.proficiency_bonus() + self.wis_mod()

  def druid_spell_casting_modifier(self):
    return self.wis_mod()

  def max_slots_for_druid(self, level):
    table = DRUID_SPELL_SLOT_TABLE[self.druid_level - 1]
    # Index 0 is cantrips, levels 1+ map directly.
    return table[level] if 0 <= level < len(table) else 0

  def reset_druid_spell_slots(self):
    return OrderedDict(
      (index, slots)
      for index, slots in enumerate(DRUID_SPELL_SLOT_TABLE[self.druid_level - 1])
    )

  # ---------------- Wild Shape ----------------

  def _wild_shape_max(self):
    if not getattr(self, 'druid_level', 0):
      return 0
    if self.druid_level < 2:
      return 0
    return WILD_SHAPE_USES

  def has_wild_shape(self, qty=1):
    return (self.wild_shape_count or 0) >= qty

  def consume_wild_shape(self, qty=1):
    self.wild_shape_count = max(0, (self.wild_shape_count or 0) - qty)

  # ---------------- Action discovery ----------------

  def special_actions_for_druid(self, session, battle):
    # Druid actions are surfaced via PlayerCharacter.ACTION_LIST; this hook
    # is left empty so the generic class iteration finds a valid (no-op)
    # entry point.
    return []

  # ---------------- Rest hooks ----------------

  def short_rest_for_druid(self, _battle):
    # Wild Shape recharges on a short or long rest.
    self.wild_shape_count = self._wild_shape_max()

  def long_rest_for_druid(self, _battle):
    self.spell_slots['druid'] = self.reset_druid_spell_slots()
    self.wild_shape_count = self._wild_shape_max()
    self.wild_shape_max = self._wild_shape_max()
