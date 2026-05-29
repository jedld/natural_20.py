import unittest
from unittest.mock import MagicMock, patch

from natural20.combat_script import process_combat_script, _run_on_complete
from natural20.session import Session


class CombatScriptTest(unittest.TestCase):
    def setUp(self):
        self.session = Session(root_path='user_levels/wild_sheep_chase')
        self.map = self.session.maps['treehouse_bedroom']
        self.battle = MagicMock()
        self.battle.session = self.session

    def test_flee_countdown_spawns_bed_dragon(self):
        from natural20.npc import Npc

        noke = Npc(self.session, 'ahmed_noke', {'name': 'Noke', 'overrides': {'entity_uid': 'test_noke'}})
        self.map.add(noke, 7, 7, group='b')
        self.battle.add = MagicMock()

        noke.properties['_flee_countdown_started'] = True
        noke.properties['_flee_countdown_remaining'] = 1
        template = Npc(self.session, 'ahmed_noke', {'name': '_template_'})
        noke.properties['combat_script'] = template.properties.get('combat_script')

        process_combat_script(noke, self.battle)

        self.assertTrue(noke.properties.get('_flee_countdown_complete'))
        spawned = [ent for ent in self.map.interactable_objects.keys()
                   if getattr(ent, 'npc_type', None) == 'bed_dragon_wyrmling']
        spawned += [ent for ent in self.map.entities
                    if getattr(ent, 'npc_type', None) == 'bed_dragon_wyrmling']
        self.assertTrue(len(spawned) >= 1 or self.battle.add.called)


class GuzRecklessTest(unittest.TestCase):
    def test_reckless_property_on_entity(self):
        from natural20.npc import Npc

        session = Session(root_path='user_levels/wild_sheep_chase')
        guz = Npc(session, 'guz', {'name': 'Guz'})
        self.assertTrue(guz.is_reckless())


if __name__ == '__main__':
    unittest.main()
