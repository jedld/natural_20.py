import json
import random
import unittest

from natural20.actions.summon_creatures_action import DismissSummonsAction, SummonCreaturesAction
from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.generic_controller import GenericController
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.utils import summons as summon_utils


CHILDREN_OF_THE_NIGHT = {
    'name': 'children_of_the_night',
    'label': 'Children of the Night',
    'uses_per_day': 1,
    'cost': 'action',
    'blocked_by': ['sunlight'],
    'arrival': 1,
    'duration': 3600,
    'dismiss': 'bonus_action',
    'options': [
        {'npc': 'swarm_of_bats', 'count': 3},
        {'npc': 'swarm_of_rats', 'count': 2},
        {'npc': 'wolf', 'count': 4, 'requires': ['outdoors']},
    ],
}


class SummonTestBase(unittest.TestCase):
    def setUp(self):
        random.seed(99)
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.map = Map(self.session, 'tests/fixtures/jev_arena.yml')
        self.session.register_map('arena', self.map)
        self.battle = Battle(self.session, self.map)
        self.controller = GenericController(self.session)
        self.pc = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle.add(self.pc, 'a', position=[5, 1], add_to_initiative=True)
        self.vampire = self.session.npc('vampire_lord')
        self.vampire.properties['summons'] = [dict(CHILDREN_OF_THE_NIGHT)]
        self.map.add(self.vampire, 5, 5)
        self.battle.add(self.vampire, 'b', controller=self.controller, add_to_initiative=True)
        self.battle.start()
        self.battle.set_current_turn(self.vampire)
        self.vampire.reset_turn(self.battle)
        self.pc.reset_turn(self.battle)

    def summon_actions(self):
        return [a for a in self.vampire.available_actions(self.session, self.battle, map=self.map)
                if isinstance(a, SummonCreaturesAction)]

    def call(self, option=0):
        action = SummonCreaturesAction(self.session, self.vampire, 'summon_creatures',
                                       {'summon': 'children_of_the_night', 'option': option})
        self.battle.action(action)
        self.battle.commit(action)
        return action

    def arrive(self):
        self.battle.round += 1
        self.battle.set_current_turn(self.vampire)
        self.battle.start_turn()
        return summon_utils.active_summons(self.vampire)


class TestSummonAvailability(SummonTestBase):
    def test_indoor_options_exclude_wolves(self):
        labels = [a.label() for a in self.summon_actions()]
        self.assertEqual(len(labels), 2)
        self.assertTrue(any('Swarm of Bats' in l for l in labels))
        self.assertFalse(any('Wolf' in l for l in labels))

    def test_outdoors_offers_wolves(self):
        self.map.properties['outdoors'] = True
        self.assertEqual(len(self.summon_actions()), 3)

    def test_sunlight_blocks_the_call(self):
        self.map.properties['sunlight'] = True
        self.assertEqual(self.summon_actions(), [])

    def test_once_per_day_and_long_rest_recharges(self):
        self.call()
        self.vampire.reset_turn(self.battle)
        self.assertEqual(self.summon_actions(), [])
        self.vampire.long_rest(force=True)
        self.assertEqual(summon_utils.uses_remaining(self.vampire, CHILDREN_OF_THE_NIGHT), 1)

    def test_button_carries_choice(self):
        action = self.summon_actions()[0]
        self.assertEqual(action.to_h()['choice'], 'children_of_the_night:0')
        bare = SummonCreaturesAction(self.session, self.vampire, 'summon_creatures')
        built = bare.build_map()
        self.assertEqual(built['param'][0]['type'], 'select_choice')
        self.assertIs(built['next']('children_of_the_night:1'), bare)
        self.assertEqual(bare.option_index, 1)


class TestSummonLifecycle(SummonTestBase):
    def test_creatures_arrive_after_delay_and_join_the_fight(self):
        self.call(0)
        self.assertEqual(self.battle.entity_state_for(self.vampire)['action'], 0)
        self.assertEqual(summon_utils.active_summons(self.vampire), [])
        self.assertEqual(len(self.vampire.attributes['pending_summons']), 1)

        bats = self.arrive()
        self.assertEqual(len(bats), 3)
        for bat in bats:
            self.assertIn(bat, self.battle.combat_order)
            self.assertEqual(self.battle.entities[bat]['group'], 'b')
            self.assertIsNotNone(self.battle.controller_for(bat))
            self.assertEqual(bat.properties['summoner_uid'], self.vampire.entity_uid)
            self.assertIsNotNone(self.map.position_of(bat))
        self.assertEqual(self.battle.current_turn(), self.vampire)
        json.dumps(self.vampire.attributes['active_summons'])

    def test_out_of_combat_call_is_immediate(self):
        battle = Battle(self.session, self.map)
        spawned = summon_utils.begin_summon(self.vampire, 'children_of_the_night', 1, battle)
        self.assertEqual(len(spawned), 2)

    def test_summoner_death_sends_them_away(self):
        self.call(0)
        bats = self.arrive()
        self.vampire.make_dead(self.battle)
        for bat in bats:
            self.assertNotIn(bat, self.battle.combat_order)
            self.assertNotIn(bat, self.map.entities)
        self.assertEqual(self.vampire.attributes['active_summons'], [])

    def test_pending_summons_cancelled_on_death(self):
        self.call(0)
        self.vampire.make_dead(self.battle)
        self.assertEqual(self.vampire.attributes['pending_summons'], [])

    def test_summons_expire_after_duration(self):
        self.call(1)
        rats = self.arrive()
        self.session.game_time = int(self.session.game_time or 0) + 3601
        self.battle.set_current_turn(self.vampire)
        self.battle.start_turn()
        for rat in rats:
            self.assertNotIn(rat, self.battle.combat_order)

    def test_dismiss_as_bonus_action(self):
        self.call(0)
        bats = self.arrive()
        self.vampire.reset_turn(self.battle)
        dismiss = next(a for a in self.vampire.available_actions(self.session, self.battle, map=self.map)
                       if isinstance(a, DismissSummonsAction))
        self.battle.action(dismiss)
        self.battle.commit(dismiss)
        self.assertEqual(self.battle.entity_state_for(self.vampire)['bonus_action'], 0)
        self.assertTrue(all(b not in self.battle.combat_order for b in bats))


class TestSummonAI(SummonTestBase):
    def test_ai_values_summon_only_against_enemies(self):
        action = self.summon_actions()[0]
        self.assertGreater(action.ai_value(self.battle, 1), 0)
        self.assertEqual(action.ai_value(self.battle, 0), 0)

    def test_generic_controller_scores_summon(self):
        scored = self.controller._sort_actions_with_scores(
            self.vampire, self.battle, self.summon_actions())
        self.assertTrue(all(score > 0 for _, score in scored))


class TestBattleRemoveKeepsTurn(SummonTestBase):
    def test_removing_earlier_combatant_keeps_current_turn(self):
        current = self.battle.current_turn()
        other = next(e for e in self.battle.combat_order if e is not current)
        self.battle.remove(other)
        self.assertEqual(self.battle.current_turn(), current)
