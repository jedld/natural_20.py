"""Strategist attack steps → JEV action-menu follow-through.

The hybrid controller's MOVE: tag already hard-steers the move menu; these
tests cover the parallel for the ACTION menu: when the commander's orders
command an attack on a named creature, the matching attack/cast leaves are
tagged and hoisted so the System One executor cannot silently pick Hide,
Dodge or pass instead of the ordered strike.
"""

import unittest
from types import SimpleNamespace

from natural20.utils.jev_decision import (
    ORDERED_ACTION_TAG,
    apply_strategist_action_bias,
    _orders_command_attack,
)


def _leaf(desc, kind='attack'):
    return (kind, SimpleNamespace(desc=desc), desc)


class TestOrdersCommandAttack(unittest.TestCase):
    def test_affirmative_attack_step(self):
        self.assertTrue(_orders_command_attack(
            "1. Move to (4, 8)\n2. Attack Gomerin with Morningstar\nMOVE: engage"))

    def test_negated_attack_does_not_count(self):
        for orders in (
            "1. No visible enemies; stay hidden and wait.\n2. Use Hide.",
            "1. Do not attack; hold position.",
            "1. Avoid combat; no enemies are visible.",
        ):
            self.assertFalse(_orders_command_attack(orders), orders)


class TestApplyStrategistActionBias(unittest.TestCase):
    ORDERS = (
        "Focus fire on Gomerin from range.\n"
        "1. Move to (8, 9).\n"
        "2. Attack Gomerin with Shortbow.\n"
        "3. Hold reaction.\n"
        "MOVE: range"
    )
    NAMES = ['Gomerin', 'Vrogvakrog', 'Wolf']

    def _menu(self):
        return [
            _leaf('attack Wolf with Javelin'),
            _leaf('hide', kind='hide'),
            _leaf('attack Gomerin with Shortbow (hits 40%)'),
            _leaf('dodge', kind='dodge'),
            _leaf('move: defensive away from [5, 4]', kind='move'),
            _leaf('cast Minor Illusion', kind='spell'),
        ]

    def test_ordered_attack_hoisted_and_tagged(self):
        leaves, ordered = apply_strategist_action_bias(
            self._menu(), self.ORDERS, self.NAMES)
        self.assertTrue(ordered)
        first_kind, _, first_desc = leaves[0]
        self.assertEqual(first_kind, 'attack')
        self.assertIn('Gomerin', first_desc)
        self.assertIn(ORDERED_ACTION_TAG, first_desc)
        # The unordered attack on Wolf stays in its original relative place.
        self.assertNotIn(ORDERED_ACTION_TAG,
                        next(d for _t, _a, d in leaves if 'Wolf' in d))
        # Everything else keeps its original relative order after the
        # hoisted leaves (the unordered Wolf attack stays among them).
        self.assertEqual([t for t, _a, _d in leaves][1:],
                         ['attack', 'hide', 'dodge', 'move', 'spell'])

    def test_spell_named_in_orders_matches_too(self):
        orders = "1. Cast Fireball at Gomerin's square.\nMOVE: range"
        leaves, ordered = apply_strategist_action_bias(
            [_leaf('attack Gomerin with Shortbow'),
             _leaf('cast Fireball on [5, 4]', kind='spell')],
            orders, self.NAMES)
        # No spell-name mention of Gomerin in the spell leaf: only the attack
        # names the target, so only it is hoisted.
        self.assertTrue(ordered)
        self.assertEqual(leaves[0][0], 'attack')

    def test_display_name_position_suffix_tolerated(self):
        leaves, ordered = apply_strategist_action_bias(
            [_leaf('attack Gomerin@[5, 4] with Rapier')],
            self.ORDERS, ['Gomerin@[5, 4]'])
        self.assertTrue(ordered)
        self.assertIn(ORDERED_ACTION_TAG, leaves[0][2])

    def test_no_orders_no_change(self):
        menu = self._menu()
        out, ordered = apply_strategist_action_bias(menu, None, self.NAMES)
        self.assertIs(out, menu)
        self.assertFalse(ordered)

    def test_orders_without_target_names_no_change(self):
        menu = self._menu()
        out, ordered = apply_strategist_action_bias(
            menu, "1. Attack the intruder with the shortbow.\nMOVE: range",
            self.NAMES)
        self.assertIs(out, menu)
        self.assertFalse(ordered)

    def test_avoidance_orders_never_boost_attacks(self):
        out, ordered = apply_strategist_action_bias(
            self._menu(),
            "1. No visible enemies; stay hidden.\n2. Use Hide.\nMOVE: hide",
            self.NAMES)
        self.assertFalse(ordered)
        self.assertEqual(out[0][0], 'attack')  # untouched original order

    def test_movement_leaves_untouched(self):
        # A move leaf naming the same target is steered by MOVE:, not here.
        leaves, _ordered = apply_strategist_action_bias(
            [_leaf('move: offensive toward Gomerin', kind='move'),
             _leaf('attack Gomerin with Shortbow')],
            self.ORDERS, self.NAMES)
        self.assertEqual(leaves[0][0], 'attack')
        self.assertNotIn(ORDERED_ACTION_TAG, leaves[1][2])

    def test_blind_attack_matched_by_named_square(self):
        # An unseen target: the orders name Gomerin's square, the blind
        # attack leaf names only that square — they must still line up.
        orders = (
            "1. Stay hidden.\n"
            "2. Fire the Shortbow at Gomerin's position [0, 1] "
            "at disadvantage.\n"
            "MOVE: range"
        )
        leaves, ordered = apply_strategist_action_bias(
            [_leaf('hide', kind='hide'),
             _leaf('attack unseen creature at square [0, 1] (last known '
                   'position, it may have moved) with Shortbow '
                   '(disadvantage; misses if nothing is there)'),
             _leaf('attack unseen creature at square [9, 3] (last known '
                   'position, it may have moved) with Shortbow '
                   '(disadvantage; misses if nothing is there)')],
            orders, self.NAMES)
        self.assertTrue(ordered)
        self.assertIn('square [0, 1]', leaves[0][2])
        self.assertIn(ORDERED_ACTION_TAG, leaves[0][2])
        self.assertNotIn(ORDERED_ACTION_TAG, leaves[1][2])


if __name__ == '__main__':
    unittest.main()
