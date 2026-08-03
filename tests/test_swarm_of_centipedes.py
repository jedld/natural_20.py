import random
import unittest

from natural20.actions.attack_action import AttackAction
from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session


class SwarmOfCentipedesTestCase(unittest.TestCase):
    def setUp(self):
        random.seed(4242)
        self.session = Session(root_path='user_levels/death_house', event_manager=EventManager())
        self.swarm = self.session.npc('swarm_of_centipedes', {'name': 'Centipedes', 'rand_life': True})
        self.fixture_session = Session(root_path='tests/fixtures', event_manager=EventManager())

    def test_stat_block(self):
        props = self.swarm.properties
        self.assertEqual(props['max_hp'], 22)
        self.assertEqual(props['default_ac'], 12)
        self.assertIn('swarm', props['attributes'])
        self.assertIn('swarm_centipede_venom', props['attributes'])
        bite = next(a for a in props['actions'] if a['name'] == 'bite')
        self.assertEqual(bite['damage_die'], '4d4')
        self.assertEqual(bite['damage_die_half_hp'], '2d4')
        self.assertEqual(bite['range'], 0)

    def test_swarm_entities_can_share_space(self):
        battle_map = Map(self.fixture_session, 'battle_sim')
        fighter = self.fixture_session.npc('goblin', {'name': 'Goblin', 'rand_life': True})
        swarm = self.session.npc('swarm_of_centipedes', {'name': 'Centipedes', 'rand_life': True})
        battle_map.add(fighter, 2, 2)
        battle_map.add(swarm, 2, 2)
        self.assertTrue(battle_map.placeable(swarm, 2, 2))
        self.assertTrue(battle_map.placeable(fighter, 2, 2))

    def test_swarm_cannot_heal_or_gain_temp_hp(self):
        self.swarm.attributes['hp'] = 5
        self.swarm.heal(10)
        self.assertEqual(self.swarm.hp(), 5)
        granted = self.swarm.grant_temp_hp(8)
        self.assertEqual(granted, 0)
        self.assertEqual(self.swarm.temp_hp(), 0)

    def test_bite_uses_half_damage_die_at_half_hp(self):
        battle_map = Map(self.fixture_session, 'battle_sim')
        battle = Battle(self.session, battle_map)
        target = self.fixture_session.npc('goblin', {'name': 'Goblin', 'rand_life': True})
        self.swarm.attributes['hp'] = self.swarm.max_hp() // 2
        battle_map.add(self.swarm, 2, 2)
        battle_map.add(target, 2, 2)
        battle.add(self.swarm, 'b', add_to_initiative=True)
        battle.add(target, 'a', add_to_initiative=True)
        battle.start(combat_order=[self.swarm, target])

        action = AttackAction(self.session, self.swarm, 'attack')
        action.npc_action = next(a for a in self.swarm.npc_actions if a['name'] == 'bite')
        action.target = target
        weapon, _, _, damage_roll, _ = action.get_weapon_info({'npc_action': action.npc_action})
        self.assertEqual(damage_roll, '2d4')
        self.assertEqual(weapon['damage_die_half_hp'], '2d4')

    def test_centipede_venom_makes_target_stable_poisoned_and_paralyzed(self):
        pc = PlayerCharacter.load(self.session, 'characters/high_elf_mage.yml')
        pc.attributes['hp'] = 5
        self.swarm.class_feature = lambda f: f == 'swarm_centipede_venom'
        pc.take_damage(5, session=self.session, item={'source': self.swarm})
        self.assertTrue(pc.stable())
        self.assertTrue(pc.poisoned())
        self.assertTrue(pc.paralyzed())

    def test_elisabeth_crypt_door_spawns_centipedes(self):
        battle_map = Map(self.session, 'maps/basement_1')
        door = None
        for obj, pos in battle_map.interactable_objects.items():
            if getattr(obj, 'entity_uid', None) == 'elisabeth_crypt_door':
                door = obj
                self.assertEqual(pos, [15, 7])
                break
        self.assertIsNotNone(door)
        self.assertTrue(door.closed())

        results = door.open()
        self.assertTrue(any(r.get('type') == 'message' for r in results))
        spawned = battle_map.entity_at(17, 7)
        self.assertIsNotNone(spawned)
        self.assertIn('centipede', spawned.name.lower())


if __name__ == '__main__':
    unittest.main()
