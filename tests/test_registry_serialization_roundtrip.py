import unittest
import random
import uuid

from natural20.session import Session
from natural20.battle import Battle
from natural20.map import Map
from natural20.utils.serialization import Serialization


class TestRegistrySerializationRoundtrip(unittest.TestCase):
    def make_session(self):
        from natural20.event_manager import EventManager
        em = EventManager()
        em.standard_cli()
        random.seed(1234)
        return Session(root_path='tests/fixtures', event_manager=em)

    def test_entity_resolution_after_deserialize(self):
        session = self.make_session()
        battle_map = Map(session, 'entryway')
        battle = Battle(session, battle_map)

        # Pick a known character and ensure it has a UID
        gomerin = battle_map.entity_by_uid('gomerin')
        self.assertIsNotNone(gomerin)
        uid = str(getattr(gomerin, 'entity_uid'))
        self.assertTrue(uid)

        # Serialize and deserialize
        ser = Serialization()
        yaml_str = ser.serialize(session, battle, [battle_map])
        new_session, new_battle, new_maps = ser.deserialize(yaml_str)

        # Validate registry-backed lookups work in the new session/map
        new_map = new_maps[0]
        resolved = new_map.entity_by_uid(uid)
        self.assertIsNotNone(resolved)
        self.assertEqual(str(resolved.entity_uid), uid)

        # Session-level lookup should also work
        self.assertIs(new_session.entity_by_uid(uid), resolved)

    def test_object_uid_resolution_after_deserialize(self):
        session = self.make_session()
        obj_map = Map(session, 'maps/object_map')

        # find first object with an entity_uid
        target_obj = None
        for col in obj_map.objects:
            for cell in col:
                for obj in cell:
                    if hasattr(obj, 'entity_uid') and obj.entity_uid:
                        target_obj = obj
                        break
                if target_obj:
                    break
            if target_obj:
                break

        self.assertIsNotNone(target_obj)
        uid = str(target_obj.entity_uid)

        ser = Serialization()
        yaml_str = ser.serialize(session, None, [obj_map])
        new_session, new_battle, new_maps = ser.deserialize(yaml_str)
        new_map = new_maps[0]

        resolved = new_map.entity_by_uid(uid)
        self.assertIsNotNone(resolved)
        self.assertEqual(str(resolved.entity_uid), uid)
        self.assertIs(new_session.entity_by_uid(uid), resolved)

    def test_multi_map_roundtrip_registry(self):
        session = self.make_session()
        map1 = Map(session, 'entryway')
        map2 = Map(session, 'maps/object_map')

        # choose an entity from map1 and an object from map2
        ent1 = map1.entity_by_uid('gomerin')
        self.assertIsNotNone(ent1)
        uid1 = str(ent1.entity_uid)

        target_obj2 = None
        for col in map2.objects:
            for cell in col:
                for obj in cell:
                    if hasattr(obj, 'entity_uid') and obj.entity_uid:
                        target_obj2 = obj
                        break
                if target_obj2:
                    break
            if target_obj2:
                break
        self.assertIsNotNone(target_obj2)
        uid2 = str(target_obj2.entity_uid)

        ser = Serialization()
        yaml_str = ser.serialize(session, None, [map1, map2])
        new_session, new_battle, new_maps = ser.deserialize(yaml_str)

        # verify registry-backed lookups for both maps
        self.assertIsNotNone(new_session.entity_by_uid(uid1))
        self.assertIsNotNone(new_session.entity_by_uid(uid2))
        # find the map containing ent1 by uid
        found1 = None
        for m in new_maps:
            if m.entity_by_uid(uid1):
                found1 = m
                break
        self.assertIsNotNone(found1)
        self.assertEqual(str(found1.entity_by_uid(uid1).entity_uid), uid1)

        found2 = None
        for m in new_maps:
            if m.entity_by_uid(uid2):
                found2 = m
                break
        self.assertIsNotNone(found2)
        self.assertEqual(str(found2.entity_by_uid(uid2).entity_uid), uid2)
