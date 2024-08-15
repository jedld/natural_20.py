import unittest
from natural20.player_character import PlayerCharacter
from natural20.event_manager import EventManager
from natural20.session import Session
from natural20.battle import Battle
import random
import numpy as np

class TestPlayerCharacter(unittest.TestCase):
    def make_session(self):
        event_manager = EventManager()
        event_manager.register_event_listener(['died'], lambda event: print(f"{event['source'].name} died."))
        event_manager.register_event_listener(['unconscious'], lambda event: print(f"{event['source'].name} unconscious."))
        event_manager.register_event_listener(['initiative'], lambda event: print(f"{event['source'].name} rolled a {event['roll']} = ({event['value']}) with dex tie break for initiative."))
        return Session(root_path='tests/fixtures', event_manager=event_manager)

    def load_mage_character(self):
        player = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.battle.add(player, 'a')
        player.reset_turn(self.battle)
        return player
    
    def load_fighter_character(self):
        player = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle.add(player, 'a')
        player.reset_turn(self.battle)
        return player
    
    def load_rogue_character(self):
        player = PlayerCharacter.load(self.session, 'halfling_rogue.yml')
        self.battle.add(player, 'a')
        player.reset_turn(self.battle)
        return player
    
    def load_elf_rogue_character(self):
        player = PlayerCharacter.load(self.session, 'elf_rogue.yml')
        self.battle.add(player, 'a')
        player.reset_turn(self.battle)
        return player    
    
    def setUp(self):
        self.session = self.make_session()
        self.battle = Battle(self.session, None)
        np.random.seed(7000)
        random.seed(7000)

    def test_wizard_has_spells(self):
        self.player = self.load_mage_character()
        self.assertTrue(self.player.has_spells())

    def test_wizard_available_actions(self):
        self.player = self.load_mage_character()
        expected_actions = ['Spell', 'Look', 'Attack', 'Move', 'Use item', 'Interact', 'Ground interact', 'Inventory', 'Grapple', 'Drop grapple', 'Shove', 'Push']
        self.assertEqual([str(action) for action in self.player.available_actions(self.session, self.battle)], expected_actions)

    def test_wizard_spell_attack_modifier(self):
        self.player = self.load_mage_character()
        self.assertEqual(self.player.spell_attack_modifier(), 6)

    def test_wizard_ranged_spell_attack(self):
        self.player = self.load_mage_character()
        attack = self.player.ranged_spell_attack(self.battle, 'firebolt')
        self.assertEqual(attack.roller.roll_str, '1d20+6')

    def test_wizard_spell_slots(self):
        self.player = self.load_mage_character()
        self.assertEqual(self.player.spell_slots_count(1), 2)
        self.assertEqual(self.player.spell_slots_count(9), 0)

    def test_wizard_max_spell_slots(self):
        self.player = self.load_mage_character()
        self.assertEqual(self.player.max_spell_slots(1), 2)
        self.assertEqual(self.player.max_spell_slots(9), 0)

    def test_wizard_proficient_with_weapon(self):
        self.player = self.load_mage_character()
        self.assertTrue(self.player.proficient_with_weapon('dagger'))

    def test_wizard_available_spells(self):
        self.player = self.load_mage_character()
        expected_spells = ['firebolt', 'mage_armor', 'magic_missile']
        self.assertEqual(self.player.available_spells(self.battle), expected_spells)

    def test_fighter_name(self):
        self.player = self.load_fighter_character()
        self.assertEqual(self.player.name, 'Gomerin')

    def test_fighter_str_mod(self):
        self.player = self.load_fighter_character()
        self.assertEqual(self.player.str_mod(), 1)

    def test_fighter_hp(self):
        self.player = self.load_fighter_character()
        self.assertEqual(self.player.hp(), 67)

    def test_fighter_passive_perception(self):
        self.player = self.load_fighter_character()
        self.assertEqual(self.player.passive_perception(), 14)

    def test_fighter_standing_jump_distance(self):
        self.player = self.load_fighter_character()
        self.assertEqual(self.player.standing_jump_distance(), 6)

    def test_fighter_long_jump_distance(self):
        self.player = self.load_fighter_character()
        self.assertEqual(self.player.long_jump_distance(), 12)

    def test_fighter_armor_class(self):
        self.player = self.load_fighter_character()
        self.assertEqual(self.player.armor_class(), 19)

    def test_fighter_speed(self):
        self.player = self.load_fighter_character()
        self.assertEqual(self.player.speed(), 30)

    def test_fighter_available_actions(self):
        self.player = self.load_fighter_character()
        expected_actions = ['Look', 'Attack', 'Attack', 'Attack', 'Move', 'Dash', 'Hide', 'Help', 'Dodge', 'Use item', 'Interact', 'Inventory', 'Grapple', 'Shove', 'Push', 'Prone', 'Short rest', 'Second wind']
        self.assertEqual([str(action) for action in self.player.available_actions(self.session, self.battle)], expected_actions)

    def test_fighter_to_h(self):
        self.player = self.load_fighter_character()
        expected_dict = {
            'ability': {'cha': 11, 'con': 16, 'dex': 20, 'int': 16, 'str': 12, 'wis': 12},
            'classes': {'fighter': 1},
            'hp': 67,
            'name': 'Gomerin',
            'passive': {'insight': 11, 'investigation': 13, 'perception': 14}
        }
        self.assertEqual(self.player.to_dict(), expected_dict)

    def test_fighter_usable_items(self):
        self.player = self.load_fighter_character()
        expected_items = [{
            'item': {
                'consumable': True,
                'hp_regained': '2d4+2',
                'item_class': 'ItemLibrary::HealingPotion',
                'name': 'Potion of Healing',
                'type': 'potion',
                'usable': True
            },
            'label': 'Potion of Healing',
            'name': 'healing_potion',
            'consumable': True,
            'qty': 1
        }]
        self.assertEqual(self.player.usable_items(), expected_items)

    def test_fighter_inventory_weight(self):
        self.player = self.load_fighter_character()
        self.assertEqual(self.player.inventory_weight(self.session), 30.0)

    def test_fighter_carry_capacity(self):
        self.player = self.load_fighter_character()
        self.assertEqual(self.player.carry_capacity(), 180.0)

    def test_fighter_perception_check(self):
        self.player = self.load_fighter_character()
        self.assertEqual(self.player.perception_check().modifier, 4)
        self.assertEqual(self.player.perception_check().result(), 6)

    def test_fighter_dexterity_check(self):
        self.player = self.load_fighter_character()
        check_val = self.player.dexterity_check()
        self.assertEqual(str(check_val), 'd20(11) + 5')
        self.assertEqual(check_val.result(), 16)

    def test_fighter_stealth_check(self):
        self.player = self.load_fighter_character()
        self.assertEqual(str(self.player.stealth_check()), 'd20(11) + 5')

    def test_fighter_acrobatics_check(self):
        self.player = self.load_fighter_character()
        check_val = self.player.acrobatics_check()
        self.assertEqual(str(check_val), 'd20(11) + 8')
        self.assertEqual(check_val.result(), 19)

    def test_fighter_athletics_check(self):
        self.player = self.load_fighter_character()
        check_val = self.player.athletics_check()
        self.assertEqual(str(check_val), 'd20(11) + 4')
        self.assertEqual(check_val.result(), 15)

    def test_fighter_languages(self):
        self.player = self.load_fighter_character()
        expected_languages = ['abyssal', 'celestial', 'common', 'common', 'elvish', 'elvish', 'goblin']
        self.assertEqual(self.player.languages(), expected_languages)

    def test_fighter_darkvision(self):
        self.player = self.load_fighter_character()
        self.assertTrue(self.player.darkvision(60))

    def test_fighter_check_equip(self):
        self.player = self.load_fighter_character()
        self.player.unequip_all()
        self.assertEqual(self.player.check_equip('light_crossbow'), 'ok')
        self.player.equip('light_crossbow', ignore_inventory=True)
        self.assertEqual(self.player.check_equip('studded_leather'), 'ok')
        self.assertEqual(self.player.check_equip('scimitar'), 'hands_full')

    def test_fighter_proficient_with_weapon(self):
        self.player = self.load_fighter_character()
        self.assertTrue(self.player.proficient_with_weapon('rapier'))
        self.assertTrue(self.player.proficient_with_weapon('longbow'))

    def test_fighter_proficient(self):
        self.player = self.load_fighter_character()
        self.assertTrue(self.player.proficient('perception'))

    def test_fighter_take_damage(self):
        self.player = self.load_fighter_character()
        self.player.take_damage(80)
        self.assertTrue(self.player.unconscious())
        self.assertFalse(self.player.dead())

        self.player.heal(10)
        self.assertFalse(self.player.unconscious())

        self.player.take_damage(200)
        self.assertTrue(self.player.dead())

    def test_fighter_hit_die(self):
        self.player = self.load_fighter_character()
        self.assertEqual(self.player.hit_die(), {10: 1})

    def test_fighter_short_rest(self):
        self.player = self.load_fighter_character()
        self.player.take_damage(4)
        self.assertEqual(self.player.hit_die(), {10: 1})
        self.player.short_rest(self.battle)
        self.assertEqual(self.player.hp(), 67)
        self.assertEqual(self.player.hit_die(), {10: 0})

    def test_fighter_saving_throw(self):
        self.player = self.load_fighter_character()
        result = [self.player.saving_throw(attribute) for attribute in self.player.ATTRIBUTE_TYPES]
        expected_results = ['d20+4', 'd20+5', 'd20+6', 'd20+3', 'd20+1', 'd20+0']
        self.assertEqual([str(dr.roller.roll_str) for dr in result], expected_results)

    def test_fighter_skill_mods(self):
        self.player = self.load_fighter_character()
        self.assertEqual(self.player.acrobatics_mod(), 8)
        self.assertEqual(self.player.arcana_mod(), 6)

    def test_rogue_halfling_languages(self):
        self.player = self.load_rogue_character()
        expected_languages = ['common', 'halfling', 'thieves_cant']
        self.assertEqual(self.player.languages(), expected_languages)

    def test_rogue_halfling_light_properties(self):
        self.player = self.load_rogue_character()
        expected_light_properties = {'bright': 20.0, 'dim': 20.0}
        self.assertEqual(self.player.light_properties(), expected_light_properties)

    def test_rogue_halfling_proficient(self):
        self.player = self.load_rogue_character()
        self.assertTrue(self.player.proficient('longsword'))

    def test_rogue_elf_languages(self):
        self.player = self.load_elf_rogue_character()
        expected_languages = ['common', 'elvish', 'thieves_cant']
        self.assertEqual(self.player.languages(), expected_languages)

    def test_rogue_elf_light_properties(self):
        self.player = self.load_elf_rogue_character()
        expected_light_properties = {'bright': 20.0, 'dim': 20.0}
        self.assertEqual(self.player.light_properties(), expected_light_properties)

    def test_rogue_elf_proficient(self):
        self.player = self.load_elf_rogue_character()
        self.assertTrue(self.player.proficient('longsword'))

if __name__ == '__main__':
    unittest.main()
