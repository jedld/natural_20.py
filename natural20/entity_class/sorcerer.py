from collections import OrderedDict

# Sorcerer follows the standard full-caster spell slot progression
# (identical to the Wizard table in the 5e SRD/PHB).  Index 0 is the
# cantrip slot count followed by 1st-level slots and so on.
SORCERER_SPELL_SLOT_TABLE = [
    # cantrips, 1st, 2nd, 3rd, 4th, 5th, 6th, 7th, 8th, 9th
    [4, 2],                                   # 1
    [4, 3],                                   # 2
    [4, 4, 2],                                # 3
    [5, 4, 3],                                # 4
    [5, 4, 3, 2],                             # 5
    [5, 4, 3, 3],                             # 6
    [5, 4, 3, 3, 1],                          # 7
    [5, 4, 3, 3, 2],                          # 8
    [5, 4, 3, 3, 3, 1],                       # 9
    [6, 4, 3, 3, 3, 2],                       # 10
    [6, 4, 3, 3, 3, 2, 1],                    # 11
    [6, 4, 3, 3, 3, 2, 1],                    # 12
    [6, 4, 3, 3, 3, 2, 1, 1],                 # 13
    [6, 4, 3, 3, 3, 2, 1, 1],                 # 14
    [6, 4, 3, 3, 3, 2, 1, 1, 1],              # 15
    [6, 4, 3, 3, 3, 2, 1, 1, 1],              # 16
    [6, 4, 3, 3, 3, 2, 1, 1, 1, 1],           # 17
    [6, 4, 3, 3, 3, 3, 1, 1, 1, 1],           # 18
    [6, 4, 3, 3, 3, 3, 2, 1, 1, 1],           # 19
    [6, 4, 3, 3, 3, 3, 2, 2, 1, 1],           # 20
]

# Sorcery Points granted by Font of Magic (gained at 2nd level): equals
# the sorcerer's class level from level 2 onward.
SORCERY_POINTS_TABLE = [0, 2, 3, 4, 5, 6, 7, 8, 9, 10,
                        11, 12, 13, 14, 15, 16, 17, 18, 19, 20]


class Sorcerer:
    """Sorcerer class mixin.

    Provides spell slot accounting (full caster table), Charisma-based
    spellcasting modifiers, and a lightweight Font of Magic (sorcery
    points) resource that survives save/load via ``properties``.
    """

    def initialize_sorcerer(self):
        self.spell_slots['sorcerer'] = self.reset_sorcerer_spell_slots()
        # Restore sorcery points from saved character state when reloading
        # a session; default to the class maximum on a fresh build.
        max_points = self.max_sorcery_points()
        saved = self.properties.get('sorcery_points', None)
        if saved is None:
            self.sorcery_points = max_points
        else:
            try:
                self.sorcery_points = max(0, min(int(saved), max_points))
            except (TypeError, ValueError):
                self.sorcery_points = max_points

    def sorcerer_spell_attack_modifier(self):
        return self.proficiency_bonus() + self.cha_mod()

    def sorcerer_spell_casting_modifier(self):
        return self.cha_mod()

    def special_actions_for_sorcerer(self, session, battle):
        return []

    def short_rest_for_sorcerer(self, battle):
        # Sorcery points and slots reset only on a long rest in 5e RAW.
        pass

    def long_rest_for_sorcerer(self, battle):
        self.spell_slots['sorcerer'] = self.reset_sorcerer_spell_slots()
        self.sorcery_points = self.max_sorcery_points()
        self.properties['sorcery_points'] = self.sorcery_points

    def max_slots_for_sorcerer(self, level):
        table = SORCERER_SPELL_SLOT_TABLE[self.sorcerer_level - 1]
        return table[level] if level < len(table) else 0

    def max_sorcery_points(self):
        idx = max(0, min(self.sorcerer_level, len(SORCERY_POINTS_TABLE)) - 1)
        return SORCERY_POINTS_TABLE[idx]

    def consume_sorcery_points(self, qty):
        qty = int(qty)
        if qty <= 0 or getattr(self, 'sorcery_points', 0) < qty:
            return False
        self.sorcery_points -= qty
        self.properties['sorcery_points'] = self.sorcery_points
        return True

    def reset_sorcerer_spell_slots(self):
        return OrderedDict(
            (index, slots)
            for index, slots in enumerate(
                SORCERER_SPELL_SLOT_TABLE[self.sorcerer_level - 1]
            )
        )
