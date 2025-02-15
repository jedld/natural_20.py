from collections import OrderedDict
# import pdb

BARD_SPELL_SLOT_TABLE = [
  # cantrips, 1st, 2nd, 3rd ... etc
  [3, 2],  # 1
  [3, 3],  # 2
  [3, 4, 2],  # 3
  [4, 4, 3],  # 4
  [4, 4, 3, 2],  # 5
  [4, 4, 3, 3],  # 6
  [4, 4, 3, 3, 1],  # 7
  [4, 4, 3, 3, 2],  # 8
  [4, 4, 3, 3, 3, 1],  # 9
  [5, 4, 3, 3, 3, 2],  # 10
  [5, 4, 3, 3, 3, 2, 1],  # 11
  [5, 4, 3, 3, 3, 2, 1],  # 12
  [5, 4, 3, 3, 3, 2, 1, 1],  # 13
  [5, 4, 3, 3, 3, 2, 1, 1],  # 14
  [5, 4, 3, 3, 3, 2, 1, 1, 1],  # 15
  [5, 4, 3, 3, 3, 2, 1, 1, 1],  # 16
  [5, 4, 3, 3, 3, 2, 1, 1, 1, 1],  # 17
  [5, 4, 3, 3, 3, 3, 1, 1, 1, 1],  # 18
  [5, 4, 3, 3, 3, 3, 2, 1, 1, 1],  # 19
  [5, 4, 3, 3, 3, 3, 2, 2, 1, 1]  # 20
]

class Bard:
  def initialize_bard(self):
    self.bard_spell_slots = {}
    self.spell_slots['bard'] = self.reset_spell_slots()
    

  def bard_spell_attack_modifier(self):
    return self.proficiency_bonus() + self.cha_mod()

  def special_actions_for_bard(self, session, battle):
    return []

  def short_rest_for_bard(self, battle):
    pass

  def max_slots_for_wizard(self, level):
    return BARD_SPELL_SLOT_TABLE[self.wizard_level - 1][level] if level < len(WIZARD_SPELL_SLOT_TABLE[self.wizard_level - 1]) else 0

  def reset_spell_slots(self):
    return OrderedDict((index, slots) for index, slots in enumerate(WIZARD_SPELL_SLOT_TABLE[self.wizard_level - 1]))