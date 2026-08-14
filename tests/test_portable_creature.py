import os
import unittest

from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.utils.item_size import creature_body_weight_lbs, size_allows
from natural20.utils.portable_creature import (
    creature_inventory_key,
    is_portable_creature_entry,
    pickup_creature,
    place_creature_from_item,
    serialize_portable_creature,
)


class TestItemSize(unittest.TestCase):
    def test_size_allows_small_not_medium(self):
        self.assertTrue(size_allows('tiny', 'small'))
        self.assertTrue(size_allows('small', 'small'))
        self.assertFalse(size_allows('medium', 'small'))
        self.assertFalse(size_allows('large', 'medium'))


class TestPortableCreature(unittest.TestCase):
    def setUp(self):
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.entity = PlayerCharacter.load(self.session, os.path.join('high_elf_fighter.yml'))
        self.battle_map = Map(self.session, 'battle_sim_objects')
        self.session.register_map('warehouse', self.battle_map)
        self.battle = Battle(self.session, self.battle_map)
        self.battle_map.place((1, 5), self.entity, 'G')
        self.dead_goblin = next(
            ent for ent in self.battle_map.entities if getattr(ent, 'dead', lambda: False)()
        )
        self.battle.add(self.entity, group='a')

    def test_serialize_snapshot_has_size_and_weight(self):
        snap = serialize_portable_creature(self.dead_goblin)
        self.assertTrue(is_portable_creature_entry(snap))
        self.assertEqual(snap['size'], 'small')
        self.assertGreater(snap['weight'], 0)
        self.assertTrue(snap['type'].startswith('creature:'))
        self.assertIn('dead', snap['label'].lower())

    def test_pickup_moves_corpse_into_inventory(self):
        uid = self.dead_goblin.entity_uid
        key = creature_inventory_key(self.dead_goblin)
        ok, reason = pickup_creature(
            self.entity, self.dead_goblin, battle=self.battle, map_obj=self.battle_map,
        )
        self.assertTrue(ok, reason)
        self.assertNotIn(self.dead_goblin, self.battle_map.entities)
        self.assertIn(key, self.entity.inventory)
        self.assertTrue(self.entity.inventory[key]['is_creature'])
        names = [item['name'] for item in self.entity.inventory_items(self.session)]
        self.assertIn(key, names)
        self.assertEqual(self.session.entity_by_uid(uid), self.dead_goblin)

    def test_drop_places_corpse_back_on_map(self):
        ok, reason = pickup_creature(
            self.entity, self.dead_goblin, battle=self.battle, map_obj=self.battle_map,
        )
        self.assertTrue(ok, reason)
        key = creature_inventory_key(self.dead_goblin)
        entry = self.entity.deduct_item(key, 1)
        origin = self.battle_map.position_of(self.entity)
        creature, err = place_creature_from_item(
            self.session, entry, self.battle_map, origin, battle=self.battle,
        )
        self.assertIsNotNone(creature, err)
        self.assertIn(creature, self.battle_map.entities)
        self.assertTrue(creature.dead())

    def test_backpack_rejects_medium_corpse(self):
        self.entity.inventory['backpack'] = {
            'type': 'backpack', 'qty': 1, 'contents': [], 'is_container': True,
        }
        cleric = PlayerCharacter.load(self.session, os.path.join('dwarf_cleric.yml'))
        cleric.make_dead()
        snap = serialize_portable_creature(cleric)
        self.assertEqual(snap['size'], 'medium')
        templates = Session(root_path='templates', event_manager=EventManager())
        self.entity.session = templates
        ok, reason = self.entity.add_to_container_checked(
            'backpack', snap['type'], 1, session=templates, source_item=snap,
        )
        self.assertFalse(ok)
        self.assertIn('cannot hold medium', reason)

    def test_carry_capacity_blocks_large_corpse(self):
        ogre = self.session.npc('ogre')
        ogre.make_dead()
        self.battle_map.place((2, 5), ogre, 'O')
        self.assertGreater(creature_body_weight_lbs(ogre), self.entity.carry_capacity())
        ok, reason = pickup_creature(
            self.entity, ogre, battle=self.battle, map_obj=self.battle_map,
        )
        self.assertFalse(ok)
        self.assertIn('carrying capacity', reason)
        self.assertIn(ogre, self.battle_map.entities)

    def test_chest_rejects_large_corpse(self):
        ogre = self.session.npc('ogre')
        ogre.make_dead()
        snap = serialize_portable_creature(ogre)
        chest = self.battle_map.object_at(1, 6)
        ok, reason = chest.can_accept_item(snap['type'], 1, source_item=snap)
        self.assertFalse(ok)
        self.assertIn('cannot hold large', reason)

    def test_pickup_dead_player_character(self):
        self.entity.carry_capacity = lambda: 400.0
        cleric = PlayerCharacter.load(self.session, os.path.join('dwarf_cleric.yml'))
        cleric.make_dead()
        self.battle_map.place((2, 6), cleric, 'C')
        ok, reason = pickup_creature(
            self.entity, cleric, battle=self.battle, map_obj=self.battle_map,
        )
        self.assertTrue(ok, reason)
        self.assertNotIn(cleric, self.battle_map.entities)
        key = creature_inventory_key(cleric)
        self.assertIn(key, self.entity.inventory)
        self.assertEqual(self.entity.inventory[key]['size'], 'medium')


if __name__ == '__main__':
    unittest.main()
