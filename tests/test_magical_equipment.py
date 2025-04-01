import unittest
from natural20.player_character import PlayerCharacter
from natural20.event_manager import EventManager
from natural20.session import Session
from natural20.battle import Battle
import random
import numpy as np
import pdb

class TestMagicalEquipment(unittest.TestCase):
    def make_session(self):
        event_manager = EventManager()
        event_manager.register_event_listener(['died'], lambda event: print(f"{event['source'].name} died."))
        event_manager.register_event_listener(['unconscious'], lambda event: print(f"{event['source'].name} unconscious."))
        event_manager.register_event_listener(['initiative'], lambda event: print(f"{event['source'].name} rolled a {event['roll']} = ({event['value']}) with dex tie break for initiative."))
        return Session(root_path='tests/fixtures', event_manager=event_manager)

    def load_mage_character(self):
        player = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.battle.add(player, 'a')
        self.battle.start()
        player.reset_turn(self.battle)
        return player
    
    def load_fighter_character(self):
        player = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle.add(player, 'a')
        self.battle.start()
        player.reset_turn(self.battle)
        return player

    def load_rogue_character(self):
        player = PlayerCharacter.load(self.session, 'halfling_rogue.yml')
        self.battle.add(player, 'a')
        self.battle.start()
        player.reset_turn(self.battle)
        return player

    def load_elf_rogue_character(self):
        player = PlayerCharacter.load(self.session, 'elf_rogue.yml')
        self.battle.add(player, 'a')
        self.battle.start()
        player.reset_turn(self.battle)
        return player

    def load_elf_rogue_lvl2_character(self):
        player = PlayerCharacter.load(self.session, 'elf_rogue_2.yml')
        self.battle.add(player, 'a')
        self.battle.start()
        player.reset_turn(self.battle)
        return player

    def setUp(self):
        self.session = self.make_session()
        self.battle = Battle(self.session, None)
        np.random.seed(7000)
        random.seed(7000)

    def test_cloak_of_protection(self):
        player = self.load_mage_character()
        player.inventory['cloak_of_protection'] = { 'qty' : 1 }

        self.assertEqual(player.armor_class(), 12)
        self.assertEqual(str(player.save_throw('constitution', None)), "d20(2) + 2")
        player.equip('cloak_of_protection')
        self.assertEqual(player.armor_class(), 13)
        self.assertEqual(str(player.save_throw('constitution', None)), "d20(11) + 2 + 1")
