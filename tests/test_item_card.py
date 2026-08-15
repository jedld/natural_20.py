import unittest

from natural20.event_manager import EventManager
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.utils.item_card import (
    _flavor_text,
    build_item_card,
    format_item_cost,
)


class TestItemCard(unittest.TestCase):
    def setUp(self):
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.player = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')

    def test_format_item_cost(self):
        self.assertEqual(format_item_cost(10), '10 gp')
        self.assertEqual(format_item_cost('2sp'), '2 sp')
        self.assertEqual(format_item_cost(0.05), '5 cp')
        self.assertIsNone(format_item_cost(0))
        self.assertIsNone(format_item_cost(None))

    def test_flavor_text_keys(self):
        self.assertEqual(_flavor_text({'flavor_text': 'A wickedly sharp blade.'}), 'A wickedly sharp blade.')
        self.assertEqual(_flavor_text({'lore': 'Forged in starlight.'}), 'Forged in starlight.')
        self.assertIsNone(_flavor_text({'description': 'Not flavor.'}))

    def test_bundled_templates_include_flavor_text(self):
        from pathlib import Path
        from natural20.yaml_loader import load_yaml
        weapons = load_yaml(Path('templates/items/weapons.yml'))
        equipment = load_yaml(Path('templates/items/equipment.yml'))
        magic = load_yaml(Path('templates/items/magic_items.yml'))
        self.assertTrue(weapons['dagger']['flavor_text'])
        self.assertTrue(equipment['backpack']['flavor_text'])
        self.assertTrue(magic['cloak_of_protection']['flavor_text'])
        self.assertTrue(magic['cloak_of_protection']['description'])

    def test_weapon_card_includes_stats_and_properties(self):
        card = self.player.item_card('dagger')
        self.assertIsNotNone(card)
        self.assertEqual(card['label'], 'Dagger')
        self.assertEqual(card['type_label'], 'Melee Weapon')
        self.assertEqual(card['icon'], '/assets/items/dagger.png')
        self.assertIn('1d4 piercing', [row['value'] for row in card['stats']])
        self.assertIn('Light', card['properties'])
        self.assertIn('Thrown', card['properties'])
        self.assertTrue(any(row['label'] == 'Thrown' for row in card['stats']))
        self.assertEqual(card['cost_label'], '2 gp')

    def test_equipped_weapon_rarity_and_to_hit(self):
        card = self.player.item_card('vicious_rapier')
        self.assertEqual(card['rarity_label'], 'Very Rare')
        self.assertTrue(card['equipped'])
        self.assertTrue(any(row['label'] == 'To Hit' for row in card['stats']))
        self.assertTrue(any(row['label'] == 'Damage' and '1d8' in row['value'] for row in card['stats']))

    def test_description_and_light_on_torch(self):
        card = self.player.item_card('torch')
        self.assertIsNotNone(card['description'])
        self.assertIn('bright light', card['description'])
        self.assertTrue(any(row['label'] == 'Light' for row in card['stats']))

    def test_armor_stealth_disadvantage(self):
        card = self.player.item_card('padded')
        self.assertEqual(card['type_label'], 'Armor')
        self.assertTrue(any(row['label'] == 'Stealth' and row['value'] == 'Disadvantage' for row in card['stats']))

    def test_potion_healing(self):
        card = self.player.item_card('healing_potion')
        self.assertEqual(card['label'], 'Potion of Healing')
        self.assertTrue(card['usable'])
        self.assertTrue(card['consumable'])
        self.assertTrue(any(row['label'] == 'Healing' and row['value'] == '2d4+2' for row in card['stats']))

    def test_unknown_item_returns_none(self):
        self.assertIsNone(self.player.item_card('definitely_not_an_item'))
        self.assertIsNone(build_item_card(self.player, ''))
        self.assertIsNone(build_item_card(None, 'dagger'))

    def test_carried_gear_includes_container_contents(self):
        self.player.add_item('backpack', 1)
        ok, reason = self.player.stow_item('backpack', 'healing_potion', 1, self.session)
        self.assertTrue(ok, reason)
        rows = self.player.carried_gear_items()
        nested = [row for row in rows if row.get('nested')]
        self.assertEqual(len(nested), 1)
        self.assertEqual(nested[0]['name'], 'healing_potion')
        self.assertEqual(nested[0]['container'], 'backpack')
        self.assertEqual(nested[0]['container_label'], 'Backpack')
        self.assertTrue(nested[0]['usable'])
        names = [row['name'] for row in rows]
        self.assertIn('backpack', names)

    def test_container_card_lists_contents(self):
        self.player.add_item('backpack', 1)
        ok, reason = self.player.stow_item('backpack', 'healing_potion', 1, self.session)
        self.assertTrue(ok, reason)
        card = self.player.item_card('backpack')
        self.assertTrue(card['is_container'])
        self.assertEqual(len(card['contents']), 1)
        self.assertEqual(card['contents'][0]['name'], 'healing_potion')
        self.assertTrue(card['contents'][0]['usable'])
        nested = self.player.item_card('healing_potion', container_name='backpack')
        self.assertEqual(nested['container'], 'backpack')
        self.assertEqual(nested['container_label'], 'Backpack')
        self.assertEqual(nested['qty'], 1)
