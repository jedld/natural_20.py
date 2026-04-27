"""Phase 4 tests for SummonedEntity helper + Battle summon registry."""

import unittest

from natural20.session import Session
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.battle import Battle
from natural20.player_character import PlayerCharacter
from natural20.utils.summoned_entity import SummonedEntity


class TestSummonedEntity(unittest.TestCase):
    def make_session(self):
        em = EventManager()
        em.standard_cli()
        return Session(root_path='tests/fixtures', event_manager=em)

    def setUp(self):
        self.session = self.make_session()
        self.battle_map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.battle_map)
        self.owner = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.summon_entity = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.battle.add(self.owner, 'a', position=[0, 0])

    def test_register_and_lookup(self):
        s = SummonedEntity(entity=self.summon_entity, owner=self.owner,
                           expiration_round=5, source_id='find_familiar')
        self.battle.register_summon(s)
        self.assertIn(s, self.battle.summons_for(self.owner))
        self.assertIn(s, self.battle.all_summons())

    def test_unregister(self):
        s = SummonedEntity(entity=self.summon_entity, owner=self.owner)
        self.battle.register_summon(s)
        self.assertTrue(self.battle.unregister_summon(s))
        self.assertEqual(self.battle.summons_for(self.owner), [])

    def test_tick_drops_expired(self):
        # expiration_round=0; current round starts at 0 too — tick once after
        # advancing to round 2 so the expiration trips.
        s = SummonedEntity(entity=self.summon_entity, owner=self.owner,
                           expiration_round=0)
        self.battle.register_summon(s)
        self.battle.round = 2
        self.battle.tick_summons()
        self.assertNotIn(s, self.battle.all_summons())

    def test_round_trip(self):
        s = SummonedEntity(entity=self.summon_entity, owner=self.owner,
                           expiration_round=3, source_id='spiritual_weapon',
                           concentration=True)
        # Register both entities so the registry can resolve UIDs on rehydrate.
        self.session.register_entity(self.summon_entity)
        data = s.to_dict()
        rehydrated = SummonedEntity.from_dict(data, self.session)
        self.assertEqual(rehydrated.expiration_round, 3)
        self.assertEqual(rehydrated.source_id, 'spiritual_weapon')
        self.assertTrue(rehydrated.concentration)
        self.assertIs(rehydrated.owner, self.owner)
        self.assertIs(rehydrated.entity, self.summon_entity)


if __name__ == '__main__':
    unittest.main()
