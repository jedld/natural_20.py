import random
import unittest

from natural20.battle import Battle
from natural20.die_roll import DieRoll
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.utils.death_info import describe_death


class TestDeathInfo(unittest.TestCase):
    def setUp(self):
        random.seed(7000)
        self.died = []
        em = EventManager()
        em.register_event_listener(['died'], lambda event: self.died.append(event))
        self.session = Session(root_path='tests/fixtures', event_manager=em)
        self.map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.map)
        self.pc = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.goblin = self.session.npc('goblin')
        self.battle.add(self.pc, 'a', position='spawn_point_1', token='G')
        self.battle.add(self.goblin, 'b', position='spawn_point_2', token='g')

    def _hit(self, dmg, critical=False):
        item = {'source': self.goblin, 'type': 'damage', 'attack_name': 'scimitar'}
        self.pc.take_damage(dmg, battle=self.battle, damage_type='slashing',
                            item=item, critical=critical)

    def test_massive_damage_records_killer_and_attack(self):
        self._hit(self.pc.hp() + self.pc.max_hp())
        self.assertTrue(self.pc.dead())
        info = self.died[-1]['death_info']
        self.assertEqual(info['cause'], 'massive_damage')
        self.assertEqual(info['killer_uid'], self.goblin.entity_uid)
        self.assertEqual(info['attack_name'], 'scimitar')
        self.assertEqual(info['damage_type'], 'slashing')
        self.assertEqual(self.pc.attributes['death_info'], info)
        self.assertIn('killed', describe_death(info, killer_pov=True))

    def test_failed_death_saves_credit_the_creature_that_downed_them(self):
        self._hit(self.pc.hp())
        self.assertTrue(self.pc.unconscious())
        self.pc.attributes['last_damage'] = {'killer_uid': 'someone_else'}
        self.pc.death_fails = 2
        while not self.pc.dead():
            self.pc.death_saving_throw(self.battle)
            if self.pc.conscious() or self.pc.stable():
                self.skipTest('death save roll did not fail with this seed')
        info = self.died[-1]['death_info']
        self.assertEqual(info['cause'], 'failed_death_saves')
        self.assertEqual(info['killer_uid'], self.goblin.entity_uid)
        self.assertIn('bled out', describe_death(info))

    def test_damage_while_down_finishes_them(self):
        self._hit(self.pc.hp())
        self._hit(1, critical=True)
        self._hit(1)
        self.assertTrue(self.pc.dead())
        self.assertEqual(self.died[-1]['death_info']['cause'], 'damage_while_dying')

    def test_dm_set_dead_has_no_killer(self):
        self._hit(3)
        self.pc.make_dead()
        info = self.died[-1]['death_info']
        self.assertEqual(info['cause'], 'unknown')
        self.assertNotIn('killer_uid', info)


if __name__ == '__main__':
    unittest.main()
