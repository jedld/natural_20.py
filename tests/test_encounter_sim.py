"""Seeded encounter runner: identical traces, aggregate rates, loader errors."""

import tempfile
import unittest
from pathlib import Path

import yaml

from natural20.sim.encounter import EncounterError, run_trial, run_trials

ROOT = Path(__file__).resolve().parent.parent
FIGHT = ROOT / 'benchmarks' / 'encounters' / 'fighters_vs_goblins.yml'


class EncounterSimTest(unittest.TestCase):
    def test_same_seed_same_trace(self):
        first = run_trial(FIGHT, 1000, max_rounds=1)
        second = run_trial(FIGHT, 1000, max_rounds=1)
        self.assertEqual(first['trace'], second['trace'])
        self.assertEqual(first['winner'], second['winner'])
        self.assertEqual(first['combatants'], second['combatants'])
        self.assertTrue(first['trace'])
        for row in first['trace']:
            self.assertNotIn('explain', row)

    def test_explain_records_top_choices(self):
        trial = run_trial(FIGHT, 1000, explain=True, max_rounds=1)
        explained = [row for row in trial['trace'] if row.get('explain')]
        self.assertTrue(explained)
        top = explained[0]['explain']
        self.assertGreaterEqual(len(top), 1)
        self.assertLessEqual(len(top), 3)
        self.assertIn('action', top[0])
        self.assertIn('score', top[0])

    def test_report_counts_wins_and_survival(self):
        report = run_trials(FIGHT, 2, 1000, max_rounds=1)
        self.assertEqual(report['trials'], 2)
        accounted = report['party_wins'] + report['monster_wins'] + report['timeouts']
        accounted += sum(1 for game in report['games'] if game['winner'] == 'none')
        self.assertEqual(accounted, 2)
        self.assertEqual(report['party_wipe_rate'], round(report['party_wipes'] / 2, 4))
        self.assertEqual(report['party_win_rate'], round(report['party_wins'] / 2, 4))
        names = {row['name'] for row in report['combatants']}
        self.assertIn('Fighter 1', names)
        self.assertIn('Goblin 1', names)
        for row in report['combatants']:
            self.assertGreaterEqual(row['survival_rate'], 0.0)
            self.assertLessEqual(row['survival_rate'], 1.0)
        fighter = next(row for row in report['combatants'] if row['name'] == 'Fighter 1')
        self.assertEqual(fighter['side'], 'party')

    def test_missing_npc_is_rejected(self):
        text = yaml.safe_load(FIGHT.read_text(encoding='utf-8'))
        text['sides']['monsters']['members'][0]['npc'] = 'not_a_real_monster'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'bad.yml'
            path.write_text(yaml.safe_dump(text), encoding='utf-8')
            with self.assertRaises(EncounterError) as caught:
                run_trial(path, 1, root=ROOT / 'benchmarks', max_rounds=1)
        self.assertIn('not_a_real_monster', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
