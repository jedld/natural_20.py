import os
from natural20.item_library.chest import Chest
from natural20.session import Session
from natural20.player_character import PlayerCharacter
import unittest
from natural20.battle import Battle
from natural20.map import Map
from natural20.map_renderer import MapRenderer
from natural20.event_manager import EventManager
import random

# typed: false
class TestItems(unittest.TestCase):
    def make_session(self):
        event_manager = EventManager()
        event_manager.standard_cli()
        random.seed(7000)
        return Session(root_path='tests/fixtures', event_manager=event_manager)

    def setUp(self):
        self.session = self.make_session()
        self.entity = PlayerCharacter.load(self.session, os.path.join("high_elf_fighter.yml"))
        self.battle_map = Map(self.session, "battle_sim_objects")
        self.battle_map.place((0, 5), self.entity, "G")
        self.door = self.battle_map.object_at(1, 4)

    def test_doors(self):
        self.assertIsNotNone(self.door.entity_uid)
        self.assertEqual(self.door.token_image(), 'objects/wooden_door')
        print(f"door entity uid: {self.door.entity_uid}")
        self.assertEqual(self.door.facing(), 'up')
        print(MapRenderer(self.battle_map).render())

        # test line of sight
        self.assertTrue(self.door.closed())
        self.assertFalse(self.door.passable())
        self.assertEqual(self.door.token(), '=')
        self.assertFalse(self.battle_map.can_see_square(self.entity, (1, 3)))
        self.door.open()
        self.assertTrue(self.battle_map.can_see_square(self.entity, (1, 3)))

    def test_hide_map_token_suppresses_map_sprite_only(self):
        chest = Chest(self.session, self.battle_map, {
            'name': 'Bar Counter',
            'token_image': 'tavern_bar_counter',
            'hide_map_token': True,
            'state': 'opened',
        })
        self.assertIsNone(chest.token_image())
        self.assertEqual(chest.profile_image(), 'tavern_bar_counter.png')

    def test_inventory_items_uses_item_label_and_image(self):
        goblin = self.session.npc('goblin')
        items = goblin.inventory_items(self.session)
        arrows = next(item for item in items if item['name'] == 'arrows')
        self.assertEqual(arrows['label'], 'Arrows')
        self.assertEqual(arrows['image'], 'arrows')
        self.assertEqual(arrows['type'], 'arrows')

    def test_inventory_items_skips_unknown_item_ids(self):
        goblin = self.session.npc('goblin')
        goblin.inventory['deed_to_the_house'] = {'qty': 1}

        items = goblin.inventory_items(self.session)

        self.assertFalse(any(item['name'] == 'deed_to_the_house' for item in items))