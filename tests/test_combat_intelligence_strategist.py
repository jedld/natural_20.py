"""Intelligence-scaled battle planning (``natural20.utils.combat_intelligence``).

The hybrid LLM strategist must plan the way the creature thinks: a wolf
(INT 3) gets no step-by-step plan and cannot follow a ``hide``/kiting order,
while a mastermind gets the full planning vocabulary.
"""

import unittest

from natural20.utils.combat_intelligence import (
    allowed_move_intents,
    can_plan,
    strategist_policy,
    tactics_tier,
)


class _Ent:
    """Minimal entity stand-in: ability scores plus YAML properties."""

    def __init__(self, intelligence, name='Creacher', **props):
        self.name = name
        self.ability_scores = {'int': intelligence, 'wis': 10, 'cha': 10}
        self.properties = dict(props)


class TestStrategistPolicy(unittest.TestCase):
    def test_wolf_instinct_gets_no_plan(self):
        wolf = _Ent(3, name='Wolf')
        self.assertEqual(tactics_tier(wolf), 'instinct')
        policy = strategist_policy(wolf)
        self.assertFalse(policy['plan'])
        self.assertFalse(can_plan(wolf))
        self.assertEqual(allowed_move_intents(wolf), ())

    def test_simple_tier_plans_bluntly(self):
        gnoll = _Ent(5, name='Gnoll')
        policy = strategist_policy(gnoll)
        self.assertTrue(policy['plan'])
        self.assertEqual(policy['tier'], 'simple')
        self.assertLessEqual(policy['max_lines'], 4)
        self.assertEqual(policy['steps'], 1)
        self.assertFalse(policy['reactions'])
        tags = allowed_move_intents(gnoll)
        self.assertIn('engage', tags)
        self.assertIn('retreat', tags)
        self.assertNotIn('hide', tags)
        self.assertNotIn('range', tags)

    def test_tactical_and_mastermind_get_the_full_vocabulary(self):
        fighter = strategist_policy(_Ent(10))
        mastermind = strategist_policy(_Ent(16))
        for tag in ('engage', 'retreat', 'range', 'hide', 'hold'):
            self.assertIn(tag, fighter['move_tags'])
            self.assertIn(tag, mastermind['move_tags'])
        self.assertTrue(fighter['reactions'])
        self.assertTrue(mastermind['reactions'])
        self.assertGreater(mastermind['max_lines'], fighter['max_lines'])
        self.assertLess(fighter['max_lines'], 16)

    def test_guidance_speaks_of_the_creature_and_its_wits(self):
        policy = strategist_policy(_Ent(3, name='Wolf'))
        self.assertIn('Wolf', policy['guidance'])
        self.assertIn('INT 3', policy['guidance'])
        self.assertNotIn(policy['guidance'], strategist_policy(_Ent(16))['guidance'])

    def test_yaml_strategist_override_forces_plan_on(self):
        wolf = _Ent(3, name='Wolf', strategist='always')
        self.assertTrue(strategist_policy(wolf)['plan'])

    def test_yaml_strategist_override_turns_plan_off(self):
        archmage = _Ent(18, name='Archmage', strategist='off')
        self.assertFalse(strategist_policy(archmage)['plan'])

    def test_controller_mode_beats_the_default_but_not_the_creature(self):
        wolf = _Ent(3, name='Wolf')
        self.assertTrue(strategist_policy(wolf, 'always')['plan'])
        archmage = _Ent(18, strategist='always')
        self.assertFalse(strategist_policy(archmage, 'off')['plan'])

    def test_tactics_override_drives_the_policy(self):
        wolf = _Ent(3, name='Wolf', tactics='mastermind')
        policy = strategist_policy(wolf)
        self.assertEqual(policy['tier'], 'mastermind')
        self.assertTrue(policy['plan'])
        self.assertIn('hide', allowed_move_intents(wolf))


if __name__ == '__main__':
    unittest.main()
