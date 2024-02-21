import random
import i18n
class DieRollDetail:
    def __init__(self):
        self.die_count = None  # Integer
        self.die_type = None  # String
        self.modifier = None  # Integer
        self.modifier_op = None  # Symbol
class Roller:
    def __init__(self, roll_str, crit=False, disadvantage=False, advantage=False, description=None, entity=None, battle=None, controller=None):
        self.roll_str = roll_str
        self.crit = crit
        self.advantage = advantage
        self.disadvantage = disadvantage
        self.description = description
        self.entity = entity
        self.battle = battle
        self.controller = controller

    def roll(self, lucky=False, description_override=None):
        die_sides = 20

        detail = DieRoll.parse(self.roll_str)
        number_of_die = detail.die_count
        die_type_str = detail.die_type
        modifier_str = detail.modifier
        modifier_op = detail.modifier_op

        if not die_type_str:
            return DieRoll([number_of_die], int(f"{modifier_op}{modifier_str}"), 0, roller=self)

        die_sides = int(die_type_str)

        if self.crit:
            number_of_die *= 2 

        description = f"dice_roll.description, description={description_override or self.description}, roll_str={self.roll_str}"
        description = f"(lucky) {description}" if lucky else description
        if self.advantage:
            description = '\033[34m(with advantage)\033[0m' + description 
        elif self.disadvantage:
            description = '\033[31m(with disadvantage)\033[0m' + description

        if self.advantage or self.disadvantage:
            if self.battle:
                rolls = self.battle.roll_for(self.entity, die_sides, number_of_die, description, advantage=self.advantage, disadvantage=self.disadvantage, controller=self.controller)
            else:
                rolls = [(random.randint(1, die_sides), random.randint(1, die_sides)) for _ in range(number_of_die)]
        elif self.battle:
            rolls = self.battle.roll_for(self.entity, die_sides, number_of_die, description, controller=self.controller)
        else:
            rolls = [random.randint(1, die_sides) for _ in range(number_of_die)]

        return DieRoll(rolls, 0 if not modifier_str else int(f"{modifier_op}{modifier_str}"), die_sides, advantage=self.advantage, disadvantage=self.disadvantage, roller=self)

    def t(self, key, options=None):
        return i18n.t(key, **options)

class DieRolls:
    def __init__(self, rolls=[]):
        self.rolls = rolls

    def add_to_front(self, die_roll):
        if isinstance(die_roll, DieRoll):
            self.rolls.insert(0, die_roll)
        elif isinstance(die_roll, self.__class__):
            self.rolls = die_roll.rolls + self.rolls

    def __add__(self, other):
        if isinstance(other, DieRoll):
            self.rolls.append(other)
        elif isinstance(other, self.__class__):
            self.rolls += other.rolls

    def result(self):
        return sum(roll.result() for roll in self.rolls)

    def expected(self):
        return sum(roll.expected() for roll in self.rolls)

    def __eq__(self, other):
        if len(other.rolls) != len(self.rolls):
            return False

        for index, roll in enumerate(self.rolls):
            if other.rolls[index] != roll:
                return False

        return True

    def __str__(self):
        return ' + '.join(str(roll) for roll in self.rolls)

class DieRoll:
    def __init__(self, rolls, modifier, die_sides=20, advantage=False, disadvantage=False, description=None, roller=None):
        self.rolls = rolls
        self.modifier = modifier
        self.die_sides = die_sides
        self.advantage = advantage
        self.disadvantage = disadvantage
        self.description = description
        self.roller = roller

    def nat_20(self):
        if self.advantage:
            return any(roll == 20 for roll in [max(r) for r in self.rolls])
        elif self.disadvantage:
            return any(roll == 20 for roll in [min(r) for r in self.rolls])
        else:
            return 20 in self.rolls

    def nat_1(self):
        if self.advantage:
            return any(roll == 1 for roll in [max(r) for r in self.rolls])
        elif self.disadvantage:
            return any(roll == 1 for roll in [min(r) for r in self.rolls])
        else:
            return 1 in self.rolls

    def reroll(self, lucky=False):
        return self.roller.roll(lucky=lucky)

    def result(self):
        if self.advantage:
            sum_rolls = sum(max(r) for r in self.rolls)
        elif self.disadvantage:
            sum_rolls = sum(min(r) for r in self.rolls)
        else:
            sum_rolls = sum(self.rolls)

        return sum_rolls + self.modifier

    def expected(self):
        if self.die_sides == 0:
            return sum(self.rolls) + self.modifier

        sum_expected = 0.0

        if self.advantage:
            for i in range(1, self.die_sides + 1):
                prob = 1.0 / self.die_sides
                prob2 = i * (1.0 / self.die_sides)
                prob3 = (i - 1) * (1.0 / self.die_sides)
                sum_expected += i * (prob * prob2 + prob3 * prob)
        elif self.disadvantage:
            for i in range(1, self.die_sides + 1):
                prob = 1.0 / self.die_sides
                prob2 = (self.die_sides - i + 1) * (1.0 / self.die_sides)
                prob3 = (self.die_sides - i) * (1.0 / self.die_sides)
                sum_expected += i * (prob * prob2 + prob3 * prob)
        else:
            for i in range(1, self.die_sides + 1):
                sum_expected += i * (1.0 / self.die_sides)

        return len(self.rolls) * sum_expected + self.modifier

    def prob(self, x):
        if x > self.die_sides + self.modifier:
            return 0.0
        elif x < 1 + self.modifier:
            return 1.0

        x = x - self.modifier
        sum_prob = 0.0

        if self.advantage:
            for i in range(x, self.die_sides + 1):
                prob = 1.0 / self.die_sides
                prob2 = i * (1.0 / self.die_sides)
                prob3 = (i - 1) * (1.0 / self.die_sides)
                sum_prob += prob * prob2 + prob3 * prob
        elif self.disadvantage:
            for i in range(x, self.die_sides + 1):
                prob = 1.0 / self.die_sides
                prob2 = (self.die_sides - i + 1) * (1.0 / self.die_sides)
                prob3 = (self.die_sides - i) * (1.0 / self.die_sides)
                sum_prob += prob * prob2 + prob3 * prob
        else:
            for i in range(x, self.die_sides + 1):
                sum_prob += 1.0 / self.die_sides

        return sum_prob

    def color_roll(self, roll):
        if roll == 1:
            return str(roll)
        elif roll == self.die_sides:
            return str(roll)
        else:
            return str(roll)

    def __str__(self):
        rolls = []
        for r in self.rolls:
            if self.advantage:
                rolls.append(' | '.join(self.color_roll(i).bold if i == max(r) else str(i) for i in r))
            elif self.disadvantage:
                rolls.append(' | '.join(self.color_roll(i).bold if i == min(r) else str(i) for i in r))
            else:
                rolls.append(self.color_roll(r))

        if self.modifier != 0:
            return f"({' + '.join(rolls)}) + {self.modifier}"
        else:
            return f"({' + '.join(rolls)})"

    @staticmethod
    def numeric(c):
        try:
            float(c)
            return True
        except ValueError:
            return False

    def __eq__(self, other):
        return other.rolls == self.rolls and other.modifier == self.modifier and other.die_sides == self.die_sides

    def __lt__(self, other):
        return self.result() < other.result()

    def __add__(self, other):
        if isinstance(other, DieRolls):
            other.add_to_front(self)
            return other
        else:
            return DieRolls([self, other])

    @staticmethod
    def parse(roll_str):
        die_count_str = ''
        die_type_str = ''
        modifier_str = ''
        modifier_op = ''
        state = 'initial'

        roll_str = roll_str.strip()
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
            elif state == 'modifier':
                if c != ' ':
                    if DieRoll.numeric(c):
                        modifier_str += c

        if state == 'initial':
            modifier_str = die_count_str
            die_count_str = '0'

        number_of_die = 1 if die_count_str == '' else int(die_count_str)

        detail = DieRollDetail()
        detail.die_count = number_of_die
        detail.die_type = die_type_str
        detail.modifier = modifier_str
        detail.modifier_op = modifier_op
        return detail

    @staticmethod
    def roll(roll_str, crit=False, disadvantage=False, advantage=False, description=None, entity=None, battle=None, controller=None):
        roller = Roller(roll_str, crit=crit, disadvantage=disadvantage, advantage=advantage,
                        description=description, entity=entity, battle=battle, controller=controller)
        return roller.roll()

    @staticmethod
    def roll_with_lucky(entity, roll_str, crit=False, disadvantage=False, advantage=False, description=None, battle=None):
        roller = Roller(roll_str, crit=crit, disadvantage=disadvantage, advantage=advantage,
                        description=description, entity=entity, battle=battle)
        result = roller.roll()
        if result.nat_1() and entity.class_feature('lucky'):
            return roller.roll(lucky=True)
        else:
            return result

    @staticmethod
    def t(key, options=None):
        return i18n.t(key, **options)
