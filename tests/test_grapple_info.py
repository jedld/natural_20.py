import unittest

from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.web.grapple_info import (
    grapple_info,
    grapple_tile_attributes,
    grapple_tooltip_lines,
)
from natural20.web.json_renderer import JsonRenderer
from natural20.web.map_state import entities_from_tiles
from natural20.web.terrain_tooltip import build_terrain_tooltip


class TestGrappleInfo(unittest.TestCase):
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

    def test_no_grapple_yields_no_tile_attributes(self):
        self.assertEqual(grapple_tile_attributes(self.npc), {})
        self.assertEqual(grapple_tile_attributes(self.fighter), {})

    def test_both_sides_of_grapple(self):
        self.npc.do_grappled_by(self.fighter)
        self.npc.attributes['grapple_escape_dcs'] = {self.fighter.entity_uid: 14}

        grappled = grapple_info(self.npc)
        self.assertTrue(grappled['grappled'])
        self.assertEqual(
            grappled['grappled_by'],
            [{'id': self.fighter.entity_uid, 'name': self.fighter.label(), 'escape_dc': 14}],
        )
        self.assertEqual(grappled['grappling'], [])

        grappler = grapple_info(self.fighter)
        self.assertFalse(grappler['grappled'])
        self.assertEqual(grappler['grappling'], [{'id': self.npc.entity_uid, 'name': self.npc.label()}])

        self.assertEqual(
            grapple_tooltip_lines(grappled),
            [f"Grappled by {self.fighter.label()} (escape DC 14)"],
        )
        self.assertEqual(grapple_tooltip_lines(grappler), [f"Grappling {self.npc.label()}"])

    def test_escape_clears_info(self):
        self.npc.do_grappled_by(self.fighter)
        self.npc.escape_grapple_from(self.fighter)
        self.assertEqual(grapple_tile_attributes(self.npc), {})
        self.assertEqual(grapple_tile_attributes(self.fighter), {})

    def test_terrain_tooltip_names_grappler(self):
        self.npc.do_grappled_by(self.fighter)
        tip = build_terrain_tooltip({'x': 1, 'y': 1, 'light': 1.0}, self.map, self.battle, entity=self.npc)
        self.assertIn(f"Grappled by {self.fighter.label()}", tip)
        tip = build_terrain_tooltip({'x': 1, 'y': 2, 'light': 1.0}, self.map, self.battle, entity=self.fighter)
        self.assertIn(f"Grappling {self.npc.label()}", tip)

    def test_renderer_tiles_and_map_state(self):
        self.npc.do_grappled_by(self.fighter)
        tiles = [t for row in JsonRenderer(self.map, self.battle).render() for t in row]
        by_id = {t.get('id'): t for t in tiles if t.get('entity') and t.get('id')}

        npc_tile = by_id[self.npc.entity_uid]
        self.assertTrue(npc_tile['grappled'])
        self.assertEqual([r['id'] for r in npc_tile['grappled_by']], [self.fighter.entity_uid])
        self.assertIn('Grappled by', npc_tile['grapple_tooltip'])

        fighter_tile = by_id[self.fighter.entity_uid]
        self.assertEqual([r['id'] for r in fighter_tile['grappling']], [self.npc.entity_uid])

        entries = {e['uid']: e for e in entities_from_tiles(tiles)}
        self.assertEqual(entries[self.npc.entity_uid]['grappled_by'], [self.fighter.entity_uid])
        self.assertEqual(entries[self.fighter.entity_uid]['grappling'], [self.npc.entity_uid])


if __name__ == '__main__':
    unittest.main()
