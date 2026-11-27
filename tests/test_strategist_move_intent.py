"""Strategist MOVE: tags → JEV move-leaf constraints."""

import unittest
from types import SimpleNamespace

from natural20.utils import combat_intelligence
from natural20.utils.jev_decision import (
    MOVE_INTENT_ENGAGE,
    MOVE_INTENT_HIDE,
    MOVE_INTENT_HOLD,
    MOVE_INTENT_RANGE,
    MOVE_INTENT_RETREAT,
    apply_strategist_move_bias,
    filter_move_leaves_by_wits,
    parse_strategist_move_intent,
)


def _leaf(desc, kind='move'):
    return (kind, SimpleNamespace(desc=desc), desc)


class TestParseStrategistMoveIntent(unittest.TestCase):
    def test_explicit_move_tag_wins(self):
        orders = (
            "Focus the archer.\n"
            "1. Close on the goblin\n"
            "MOVE: hold\n"
            "Reaction: hold"
        )
        self.assertEqual(parse_strategist_move_intent(orders), MOVE_INTENT_HOLD)

    def test_explicit_none_clears_intent(self):
        orders = "Stay at range.\nMOVE: none\nReaction: hold"
        self.assertIsNone(parse_strategist_move_intent(orders))

    def test_prose_hold(self):
        self.assertEqual(
            parse_strategist_move_intent("1. Do not move; cast from here."),
            MOVE_INTENT_HOLD,
        )

    def test_prose_range_beats_close_wording(self):
        self.assertEqual(
            parse_strategist_move_intent(
                "Stay at range; do not close into melee. Cast Magic Missile."),
            MOVE_INTENT_RANGE,
        )

    def test_prose_retreat_and_step_away(self):
        self.assertEqual(
            parse_strategist_move_intent("1. Move 5 feet away from Strahd."),
            MOVE_INTENT_RETREAT,
        )
        self.assertEqual(
            parse_strategist_move_intent("Fall back out of reach."),
            MOVE_INTENT_RETREAT,
        )

    def test_prose_engage_and_hide(self):
        self.assertEqual(
            parse_strategist_move_intent("1. Engage the vampire in melee."),
            MOVE_INTENT_ENGAGE,
        )
        self.assertEqual(
            parse_strategist_move_intent("2. Hide behind the pillar."),
            MOVE_INTENT_HIDE,
        )


class TestApplyStrategistMoveBias(unittest.TestCase):
    def setUp(self):
        self.leaves = [
            _leaf('move: engage Goblin: (3, 4)'),
            _leaf('move: offensive (4, 4) [OA-free, in reach of 5 ft foe)'),
            _leaf('move: defensive (1, 1) [half cover, safe, 15 ft from nearest foe)'),
            _leaf('move: retreat to (0, 0) (out of reach, 20 ft from nearest foe)'),
            _leaf('move: hide at (2, 2) (2 steps)'),
            _leaf('attack Goblin with Shortbow', 'attack'),
        ]

    def test_hold_drops_all_moves(self):
        out = apply_strategist_move_bias(self.leaves, "MOVE: hold")
        self.assertEqual([t for t, _, _ in out], ['attack'])

    def test_range_drops_engage_and_offensive(self):
        out = apply_strategist_move_bias(self.leaves, "MOVE: range")
        kinds = [d for t, _, d in out if t == 'move']
        self.assertTrue(all('engage' not in d and 'offensive' not in d for d in kinds))
        self.assertTrue(any('retreat' in d or 'defensive' in d for d in kinds))
        self.assertTrue(any('[commander ordered]' in d for d in kinds))

    def test_engage_drops_retreat(self):
        out = apply_strategist_move_bias(self.leaves, "MOVE: engage")
        kinds = [d for t, _, d in out if t == 'move']
        self.assertFalse(any('retreat' in d for d in kinds))
        self.assertTrue(any('engage' in d for d in kinds))

    def test_empty_filter_restores_defensive_fallback(self):
        # Only engage leaves exist; range intent would drop them all.
        leaves = [
            _leaf('move: engage Goblin: (3, 4)'),
            _leaf('attack Goblin with Shortbow', 'attack'),
        ]
        out = apply_strategist_move_bias(leaves, "Stay at range; MOVE: range")
        self.assertTrue(any(t == 'move' for t, _, _ in out))

    def test_no_orders_passthrough(self):
        out = apply_strategist_move_bias(self.leaves, None)
        self.assertEqual(out, self.leaves)


def _wits(intelligence, **props):
    return SimpleNamespace(name='Creacher', ability_scores={'int': intelligence},
                           properties=dict(props))


class TestWitsGating(unittest.TestCase):
    """A plan above the creature's own wits is never executed."""

    def setUp(self):
        self.leaves = [
            _leaf('move: hide at (7, 2)'),
            _leaf('move: retreat (back away)'),
            _leaf('move: engage Goblin: (3, 4)'),
            _leaf('attack Goblin with Shortbow', 'attack'),
        ]

    def test_intent_beyond_its_wits_is_ignored(self):
        orders = "Slip behind the pillar.\nMOVE: hide"
        simple = ('engage', 'retreat', 'hold')
        self.assertIsNone(parse_strategist_move_intent(orders, simple))
        self.assertEqual(parse_strategist_move_intent(orders, ('hide',)),
                         MOVE_INTENT_HIDE)
        # unrestricted calls keep working
        self.assertEqual(parse_strategist_move_intent(orders), MOVE_INTENT_HIDE)

    def test_bias_drops_an_unfollowable_intent(self):
        wolf = _wits(3)
        out = apply_strategist_move_bias(self.leaves, "MOVE: hide",
                                         allowed=combat_intelligence.allowed_move_intents(wolf))
        self.assertEqual([d for _t, _a, d in out],
                         [d for _t, _a, d in self.leaves])

    def test_beasts_are_not_offered_positioning_moves(self):
        beast = _wits(3)
        kinds = [d for _t, _a, d in filter_move_leaves_by_wits(self.leaves, beast)]
        self.assertFalse(any(d.startswith('move: hide') for d in kinds))
        self.assertTrue(any(d.startswith('move: engage') for d in kinds))

    def test_clever_creatures_keep_every_move_option(self):
        veteran = _wits(12)
        self.assertEqual(filter_move_leaves_by_wits(self.leaves, veteran), self.leaves)

    def test_filter_never_empties_the_move_menu(self):
        # Only positioning leaves exist: keep them rather than freeze the beast.
        leaves = [_leaf('move: hide at (7, 2)'), _leaf('move: offensive flank')]
        out = filter_move_leaves_by_wits(leaves, _wits(3))
        self.assertTrue(any(t == 'move' for t, _a, d in out))


if __name__ == '__main__':
    unittest.main()
