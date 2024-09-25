from collections import OrderedDict
# import pdb

WIZARD_SPELL_SLOT_TABLE = [
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

class Wizard:
  def initialize_wizard(self):
    self.wizard_spell_slots = {}
    self.arcane_recovery = 1
    self.spell_slots['wizard'] = self.reset_spell_slots()
    self.arcane_recovery = 1

  def wizard_spell_attack_modifier(self):
    return self.proficiency_bonus() + self.int_mod()

  def special_actions_for_wizard(self, session, battle):
    return []

  def short_rest_for_wizard(self, battle):
    if self.arcane_recovery > 0:
      controller = battle.controller_for(self)
      if controller and hasattr(controller, 'arcane_recovery_ui'):
        max_sum = (self.wizard_level / 2).ceil()
        while True:
          current_sum = 0
          avail_levels = [
            index for index, slots in enumerate(WIZARD_SPELL_SLOT_TABLE[self.wizard_level - 1])
            if index > 0 and index < 6 and self.wizard_spell_slots['wizard'][index] < slots and current_sum <= max_sum
          ]

          if not avail_levels:
            break

          level = controller.arcane_recovery_ui(self, avail_levels)
          if level is None:
            break

          self.wizard_spell_slots['wizard'][level] += 1
          self.arcane_recovery = 0
          max_sum -= level

  def max_slots_for_wizard(self, level):
    return WIZARD_SPELL_SLOT_TABLE[self.wizard_level - 1][level] if level < len(WIZARD_SPELL_SLOT_TABLE[self.wizard_level - 1]) else 0

  def reset_spell_slots(self):
    return OrderedDict((index, slots) for index, slots in enumerate(WIZARD_SPELL_SLOT_TABLE[self.wizard_level - 1]))
