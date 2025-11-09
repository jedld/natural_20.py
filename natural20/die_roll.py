from typing import Optional
import random
import i18n
import copy
import pdb
import re
from collections import deque

# Global dictionary used for "fudged" rolls.
FUDGE_HASH = {}
DIE_ROLL = {}
DIE_ROLLS = deque(maxlen=100)

class DieRollDetail:
    def __init__(self):
        self.die_count: Optional[int] = None   # Integer: number of dice to roll or fixed number value
        self.die_type: Optional[str] = None    # String: e.g. "20" for a d20; empty if not a dice roll
        self.modifier: Optional[str] = None    # String: digits for the modifier (if any)
        self.modifier_op: Optional[str] = None  # String: '+', '-', '*', or '/' (if any)

class Rollable:
    def result(self):
        raise NotImplementedError


class Roller:
    def __init__(self, roll_str, crit=False, disadvantage=False, advantage=False,
                 description=None, entity=None, battle=None, controller=None, advantage_str=None, disadvantage_str=None):
        self.roll_str = roll_str
        self.crit = crit
        self.advantage = advantage
        self.disadvantage = disadvantage
        self.description = description
        self.entity = entity
        self.battle = battle
        self.controller = controller
        self.advantage_str = advantage_str
        self.disadvantage_str = disadvantage_str

    # support >= and <=
    def __ge__(self, other):
        return self.result() >= other

    def __le__(self, other):
        return self.result() <= other

    def __gt__(self, other):
        return self.result() > other

    def __lt__(self, other):
        return self.result() < other

    def __eq__(self, other):
        return self.result() == other

    def roll(self, lucky=False, description_override=None):
        # Default die sides is 20 until we know otherwise.
        die_sides = 20
        detail = DieRoll.parse(self.roll_str)
        number_of_die = detail.die_count
        die_type_str = detail.die_type
        modifier_str = detail.modifier
        modifier_op = detail.modifier_op

        # If no die type is specified, treat this as a fixed modifier roll.
        if not die_type_str:
            mod_value = int(f"{modifier_op}{modifier_str}") if modifier_str else 0
            return DieRoll([number_of_die], mod_value, 0, roller=self)

        die_sides = int(die_type_str)

        # Double the number of dice for a critical hit.
        if self.crit:
            number_of_die *= 2

        # Build a description string.
        roll_desc = f"dice_roll.description, description={description_override or self.description}, roll_str={self.roll_str}, advantage_str={self.advantage_str}, disadvantage_str={self.disadvantage_str}"
        if lucky:
            roll_desc = f"(lucky) {roll_desc}"
        if self.advantage:
            roll_desc = '\033[34m(with advantage)\033[0m' + roll_desc
        elif self.disadvantage:
            roll_desc = '\033[31m(with disadvantage)\033[0m' + roll_desc

        # Roll using the battle's context if available.
        if self.advantage or self.disadvantage:
            if self.battle:
                rolls = self.battle.roll_for(self.entity, die_sides, number_of_die, roll_desc,
                                             advantage=self.advantage, disadvantage=self.disadvantage,
                                             controller=self.controller)
            else:
                rolls = [
                    (DieRoll.generate_number(die_sides), DieRoll.generate_number(die_sides))
                    for _ in range(number_of_die)
                ]
        elif self.battle:
            rolls = self.battle.roll_for(self.entity, die_sides, number_of_die, roll_desc,
                                         controller=self.controller)
        else:
            rolls = [DieRoll.generate_number(die_sides) for _ in range(number_of_die)]

        # Handle the modifier operation
        if modifier_op in ['*', '/']:
            # For multiplication and division, use the new system
            mod_value = 0  # No legacy modifier
            modifier_val = int(modifier_str) if modifier_str else None
            result = DieRoll(rolls, mod_value, die_sides,
                           advantage=self.advantage, disadvantage=self.disadvantage, roller=self,
                           modifier_op=modifier_op, modifier_val=modifier_val)
        else:
            # For addition and subtraction, use the legacy system for backward compatibility
            mod_value = 0 if not modifier_str else int(f"{modifier_op}{modifier_str}")
            result = DieRoll(rolls, mod_value, die_sides,
                           advantage=self.advantage, disadvantage=self.disadvantage, roller=self)
        
        DIE_ROLLS.append(result)
        return result

    def t(self, key, options=None):
        return i18n.t(key, **(options or {}))


class DieRolls(Rollable):
    def __init__(self, rolls=None):
        self.rolls = rolls if rolls is not None else []

    def add_to_front(self, die_roll):
        if isinstance(die_roll, DieRoll):
            self.rolls.insert(0, die_roll)
        elif isinstance(die_roll, DieRolls):
            self.rolls = die_roll.rolls + self.rolls

    def __add__(self, other):
        if isinstance(other, DieRoll):
            self.rolls.append(other)
        elif isinstance(other, DieRolls):
            self.rolls += other.rolls
        return self

    def result(self):
        return sum(roll if isinstance(roll, int) else roll.result() for roll in self.rolls)

    def expected(self):
        return sum(roll.expected() if isinstance(roll, DieRoll) else roll for roll in self.rolls)

    def nat_20(self):
        return any(roll.nat_20() for roll in self.rolls)

    def nat_1(self):
        return any(roll.nat_1() for roll in self.rolls)

    def reroll(self, lucky=False):
        new_rolls = copy.deepcopy(self.rolls)
        new_die_rolls = DieRolls(rolls=new_rolls)
        if lucky:
            for index, roll in enumerate(self.rolls):
                if roll.nat_1():
                    new_rolls[index] = roll.reroll(lucky=True)
        else:
            for index, roll in enumerate(self.rolls):
                new_rolls[index] = roll.reroll()
        return new_die_rolls

    def __eq__(self, other):
        # Equality by numeric result when comparing against non-DieRolls collections or numbers
        if isinstance(other, DieRolls):
            # Prefer structural equality when both are DieRolls collections and lengths match
            if len(other.rolls) == len(self.rolls):
                return all(r1 == r2 for r1, r2 in zip(self.rolls, other.rolls))
            # Fallback to numeric equality
            return self.result() == other.result()
        if isinstance(other, DieRoll):
            return self.result() == other.result()
        # numeric fallback
        return self.result() == other

    # Rich comparisons compare by total numeric result
    def __lt__(self, other):
        rhs = other.result() if isinstance(other, (DieRoll, DieRolls)) else other
        return self.result() < rhs

    def __le__(self, other):
        rhs = other.result() if isinstance(other, (DieRoll, DieRolls)) else other
        return self.result() <= rhs

    def __gt__(self, other):
        rhs = other.result() if isinstance(other, (DieRoll, DieRolls)) else other
        return self.result() > rhs

    def __ge__(self, other):
        rhs = other.result() if isinstance(other, (DieRoll, DieRolls)) else other
        return self.result() >= rhs

    def __str__(self):
        parts = []
        for roll in self.rolls:
            if parts:
                if isinstance(roll, int):
                    parts.append(' + ')
                    parts.append(str(roll))
                elif roll.result() >= 0:
                    parts.append(' + ')
                    parts.append(str(roll))
                else:
                    parts.append(' - ')
                    parts.append(str(roll).replace('-', ''))
            else:
                parts.append(str(roll))
        return ''.join(parts)


class DieRollResult(int):
    """Numeric wrapper for DieRoll totals that allows conditional guidance injection."""

    def __new__(cls, value, die_roll, base_total):
        obj = int.__new__(cls, value)
        obj._die_roll = die_roll
        obj._base_total = base_total
        return obj

    def _numeric_value(self):
        die_roll = getattr(self, "_die_roll", None)
        if die_roll and hasattr(die_roll, "metadata"):
            return die_roll.metadata.get('last_result', super().__int__())
        return super().__int__()

    def _base_value(self):
        return getattr(self, "_base_total", super().__int__())

    def _coerce_other(self, other):
        if isinstance(other, DieRollResult):
            return other._numeric_value()
        if isinstance(other, DieRoll):
            return int(other.result())
        if isinstance(other, DieRolls):
            return other.result()
        return other

    def _prepare(self, other, comparator):
        die_roll = getattr(self, "_die_roll", None)
        other_numeric = self._coerce_other(other)
        if not die_roll:
            return self._numeric_value(), other_numeric

        base_total = self._base_value()
        die_roll._maybe_apply_guidance(base_total, other_numeric, comparator)
        left_numeric = die_roll.metadata.get('last_result', self._numeric_value())

        if isinstance(other, DieRollResult):
            other_die_roll = getattr(other, "_die_roll", None)
            if other_die_roll:
                other_die_roll._maybe_apply_guidance(other._base_value(), left_numeric, comparator)
                other_numeric = other_die_roll.metadata.get('last_result', other._numeric_value())

        return left_numeric, other_numeric

    def __ge__(self, other):
        left, right = self._prepare(other, 'ge')
        return left >= right

    def __gt__(self, other):
        left, right = self._prepare(other, 'gt')
        return left > right

    def __le__(self, other):
        left, right = self._prepare(other, 'le')
        return left <= right

    def __lt__(self, other):
        left, right = self._prepare(other, 'lt')
        return left < right

    def __int__(self):
        return self._numeric_value()

    def __float__(self):
        return float(self._numeric_value())

    def __str__(self):
        return str(self._numeric_value())

    def __repr__(self):
        return str(self)

    def __reduce__(self):
        return (int, (self._numeric_value(),))


class DieRoll(Rollable):
    def __init__(self, rolls, modifier, die_sides=20, advantage=False, disadvantage=False,
                 description=None, roller=None, prev_roll=None, modifier_op=None, modifier_val=None,
                 halved=False):
        self.rolls = rolls
        self.modifier = modifier  # Keep for backward compatibility
        self.modifier_op = modifier_op  # The operation: '+', '-', '*', '/'
        self.modifier_val = modifier_val  # The operand value
        self.die_sides = die_sides
        self.advantage = advantage
        self.disadvantage = disadvantage
        self.description = description
        self.roller = roller
        self.prev_roll = prev_roll
        self.halved = halved
        self.metadata = {}

    def clone(self):
        cloned = DieRoll(self.rolls[:], self.modifier, self.die_sides,
                         advantage=self.advantage, disadvantage=self.disadvantage,
                         description=self.description, roller=self.roller,
                         prev_roll=self.prev_roll, modifier_op=self.modifier_op,
                         modifier_val=self.modifier_val, halved=self.halved)
        cloned.metadata = copy.deepcopy(getattr(self, 'metadata', {}))
        return cloned

    def nat_20(self):
        if self.die_sides != 20:
            return False
        if self.advantage:
            # When rolling with advantage, each element is expected to be a tuple.
            return any(max(roll) == 20 for roll in self.rolls if isinstance(roll, (tuple, list)))
        elif self.disadvantage:
            return any(min(roll) == 20 for roll in self.rolls if isinstance(roll, (tuple, list)))
        else:
            return 20 in self.rolls

    def nat_1(self):
        if self.die_sides != 20:
            return False
        if self.advantage:
            return any(max(roll) == 1 for roll in self.rolls if isinstance(roll, (tuple, list)))
        elif self.disadvantage:
            return any(min(roll) == 1 for roll in self.rolls if isinstance(roll, (tuple, list)))
        else:
            return 1 in self.rolls

    def rolled_a_1(self):
        if self.advantage or self.disadvantage:
            return any(min(roll) == 1 for roll in self.rolls if isinstance(roll, (tuple, list)))
        return 1 in self.rolls

    def reroll(self, lucky=False):
        new_rolls = copy.deepcopy(self.rolls)
        if lucky:
            for index, roll in enumerate(self.rolls):
                if isinstance(roll, (tuple, list)):
                    new_vals = list(roll)
                    for i, value in enumerate(new_vals):
                        if value == 1:
                            new_vals[i] = DieRoll.generate_number(self.die_sides)
                    new_rolls[index] = tuple(new_vals)
                elif roll == 1:
                    new_rolls[index] = DieRoll.generate_number(self.die_sides)
        else:
            # Use enumerate to update each roll.
            for index, roll in enumerate(self.rolls):
                if isinstance(roll, (tuple, list)):
                    if min(roll) == 1 or max(roll) == self.die_sides:
                        new_rolls[index] = DieRoll.generate_number(self.die_sides)
                elif roll == 1 or roll == self.die_sides:
                    new_rolls[index] = DieRoll.generate_number(self.die_sides)
        desc = f"(lucky) {self.description} {self.rolls} -> {new_rolls}" if lucky else self.description
        rerolled = DieRoll(new_rolls, self.modifier, self.die_sides,
                           advantage=self.advantage, disadvantage=self.disadvantage,
                           roller=self.roller, description=desc, prev_roll=self,
                           modifier_op=self.modifier_op, modifier_val=self.modifier_val)
        rerolled.metadata = copy.deepcopy(getattr(self, 'metadata', {}))
        return rerolled

    def result(self):
        total = self._apply_modifiers(self._sum_rolls())
        self.metadata.setdefault('guidance_base', total)
        self.metadata['last_result'] = total
        return DieRollResult(total, self, self.metadata['guidance_base'])

    def _sum_rolls(self):
        if self.advantage:
            return sum(max(roll) if isinstance(roll, (tuple, list)) else roll for roll in self.rolls)
        if self.disadvantage:
            return sum(min(roll) if isinstance(roll, (tuple, list)) else roll for roll in self.rolls)
        return sum(self.rolls)

    def _apply_modifiers(self, total):
        result = total + self.modifier

        if self.modifier_op and self.modifier_val is not None:
            if self.modifier_op == '+':
                result += self.modifier_val
            elif self.modifier_op == '-':
                result -= self.modifier_val
            elif self.modifier_op == '*':
                result *= self.modifier_val
            elif self.modifier_op == '/':
                result = int(result / self.modifier_val)

        if self.halved:
            result = int(result // 2)

        return result

    def _maybe_apply_guidance(self, base_total, comparison_value, comparator):
        if not getattr(self, 'metadata', None):
            return
        if not self.metadata.get('is_ability_check'):
            return
        if self.metadata.get('guidance_applied'):
            return
        if comparison_value is None:
            return

        entity = self.roller.entity if self.roller else None
        if entity is None or not entity.has_effect('guidance'):
            return

        failed = False
        if comparator == 'ge':
            failed = base_total < comparison_value
        elif comparator == 'gt':
            failed = base_total <= comparison_value
        elif comparator == 'le':
            failed = base_total > comparison_value
        elif comparator == 'lt':
            failed = base_total >= comparison_value

        if not failed:
            return

        effect_entry = self._find_active_effect(entity, 'guidance')
        if not effect_entry:
            return

        battle = self.roller.battle if self.roller else None
        guidance_roll = DieRoll.roll_with_lucky(entity, '1d4', description='guidance', battle=battle)
        bonus = guidance_roll.result()

        self.metadata.setdefault('guidance_base', base_total)
        self.modifier += bonus
        new_total = base_total + bonus
        self.metadata['last_result'] = new_total
        self.metadata['guidance_applied'] = True
        self.metadata['guidance_bonus'] = bonus
        self.metadata['guidance_roll'] = guidance_roll

        effect_obj = effect_entry.get('effect')
        try:
            if effect_obj and hasattr(effect_obj, 'source') and effect_obj.source:
                effect_obj.source.dismiss_effect(effect_obj)
            elif effect_obj:
                entity.remove_effect(effect_obj)
        except Exception:
            try:
                if effect_obj:
                    entity.remove_effect(effect_obj)
            except Exception:
                pass

        event_manager = getattr(entity.session, 'event_manager', None)
        if event_manager:
            event_manager.received_event({
                'event': 'guidance',
                'source': effect_entry.get('source', entity),
                'target': entity,
                'bonus': bonus
            })

    @staticmethod
    def _find_active_effect(entity, effect_type):
        if effect_type not in entity.effects:
            return None

        active = [effect for effect in entity.effects[effect_type]
                  if not effect.get('expiration') or effect['expiration'] > entity.session.game_time]
        return active[-1] if active else None

    def half(self):
        _roll = self.clone()
        _roll.halved = True
        return _roll

    def expected(self):
        if self.die_sides == 0:
            return sum(self.rolls) + self.modifier

        if self.advantage:
            expected_value = sum(
                i * ((1.0 / self.die_sides * (i * 1.0 / self.die_sides))
                     + ((i - 1) * (1.0 / self.die_sides) * (1.0 / self.die_sides)))
                for i in range(1, self.die_sides + 1)
            )
        elif self.disadvantage:
            expected_value = sum(
                i * ((1.0 / self.die_sides * ((self.die_sides - i + 1) * 1.0 / self.die_sides))
                     + (((self.die_sides - i) * (1.0 / self.die_sides)) * (1.0 / self.die_sides)))
                for i in range(1, self.die_sides + 1)
            )
        else:
            expected_value = sum(i * (1.0 / self.die_sides) for i in range(1, self.die_sides + 1))

        return len(self.rolls) * expected_value + self.modifier

    def prob(self, x):
        # Returns the probability that the roll will be at least x.
        if x > self.die_sides + self.modifier:
            return 0.0
        if x < 1 + self.modifier:
            return 1.0

        x_adjusted = x - self.modifier
        sum_prob = 0.0

        if self.advantage:
            for i in range(x_adjusted, self.die_sides + 1):
                p = 1.0 / self.die_sides
                p2 = i * (1.0 / self.die_sides)
                p3 = (i - 1) * (1.0 / self.die_sides)
                sum_prob += p * p2 + p3 * p
        elif self.disadvantage:
            for i in range(x_adjusted, self.die_sides + 1):
                p = 1.0 / self.die_sides
                p2 = (self.die_sides - i + 1) * (1.0 / self.die_sides)
                p3 = (self.die_sides - i) * (1.0 / self.die_sides)
                sum_prob += p * p2 + p3 * p
        else:
            # For a normal roll, the probability is the count of numbers >= x_adjusted.
            sum_prob = (self.die_sides - x_adjusted + 1) / self.die_sides

        return sum_prob

    def color_roll(self, roll):
        # In this simple refactoring the color formatting is a pass‐through.
        return str(roll)

    def describe(self):
        roll_parts = []
        for r in self.rolls:
            if self.advantage and isinstance(r, (tuple, list)):
                # Mark the higher roll with an asterisk.
                roll_parts.append(' | '.join(f"{self.color_roll(i)}*" if i == max(r) else str(i) for i in r))
            elif self.disadvantage and isinstance(r, (tuple, list)):
                # Mark the lower roll with an asterisk.
                roll_parts.append(' | '.join(f"{self.color_roll(i)}*" if i == min(r) else str(i) for i in r))
            else:
                roll_parts.append(self.color_roll(r))
        rolls_str = ' + '.join(roll_parts)
        
        # Handle legacy modifier
        if self.modifier != 0:
            sign = ' - ' if self.modifier < 0 else ' + '
            base_str = f"d{self.die_sides}({rolls_str}){sign}{abs(self.modifier)}"
        else:
            base_str = f"d{self.die_sides}({rolls_str})"
        
        # Handle new modifier operations
        if self.modifier_op and self.modifier_val is not None:
            base_str += f" {self.modifier_op} {self.modifier_val}"
        
        if self.halved:
            base_str += " / 2"
        return base_str

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        if self.prev_roll and self != self.prev_roll:
            return f"{self.prev_roll.describe()} lucky -> {self.describe()}"
        return self.describe()

    # support >= and <=
    def __ge__(self, other):
        return self.result() >= other

    def __le__(self, other):
        return self.result() <= other

    def __gt__(self, other):
        return self.result() > other

    @staticmethod
    def numeric(c):
        try:
            float(c)
            return True
        except ValueError:
            return False

    def __eq__(self, other):
        if isinstance(other, DieRoll):
            return (self.rolls == other.rolls and
                    self.modifier == other.modifier and
                    self.die_sides == other.die_sides)
        else:
            return self.result() == other

    def __lt__(self, other):
        if isinstance(other, DieRoll):
            return self.result() < other.result()
        return self.result() < other

    def __add__(self, other):
        if isinstance(other, DieRolls):
            other.add_to_front(self)
            return other
        return DieRolls([self, other])

    @staticmethod
    def parse(roll_str: str) -> DieRollDetail:
        """
        Parse a dice roll string into its components.
        Expected format: "[number]d[sides][+/-/*// modifier]"
        For example: "2d6+3" or "d20" or "1d20/2" or just "5" (a fixed modifier).
        """
        roll_str = str(roll_str).strip()
        # Try to parse with a regular expression.
        pattern = r'^(?:(\d+)?d(\d+))?(?:\s*([+\-*/])\s*(\d+))?$'
        match = re.match(pattern, roll_str)
        detail = DieRollDetail()
        if match:
            die_count, die_type, op, modifier = match.groups()
            if die_type:
                detail.die_count = int(die_count) if die_count else 1
                detail.die_type = die_type
            else:
                # If no die type, interpret the entire string as a fixed modifier.
                detail.die_count = int(die_count) if die_count else 0
                detail.die_type = ''
            detail.modifier_op = op if op else ''
            detail.modifier = modifier if modifier else ''
        else:
            # Fallback to the original state‐machine parsing.
            die_count_str = ''
            die_type_str = ''
            modifier_str = ''
            modifier_op = ''
            state = 'initial'
            for c in roll_str:
                if state == 'initial':
                    if DieRoll.numeric(c):
                        die_count_str += c
                    elif c == 'd':
                        state = 'die_type'
                    elif c == '+':
                        state = 'modifier'
                elif state == 'die_type':
                    if c != ' ':
                        if DieRoll.numeric(c):
                            die_type_str += c
                        elif c == '+':
                            state = 'modifier'
                        elif c == '-':
                            modifier_op = '-'
                            state = 'modifier'
                        elif c == '*':
                            modifier_op = '*'
                            state = 'modifier'
                        elif c == '/':
                            modifier_op = '/'
                            state = 'modifier'
                elif state == 'modifier':
                    if c != ' ' and DieRoll.numeric(c):
                        modifier_str += c
            if state == 'initial':
                modifier_str = die_count_str
                die_count_str = '0'
            detail.die_count = 1 if die_count_str == '' else int(die_count_str)
            detail.die_type = die_type_str
            detail.modifier = modifier_str
            detail.modifier_op = modifier_op
        return detail

    @staticmethod
    def roll(roll_str, crit=False, disadvantage=False, advantage=False,
             description=None, entity=None, battle=None, controller=None, advantage_str=None, disadvantage_str=None):
        roller = Roller(roll_str, crit=crit, disadvantage=disadvantage, advantage=advantage,
                        description=description, entity=entity, battle=battle, controller=controller, advantage_str=advantage_str, disadvantage_str=disadvantage_str)
        return roller.roll()

    @staticmethod
    def fudge(fixed_roll, die_sides=20):
        global FUDGE_HASH
        FUDGE_HASH[die_sides] = fixed_roll

    @staticmethod
    def unfudge(die_sides=20):
        global FUDGE_HASH
        FUDGE_HASH.pop(die_sides, None)

    @staticmethod
    def roll_for(die_type, number_of_times, advantage=False, disadvantage=False, advantage_str=None, disadvantage_str=None):
        if advantage or disadvantage:
            return [DieRoll.generate_number(die_type, advantage=advantage, disadvantage=disadvantage)
                    for _ in range(number_of_times)]
        return [DieRoll.generate_number(die_type) for _ in range(number_of_times)]

    @staticmethod
    def generate_number(die_sides, advantage=False, disadvantage=False):
        global FUDGE_HASH
        if die_sides in FUDGE_HASH:
            fudge_val = FUDGE_HASH.pop(die_sides)
            if advantage or disadvantage:
                return [fudge_val, fudge_val]
            return fudge_val

        if advantage or disadvantage:
            return random.sample(range(1, die_sides + 1), 2)
        return random.randint(1, die_sides)

    @staticmethod
    def roll_with_lucky(entity, roll_str, crit=False, disadvantage=False, advantage=False,
                          description=None, battle=None):
        roller = Roller(roll_str, crit=crit, disadvantage=disadvantage, advantage=advantage,
                        description=description, entity=entity, battle=battle)
        result = roller.roll()
        if result.rolled_a_1() and entity.class_feature('lucky'):
            result = result.reroll(lucky=True)
        DIE_ROLL['last_roll'] = result
        DIE_ROLLS.append(result)
        return result

    @staticmethod
    def last_roll():
        return DIE_ROLL['last_roll']

    @staticmethod
    def die_rolls():
        return DIE_ROLLS

    @staticmethod
    def t(key, options=None):
        return i18n.t(key, **(options or {}))
