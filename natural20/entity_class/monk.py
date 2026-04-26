# Monk class mixin (D&D 5e SRD 2014, levels 1-2 only)
#
# Implements:
#   * Level 1 - Unarmored Defense (AC = 10 + DEX + WIS when no armor & no shield)
#   * Level 1 - Martial Arts (DEX for monk weapons + unarmed strike, Martial
#     Arts die replacing the weapon's damage die, bonus-action unarmed strike
#     after taking the Attack action with a monk weapon or unarmed strike)
#   * Level 2 - Ki (pool equals monk level, recharges on short rest)
#   * Level 2 - Flurry of Blows (1 ki, bonus action after Attack: 2 unarmed strikes)
#   * Level 2 - Patient Defense (1 ki, bonus action: Dodge)
#   * Level 2 - Step of the Wind (1 ki, bonus action: Disengage or Dash)
#   * Level 2 - Unarmored Movement (+10 ft speed when no armor & no shield)


# Per 5e SRD: martial arts die scales by monk level.
MARTIAL_ARTS_DIE = [
    "1d4",   # 1
    "1d4",   # 2
    "1d4",   # 3
    "1d4",   # 4
    "1d6",   # 5
    "1d6",   # 6
    "1d6",   # 7
    "1d6",   # 8
    "1d6",   # 9
    "1d6",   # 10
    "1d8",   # 11
    "1d8",   # 12
    "1d8",   # 13
    "1d8",   # 14
    "1d8",   # 15
    "1d8",   # 16
    "1d10",  # 17
    "1d10",  # 18
    "1d10",  # 19
    "1d10",  # 20
]


# Unarmored Movement (feet) granted at the listed monk level (cumulative).
UNARMORED_MOVEMENT_BONUS = [
    0,   # 1
    10,  # 2
    10,  # 3
    10,  # 4
    10,  # 5
    15,  # 6
    15,  # 7
    15,  # 8
    15,  # 9
    20,  # 10
    20,  # 11
    20,  # 12
    20,  # 13
    20,  # 14
    25,  # 15
    25,  # 16
    25,  # 17
    25,  # 18
    25,  # 19
    30,  # 20
]


class Monk:
    def __init__(self, name=None):
        self.name = name
        self.ki_count = None
        self.max_ki = None

    def initialize_monk(self):
        # Ki pool equal to monk level, available starting at level 2.
        if self.monk_level >= 2:
            self.max_ki = self.monk_level
            if getattr(self, 'ki_count', None) is None:
                self.ki_count = self.monk_level
        else:
            self.max_ki = 0
            self.ki_count = 0

    # ---------------- Martial Arts helpers ----------------

    def martial_arts_die(self):
        """Return the Martial Arts die for this monk's current level."""
        if not getattr(self, 'monk_level', None):
            return None
        idx = max(1, min(self.monk_level, len(MARTIAL_ARTS_DIE))) - 1
        return MARTIAL_ARTS_DIE[idx]

    def is_monk_weapon(self, weapon):
        """Returns True if `weapon` qualifies as a monk weapon for Martial
        Arts: shortswords and simple melee weapons that lack the two-handed or
        heavy property. Unarmed strike always qualifies."""
        if weapon is None:
            return False
        if isinstance(weapon, str):
            try:
                weapon = self.session.load_weapon(weapon)
            except Exception:
                return False
            if weapon is None:
                return False
        properties = weapon.get('properties') or []
        if 'unarmed' in properties:
            return True
        if weapon.get('type') != 'melee_attack':
            return False
        # Shortsword is explicitly a monk weapon (martial finesse)
        weapon_id = weapon.get('id') or weapon.get('name', '').lower().replace(' ', '_')
        if weapon_id == 'shortsword':
            return True
        proficiency_types = weapon.get('proficiency_type') or []
        if 'simple' not in proficiency_types:
            return False
        if 'two_handed' in properties or 'heavy' in properties:
            return False
        return True

    # ---------------- Ki helpers ----------------

    def has_ki(self, qty=1):
        return bool(self.max_ki) and (self.ki_count or 0) >= qty

    def consume_ki(self, qty=1):
        if not self.max_ki:
            return
        self.ki_count = max(0, (self.ki_count or 0) - qty)

    # ---------------- Action discovery ----------------

    def special_actions_for_monk(self, session, battle):
        # Most monk actions are discovered through PlayerCharacter.ACTION_LIST;
        # this hook is left empty so multi-class characters using the generic
        # iteration still find a valid (no-op) entry point.
        return []

    # ---------------- Rest hooks ----------------

    def short_rest_for_monk(self, _battle):
        if self.max_ki:
            self.ki_count = self.max_ki

    def long_rest_for_monk(self, _battle):
        if self.max_ki:
            self.ki_count = self.max_ki
