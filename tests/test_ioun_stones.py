"""Ioun stones and other passive item mechanics (natural20/utils/item_mechanics.py)."""
import copy
import random
import unittest

from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.utils.item_mechanics import item_proficiency_bonus
from natural20.utils.serialization import Serialization


class IounStoneTest(unittest.TestCase):
    def setUp(self):
        random.seed(11)
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.base_equipped = list(self.fighter.properties['equipped'])

    def wear(self, *items, attuned=None):
        self.fighter.properties['equipped'] = self.base_equipped + list(items)
        if attuned is None:
            self.fighter.properties.pop('attuned', None)
        else:
            self.fighter.properties['attuned'] = list(attuned)

    def test_insight_raises_wisdom_without_touching_base_score(self):
        self.assertEqual(self.fighter.ability_scores['wis'], 12)
        self.wear('ioun_stone_of_insight')
        self.assertEqual(self.fighter.ability_scores['wis'], 14)
        self.assertEqual(self.fighter.wis_mod(), 2)
        self.assertEqual(self.fighter.properties['ability']['wis'], 12)
        self.wear()
        self.assertEqual(self.fighter.ability_scores['wis'], 12)

    def test_bonus_is_capped_at_twenty(self):
        self.assertEqual(self.fighter.ability_scores['dex'], 20)
        self.wear('ioun_stone_of_agility')
        self.assertEqual(self.fighter.ability_scores['dex'], 20)
        self.fighter.properties['ability']['dex'] = 19
        self.assertEqual(self.fighter.ability_scores['dex'], 20)
        self.fighter.properties['ability']['dex'] = 22
        self.assertEqual(self.fighter.ability_scores['dex'], 22)

    def test_requires_attunement_when_sheet_tracks_it(self):
        self.wear('ioun_stone_of_insight', attuned=[])
        self.assertEqual(self.fighter.ability_scores['wis'], 12)
        self.wear('ioun_stone_of_insight', attuned=['ioun_stone_of_insight'])
        self.assertEqual(self.fighter.ability_scores['wis'], 14)

    def test_writes_go_to_base_scores(self):
        self.wear('ioun_stone_of_insight')
        self.fighter.ability_scores['wis'] = 16
        self.assertEqual(self.fighter.properties['ability']['wis'], 16)
        self.assertEqual(self.fighter.ability_scores['wis'], 18)
        self.assertEqual(copy.deepcopy(self.fighter.ability_scores)['wis'], 16)

    def test_protection_adds_ac(self):
        before = self.fighter.armor_class()
        self.wear('ioun_stone_of_protection')
        self.assertEqual(self.fighter.armor_class(), before + 1)

    def test_mastery_adds_proficiency_bonus(self):
        goblin = self.session.npc('goblin', {'name': 'Goblin'})
        before = goblin.proficiency_bonus()
        goblin.properties['equipped'] = ['ioun_stone_of_mastery']
        self.assertEqual(goblin.proficiency_bonus(), before + 1)
        self.wear('ioun_stone_of_mastery')
        self.assertEqual(item_proficiency_bonus(self.fighter), 1)

    def test_awareness_prevents_surprise(self):
        self.fighter.set_surprised(True)
        self.assertTrue(self.fighter.surprised())
        self.wear('ioun_stone_of_awareness')
        self.assertFalse(self.fighter.surprised())

    def test_amulet_of_health_sets_constitution(self):
        self.wear('amulet_of_health')
        self.assertEqual(self.fighter.ability_scores['con'], 19)
        self.fighter.properties['ability']['con'] = 20
        self.assertEqual(self.fighter.ability_scores['con'], 20)

    def test_regeneration_heals_each_hour(self):
        self.session.register_entity(self.fighter)
        self.wear('ioun_stone_of_regeneration')
        self.fighter.attributes['hp'] = 10
        self.session.increment_game_time(6)
        self.session.increment_game_time(3600)
        self.assertEqual(self.fighter.hp(), 25)
        self.session.increment_game_time(1800)
        self.assertEqual(self.fighter.hp(), 25)
        self.fighter.attributes['hp'] = 0
        self.session.increment_game_time(1800)
        self.assertEqual(self.fighter.hp(), 0)

    def test_save_load_keeps_base_scores(self):
        self.wear('ioun_stone_of_insight', attuned=['ioun_stone_of_insight'])
        battle_map = Map(self.session, 'maps/empty_map')
        battle_map.add(self.fighter, 0, 0)
        battle = Battle(self.session, battle_map)
        battle.add(self.fighter, 'a')
        dump = Serialization().serialize(self.session, battle, {'empty_map': battle_map})
        session2, _battle2, _maps2 = Serialization().deserialize(dump)
        fighter2 = session2.entity_by_uid(self.fighter.entity_uid)
        self.assertEqual(fighter2.properties['ability']['wis'], 12)
        self.assertEqual(fighter2.ability_scores['wis'], 14)


if __name__ == '__main__':
    unittest.main()
