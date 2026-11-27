"""Battle psychology: nerve, courage and authored weaknesses.

A character written as a coward should break and run mid-fight even with no
LLM in the loop; undead and brave creatures never do. The disposition feeds
the strategist prompt, the JEV state and the deterministic controller, and it
also hard-constrains the JEV move menu (``apply_morale_move_bias``).
"""

import unittest

from natural20.utils import combat_psychology as psych
from natural20.utils.jev_decision import (
    MOVE_INTENT_ENGAGE,
    MOVE_INTENT_RETREAT,
    MORALE_MOVE_TAG,
    apply_morale_move_bias,
)


class _Ent:
    def __init__(self, name='Gomerin', hp=30, max_hp=30, kind='humanoid', **props):
        self.name = name
        self.properties = dict(props)
        if kind:
            self.properties.setdefault('race', [kind])
        self.damage_vulnerabilities = list(props.get('vulnerabilities') or [])
        self._hp = hp
        self._max = max_hp

    def hp(self):
        return self._hp

    def max_hp(self):
        return self._max

    def dead(self):
        return self._hp <= 0

    def npc(self):
        return self.properties.get('race') != ['humanoid']


class _Map:
    def __init__(self):
        self.feet_per_grid = 5

    def position_of(self, entity):
        return (0, 0)

    def distance(self, a, b, **kwargs):
        return 1.0


class _Battle:
    def __init__(self, entity, threats=(), allies=()):
        self._entity = entity
        self._threats = list(threats)
        self._allies = list(allies)
        self.state = {}
        self.event_manager = None

    def entity_state_for(self, entity):
        return self.state.setdefault(id(entity), {})

    def opponents_of(self, entity):
        return list(self._threats)

    def allies_of(self, entity):
        return [entity] + list(self._allies)

    def can_see(self, a, b):
        return True

    def map_for(self, entity):
        return _Map()


def _leaf(desc, kind='move'):
    return (kind, None, desc)


class TestDisposition(unittest.TestCase):
    def test_coward_tag_makes_a_runner(self):
        disp = psych.disposition(_Ent(combat_personality='cowardly'))
        self.assertEqual(disp['stance'], psych.STANCE_FLIGHTY)
        self.assertEqual(disp['flee_at_hp'], 0.5)
        self.assertTrue(disp['authored'])

    def test_personality_prose_is_inferred(self):
        coward = _Ent(personality_traits='I am a coward. I run away from any fight.')
        self.assertEqual(psych.disposition(coward)['stance'], psych.STANCE_FLIGHTY)

        brave = _Ent(flaws='Reckless, always charging in headlong.')
        self.assertEqual(psych.disposition(brave)['stance'], psych.STANCE_RECKLESS)

        zealot = _Ent(ideals='I fight to the death for my temple.')
        self.assertEqual(psych.disposition(zealot)['stance'], psych.STANCE_FEARLESS)

    def test_morale_block_wins_over_inference(self):
        ent = _Ent(combat_personality='cowardly',
                   morale={'flee_at_hp': 0.75, 'flee_when_outnumbered': False})
        disp = psych.disposition(ent)
        self.assertEqual(disp['stance'], psych.STANCE_FLIGHTY)
        self.assertAlmostEqual(disp['flee_at_hp'], 0.75)
        self.assertFalse(disp['flee_when_outnumbered'])

    def test_undead_and_fearless_never_break(self):
        skeleton = _Ent(name='Skeleton', kind='undead', combat_personality='cowardly')
        self.assertTrue(psych.disposition(skeleton)['never_flee'])
        paladin = _Ent(features=['fearless'], combat_personality='cowardly')
        self.assertTrue(psych.disposition(paladin)['never_flee'])

    def test_beast_defaults_to_normal_nerve(self):
        disp = psych.disposition(_Ent(name='Wolf', kind='beast'))
        self.assertEqual(disp['stance'], psych.STANCE_NORMAL)
        self.assertGreater(disp['flee_at_hp'], 0)


class TestMorale(unittest.TestCase):
    def setUp(self):
        self.coward = _Ent(name='Gomerin', hp=30, combat_personality='cowardly')
        self.brute = _Ent(name='Brute', hp=30, combat_personality='reckless')
        self.threat = _Ent(name='Ogre', hp=30, kind='giant')
        self.battle = _Battle(self.coward, threats=[self.threat])

    def test_nerve_holds_while_healthy(self):
        self.assertFalse(psych.morale_broken(self.battle, self.coward))
        self.assertIsNone(psych.morale_directive(self.battle, self.coward))

    def test_nerve_breaks_when_wounded_and_latches(self):
        self.coward._hp = 12
        self.assertTrue(psych.morale_broken(self.battle, self.coward))
        self.assertEqual(psych.morale_directive(self.battle, self.coward), 'retreat')
        # healing does not talk it back into the fight
        self.coward._hp = 25
        self.assertTrue(psych.morale_broken(self.battle, self.coward))

    def test_brave_creature_keeps_fighting_hurt(self):
        battle = _Battle(self.brute, threats=[self.threat])
        self.brute._hp = 1
        self.assertFalse(psych.morale_broken(battle, self.brute))

    def test_outnumbered_runner_breaks_at_full_health(self):
        one = _Ent(name='Scout', hp=30, morale={'stance': 'cautious'})
        threats = [self.threat, _Ent(name='Ogre 2', kind='giant'),
                   _Ent(name='Ogre 3', kind='giant')]
        battle = _Battle(one, threats=threats)
        self.assertTrue(psych.morale_broken(battle, one))

    def test_no_threats_no_flight(self):
        battle = _Battle(self.coward, threats=[])
        self.coward._hp = 1
        self.assertFalse(psych.morale_broken(battle, self.coward))

    def test_flee_threat_is_a_visible_enemy(self):
        self.assertIs(psych.flee_threat(self.battle, self.coward), self.threat)


class TestMoveBias(unittest.TestCase):
    def test_broken_nerve_drops_offensive_moves(self):
        coward = _Ent(name='Gomerin', hp=8, combat_personality='cowardly')
        battle = _Battle(coward, threats=[_Ent(name='Ogre', kind='giant')])
        leaves = [
            _leaf('attack: Greataxe at Ogre', kind='attack'),
            _leaf('move: engage (advance toward Ogre)'),
            _leaf('move: retreat (back away from Ogre)'),
            _leaf('pass (end turn)', kind='end_turn'),
        ]
        out = apply_morale_move_bias(leaves, battle, coward)
        descs = [d for _t, _a, d in out]
        self.assertFalse(any(d.startswith('move: engage') for d in descs))
        retreat = [d for d in descs if d.startswith('move: retreat')]
        self.assertTrue(retreat)
        self.assertIn(MORALE_MOVE_TAG, retreat[0])

    def test_intact_nerve_changes_nothing(self):
        healthy = _Ent(name='Gomerin', hp=30, combat_personality='cowardly')
        battle = _Battle(healthy, threats=[_Ent(name='Ogre', kind='giant')])
        leaves = [_leaf('move: engage (advance toward Ogre)'),
                  _leaf('move: retreat (back away from Ogre)')]
        self.assertEqual(apply_morale_move_bias(leaves, battle, healthy), leaves)

    def test_intent_constants_are_distinct(self):
        self.assertNotEqual(MOVE_INTENT_ENGAGE, MOVE_INTENT_RETREAT)


class TestPersonaLines(unittest.TestCase):
    def test_coward_persona_and_weaknesses_reach_the_prompt(self):
        ent = _Ent(name='Gomerin', hp=30, combat_personality='cowardly',
                   vulnerabilities=['fire'])
        lines = psych.persona_lines(None, ent)
        joined = '\n'.join(lines)
        self.assertIn('is a coward', joined)
        self.assertIn('breaks and runs at or below 50% of its hit points', joined)
        self.assertIn('vulnerable to fire', joined)

    def test_broken_nerve_is_stated(self):
        ent = _Ent(name='Gomerin', hp=5, combat_personality='cowardly')
        battle = _Battle(ent, threats=[_Ent(name='Ogre', kind='giant')])
        psych.morale_broken(battle, ent)
        joined = '\n'.join(psych.persona_lines(battle, ent))
        self.assertIn('nerve has ALREADY broken', joined)

    def test_fearless_creature_is_never_told_to_run(self):
        lines = psych.persona_lines(None, _Ent(name='Skeleton', kind='undead'))
        joined = '\n'.join(lines)
        self.assertIn('never retreats', joined)
        self.assertNotIn('breaks and runs', joined)


class TestCowardRunsInBattle(unittest.TestCase):
    """End to end: a cowardly character with the deterministic AI runs off."""

    def setUp(self):
        import random
        random.seed(7)
        from natural20.battle import Battle
        from natural20.event_manager import EventManager
        from natural20.generic_controller import GenericController
        from natural20.map import Map
        from natural20.session import Session

        self.session = Session(root_path='tests/fixtures',
                               event_manager=EventManager())
        self.map = Map(self.session, 'entryway')
        self.battle = Battle(self.session, self.map)
        self.pc = self.map.entity_by_uid('gomerin')
        self.goblin = self.session.npc('goblin')
        self.battle.add(self.pc, 'a')
        self.battle.add(self.goblin, 'b')
        px, py = self.map.position_of(self.pc)
        self.map.place((px + 1, py), self.goblin)
        self.battle.start()
        self.controller = GenericController(self.session)

    def _distance_to_goblin(self):
        return self.map.distance(self.pc, self.goblin)

    def test_coward_breaks_and_runs_at_full_health(self):
        # "runs away from any encounter"
        self.pc.properties['combat_personality'] = 'cowardly'
        self.pc.properties['morale'] = {'flee_at_hp': 1.0}
        self.pc.reset_turn(self.battle)
        actions = list(self.pc.available_actions(self.session, self.battle))
        action = self.controller.select_action(self.battle, self.pc, actions)
        self.assertIsNotNone(action, 'a panicking creature still acts')
        self.assertEqual(getattr(action, 'action_type', None), 'dash')
        # the Dash has now been spent (as the game loop would do): the move
        # step must actually carry the creature away
        self.battle.entity_state_for(self.pc)['action'] = 0
        before = self._distance_to_goblin()
        move = self.controller.move_for(self.pc, self.battle)
        self.assertIsNotNone(move, 'and it runs')
        self.assertEqual(getattr(move, 'action_type', None), 'move')
        path = getattr(move, 'move_path', None) or []
        self.assertGreaterEqual(len(path), 2)
        gx, gy = self.map.position_of(self.goblin)
        end_x, end_y = path[-1]
        end_distance = max(abs(end_x - gx), abs(end_y - gy))
        self.assertGreater(end_distance, before,
                           'the escape path must gain distance from the threat')

    def test_the_same_coward_stands_and_fights_when_healthy_by_default(self):
        self.pc.properties['combat_personality'] = 'cowardly'
        self.pc.reset_turn(self.battle)
        actions = list(self.pc.available_actions(self.session, self.battle))
        action = self.controller.select_action(self.battle, self.pc, actions)
        self.assertNotEqual(getattr(action, 'action_type', None), 'dash')

    def test_a_fleeing_dash_is_never_treated_as_wasteful(self):
        from natural20.actions.dash import DashAction
        from natural20.utils import pointless_actions

        self.pc.reset_turn(self.battle)
        dash = DashAction(self.session, self.pc, 'dash')
        # healthy and not a runner: dashing out of melee is wasteful
        self.assertTrue(pointless_actions.is_pointless(self.battle, self.pc, dash))
        # once its nerve breaks, running IS the plan
        self.pc.properties['combat_personality'] = 'cowardly'
        self.pc.properties['morale'] = {'flee_at_hp': 1.0}
        self.assertFalse(pointless_actions.is_pointless(self.battle, self.pc, dash))


if __name__ == '__main__':
    unittest.main()
