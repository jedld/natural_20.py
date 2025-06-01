from natural20.die_roll import DieRoll
from natural20.player_character import PlayerCharacter
from natural20.session import Session
import unittest
import random
import pdb


class TestDieRoll(unittest.TestCase):
  def setUp(self):
    random.seed(1000)

  def test_roll(self):
    self.assertEqual(DieRoll.roll('1').result(), 1)
    for _ in range(100):
      self.assertTrue(1 <= DieRoll.roll('1d6').result() <= 6)

    for _ in range(100):
      self.assertTrue(2 <= DieRoll.roll('2d6').result() <= 12)

    for _ in range(100):
      self.assertTrue(4 <= DieRoll.roll('2d6+2').result() <= 14)

    for _ in range(100):
      self.assertTrue(1 <= DieRoll.roll('2d6-1').result() <= 14)

    for _ in range(100):
      self.assertTrue(2 <= DieRoll.roll('2d20').result() <= 40)

  def test_addition_operator(self):
    sum_of_rolls = DieRoll.roll('2d8') + DieRoll.roll('1d6')
    self.assertEqual(sum_of_rolls.result(), 13)
    self.assertEqual(sum_of_rolls.__str__(), 'd8(7 + 2) + d6(4)')

  def test_expected_value(self):
    self.assertEqual(DieRoll.roll('1d6+2').expected(), 5.5)
    self.assertEqual(DieRoll.roll('1d6').expected(), 3.5)
    self.assertEqual(DieRoll.roll('1d20').expected(), 10.5)
    self.assertEqual(DieRoll.roll('2d20').expected(), 21.0)
    self.assertEqual(round(DieRoll.roll('1d20', advantage=True).expected(), 2), 13.83)
    self.assertAlmostEqual(DieRoll.roll('1d20', disadvantage=True).expected(), 7.175)
    self.assertEqual(DieRoll.roll('1d20 + 2').expected(), 12.5)

  def test_probability(self):
    self.assertEqual(round(DieRoll.roll('1d20+5').prob(10), 2), 0.8)
    self.assertEqual(round(DieRoll.roll('1d20+5', advantage=True).prob(10), 2), 0.96)

  def test_no_die_rolls(self):
    self.assertEqual(DieRoll.roll('1+1').result(), 2)

  def test_die_roll_comparison(self):
    rolls = [DieRoll.roll('1d8') for _ in range(100)]
    sorted_rolls = sorted([roll.result() for roll in rolls])
    rolls_sorted = sorted([roll.result() for roll in rolls])
    self.assertEqual(sorted_rolls, rolls_sorted)

  def test_critical_rolls(self):
    for _ in range(100):
      self.assertTrue(2 <= DieRoll.roll('1d6', crit=True).result() <= 12)

  def test_roll_with_disadvantage(self):
    roll = DieRoll.roll('1d20', disadvantage=True)
    self.assertEqual(roll.__str__(), 'd20(14 | 4*)')
    self.assertEqual(roll.result(), 4)

  def test_roll_with_advantage(self):
    roll = DieRoll.roll('1d20', advantage=True)
    self.assertEqual(roll.__str__(), 'd20(14* | 4)')
    self.assertEqual(roll.result(), 14)

  def test_roll_with_negative_modifier(self):
    roll = DieRoll.roll('1d20-5')
    self.assertEqual(roll.__str__(), 'd20(14) - 5')
    self.assertEqual(roll.result(), 9)

  def test_roll_with_addition(self):
    roll = DieRoll.roll('1d20+5') + 1
    self.assertEqual(roll.__str__(), 'd20(14) + 5 + 1')
    self.assertEqual(roll.result(), 20)

  def test_roll_with_luck(self):
    session = Session(root_path='tests/fixtures')
    random.seed(1000)
    player = PlayerCharacter.load(session, 'halfling_rogue.yml')
    DieRoll.fudge(1, 20)
    roll = DieRoll.roll_with_lucky(player, '1d20')
    self.assertEqual(str(roll), 'd20(1) lucky -> d20(14)')
    self.assertEqual(roll.description, '(lucky) None [1] -> [14]')

  def test_roll_with_luck_advantage_and_disadvantage(self):
    session = Session(root_path='tests/fixtures')
    random.seed(1000)
    player = PlayerCharacter.load(session, 'halfling_rogue.yml')
    DieRoll.fudge(1, 20)
    roll = DieRoll.roll_with_lucky(player, '1d20', advantage=True)
    self.assertEqual(str(roll), 'd20(1 | 14*) lucky -> d20(4 | 14*)')
    self.assertEqual(roll.description, '(lucky) None [(1, 14)] -> [(4, 14)]')
    DieRoll.fudge(1, 20)
    roll = DieRoll.roll_with_lucky(player, '1d20', disadvantage=True)
    self.assertEqual(str(roll), 'd20(1* | 13) lucky -> d20(12* | 13)')
    self.assertEqual(roll.description, '(lucky) None [(1, 13)] -> [(12, 13)]')

  def test_nat_1_only_on_d20(self):
    # Test that a 1 on a d6 is not considered a natural 1
    DieRoll.fudge(1, 6)
    d6_roll = DieRoll.roll('1d6')
    self.assertFalse(d6_roll.nat_1())

    # Test that a 1 on a d20 is considered a natural 1
    DieRoll.fudge(1, 20)
    d20_roll = DieRoll.roll('1d20')
    self.assertTrue(d20_roll.nat_1())

    # Test that a 1 on a d8 is not considered a natural 1
    DieRoll.fudge(1, 8)
    d8_roll = DieRoll.roll('1d8')
    self.assertFalse(d8_roll.nat_1())

  def test_nat_20_only_on_d20(self):
    # Test that a 20 on a d6 is not considered a natural 20
    DieRoll.fudge(20, 6)
    d6_roll = DieRoll.roll('1d6')
    self.assertFalse(d6_roll.nat_20())

    # Test that a 20 on a d20 is considered a natural 20
    DieRoll.fudge(20, 20)
    d20_roll = DieRoll.roll('1d20')
    self.assertTrue(d20_roll.nat_20())

    # Test that a 20 on a d8 is not considered a natural 20
    DieRoll.fudge(20, 8)
    d8_roll = DieRoll.roll('1d8')
    self.assertFalse(d8_roll.nat_20())

if __name__ == '__main__':
  unittest.main()
