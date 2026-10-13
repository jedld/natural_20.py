from collections import OrderedDict
from natural20.actions.second_wind_action import SecondWindAction
from natural20.actions.action_surge_action import ActionSurgeAction

# Eldritch Knight spell slots (PHB/SRD third-caster table), one row per
# Fighter level. Index 0 of each row is the cantrip placeholder; index n is
# the number of level-n slots.
ELDRITCH_KNIGHT_SPELL_SLOT_TABLE = [
    [0],              # level 1
    [0],              # level 2
    [0, 2],           # level 3
    [0, 3],           # level 4
    [0, 3],           # level 5
    [0, 3],           # level 6
    [0, 4, 2],        # level 7
    [0, 4, 2],        # level 8
    [0, 4, 2],        # level 9
    [0, 4, 3],        # level 10
    [0, 4, 3],        # level 11
    [0, 4, 3],        # level 12
    [0, 4, 3, 2],     # level 13
    [0, 4, 3, 2],     # level 14
    [0, 4, 3, 2],     # level 15
    [0, 4, 3, 3],     # level 16
    [0, 4, 3, 3],     # level 17
    [0, 4, 3, 3],     # level 18
    [0, 4, 3, 3, 1],  # level 19
    [0, 4, 3, 3, 1],  # level 20
]


class Fighter():
    def __init__(self, name):
        self.name = name
        self.second_wind_count = None
        self.action_surge_count = None
        self.martial_archetype = None
        # Eldritch Knight spellcasting
        self.fighter_spell_slots = {}
        self.known_spells = []
        self.cantrips_known = []
        self.spells_known = []

    def initialize_fighter(self):
        self.second_wind_count = 1
        if self.fighter_level >= 2:
            self.action_surge_count = 1
            if self.fighter_level >= 17:
                self.action_surge_count = 2

        # Initialize Eldritch Knight spellcasting if applicable
        martial_archetype = getattr(self, 'martial_archetype', None) or \
                           getattr(self, 'properties', {}).get('martial_archetype', None)
        if martial_archetype == 'eldritch_knight':
            self.martial_archetype = 'eldritch_knight'
            self._initialize_eldritch_knight()

    def _initialize_eldritch_knight(self):
        """Initialize Eldritch Knight spellcasting capabilities."""
        self.spell_slots['fighter'] = self.reset_eldritch_knight_spell_slots()
        # Known spells: INT-based, limited selection
        # Level 3: 2 cantrips + 3 1st-level spells
        # Level 4+: 1 more spell at levels 4, 7, 10, 13, 16, 19
        self.known_spells = []
        self.cantrips_known = []
        self.spells_known = []

    def second_wind_die(self):
        return f"1d10+{self.fighter_level}"
    
    def second_wind(self, amt):
        self.second_wind_count -= 1
        self.heal(amt)

    def action_surge(self):
        self.action_surge_count -= 1

    def special_actions_for_fighter(self, session, battle):
        actions = []
        if SecondWindAction.can(self, battle):
            actions.append(SecondWindAction(session, self, 'second_wind'))
        if ActionSurgeAction.can(self, battle):
            actions.append(ActionSurgeAction(session, self, 'action_surge'))
        return actions

    def short_rest_for_fighter(self, battle):
        self.second_wind_count = 1
        # Eldritch Knight spell slots don't recharge on short rest

    def long_rest_for_fighter(self, battle):
        # Eldritch Knight spell slots recharge on long rest
        if getattr(self, 'martial_archetype', None) == 'eldritch_knight':
            self.spell_slots['fighter'] = self.reset_eldritch_knight_spell_slots()

    # ------------------------------------------------------------------
    # Eldritch Knight spellcasting
    # ------------------------------------------------------------------

    def eldritch_knight_level(self):
        """Return the effective Eldritch Knight level ( Fighter level )."""
        return getattr(self, 'fighter_level', 0)

    def eldritch_knight_attack_modifier(self):
        """Spell attack bonus = proficiency bonus + INT modifier."""
        return self.proficiency_bonus() + self.int_mod()

    def eldritch_knight_spell_dc(self):
        """Spell save DC = 8 + proficiency bonus + INT modifier."""
        return 8 + self.proficiency_bonus() + self.int_mod()

    def max_slots_for_eldritch_knight(self, level):
        """Return max slots for a given spell level."""
        if self.eldritch_knight_level() <= 0:
            return 0
        table = ELDRITCH_KNIGHT_SPELL_SLOT_TABLE[min(self.eldritch_knight_level() - 1, 19)]
        return table[level] if 0 <= level < len(table) else 0

    def max_slots_for_fighter(self, level):
        if getattr(self, 'martial_archetype', None) != 'eldritch_knight':
            return 0
        return self.max_slots_for_eldritch_knight(level)

    def reset_eldritch_knight_spell_slots(self):
        """Reset spell slots to full based on current Fighter level."""
        return OrderedDict((index, slots) for index, slots in enumerate(
            ELDRITCH_KNIGHT_SPELL_SLOT_TABLE[min(self.eldritch_knight_level() - 1, 19)]))

    def known_spells_for_fighter(self):
        """Return list of known spells for the Eldritch Knight."""
        return getattr(self, 'spells_known', [])

    def cantrips_for_fighter(self):
        """Return list of known cantrips for the Eldritch Knight."""
        return getattr(self, 'cantrips_known', [])

    def available_spells_for_fighter(self):
        """Return all available prepared/known spells (cantrips + leveled)."""
        spells = list(getattr(self, 'cantrips_known', []))
        spells.extend(getattr(self, 'spells_known', []))
        return spells

    def borrowed_spell_list_classes(self):
        """Eldritch Knights cast wizard-list spells with fighter slots."""
        if getattr(self, 'martial_archetype', None) == 'eldritch_knight':
            return {'wizard': 'fighter'}
        return {}

    def fighter_spell_attack_modifier(self):
        return self.eldritch_knight_attack_modifier()

    def can_cast_spells_for_fighter(self):
        """Check if this Fighter can cast spells (Eldritch Knight)."""
        return getattr(self, 'martial_archetype', None) == 'eldritch_knight'
