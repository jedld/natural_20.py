import unittest
import random

from natural20.session import Session
from natural20.map import Map


class TestRegistryLookupHelpers(unittest.TestCase):
    def make_session(self):
        from natural20.event_manager import EventManager
        em = EventManager()
        em.standard_cli()
        random.seed(4321)
        return Session(root_path='tests/fixtures', event_manager=em)

    def test_position_of_uid_for_entity(self):
        s = self.make_session()
        m = Map(s, 'entryway')
        ent = m.entity_by_uid('gomerin')
        self.assertIsNotNone(ent)
        uid = str(ent.entity_uid)
        pos_direct = m.position_of(ent)
        pos_uid = m.position_of_uid(uid)
        self.assertEqual(pos_direct, pos_uid)

    def test_object_by_uid_and_position(self):
        s = self.make_session()
        m = Map(s, 'maps/object_map')
        # find an object with uid
        target = None
        for col in m.objects:
            for cell in col:
                for obj in cell:
                    if hasattr(obj, 'entity_uid') and obj.entity_uid:
                        target = obj
                        break
                if target:
                    break
            if target:
                break
        self.assertIsNotNone(target)
        uid = str(target.entity_uid)
        self.assertIs(m.object_by_uid(uid), target)
        self.assertEqual(m.position_of_uid(uid), m.interactable_objects[target])
