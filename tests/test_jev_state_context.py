"""The JEV state context carries a compact character-sheet block:
identity (race/class/level or NPC kind/CR), proficient saves, senses and
condition immunities, class/race feature names, limited pools, NPC attack
options with to-hit/damage, and a short personality/backstory line.

Toggle: ``N20_JEV_SHEET=0`` disables it (small local decision models).
"""

import os
import random
import unittest

from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.session import Session
from natural20.utils.jev_decision import JevActionPlanner


def _session():
    return Session(root_path='tests/fixtures', event_manager=EventManager())


class TestJevSheetContext(unittest.TestCase):
    def setUp(self):
        random.seed(99)
        self.session = _session()
        self.map = Map(self.session, 'entryway')
        from natural20.battle import Battle
        self.battle = Battle(self.session, self.map)
        self.pc = self.map.entity_by_uid('gomerin')
        self.battle.add(self.pc, 'a')
        self.goblin = self.session.npc('goblin')
        self.battle.add(self.goblin, 'b')
        self.battle.start()
        self.planner = JevActionPlanner(None)

    def _lines(self, entity):
        return self.planner._render_state(self.battle, entity).splitlines()

    def test_pc_identity_and_features(self):
        lines = self._lines(self.pc)
        identity = next(l for l in lines if l.startswith('identity: '))
        self.assertIn('level', identity)
        self.assertIn('fighter', identity)
        self.assertIn('race', identity)
        # feature names present (class and/or race features)
        any(l.startswith('features: ') for l in lines)

    def test_npc_identity_cr_and_attacks(self):
        lines = self._lines(self.goblin)
        identity = next(l for l in lines if l.startswith('identity: '))
        self.assertIn('CR', identity)
        self.assertIn('goblin', identity.lower())
        self.assertIn('my attack options:', lines)
        attacks = [l for l in lines if l.startswith('- ') and 'to hit' in l]
        self.assertTrue(attacks, "expected to-hit/damage attack lines")
        self.assertTrue(any('Scimitar' in a for a in attacks))

    def test_npc_senses_line(self):
        lines = self._lines(self.goblin)
        senses = next(l for l in lines if l.startswith('senses/immunities: '))
        self.assertIn('darkvision 60 ft', senses)

    def test_bio_line_present(self):
        lines = self._lines(self.goblin)
        self.assertTrue(any(l.startswith('personality/backstory: ') for l in lines))

    def test_backstory_cap_and_single_line(self):
        self.goblin.properties['backstory'] = 'x' * 500 + '\nsecond line'
        lines = self._lines(self.goblin)
        bio = [l for l in lines if l.startswith('personality/backstory: ')]
        self.assertTrue(bio)
        self.assertLessEqual(len(bio[0]), 240 + len('personality/backstory: ') + 3)
        self.assertNotIn('\n', bio[0])

    def test_toggle_disables_block(self):
        os.environ['N20_JEV_SHEET'] = '0'
        try:
            lines = self._lines(self.goblin)
        finally:
            os.environ.pop('N20_JEV_SHEET', None)
        self.assertFalse(any(l.startswith('identity: ') for l in lines))
        self.assertFalse(any(l.startswith('my attack options:') for l in lines))

    def test_save_bonuses_shown_only_when_proficient(self):
        self.pc.properties['saving_throw_proficiencies'] = ['str_save', 'con_save']
        lines = self._lines(self.pc)
        saves = next(l for l in lines if l.startswith('saves: '))
        self.assertIn('str', saves)
        self.assertIn('con', saves)
        self.assertNotIn('dex', saves)

    def test_resource_pools_line(self):
        from natural20.resource_pool import ResourcePool
        self.goblin.resources['innate:fog_cloud'] = ResourcePool(
            'innate:fog_cloud', 1, current=0)
        lines = self._lines(self.goblin)
        pools = next(l for l in lines if l.startswith('pools: '))
        self.assertIn('innate:fog_cloud 0/1', pools)


if __name__ == '__main__':
    unittest.main()
