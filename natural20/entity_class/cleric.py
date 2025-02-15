from collections import OrderedDict

CLERIC_SPELL_SLOT_TABLE = [
    # cantrips, 1st, 2nd, 3rd ... etc

    [3, 2],  # 1
    [3, 3],  # 2
    [3, 4, 2], # 3
    [4, 4, 3], # 4
    [4, 4, 3, 2], # 5
    [4, 4, 3, 3], # 6
    [4, 4, 3, 3, 1], # 7
    [4, 4, 3, 3, 2], # 8
    [4, 4, 3, 3, 3, 1], # 9
    [5, 4, 3, 3, 3, 2], # 10
    [5, 4, 3, 3, 3, 2, 1], # 11
    [5, 4, 3, 3, 3, 2, 1], # 12
    [5, 4, 3, 3, 3, 2, 1, 1], # 13
    [5, 4, 3, 3, 3, 2, 1, 1], # 14
    [5, 4, 3, 3, 3, 2, 1, 1, 1], # 15
    [5, 4, 3, 3, 3, 2, 1, 1, 1], # 16
    [5, 4, 3, 3, 3, 2, 1, 1, 1, 1], # 17
    [5, 4, 3, 3, 3, 3, 1, 1, 1, 1], # 18
    [5, 4, 3, 3, 3, 3, 2, 1, 1, 1], # 19
    [5, 4, 3, 3, 3, 3, 2, 2, 1, 1] # 20
]


class Cleric:
    def initialize_cleric(self):
        self.spell_slots['cleric'] = self.reset_cleric_spell_slots()
        self.channel_divinity_count = 1
        self.channel_divinity_max = 1
        if self.level() >= 6:
            self.channel_divinity_max = 2
        if self.level() >= 18:
            self.channel_divinity_max = 3

    def channel_divinity(self):
        self.channel_divinity_count -= 1

    def cleric_spell_attack_modifier(self):
        return self.proficiency_bonus() + self.wis_mod()

    def special_actions_for_cleric(self, session, battle):
        actions = []
        # if ChannelDivinityAction.can(self, battle):
        #     actions.append(ChannelDivinityAction(session, self, 'channel_divinity'))
        return actions
    
    def cleric_spell_casting_modifier(self):
        return self.wis_mod()

    def wis_mod(self):
        raise NotImplementedError

    def short_rest_for_cleric(self, battle):
        if self.channel_divinity_count < self.channel_divinity_max:
            self.channel_divinity_count += 1

    def max_slots_for_cleric(self, level):
        return CLERIC_SPELL_SLOT_TABLE[self.cleric_level - 1][level - 1] if level < len(CLERIC_SPELL_SLOT_TABLE[self.cleric_level - 1]) else 0

    def reset_cleric_spell_slots(self):
        return OrderedDict((index, slots) for index, slots in enumerate(CLERIC_SPELL_SLOT_TABLE[self.cleric_level - 1]))