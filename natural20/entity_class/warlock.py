from collections import OrderedDict

WARLOCK_SPELL_SLOT_TABLE = [
    # cantrips, 1st, 2nd, 3rd, 4th, 5th ... etc
    [2, 1],  # 1 - 1 slot at 1st level
    [2, 1],  # 2 - 1 slot at 1st level
    [2, 2],  # 3 - 2 slots at 1st level
    [2, 2],  # 4 - 2 slots at 1st level
    [3, 0, 2],  # 5 - 2 slots at 2nd level
    [3, 0, 2],  # 6 - 2 slots at 2nd level
    [3, 0, 0, 2],  # 7 - 2 slots at 3rd level
    [3, 0, 0, 2],  # 8 - 2 slots at 3rd level
    [3, 0, 0, 0, 2],  # 9 - 2 slots at 4th level
    [4, 0, 0, 0, 2],  # 10 - 2 slots at 4th level
    [4, 0, 0, 0, 0, 2],  # 11 - 2 slots at 5th level
    [4, 0, 0, 0, 0, 2],  # 12 - 2 slots at 5th level
    [4, 0, 0, 0, 0, 2],  # 13 - 2 slots at 5th level
    [4, 0, 0, 0, 0, 2],  # 14 - 2 slots at 5th level
    [4, 0, 0, 0, 0, 2],  # 15 - 2 slots at 5th level
    [4, 0, 0, 0, 0, 2],  # 16 - 2 slots at 5th level
    [4, 0, 0, 0, 0, 2],  # 17 - 2 slots at 5th level
    [4, 0, 0, 0, 0, 2],  # 18 - 2 slots at 5th level
    [4, 0, 0, 0, 0, 2],  # 19 - 2 slots at 5th level
    [4, 0, 0, 0, 0, 2]  # 20 - 2 slots at 5th level
]


class Warlock:
    def initialize_warlock(self):
        self.warlock_spell_slots = {}
        self.spell_slots['warlock'] = self.reset_warlock_spell_slots()

    def warlock_spell_attack_modifier(self):
        return self.proficiency_bonus() + self.cha_mod()

    def special_actions_for_warlock(self, session, battle):
        return []

    def short_rest_for_warlock(self, battle):
        # Warlock spell slots recharge on short rest
        self.spell_slots['warlock'] = self.reset_warlock_spell_slots()

    def warlock_spell_casting_modifier(self):
        return self.cha_mod()

    def max_slots_for_warlock(self, level):
        return WARLOCK_SPELL_SLOT_TABLE[self.warlock_level - 1][level - 1] if level < len(WARLOCK_SPELL_SLOT_TABLE[self.warlock_level - 1]) else 0

    def reset_warlock_spell_slots(self):
        return OrderedDict((index, slots) for index, slots in enumerate(WARLOCK_SPELL_SLOT_TABLE[self.warlock_level - 1]))

