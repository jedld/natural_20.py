from collections import OrderedDict
import math
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
    # Reset the once-per-day Arcane Recovery so the player may use it on
    # one short rest between long rests.  Note: per RAW arcane recovery
    # itself recharges on a long rest, but storing the gate here lets the
    # short-rest UI offer it once until consumed; long_rest_for_wizard
    # rearms it.
    if getattr(self, 'arcane_recovery', 0) <= 0:
      return
    if battle is None:
      return
    controller = battle.controller_for(self)
    if not (controller and hasattr(controller, 'arcane_recovery_ui')):
      return

    slots = self.spell_slots.get('wizard', {})
    table = WIZARD_SPELL_SLOT_TABLE[self.wizard_level - 1]
    budget = math.ceil(self.wizard_level / 2)

    while budget > 0:
      avail_levels = [
        index for index, max_slots in enumerate(table)
        if 0 < index <= 5
        and slots.get(index, 0) < max_slots
        and index <= budget
      ]

      if not avail_levels:
        break

      level = controller.arcane_recovery_ui(self, avail_levels)
      if level is None or level not in avail_levels:
        break

      slots[level] = slots.get(level, 0) + 1
      budget -= level

    self.arcane_recovery = 0

  def long_rest_for_wizard(self, battle):
    # Restore spell slots and rearm Arcane Recovery on a long rest.
    self.spell_slots['wizard'] = self.reset_spell_slots()
    self.arcane_recovery = 1

  def max_slots_for_wizard(self, level):
    return WIZARD_SPELL_SLOT_TABLE[self.wizard_level - 1][level] if level < len(WIZARD_SPELL_SLOT_TABLE[self.wizard_level - 1]) else 0

  def reset_spell_slots(self):
    return OrderedDict((index, slots) for index, slots in enumerate(WIZARD_SPELL_SLOT_TABLE[self.wizard_level - 1]))
