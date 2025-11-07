from collections import OrderedDict

WARLOCK_SPELL_SLOT_TABLE = [
    # [cantrips, 1st, 2nd, 3rd, 4th, 5th]
    [2, 1],  # 1 - 1 slot at 1st level
    [2, 2],  # 2 - 2 slots at 1st level
    [2, 0, 2],  # 3 - 2 slots at 2nd level
    [3, 0, 2],  # 4 - 2 slots at 2nd level
    [3, 0, 0, 2],  # 5 - 2 slots at 3rd level
    [3, 0, 0, 2],  # 6 - 2 slots at 3rd level
    [4, 0, 0, 0, 2],  # 7 - 2 slots at 4th level
    [4, 0, 0, 0, 2],  # 8 - 2 slots at 4th level
    [4, 0, 0, 0, 0, 2],  # 9 - 2 slots at 5th level
    [4, 0, 0, 0, 0, 2],  # 10 - 2 slots at 5th level
    [4, 0, 0, 0, 0, 3],  # 11 - 3 slots at 5th level
    [4, 0, 0, 0, 0, 3],  # 12 - 3 slots at 5th level
    [4, 0, 0, 0, 0, 3],  # 13 - 3 slots at 5th level
    [4, 0, 0, 0, 0, 3],  # 14 - 3 slots at 5th level
    [4, 0, 0, 0, 0, 3],  # 15 - 3 slots at 5th level
    [4, 0, 0, 0, 0, 3],  # 16 - 3 slots at 5th level
    [4, 0, 0, 0, 0, 4],  # 17 - 4 slots at 5th level
    [4, 0, 0, 0, 0, 4],  # 18 - 4 slots at 5th level
    [4, 0, 0, 0, 0, 4],  # 19 - 4 slots at 5th level
    [4, 0, 0, 0, 0, 4]  # 20 - 4 slots at 5th level
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
        table = WARLOCK_SPELL_SLOT_TABLE[self.warlock_level - 1]
        return table[level] if level < len(table) else 0

    def reset_warlock_spell_slots(self):
        return OrderedDict((index, slots) for index, slots in enumerate(WARLOCK_SPELL_SLOT_TABLE[self.warlock_level - 1]))

