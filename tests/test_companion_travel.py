import unittest

from natural20.companion import companion_defs, quest_allows_companion, sync_companion_to_map
from natural20.session import Session
class CompanionTravelTest(unittest.TestCase):
    def setUp(self):
        self.session = Session(root_path='user_levels/wild_sheep_chase')
        self.game_properties = self.session.game_properties
        self.town = self.session.maps['town_market']
        self.woodland = self.session.maps['woodland_path']

    def test_companion_defs_from_game_yml(self):
        defs = companion_defs(self.game_properties)
        self.assertTrue(any(d.get('entity_uid') == 'finethir_shinebright' for d in defs))

    def test_quest_gate(self):
        cfg = companion_defs(self.game_properties)[0]
        self.session.session_state = {}
        self.assertFalse(quest_allows_companion(self.session, cfg))
        self.session.session_state = {'wild_sheep_quest': 'accepted'}
        self.assertTrue(quest_allows_companion(self.session, cfg))

    def test_sync_moves_companion_to_anchor_map(self):
        from natural20.npc import Npc

        fin = self.session.entity_by_uid('finethir_shinebright')
        self.assertIsNotNone(fin)
        self.assertIn(fin, self.town.entities)

        anchor = Npc(self.session, 'guz', {'name': 'Anchor', 'overrides': {'entity_uid': 'anchor_npc'}})
        self.woodland.add(anchor, 4, 4, group='d')
        anchor_pos = self.woodland.position_of(anchor)

        cfg = companion_defs(self.game_properties)[0]
        self.session.session_state = {'wild_sheep_quest': 'accepted'}
        sync_companion_to_map(
            self.session,
            self.game_properties,
            cfg['entity_uid'],
            self.woodland,
            anchor_pos,
            offset=cfg.get('spawn_offset'),
        )
        self.assertIn(fin, self.woodland.entities)
        self.assertNotIn(fin, self.town.entities)


if __name__ == '__main__':
    unittest.main()
