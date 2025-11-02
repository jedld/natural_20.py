from collections import OrderedDict

RANGER_SPELL_SLOT_TABLE = [
    # cantrips, 1st, 2nd, 3rd, 4th, 5th ... etc (Rangers are half-casters, start at level 2)
    [0, 0],  # 1 - No spellcasting
    [0, 2],  # 2 - 2 slots at 1st level
    [0, 3],  # 3 - 3 slots at 1st level
    [0, 3],  # 4 - 3 slots at 1st level
    [0, 4, 2],  # 5 - 4 slots at 1st level, 2 at 2nd
    [0, 4, 2],  # 6 - 4 slots at 1st level, 2 at 2nd
    [0, 4, 3],  # 7 - 4 slots at 1st level, 3 at 2nd
    [0, 4, 3],  # 8 - 4 slots at 1st level, 3 at 2nd
    [0, 4, 3, 2],  # 9 - 4 slots at 1st level, 3 at 2nd, 2 at 3rd
    [0, 4, 3, 2],  # 10 - 4 slots at 1st level, 3 at 2nd, 2 at 3rd
    [0, 4, 3, 3],  # 11 - 4 slots at 1st level, 3 at 2nd, 3 at 3rd
    [0, 4, 3, 3],  # 12 - 4 slots at 1st level, 3 at 2nd, 3 at 3rd
    [0, 4, 3, 3, 1],  # 13 - 4 slots at 1st level, 3 at 2nd, 3 at 3rd, 1 at 4th
    [0, 4, 3, 3, 1],  # 14 - 4 slots at 1st level, 3 at 2nd, 3 at 3rd, 1 at 4th
    [0, 4, 3, 3, 2],  # 15 - 4 slots at 1st level, 3 at 2nd, 3 at 3rd, 2 at 4th
    [0, 4, 3, 3, 2],  # 16 - 4 slots at 1st level, 3 at 2nd, 3 at 3rd, 2 at 4th
    [0, 4, 3, 3, 3, 1],  # 17 - 4 slots at 1st level, 3 at 2nd, 3 at 3rd, 3 at 4th, 1 at 5th
    [0, 4, 3, 3, 3, 1],  # 18 - 4 slots at 1st level, 3 at 2nd, 3 at 3rd, 3 at 4th, 1 at 5th
    [0, 4, 3, 3, 3, 2],  # 19 - 4 slots at 1st level, 3 at 2nd, 3 at 3rd, 3 at 4th, 2 at 5th
    [0, 4, 3, 3, 3, 2]  # 20 - 4 slots at 1st level, 3 at 2nd, 3 at 3rd, 3 at 4th, 2 at 5th
]


class Ranger:
    def initialize_ranger(self):
        self.ranger_spell_slots = {}
        self.spell_slots['ranger'] = self.reset_ranger_spell_slots()

    def ranger_spell_attack_modifier(self):
        return self.proficiency_bonus() + self.wis_mod()

    def special_actions_for_ranger(self, session, battle):
        return []

    def short_rest_for_ranger(self, battle):
        pass

    def ranger_spell_casting_modifier(self):
        return self.wis_mod()

    def max_slots_for_ranger(self, level):
        return RANGER_SPELL_SLOT_TABLE[self.ranger_level - 1][level - 1] if level < len(RANGER_SPELL_SLOT_TABLE[self.ranger_level - 1]) else 0

    def reset_ranger_spell_slots(self):
        return OrderedDict((index, slots) for index, slots in enumerate(RANGER_SPELL_SLOT_TABLE[self.ranger_level - 1]))

