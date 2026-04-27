"""Tests for the new rest preconditions: nearby hostiles, location opt-out,
and ration consumption on a long rest."""

import unittest

from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.npc import Npc
from natural20.player_character import PlayerCharacter
from natural20.session import Session


def _make_session():
    event_manager = EventManager()
    event_manager.standard_cli()
    return Session(root_path='tests/fixtures', event_manager=event_manager)


class TestRestRestrictions(unittest.TestCase):
    def setUp(self):
        self.session = _make_session()
        self.map = Map(self.session, 'battle_sim')
        self.battle = Battle(self.session, self.map)
        self.fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.skeleton = Npc.load(self.session, 'npcs/skeleton.yml')
        self.battle.add(self.fighter, 'a', position='spawn_point_1')
        self.battle.add(self.skeleton, 'b', position='spawn_point_3')

    # ---------------- nearby hostiles ----------------
    def test_short_rest_blocked_by_nearby_hostile(self):
        self.fighter.take_damage(5, session=self.session)
        with self.assertRaises(ValueError) as ctx:
            self.fighter.short_rest(self.battle, battle_map=self.map)
        self.assertIn('hostile', str(ctx.exception).lower())

    def test_short_rest_allowed_when_only_hostile_is_dead(self):
        self.fighter.take_damage(5, session=self.session)
        # Knock the skeleton out of the picture.
        self.skeleton.take_damage(self.skeleton.hp() + 100, session=self.session)
        # No combat, no nearby live hostile -> rest succeeds.
        self.fighter.short_rest(None, battle_map=self.map)

    def test_force_overrides_hostile_check(self):
        self.fighter.take_damage(5, session=self.session)
        # Combat is not started here; force still bypasses the hostile guard.
        self.fighter.short_rest(None, battle_map=self.map, force=True)

    def test_long_rest_blocked_by_nearby_hostile(self):
        self.fighter.add_item('rations', 5)
        with self.assertRaises(ValueError) as ctx:
            self.fighter.long_rest(battle=self.battle, battle_map=self.map, require_rations=True)
        self.assertIn('hostile', str(ctx.exception).lower())

    # ---------------- location opt-out ----------------
    def test_long_rest_blocked_by_map_opt_out(self):
        # Remove hostiles to isolate the location check.
        self.skeleton.take_damage(self.skeleton.hp() + 100, session=self.session)
        self.map.properties['allow_long_rest'] = False
        self.map.properties['long_rest_denied_message'] = 'unsafe wilderness'
        self.fighter.add_item('rations', 1)
        with self.assertRaises(ValueError) as ctx:
            self.fighter.long_rest(battle_map=self.map, require_rations=True)
        self.assertIn('unsafe wilderness', str(ctx.exception))

    def test_long_rest_blocked_by_campaign_opt_out(self):
        self.skeleton.take_damage(self.skeleton.hp() + 100, session=self.session)
        self.session.game_properties['allow_long_rest'] = False
        self.fighter.add_item('rations', 1)
        try:
            with self.assertRaises(ValueError):
                self.fighter.long_rest(battle_map=self.map, require_rations=True)
        finally:
            self.session.game_properties.pop('allow_long_rest', None)

    # ---------------- ration consumption ----------------
    def test_long_rest_requires_rations_when_opted_in(self):
        self.skeleton.take_damage(self.skeleton.hp() + 100, session=self.session)
        with self.assertRaises(ValueError) as ctx:
            self.fighter.long_rest(battle_map=self.map, require_rations=True)
        self.assertIn('ration', str(ctx.exception).lower())

    def test_long_rest_consumes_one_ration(self):
        self.skeleton.take_damage(self.skeleton.hp() + 100, session=self.session)
        self.fighter.add_item('rations', 2)
        self.fighter.long_rest(battle_map=self.map, require_rations=True)
        self.assertEqual(self.fighter.item_count('rations'), 1)

    def test_long_rest_default_does_not_require_rations(self):
        # Legacy callers (no require_rations) still work even with hostiles
        # present, as long as they pass force=True like the existing tests.
        self.fighter.long_rest(force=True)

    # ---------------- rest_status reporting ----------------
    def test_rest_status_reports_combat_and_hostiles(self):
        self.battle.start()
        try:
            status = self.fighter.rest_status(battle=self.battle, battle_map=self.map,
                                              require_rations=True)
        finally:
            self.battle.started = False
        self.assertFalse(status['short']['allowed'])
        self.assertFalse(status['long']['allowed'])
        joined_short = " ".join(status['short']['reasons']).lower()
        self.assertIn('combat', joined_short)
        # Long rest also reports the missing-ration reason and is NOT
        # force-overridable when rations are missing.
        joined_long = " ".join(status['long']['reasons']).lower()
        self.assertIn('ration', joined_long)
        self.assertFalse(status['long']['force_overrides'])

    def test_rest_status_allowed_when_clear(self):
        self.skeleton.take_damage(self.skeleton.hp() + 100, session=self.session)
        self.fighter.add_item('rations', 1)
        status = self.fighter.rest_status(battle=self.battle, battle_map=self.map,
                                          require_rations=True)
        self.assertTrue(status['short']['allowed'])
        self.assertTrue(status['long']['allowed'])
        self.assertEqual(status['long']['rations_available'], 1)

    def test_rest_status_reports_location_opt_out(self):
        self.skeleton.take_damage(self.skeleton.hp() + 100, session=self.session)
        self.map.properties['allow_long_rest'] = False
        self.map.properties['long_rest_denied_message'] = 'haunted ground'
        self.fighter.add_item('rations', 1)
        status = self.fighter.rest_status(battle=self.battle, battle_map=self.map,
                                          require_rations=True)
        self.assertTrue(status['short']['allowed'])
        self.assertFalse(status['long']['allowed'])
        self.assertIn('haunted ground', status['long']['reasons'])
        # Force can override a location restriction.
        self.assertTrue(status['long']['force_overrides'])


if __name__ == '__main__':
    unittest.main()
