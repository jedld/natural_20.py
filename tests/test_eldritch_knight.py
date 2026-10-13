import random
import unittest

from natural20.actions.spell_action import SpellAction
from natural20.battle import Battle
from natural20.entity_class.fighter import ELDRITCH_KNIGHT_SPELL_SLOT_TABLE
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session


class EldritchKnightTestCase(unittest.TestCase):
    def setUp(self):
        random.seed(7000)
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.battle_map = Map(self.session, 'battle_sim')
        self.battle = Battle(self.session, self.battle_map)
        self.knight = PlayerCharacter.load(self.session, 'eldritch_knight.yml')
        self.goblin = self.session.npc('goblin')
        self.battle.add(self.knight, 'a', position=[2, 2])
        self.battle.add(self.goblin, 'b', position=[3, 2])
        self.battle.start(combat_order=[self.knight, self.goblin])
        self.knight.reset_turn(self.battle)

    def test_slot_table_matches_phb(self):
        def slots(level):
            return ELDRITCH_KNIGHT_SPELL_SLOT_TABLE[level - 1][1:]
        self.assertEqual(slots(2), [])
        self.assertEqual(slots(3), [2])
        self.assertEqual(slots(5), [3])
        self.assertEqual(slots(7), [4, 2])
        self.assertEqual(slots(13), [4, 3, 2])
        self.assertEqual(slots(20), [4, 3, 3, 1])

    def test_level_5_slots(self):
        self.assertEqual(self.knight.spell_slots_count(1, 'fighter'), 3)
        self.assertEqual(self.knight.max_spell_slots(1, 'fighter'), 3)
        self.assertEqual(self.knight.max_spell_slots(2, 'fighter'), 0)

    def test_wizard_spells_use_fighter_slots(self):
        self.assertIn('fighter', self.knight.spell_list_classes_for(self.session.load_spell('magic_missile')))
        spells = self.knight.spell_list(self.battle)
        self.assertEqual(spells['magic_missile']['disabled'], [])

        action = SpellAction.build(self.session, self.knight)['next'](['magic_missile', 1])
        action = action['next']([self.goblin, self.goblin, self.goblin])
        action.resolve(self.session, self.battle_map, {'battle': self.battle})
        self.battle.commit(action)
        self.assertEqual(self.knight.spell_slots_count(1, 'fighter'), 2)

    def test_spell_attack_uses_int(self):
        self.assertEqual(self.knight.fighter_spell_attack_modifier(),
                         self.knight.proficiency_bonus() + self.knight.int_mod())

    def test_plain_fighter_does_not_borrow_wizard_list(self):
        fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.assertEqual(fighter.borrowed_spell_list_classes(), {})
        self.assertNotIn('fighter', fighter.spell_list_classes_for(self.session.load_spell('magic_missile')))


if __name__ == '__main__':
    unittest.main()
