# Bard class mixin (D&D 5e SRD 2014, levels 1-2 only)
#
# Implements:
#   * Level 1 - Spellcasting (Charisma; full caster slot table)
#   * Level 1 - Bardic Inspiration (CHA-mod uses, recharges on long rest;
#     1d6 die at levels 1-4)
#   * Level 2 - Jack of All Trades (add half proficiency bonus to ability
#     checks not already proficient in)
#   * Level 2 - Song of Rest (1d6 added per HD spent on a short rest)
from collections import OrderedDict


BARD_SPELL_SLOT_TABLE = [
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
  [4, 4, 3, 3, 3, 3, 2, 2, 1, 1]  # 20
]


# Bardic Inspiration die size by bard level (per SRD).
BARDIC_INSPIRATION_DIE = [
  '1d6',  # 1
  '1d6',  # 2
  '1d6',  # 3
  '1d6',  # 4
  '1d8',  # 5
  '1d8',  # 6
  '1d8',  # 7
  '1d8',  # 8
  '1d8',  # 9
  '1d10',  # 10
  '1d10',  # 11
  '1d10',  # 12
  '1d10',  # 13
  '1d10',  # 14
  '1d12',  # 15
  '1d12',  # 16
  '1d12',  # 17
  '1d12',  # 18
  '1d12',  # 19
  '1d12',  # 20
]


class Bard:
  def initialize_bard(self):
    self.spell_slots['bard'] = self.reset_bard_spell_slots()
    # Bardic Inspiration uses = max(1, CHA mod); refreshes on long rest
    # (and short rest at L5+).
    if getattr(self, 'bardic_inspiration_count', None) is None:
      self.bardic_inspiration_count = self._bardic_inspiration_max()
    self.bardic_inspiration_max = self._bardic_inspiration_max()

  # ---------------- Spellcasting ----------------

  def bard_spell_attack_modifier(self):
    return self.proficiency_bonus() + self.cha_mod()

  def bard_spell_casting_modifier(self):
    return self.cha_mod()

  def max_slots_for_bard(self, level):
    table = BARD_SPELL_SLOT_TABLE[self.bard_level - 1]
    # Index 0 holds the cantrip count; spell levels 1+ map to table[level].
    return table[level] if 0 <= level < len(table) else 0

  def reset_bard_spell_slots(self):
    return OrderedDict(
      (index, slots)
      for index, slots in enumerate(BARD_SPELL_SLOT_TABLE[self.bard_level - 1])
    )

  # ---------------- Bardic Inspiration ----------------

  def _bardic_inspiration_max(self):
    return max(1, self.cha_mod())

  def bardic_inspiration_die(self):
    if not getattr(self, 'bard_level', None):
      return None
    idx = max(1, min(self.bard_level, len(BARDIC_INSPIRATION_DIE))) - 1
    return BARDIC_INSPIRATION_DIE[idx]

  def has_bardic_inspiration(self, qty=1):
    return (self.bardic_inspiration_count or 0) >= qty

  def consume_bardic_inspiration(self, qty=1):
    self.bardic_inspiration_count = max(
      0, (self.bardic_inspiration_count or 0) - qty
    )

  # ---------------- Jack of All Trades ----------------

  def jack_of_all_trades_bonus(self):
    """Half proficiency bonus (rounded down) when the bard has Jack of All
    Trades.  Returns 0 otherwise."""
    if not self.class_feature('jack_of_all_trades'):
      return 0
    return self.proficiency_bonus() // 2

  # ---------------- Action discovery ----------------

  def special_actions_for_bard(self, session, battle):
    # Bard actions are surfaced via PlayerCharacter.ACTION_LIST; this hook is
    # left empty so multi-class characters using the generic iteration still
    # find a valid (no-op) entry point.
    return []

  # ---------------- Rest hooks ----------------

  def short_rest_for_bard(self, _battle):
    # At L5+ Bardic Inspiration recharges on a short or long rest.  Below
    # that level the feature only refreshes on a long rest.
    if getattr(self, 'bard_level', 0) >= 5:
      self.bardic_inspiration_count = self._bardic_inspiration_max()

  def long_rest_for_bard(self, _battle):
    self.spell_slots['bard'] = self.reset_bard_spell_slots()
    self.bardic_inspiration_count = self._bardic_inspiration_max()
    self.bardic_inspiration_max = self._bardic_inspiration_max()
