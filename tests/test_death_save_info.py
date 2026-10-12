import unittest

from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.web.death_save_info import death_save_info, death_save_tile_attributes
from natural20.web.json_renderer import JsonRenderer
from natural20.web.map_state import entities_from_tiles


class TestDeathSaveInfo(unittest.TestCase):
    def setUp(self):
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.map)
        self.fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.npc = self.session.npc('goblin')
        self.battle.add(self.fighter, 'a', position='spawn_point_1', token='G')
        self.battle.add(self.npc, 'b', position='spawn_point_2', token='g')
        self.map.move_to(self.fighter, 1, 2, self.battle)
        self.map.move_to(self.npc, 1, 1, self.battle)

    def _drop(self, entity):
        entity.attributes['hp'] = 0
        entity.make_unconscious()

    def test_conscious_creature_has_no_tracker(self):
        self.assertIsNone(death_save_info(self.fighter))
        self.assertEqual(death_save_tile_attributes(self.fighter), {})

    def test_dying_pc_reports_tallies(self):
        self._drop(self.fighter)
        self.fighter.death_saves = 2
        self.fighter.death_fails = 1
        attrs = death_save_tile_attributes(self.fighter)
        self.assertEqual(
            attrs['death_saves'],
            {'successes': 2, 'failures': 1, 'stable': False, 'target': 3},
        )
        self.assertIn('2/3 successes', attrs['death_save_tooltip'])
        self.assertIn('1/3 failures', attrs['death_save_tooltip'])

    def test_stable_pc(self):
        self._drop(self.fighter)
        self.fighter.make_stable()
        info = death_save_info(self.fighter)
        self.assertTrue(info['stable'])
        self.assertEqual((info['successes'], info['failures']), (0, 0))

    def test_dead_pc_and_knocked_out_npc_have_no_tracker(self):
        self._drop(self.npc)
        self.assertIsNone(death_save_info(self.npc))
        self.fighter.attributes['hp'] = 0
        self.fighter.make_dead()
        self.assertIsNone(death_save_info(self.fighter))

    def test_renderer_tiles_and_map_state(self):
        self._drop(self.fighter)
        self.fighter.death_fails = 2
        tiles = [t for row in JsonRenderer(self.map, self.battle).render() for t in row]
        by_id = {t.get('id'): t for t in tiles if t.get('entity') and t.get('id')}
        self.assertEqual(by_id[self.fighter.entity_uid]['death_saves']['failures'], 2)
        self.assertNotIn('death_saves', by_id[self.npc.entity_uid])

        entries = {e['uid']: e for e in entities_from_tiles(tiles)}
        self.assertEqual(entries[self.fighter.entity_uid]['death_saves']['failures'], 2)
        self.assertNotIn('death_saves', entries[self.npc.entity_uid])


if __name__ == '__main__':
    unittest.main()
