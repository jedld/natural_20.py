import random
import unittest

from natural20.actions.spell_action import SpellAction
from natural20.battle import Battle
from natural20.die_roll import Rollable
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.utils.attack_util import damage_event


class FixedRoll(Rollable):
    def __init__(self, value):
        self.value = value

    def result(self):
        return self.value

    def __repr__(self):
        return str(self.value)


class TestArmorOfAgathysSpell(unittest.TestCase):
    def make_session(self):
        event_manager = EventManager()
        event_manager.standard_cli()
        return Session(root_path="tests/fixtures", event_manager=event_manager)

    def setUp(self):
        random.seed(9064)
        self.session = self.make_session()
        self.warlock = PlayerCharacter.load(self.session, "human_warlock.yml")
        self.enemy = PlayerCharacter.load(self.session, "human_fighter.yml")
        self.map = Map(self.session, "battle_sim_objects")
        self.battle = Battle(self.session, self.map)
        self.battle.add(self.warlock, "a", position=[0, 5])
        self.battle.add(self.enemy, "b", position=[0, 6])
        self.battle.start()
        self.warlock.reset_turn(self.battle)
        self.enemy.reset_turn(self.battle)

    def test_spell_list_includes_armor_of_agathys(self):
        spell_list = self.warlock.spell_list(self.battle)
        self.assertIn('armor_of_agathys', spell_list)
        self.assertNotIn('no_spell_slot', spell_list['armor_of_agathys']['disabled'])

    def _melee_attack_payload(self, damage):
        return {
            'type': 'damage',
            'source': self.enemy,
            'target': self.warlock,
            'attack_name': 'Longsword',
            'damage_type': 'slashing',
            'weapon': {'type': 'melee_attack'},
            'damage': FixedRoll(damage),
            'damage_roll': FixedRoll(damage),
            'advantage_mod': 0,
            'adv_info': None,
            'thrown': False,
            'sneak_attack': None,
            'attack_roll': None
        }

    def test_temp_hp_and_retaliation(self):
        action = SpellAction.build(self.session, self.warlock)['next'](['armor_of_agathys', 1])
        action.resolve(self.session, self.map, {'battle': self.battle})
        self.battle.commit(action)
        expected_temp_hp = 5 * action.at_level

        self.assertEqual(self.warlock.temp_hp(), expected_temp_hp)
        self.assertTrue(self.warlock.has_effect('armor_of_agathys'))

        initial_enemy_hp = self.enemy.hp()
        initial_warlock_hp = self.warlock.hp()

        damage_event(self._melee_attack_payload(4), self.battle)
        self.assertEqual(self.enemy.hp(), initial_enemy_hp - expected_temp_hp)
        self.assertEqual(self.warlock.temp_hp(), expected_temp_hp - 4)
        self.assertEqual(self.warlock.hp(), initial_warlock_hp)

        second_damage = expected_temp_hp - 4
        damage_event(self._melee_attack_payload(second_damage), self.battle)
        self.assertEqual(self.enemy.hp(), initial_enemy_hp - (expected_temp_hp * 2))
        self.assertEqual(self.warlock.temp_hp(), 0)
        self.assertEqual(self.warlock.hp(), initial_warlock_hp)
        self.assertFalse(self.warlock.has_effect('armor_of_agathys'))

        damage_event(self._melee_attack_payload(3), self.battle)
        self.assertEqual(self.enemy.hp(), initial_enemy_hp - (expected_temp_hp * 2))
        self.assertEqual(self.warlock.hp(), initial_warlock_hp - 3)
        self.assertEqual(self.warlock.temp_hp(), 0)


if __name__ == '__main__':
    unittest.main()
