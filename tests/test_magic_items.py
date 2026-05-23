"""Tests for magic item support (+1/+2/+3 weapons, armor, shields, accessories)."""
import unittest
from natural20.player_character import PlayerCharacter
from natural20.event_manager import EventManager
from natural20.session import Session
from natural20.battle import Battle
from natural20.npc import Npc
from natural20.weapons import damage_modifier
import random
import numpy as np


class TestMagicItems(unittest.TestCase):
    """Comprehensive tests for magic item system."""

    def make_session(self):
        event_manager = EventManager()
        return Session(root_path='tests/fixtures', event_manager=event_manager)

    def setUp(self):
        self.session = self.make_session()
        self.battle = Battle(self.session, None)
        np.random.seed(42)
        random.seed(42)

    # ------------------------------------------------------------------ #
    #  Session loading
    # ------------------------------------------------------------------ #
    def test_load_magic_item_weapon(self):
        """Magic weapons load via session.load_weapon()."""
        w = self.session.load_weapon('longsword_plus_one')
        self.assertIsNotNone(w)
        self.assertEqual(w.get('magic_bonus'), 1)
        self.assertTrue(w.get('magical'))
        self.assertEqual(w.get('subtype'), 'weapon')

    def test_load_magic_item_armor(self):
        """Magic armor loads via session.load_equipment()."""
        a = self.session.load_equipment('plate_plus_one')
        self.assertIsNotNone(a)
        self.assertEqual(a.get('magic_bonus'), 1)
        self.assertTrue(a.get('magical'))
        self.assertEqual(a.get('type'), 'armor')

    def test_load_magic_item_shield(self):
        """Magic shields load via session.load_equipment()."""
        s = self.session.load_equipment('shield_plus_one')
        self.assertIsNotNone(s)
        self.assertEqual(s.get('magic_bonus'), 1)
        self.assertTrue(s.get('magical'))
        self.assertEqual(s.get('type'), 'shield')

    def test_load_magic_item_accessory(self):
        """Magic accessories load via session.load_equipment()."""
        acc = self.session.load_equipment('ring_of_protection')
        self.assertIsNotNone(acc)
        self.assertEqual(acc.get('magic_bonus'), 1)
        self.assertTrue(acc.get('magical'))
        self.assertEqual(acc.get('type'), 'accessory')

    def test_load_all_magic_items(self):
        """load_all_magic_items returns a dict with all entries."""
        items = self.session.load_all_magic_items()
        self.assertIn('longsword_plus_one', items)
        self.assertIn('plate_plus_one', items)
        self.assertIn('shield_plus_three', items)
        self.assertIn('ring_of_protection', items)

    def test_load_thing_magic_weapon(self):
        """load_thing resolves magic weapons."""
        w = self.session.load_thing('longsword_plus_two')
        self.assertIsNotNone(w)
        self.assertEqual(w.get('magic_bonus'), 2)

    def test_load_thing_magic_armor(self):
        """load_thing resolves magic armor."""
        a = self.session.load_thing('breastplate_plus_two')
        self.assertIsNotNone(a)
        self.assertEqual(a.get('magic_bonus'), 2)

    # ------------------------------------------------------------------ #
    #  Attack roll bonus from magic weapons
    # ------------------------------------------------------------------ #
    def test_attack_roll_mod_magic_weapon_plus_one(self):
        """+1 weapon adds +1 to attack roll."""
        player = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle.add(player, 'a')
        self.battle.start()
        player.equip('longsword_plus_one')
        weapon = self.session.load_weapon('longsword_plus_one')
        mod = player.attack_roll_mod(weapon)
        # Base: ability mod + proficiency; +1 from magic
        self.assertGreaterEqual(mod, 1)  # at least the magic bonus
        # Compare to non-magic longsword (not in fixtures, so compare to longsword equivalent)
        # The +1 should be present
        base_weapon = {
            'type': 'melee_attack',
            'properties': ['versatile'],
            'proficiency_type': ['martial'],
            'name': 'Longsword',
        }
        base_mod = player.attack_roll_mod(base_weapon)
        self.assertEqual(mod, base_mod + 1)

    def test_attack_roll_mod_magic_weapon_plus_two(self):
        """+2 weapon adds +2 to attack roll."""
        player = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle.add(player, 'a')
        self.battle.start()
        weapon = self.session.load_weapon('longsword_plus_two')
        mod = player.attack_roll_mod(weapon)
        base_weapon = {
            'type': 'melee_attack',
            'properties': ['versatile'],
            'proficiency_type': ['martial'],
            'name': 'Longsword',
            'magic_bonus': 0,
        }
        base_mod = player.attack_roll_mod(base_weapon)
        self.assertEqual(mod, base_mod + 2)

    def test_attack_roll_mod_magic_weapon_plus_three(self):
        """+3 weapon adds +3 to attack roll."""
        player = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle.add(player, 'a')
        self.battle.start()
        weapon = self.session.load_weapon('longsword_plus_three')
        mod = player.attack_roll_mod(weapon)
        base_weapon = {
            'type': 'melee_attack',
            'properties': ['versatile'],
            'proficiency_type': ['martial'],
            'name': 'Longsword',
            'magic_bonus': 0,
        }
        base_mod = player.attack_roll_mod(base_weapon)
        self.assertEqual(mod, base_mod + 3)

    # ------------------------------------------------------------------ #
    #  Damage modifier from magic weapons
    # ------------------------------------------------------------------ #
    def test_damage_modifier_magic_weapon_plus_one(self):
        """+1 weapon adds +1 to damage modifier."""
        player = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle.add(player, 'a')
        self.battle.start()
        weapon = self.session.load_weapon('longsword_plus_one')
        dmg = damage_modifier(player, weapon)
        # Parse the dice string to extract the flat modifier
        # Format: "1d8+X" or "1d8+X+1" — the magic bonus is included
        base_weapon = dict(weapon)
        base_weapon['magic_bonus'] = 0
        base_dmg = damage_modifier(player, base_weapon)
        # The +1 should be reflected in the modifier portion
        self.assertIn('+', dmg)
        # Extract numeric modifier from the string
        def extract_mod(s):
            """Extract total flat modifier from a dice string like '1d8+5'."""
            parts = s.replace('-', '+-').split('+')
            total = 0
            for p in parts[1:]:  # skip the dice part
                try:
                    total += int(p)
                except ValueError:
                    pass
            return total
        self.assertEqual(extract_mod(dmg), extract_mod(base_dmg) + 1)

    def test_damage_modifier_magic_weapon_plus_two(self):
        """+2 weapon adds +2 to damage modifier."""
        player = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle.add(player, 'a')
        self.battle.start()
        weapon = self.session.load_weapon('greataxe_plus_two')
        dmg = damage_modifier(player, weapon)
        base_weapon = dict(weapon)
        base_weapon['magic_bonus'] = 0
        base_dmg = damage_modifier(player, base_weapon)
        def extract_mod(s):
            parts = s.replace('-', '+-').split('+')
            total = 0
            for p in parts[1:]:
                try:
                    total += int(p)
                except ValueError:
                    pass
            return total
        self.assertEqual(extract_mod(dmg), extract_mod(base_dmg) + 2)

    # ------------------------------------------------------------------ #
    #  AC from magic armor
    # ------------------------------------------------------------------ #
    def _unequip_armor_and_shield(self, player):
        """Helper to unequip default armor and shield."""
        for item in list(player.properties['equipped']):
            loaded = self.session.load_equipment(item)
            if loaded and loaded.get('type') in ('armor', 'shield'):
                player.unequip(item)

    def test_ac_magic_armor_plus_one(self):
        """+1 armor adds +1 to AC."""
        player = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle.add(player, 'a')
        self.battle.start()
        self._unequip_armor_and_shield(player)
        player.equip('plate_plus_one')
        ac = player.armor_class()
        # Plate base AC is 18, +1 = 19
        self.assertEqual(ac, 19)

    def test_ac_magic_armor_plus_two(self):
        """+2 armor adds +2 to AC."""
        player = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle.add(player, 'a')
        self.battle.start()
        self._unequip_armor_and_shield(player)
        player.equip('plate_plus_two')
        ac = player.armor_class()
        self.assertEqual(ac, 20)

    def test_ac_magic_shield_plus_one(self):
        """+1 shield adds +1 on top of base shield AC."""
        player = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle.add(player, 'a')
        self.battle.start()
        self._unequip_armor_and_shield(player)
        player.equip('plate_plus_one')
        player.equip('shield_plus_one')
        ac = player.armor_class()
        # Plate 18 + 1 (magic) + 2 (shield base) + 1 (shield magic) = 22
        self.assertEqual(ac, 22)

    def test_ac_magic_shield_plus_three(self):
        """+3 shield adds +3 on top of base shield AC."""
        player = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle.add(player, 'a')
        self.battle.start()
        self._unequip_armor_and_shield(player)
        player.equip('plate_plus_one')
        player.equip('shield_plus_three')
        ac = player.armor_class()
        # Plate 18 + 1 + 2 + 3 = 24
        self.assertEqual(ac, 24)

    def test_ac_magic_accessory_ring_of_protection(self):
        """Ring of Protection adds +1 to AC."""
        player = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle.add(player, 'a')
        self.battle.start()
        self._unequip_armor_and_shield(player)
        player.equip('plate_plus_one')
        ac_with_plate = player.armor_class()
        player.equip('ring_of_protection')
        ac_with_ring = player.armor_class()
        self.assertEqual(ac_with_ring, ac_with_plate + 1)

    def test_ac_magic_accessory_cloak_of_protection(self):
        """Cloak of Protection adds +1 to AC."""
        player = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle.add(player, 'a')
        self.battle.start()
        self._unequip_armor_and_shield(player)
        player.equip('plate_plus_one')
        ac_with_plate = player.armor_class()
        player.equip('cloak_of_protection')
        ac_with_cloak = player.armor_class()
        self.assertEqual(ac_with_cloak, ac_with_plate + 1)

    def test_ac_multiple_accessories(self):
        """Multiple accessories stack for AC bonus."""
        player = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle.add(player, 'a')
        self.battle.start()
        self._unequip_armor_and_shield(player)
        player.equip('plate_plus_one')
        player.equip('ring_of_protection')
        player.equip('cloak_of_protection')
        ac = player.armor_class()
        # Plate 18 + 1 + ring 1 + cloak 1 = 21
        self.assertEqual(ac, 21)

    # ------------------------------------------------------------------ #
    #  Magical weapon bypasses non-magical resistance
    # ------------------------------------------------------------------ #
    def test_resistant_to_non_magical_bypassed(self):
        """Magical weapons bypass 'non-magical <type>' resistances."""
        # Create NPC with non-magical slashing resistance
        npc = Npc(self.session, 'goblin', {})
        npc.resistances = ['non-magical slashing', 'non-magical piercing']
        # Without magical weapon, slashing is resisted
        self.assertTrue(npc.resistant_to('slashing'))
        # With magical weapon, slashing is NOT resisted
        magical_weapon = {'magical': True, 'magic_bonus': 1}
        self.assertFalse(npc.resistant_to('slashing', weapon=magical_weapon))
        # With magical weapon, piercing is also NOT resisted
        self.assertFalse(npc.resistant_to('piercing', weapon=magical_weapon))
        # Bludgeoning not in resistances at all
        self.assertFalse(npc.resistant_to('bludgeoning', weapon=magical_weapon))

    def test_resistant_to_normal_damage_type(self):
        """Normal damage type resistances still work."""
        npc = Npc(self.session, 'goblin', {})
        npc.resistances = ['acid', 'fire']
        self.assertTrue(npc.resistant_to('acid'))
        self.assertTrue(npc.resistant_to('fire'))
        self.assertFalse(npc.resistant_to('slashing'))
        # Magical weapon does NOT bypass normal resistances
        magical_weapon = {'magical': True}
        self.assertTrue(npc.resistant_to('acid', weapon=magical_weapon))

    def test_resistant_to_non_magical_no_weapon(self):
        """Without weapon context, non-magical resistance still applies."""
        npc = Npc(self.session, 'goblin', {})
        npc.resistances = ['non-magical slashing']
        self.assertTrue(npc.resistant_to('slashing'))
        self.assertTrue(npc.resistant_to('slashing', weapon=None))

    # ------------------------------------------------------------------ #
    #  Magic item equipping
    # ------------------------------------------------------------------ #
    def test_equip_magic_weapon(self):
        """Player can equip a magic weapon."""
        player = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle.add(player, 'a')
        self.battle.start()
        player.inventory['longsword_plus_one'] = {'qty': 1}
        player.equip('longsword_plus_one')
        self.assertIn('longsword_plus_one', player.properties['equipped'])
        weapons = player.equipped_weapons(self.session)
        self.assertIn('longsword_plus_one', weapons)

    def test_equip_magic_armor(self):
        """Player can equip magic armor."""
        player = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle.add(player, 'a')
        self.battle.start()
        player.inventory['plate_plus_one'] = {'qty': 1}
        player.equip('plate_plus_one')
        self.assertIn('plate_plus_one', player.properties['equipped'])
        # Verify the armor loads with correct name from session
        armor_data = self.session.load_equipment('plate_plus_one')
        self.assertEqual(armor_data['name'], 'Plate Armor +1')

    def test_unequip_magic_weapon(self):
        """Player can unequip a magic weapon."""
        player = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle.add(player, 'a')
        self.battle.start()
        player.equip('longsword_plus_one')
        self.assertIn('longsword_plus_one', player.properties['equipped'])
        player.unequip('longsword_plus_one')
        self.assertNotIn('longsword_plus_one', player.properties['equipped'])

    # ------------------------------------------------------------------ #
    #  Named magic weapons
    # ------------------------------------------------------------------ #
    def test_flame_tongue_loads(self):
        """Flame Tongue weapon loads correctly."""
        w = self.session.load_weapon('flame_tongue_longsword')
        self.assertIsNotNone(w)
        self.assertEqual(w.get('magic_bonus'), 2)
        self.assertTrue(w.get('magical'))
        self.assertEqual(w.get('fire_damage'), '1d6')

    def test_sun_blade_loads(self):
        """Sunblade loads correctly."""
        w = self.session.load_weapon('sun_blade')
        self.assertIsNotNone(w)
        self.assertEqual(w.get('magic_bonus'), 2)
        self.assertTrue(w.get('magical'))
        self.assertEqual(w.get('damage_type'), 'radiant')

    # ------------------------------------------------------------------ #
    #  Edge cases
    # ------------------------------------------------------------------ #
    def test_nonexistent_magic_item(self):
        """Loading a nonexistent magic item returns None."""
        w = self.session.load_magic_item('does_not_exist')
        self.assertIsNone(w)

    def test_magic_bonus_zero(self):
        """Items with magic_bonus=0 don't add anything."""
        player = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle.add(player, 'a')
        self.battle.start()
        weapon = {
            'type': 'melee_attack',
            'properties': ['versatile'],
            'proficiency_type': ['martial'],
            'name': 'Longsword',
            'magic_bonus': 0,
        }
        mod = player.attack_roll_mod(weapon)
        base_weapon = dict(weapon)
        del base_weapon['magic_bonus']
        base_mod = player.attack_roll_mod(base_weapon)
        self.assertEqual(mod, base_mod)


if __name__ == '__main__':
    unittest.main()
