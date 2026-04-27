"""Tests for PersistentAoEZone lifecycle wiring with Battle."""

import unittest
from natural20.session import Session
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.battle import Battle
from natural20.spell.extensions.persistent_zone import PersistentAoEZone


class _RecordingZone(PersistentAoEZone):
    __slots__ = ("entered", "ticked_start", "ticked_end", "dismissed_called")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.entered = []
        self.ticked_start = []
        self.ticked_end = []
        self.dismissed_called = 0

    def on_enter(self, entity):
        self.entered.append(entity)

    def on_turn_start(self, entity):
        self.ticked_start.append(entity)

    def on_turn_end(self, entity):
        self.ticked_end.append(entity)

    def on_dismiss(self):
        self.dismissed_called += 1


class TestPersistentAoEZone(unittest.TestCase):
    def setUp(self):
        em = EventManager()
        self.session = Session(root_path='tests/fixtures', event_manager=em)
        self.map = Map(self.session, 'battle_sim')
        self.battle = Battle(self.session, self.map)
        self.caster = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.victim = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.victim.entity_uid = 'victim_uid'
        self.battle.add(self.caster, 'a', position=[1, 5])
        self.battle.add(self.victim, 'b', position=[5, 5])

    def _make_zone(self, **kwargs):
        squares = [(3, 5), (4, 5), (5, 5)]
        zone = _RecordingZone(
            self.caster, self.battle, self.map, squares,
            name='test', shape='line', **kwargs,
        )
        self.battle.register_zone(zone)
        return zone

    def test_register_and_zones_at(self):
        zone = self._make_zone()
        self.assertIn(zone, self.battle.active_zones)
        self.assertEqual(self.battle.zones_at((4, 5)), [zone])
        self.assertEqual(self.battle.zones_at((0, 0)), [])

    def test_movement_step_fires_on_enter(self):
        zone = self._make_zone()
        # Move from outside (2,5) into zone (3,5)
        self.battle.trigger_movement_step(self.victim, (2, 5), (3, 5))
        self.assertEqual(zone.entered, [self.victim])

    def test_movement_step_does_not_fire_when_already_inside(self):
        zone = self._make_zone()
        # From inside-zone to inside-zone
        self.battle.trigger_movement_step(self.victim, (3, 5), (4, 5))
        self.assertEqual(zone.entered, [])

    def test_start_of_turn_ticks_only_when_target_inside(self):
        zone = self._make_zone()
        # victim at (5,5) is inside zone
        self.battle.trigger_event('start_of_turn', self.victim, {'target': self.victim})
        self.assertEqual(zone.ticked_start, [self.victim])
        # caster at (1,5) is outside zone
        self.battle.trigger_event('start_of_turn', self.caster, {'target': self.caster})
        self.assertEqual(zone.ticked_start, [self.victim])

    def test_end_of_turn_ticks(self):
        zone = self._make_zone()
        self.battle.trigger_event('end_of_turn', self.victim, {'target': self.victim})
        self.assertEqual(zone.ticked_end, [self.victim])

    def test_dismiss_unregisters_and_calls_hook(self):
        zone = self._make_zone()
        zone.dismiss()
        self.assertEqual(zone.dismissed_called, 1)
        self.assertNotIn(zone, self.battle.active_zones)

    def test_expiration_by_round(self):
        # Start battle so current_round is defined
        self.battle.start()
        zone = self._make_zone(duration_rounds=1)
        # Same round -> not expired
        self.assertFalse(zone.expired())
        # Force round advance beyond expiration
        zone.expiration_round = self.battle.current_round() - 1
        self.assertTrue(zone.expired())

    def test_expired_zone_dismissed_on_event_tick(self):
        zone = self._make_zone()
        zone._dismissed = False
        zone.expiration_round = -1  # already expired
        # any tick should drop it
        self.battle.trigger_event('start_of_turn', self.victim, {'target': self.victim})
        self.assertNotIn(zone, self.battle.active_zones)


if __name__ == '__main__':
    unittest.main()
