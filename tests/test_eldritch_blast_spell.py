import unittest
import random
from natural20.session import Session
from natural20.event_manager import EventManager
from natural20.player_character import PlayerCharacter
from natural20.map import Map
from natural20.battle import Battle
from natural20.actions.spell_action import SpellAction
from natural20.die_roll import DieRoll


class TestEldritchBlastSpell(unittest.TestCase):
    def make_session(self):
        em = EventManager()
        em.standard_cli()
        return Session(root_path='tests/fixtures', event_manager=em)

    def setUp(self):
        random.seed(7000)
        self.session = self.make_session()
        self.warlock = PlayerCharacter.load(self.session, 'human_warlock.yml')
        self.map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.map)
        self.npc = self.map.entity_at(5, 5)
        self.battle.add(self.warlock, 'a', position=[0, 5])
        self.battle.start()
        self.warlock.reset_turn(self.battle)
        DieRoll.die_rolls().clear()

    def test_eldritch_blast_single_beam_low_level(self):
        """Test that Eldritch Blast fires 1 beam at levels 1-4"""
        # Warlock is level 5, so let's test with a lower level character
        self.warlock.properties['classes']['warlock'] = 1
        self.warlock.properties['level'] = 1
        setattr(self.warlock, 'warlock_level', 1)
        self.warlock.initialize_warlock()
        
        initial_hp = self.npc.hp()
        random.seed(7002)
        
        action = SpellAction.build(self.session, self.warlock)['next'](['eldritch_blast', 0])['next'](self.npc)
        action.resolve(self.session, self.map, {"battle": self.battle})
        
        # Should have exactly one attack (either hit or miss)
        attack_events = [r for r in action.result if 'attack_roll' in r]
        self.assertEqual(len(attack_events), 1)
        
        # Check damage type
        damage_events = [r for r in action.result if r.get('type') == 'spell_damage']
        if damage_events:
            self.assertEqual(damage_events[0]['damage_type'], 'force')
            self.battle.commit(action)
            self.assertLess(self.npc.hp(), initial_hp)

    def test_eldritch_blast_two_beams_level_5(self):
        """Test that Eldritch Blast fires 2 beams at level 5"""
        # Warlock is level 5
        initial_hp = self.npc.hp()
        random.seed(7002)
        
        action = SpellAction.build(self.session, self.warlock)['next'](['eldritch_blast', 0])['next'](self.npc)
        action.resolve(self.session, self.map, {"battle": self.battle})
        
        # Should have exactly 2 attacks
        attack_events = [r for r in action.result if 'attack_roll' in r]
        self.assertEqual(len(attack_events), 2)
        
        # Both beams should have beam numbers
        for i, event in enumerate(attack_events):
            self.assertEqual(event.get('beam'), i + 1)
        
        # Check that we can get damage from both beams
        damage_events = [r for r in action.result if r.get('type') == 'spell_damage']
        self.assertLessEqual(len(damage_events), 2)  # Can be 0-2 depending on hits
        
        self.battle.commit(action)
        # If at least one hit, HP should be lower
        if damage_events:
            self.assertLess(self.npc.hp(), initial_hp)

    def test_eldritch_blast_three_beams_level_11(self):
        """Test that Eldritch Blast fires 3 beams at level 11"""
        # Set warlock to level 11
        self.warlock.properties['classes']['warlock'] = 11
        self.warlock.properties['level'] = 11
        setattr(self.warlock, 'warlock_level', 11)
        self.warlock.initialize_warlock()
        
        random.seed(7002)
        
        action = SpellAction.build(self.session, self.warlock)['next'](['eldritch_blast', 0])['next'](self.npc)
        action.resolve(self.session, self.map, {"battle": self.battle})
        
        # Should have exactly 3 attacks
        attack_events = [r for r in action.result if 'attack_roll' in r]
        self.assertEqual(len(attack_events), 3)
        
        # All beams should have correct beam numbers
        for i, event in enumerate(attack_events):
            self.assertEqual(event.get('beam'), i + 1)

    def test_eldritch_blast_four_beams_level_17(self):
        """Test that Eldritch Blast fires 4 beams at level 17"""
        # Set warlock to level 17
        self.warlock.properties['classes']['warlock'] = 17
        self.warlock.properties['level'] = 17
        setattr(self.warlock, 'warlock_level', 17)
        self.warlock.initialize_warlock()
        
        random.seed(7002)
        
        action = SpellAction.build(self.session, self.warlock)['next'](['eldritch_blast', 0])['next'](self.npc)
        action.resolve(self.session, self.map, {"battle": self.battle})
        
        # Should have exactly 4 attacks
        attack_events = [r for r in action.result if 'attack_roll' in r]
        self.assertEqual(len(attack_events), 4)
        
        # All beams should have correct beam numbers
        for i, event in enumerate(attack_events):
            self.assertEqual(event.get('beam'), i + 1)

    def test_eldritch_blast_multiple_targets(self):
        """Test that Eldritch Blast can target multiple creatures"""
        # Warlock is level 5, so 2 beams
        npc2 = self.session.npc('skeleton')
        self.battle.add(npc2, 'b', position=[2, 5])
        npc2.reset_turn(self.battle)
        
        initial_hp_npc1 = self.npc.hp()
        initial_hp_npc2 = npc2.hp()
        random.seed(7002)
        
        action = SpellAction.build(self.session, self.warlock)['next'](['eldritch_blast', 0])['next']([self.npc, npc2])
        action.resolve(self.session, self.map, {"battle": self.battle})
        
        # Should have 2 attacks (one per beam)
        attack_events = [r for r in action.result if 'attack_roll' in r]
        self.assertEqual(len(attack_events), 2)
        
        # Check that targets are different (or same if only one target specified)
        targets = [r['target'] for r in attack_events]
        self.assertEqual(len(set(targets)), min(len(targets), 2))
        
        self.battle.commit(action)
        
        # If hits occurred, HP should be reduced
        damage_events = [r for r in action.result if r.get('type') == 'spell_damage']
        if damage_events:
            self.assertTrue(self.npc.hp() < initial_hp_npc1 or npc2.hp() < initial_hp_npc2)

    def test_eldritch_blast_force_damage(self):
        """Test that Eldritch Blast deals force damage"""
        random.seed(7002)
        
        action = SpellAction.build(self.session, self.warlock)['next'](['eldritch_blast', 0])['next'](self.npc)
        action.resolve(self.session, self.map, {"battle": self.battle})
        
        # All damage events should be force type
        damage_events = [r for r in action.result if r.get('type') == 'spell_damage']
        for event in damage_events:
            self.assertEqual(event['damage_type'], 'force')

    def test_eldritch_blast_separate_attack_rolls(self):
        """Test that each beam makes a separate attack roll"""
        random.seed(7002)
        
        action = SpellAction.build(self.session, self.warlock)['next'](['eldritch_blast', 0])['next'](self.npc)
        action.resolve(self.session, self.map, {"battle": self.battle})
        
        # Should have 2 separate attack rolls (level 5 warlock)
        attack_events = [r for r in action.result if 'attack_roll' in r]
        self.assertEqual(len(attack_events), 2)
        
        # Each should be a separate roll (may have different results)
        attack_rolls = [r['attack_roll'] for r in attack_events]
        # They could be the same or different, but should be separate instances
        self.assertEqual(len(attack_rolls), 2)

    def test_eldritch_blast_hit_and_miss(self):
        """Test that beams can hit or miss independently"""
        random.seed(7002)
        
        action = SpellAction.build(self.session, self.warlock)['next'](['eldritch_blast', 0])['next'](self.npc)
        action.resolve(self.session, self.map, {"battle": self.battle})
        
        # Should have both hit and miss events possible
        damage_events = [r for r in action.result if r.get('type') == 'spell_damage']
        miss_events = [r for r in action.result if r.get('type') == 'spell_miss']
        
        # Total should equal number of beams (2 at level 5)
        self.assertEqual(len(damage_events) + len(miss_events), 2)

    def test_eldritch_blast_damage_amount(self):
        """Test that each beam deals 1d10 damage"""
        random.seed(7002)
        
        action = SpellAction.build(self.session, self.warlock)['next'](['eldritch_blast', 0])['next'](self.npc)
        action.resolve(self.session, self.map, {"battle": self.battle})
        
        damage_events = [r for r in action.result if r.get('type') == 'spell_damage']
        
        for event in damage_events:
            damage_roll = event['damage_roll']
            # Damage should be 1d10 (result between 1 and 10, or 2-20 on crit)
            result = damage_roll.result()
            self.assertGreaterEqual(result, 1)
            self.assertLessEqual(result, 20)  # Can be up to 20 on crit

    def test_eldritch_blast_available_to_warlock(self):
        """Test that Eldritch Blast is available to Warlock"""
        available_spells = self.warlock.available_spells(self.battle)
        self.assertIn('eldritch_blast', available_spells)

    def test_eldritch_blast_cantrip(self):
        """Test that Eldritch Blast is a cantrip and doesn't consume spell slots"""
        initial_slots = self.warlock.spell_slots_count(1, 'warlock')
        
        action = SpellAction.build(self.session, self.warlock)['next'](['eldritch_blast', 0])['next'](self.npc)
        action.resolve(self.session, self.map, {"battle": self.battle})
        self.battle.commit(action)
        
        # Cantrips don't consume spell slots
        final_slots = self.warlock.spell_slots_count(1, 'warlock')
        self.assertEqual(initial_slots, final_slots)


if __name__ == '__main__':
    unittest.main()

