import os
import unittest

from natural20.actions.interact_action import InteractAction
from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.item_library.chest import Chest
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.utils.portable_object import can_pickup_object, pickup_object, resolve_map_object


class TestPortableChest(unittest.TestCase):
    def setUp(self):
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.entity = PlayerCharacter.load(self.session, os.path.join('high_elf_fighter.yml'))
        self.battle_map = Map(self.session, 'battle_sim_objects')
        self.session.register_map('warehouse', self.battle_map)
        self.battle = Battle(self.session, self.battle_map)
        self.battle_map.place((1, 5), self.entity, 'G')
        self.battle.add(self.entity, group='a')
        self.ground = next(
            obj for obj in self.battle_map.objects_at(1, 5) if type(obj).__name__ == 'Ground'
        )

    def _give_chest(self, contents=None):
        self.entity.add_item('chest', 1, source_item={
            'type': 'chest', 'qty': 1, 'contents': contents or [], 'is_container': True,
        })

    def _drop_chest(self):
        self.ground.transfer(self.battle, self.entity, self.ground, {
            'to': {'items': ['chest'], 'qty': ['1']},
        })

    def _placed_chest(self):
        return next(
            (obj for obj in self.battle_map.objects_at(1, 5) if isinstance(obj, Chest)), None
        )

    def test_chest_gear_is_a_container(self):
        definition = self.session.load_thing('chest')
        self.assertEqual(definition['type'], 'container')
        self.assertEqual(definition['placeable_object'], 'chest')
        self._give_chest()
        self.assertTrue(self.entity.is_container('chest'))
        self.assertEqual(self.entity.check_equip('chest'), 'unequippable')

    def test_drop_on_ground_places_chest_object_with_contents(self):
        self._give_chest([{'type': 'arrows', 'qty': 10}])
        self._drop_chest()
        self.assertNotIn('chest', self.entity.inventory)
        chest = self._placed_chest()
        self.assertIsNotNone(chest)
        self.assertEqual(chest.properties.get('portable_item'), 'chest')
        self.assertEqual(chest.inventory['arrows']['qty'], 10)
        self.assertNotIn('chest', self.ground.inventory or {})

    def test_placed_chest_opens_and_offers_pick_up(self):
        self._give_chest()
        self._drop_chest()
        chest = self._placed_chest()
        interactions = chest.available_interactions(self.entity, self.battle)
        self.assertIn('open', interactions)
        self.assertEqual(interactions.get('pick_up'), {})

    def test_pick_up_returns_chest_and_contents_to_inventory(self):
        self._give_chest([{'type': 'arrows', 'qty': 10}])
        self._drop_chest()
        chest = self._placed_chest()
        chest.add_item('healing_potion', 2)

        action = InteractAction(self.session, self.entity, 'interact')
        action.target = chest
        action.object_action = 'pick_up'
        self.battle.action(action)
        self.battle.commit(action)

        self.assertNotIn(chest, self.battle_map.interactable_objects)
        self.assertIn('chest', self.entity.inventory)
        contents = {row['type']: row['qty'] for row in self.entity.get_container_contents('chest')}
        self.assertEqual(contents, {'arrows': 10, 'healing_potion': 2})

    def test_cannot_pick_up_when_too_heavy(self):
        self._give_chest()
        self._drop_chest()
        chest = self._placed_chest()
        self.entity.ability_scores['str'] = 1
        ok, reason = can_pickup_object(self.entity, chest)
        self.assertFalse(ok)
        self.assertIn('carrying capacity', reason)
        self.assertTrue(chest.available_interactions(self.entity, self.battle)['pick_up']['disabled'])

        picked, _ = pickup_object(self.entity, chest, battle=self.battle)
        self.assertFalse(picked)
        self.assertIn(chest, self.battle_map.interactable_objects)

    def test_contents_weight_counts_toward_pickup(self):
        self._give_chest()
        self._drop_chest()
        chest = self._placed_chest()
        capacity = self.entity.carry_capacity()
        current = self.entity.carry_weight_status(self.session)['weight_lbs']
        self.assertTrue(can_pickup_object(self.entity, chest)[0])
        mail_weight = float(self.session.load_thing('chain_mail')['weight'])
        qty = int((capacity - current - 25) // mail_weight) + 1
        chest.add_item('chain_mail', qty)
        self.assertFalse(can_pickup_object(self.entity, chest)[0])

    def test_stacking_containers_pools_contents(self):
        self._give_chest([{'type': 'arrows', 'qty': 5}])
        self._give_chest([{'type': 'arrows', 'qty': 3}, {'type': 'dagger', 'qty': 1}])
        contents = {row['type']: row['qty'] for row in self.entity.get_container_contents('chest')}
        self.assertEqual(contents, {'arrows': 8, 'dagger': 1})
        self.assertEqual(self.entity.inventory['chest']['qty'], 2)


class TestResolveMapObject(unittest.TestCase):
    def setUp(self):
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())

    def test_object_catalog_type_passes_through(self):
        info, meta = resolve_map_object(self.session, {'type': 'chest', 'name': 'C'})
        self.assertEqual(info.get('item_class'), 'Chest')
        self.assertEqual(meta, {'type': 'chest', 'name': 'C'})

    def test_container_item_defaults_to_chest_object(self):
        info, meta = resolve_map_object(self.session, {'type': 'backpack'})
        self.assertEqual(info.get('item_class'), 'Chest')
        self.assertEqual(meta.get('portable_item'), 'backpack')
        self.assertNotIn('inventory', meta)

    def test_item_placeable_object_key_is_used(self):
        self.session.magic_items['magic_box'] = {'type': 'gear', 'placeable_object': 'barrel'}
        info, meta = resolve_map_object(self.session, {'type': 'magic_box'})
        self.assertEqual(info.get('name'), 'Barrel')
        self.assertEqual(meta.get('portable_item'), 'magic_box')

    def test_item_inventory_seeds_object_contents(self):
        self.session.magic_items['test_pack'] = {
            'type': 'container',
            'inventory': [{'type': 'arrows', 'qty': 3}],
        }
        info, meta = resolve_map_object(self.session, {'type': 'test_pack'})
        self.assertEqual(meta.get('portable_item'), 'test_pack')
        self.assertEqual(meta.get('inventory'), [{'type': 'arrows', 'qty': 3}])

    def test_non_container_item_without_placeable_object_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            resolve_map_object(self.session, {'type': 'leather_armor'})
        self.assertIn('placeable_object', str(ctx.exception))

    def test_unknown_type_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            resolve_map_object(self.session, {'type': 'no_such_thing'})
        self.assertIn('no_such_thing', str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
