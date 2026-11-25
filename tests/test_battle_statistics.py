"""End-of-combat battle statistics (utils/battle_statistics).

Runs a real fixture battle through ``while_active`` and checks that
``Battle.statistics()`` aggregates the battle log (pairs, types, hits,
teams, fates), stays JSON-safe, and that the report is emitted DM-only into
the combat log at ``end_of_combat`` unless disabled via ``game.yml``.
"""

import json
import random
import unittest

from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.session import Session
from natural20.utils.battle_statistics import (collect_statistics,
                                               format_statistics_lines,
                                               settings_for)


class CapturingOutputLogger:
    def __init__(self):
        self.entries = []  # (msg, visibility)

    def log(self, event_msg, event=None, visibility=None):
        self.entries.append((event_msg, visibility))


class TestBattleStatistics(unittest.TestCase):
    def setUp(self):
        random.seed(11)
        self.logger = CapturingOutputLogger()
        em = EventManager(output_logger=self.logger)
        em.standard_cli()
        self.session = Session(root_path='tests/fixtures', event_manager=em)
        self.map = Map(self.session, 'entryway')
        self.battle = Battle(self.session, self.map)
        self.pc = self.map.entity_by_uid('gomerin')
        self.goblin = self.session.npc('goblin')
        self.map.place((1, 2), self.goblin)
        self.battle.add(self.pc, 'a')
        self.battle.add(self.goblin, 'b')
        self.battle.start()
        self.map.remove(self.pc)
        self.map.place((2, 2), self.pc)  # adjacent so the fight actually bites

    def _fight(self, max_rounds=12):
        """Run combat with ``while_active`` while acting as the host loop:
        the engine's turn runner leaves the action phase to the controller-
        driving host, so the callback plays each turn with GenericController
        before the turn ends."""
        from natural20.generic_controller import GenericController
        controller = GenericController(self.session)

        def take_turn(entity):
            if not entity.conscious() or entity.incapacitated():
                return False
            action = controller.select_action(
                self.battle, entity,
                entity.available_actions(self.session, self.battle))
            if action is not None:
                self.battle.execute_action(action)
            move = controller.move_for(entity, self.battle)
            if move is not None:
                self.battle.execute_action(move)
            return False

        self.battle.while_active(max_rounds, take_turn)

    def test_full_battle_produces_nonempty_statistics(self):
        self._fight()
        stats = self.battle.statistics()
        self.assertEqual(stats, collect_statistics(self.battle))
        self.assertGreater(stats['rounds'], 0)
        self.assertGreater(stats['totals']['damage'], 0)
        self.assertTrue(stats['pairs'])
        self.assertTrue(stats['damage_types'])
        self.assertTrue(any(t['dealt'] or t['taken']
                            for t in stats['teams'].values()))
        # hits/misses accounting adds up per side
        for side in stats['combatants'].values():
            self.assertGreaterEqual(side['hits'] + side['misses'], 1)
        # someone fell: the fight ended, so a fate is recorded
        fates = [f['fate'] for f in stats['fates']]
        self.assertIn('dead', fates)
        # kill attribution exists for the dead
        victims = {k['victim'] for k in stats['kills']}
        dead = {f['name'] for f in stats['fates'] if f['fate'] == 'dead'}
        self.assertTrue(dead - victims == set() or stats['kills'])

    def test_report_is_logged_dm_only(self):
        self._fight()
        header = [m for m, v in self.logger.entries
                  if 'Battle statistics after' in m]
        self.assertTrue(header, 'no statistics report logged at combat end')
        totals = [(m, v) for m, v in self.logger.entries
                  if m.startswith('[DM] Totals:')]
        self.assertTrue(totals)
        for _msg, visibility in totals:
            self.assertEqual(visibility, 'dm')

    def test_statistics_are_json_safe(self):
        self._fight()
        json.dumps(self.battle.statistics())

    def test_disabled_by_game_properties(self):
        self.session.game_properties = {'battle_statistics': False}
        self.assertFalse(settings_for(self.session)['enabled'])
        self._fight()
        self.assertFalse([m for m, _v in self.logger.entries
                          if 'Battle statistics' in m])

    def test_visibility_all_shows_players(self):
        self.session.game_properties = {'battle_statistics':
                                        {'visibility': 'all'}}
        self._fight()
        visible = [(m, v) for m, v in self.logger.entries
                   if m.startswith('Totals:')]
        self.assertTrue(visible)
        self.assertIsNone(visible[0][1])

    def test_format_lines_empty_for_boring_battle(self):
        # no actions committed yet: nothing to report
        self.assertEqual(format_statistics_lines(self.battle), [])


if __name__ == '__main__':
    unittest.main()
