import unittest

from natural20.battle import Battle
from natural20.environment_zones import (
    demote_battle_zones_to_environment,
    promote_environment_zones_to_battle,
    register_environment_zone,
    tick_environment_zones,
)
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.session import Session
from natural20.spell.extensions.persistent_zone import PersistentAoEZone


class _RecordingZone(PersistentAoEZone):
    def __init__(self, owner, battle, battle_map, squares):
        super().__init__(owner, battle, battle_map, squares, name='recording')
        self.turn_starts = []

    def on_turn_start(self, entity):
        self.turn_starts.append(entity)


class EnvironmentZonesTestCase(unittest.TestCase):
    def setUp(self):
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.battle_map = Map(self.session, 'battle_sim')
        self.battle = Battle(self.session, self.battle_map)
        self.npc = self.session.npc('goblin', {'name': 'Goblin'})
        self.battle_map.add(self.npc, 3, 3)

    def test_tick_environment_zones_runs_on_turn_start(self):
        zone = _RecordingZone(self.npc, None, self.battle_map, [(3, 3)])
        register_environment_zone(zone)
        tick_environment_zones({'battle_sim': self.battle_map})
        self.assertIn(self.npc, zone.turn_starts)

    def test_promote_and_demote_between_battle_and_map(self):
        zone = _RecordingZone(self.npc, None, self.battle_map, [(3, 3)])
        register_environment_zone(zone)
        self.battle.add(self.npc, 'b')
        promote_environment_zones_to_battle(self.battle)
        self.assertIn(zone, self.battle.active_zones)
        self.assertEqual(getattr(self.battle_map, 'environment_zones', []), [])
        demote_battle_zones_to_environment(self.battle)
        self.assertEqual(self.battle.active_zones, [])
        self.assertIn(zone, self.battle_map.environment_zones)


if __name__ == '__main__':
    unittest.main()
