from natural20.die_roll import DieRoll
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
    self.assertEqual(DieRoll.roll('1d20', disadvantage=True).expected(), 7.175)
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


if __name__ == '__main__':
  unittest.main()
