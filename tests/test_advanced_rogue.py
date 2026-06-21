import unittest

from natural20.actions.disarming_attack_action import DisarmingAttackAction
from natural20.actions.attack_action import AttackAction
from natural20.battle import Battle
from natural20.die_roll import DieRoll
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session


class TestAdvancedRogue(unittest.TestCase):
    def make_session(self):
        event_manager = EventManager()
        event_manager.standard_cli()
        return Session(root_path='tests/fixtures', event_manager=event_manager)

    def make_rogue(self):
        return PlayerCharacter(self.session, {
            'name': 'Rumblebelly',
            'race': 'halfling',
            'subrace': 'lightfoot',
            'classes': {'rogue': 15},
            'level': 15,
            'hit_die': 'inherit',
            'max_hp': 100,
            'ability': {
                'str': 11,
                'dex': 20,
                'con': 18,
                'int': 12,
                'wis': 12,
                'cha': 17,
            },
            'roguish_archetype': 'swashbuckler',
            'skills': ['stealth', 'deception'],
            'expertise': ['stealth'],
            'feats': ['martial_adept', 'sentinel'],
            'maneuvers': ['disarming_attack', 'riposte'],
            'superiority_die': '1d6',
            'superiority_dice': 1,
            'weapon_proficiencies': ['simple', 'rapier', 'shortsword'],
            'equipped': ['dagger'],
            'inventory': [{'type': 'dagger', 'qty': 1}],
        })

    def setUp(self):
        self.session = self.make_session()
        self.rogue = self.make_rogue()

    def test_level_15_swashbuckler_features_are_discovered(self):
        self.assertTrue(self.rogue.class_feature('uncanny_dodge'))
        self.assertTrue(self.rogue.class_feature('evasion'))
        self.assertTrue(self.rogue.class_feature('reliable_talent'))
        self.assertTrue(self.rogue.class_feature('rakish_audacity'))
        self.assertTrue(self.rogue.class_feature('sentinel'))
        self.assertEqual(self.rogue.resource_value('superiority_dice'), 1)

    def test_reliable_talent_floors_proficient_skill_rolls(self):
        DieRoll.fudge(1)
        roll = self.rogue.stealth_check()
        DieRoll.unfudge()
        self.assertGreaterEqual(roll.result(), 25)

    def test_rakish_audacity_adds_charisma_to_initiative(self):
        self.assertEqual(self.rogue.initiative_bonus(), 8)

    def test_disarming_attack_uses_superiority_die_and_can_disarm(self):
        battle_map = Map(self.session, 'battle_sim_objects')
        battle = Battle(self.session, battle_map)
        target = self.session.npc('skeleton')
        battle.add(self.rogue, 'a', position=[0, 5])
        battle.add(target, 'b', position=[0, 6])
        battle.start()
        self.rogue.reset_turn(battle)
        DieRoll.fudge(20)

        build = DisarmingAttackAction.build(self.session, self.rogue)['next']('dagger')
        action = build['next'](target)
        battle.action(action)
        battle.commit(action)
        DieRoll.unfudge()

        self.assertEqual(self.rogue.resource_value('superiority_dice'), 0)
        self.assertTrue(any(item.get('maneuver') == 'disarming_attack' for item in action.result))

    def test_riposte_triggers_when_melee_attack_misses(self):
        battle_map = Map(self.session, 'battle_sim_objects')
        battle = Battle(self.session, battle_map)
        attacker = self.session.npc('skeleton')
        battle.add(self.rogue, 'a', position=[0, 5])
        battle.add(attacker, 'b', position=[0, 6])
        battle.start()
        self.rogue.reset_turn(battle)
        attacker.reset_turn(battle)
        DieRoll.fudge(1)

        action = AttackAction(self.session, attacker, 'attack')
        action.using = 'Short Sword'
        action.target = self.rogue
        battle.action(action)
        battle.commit(action)
        DieRoll.unfudge()

        self.assertEqual(self.rogue.resource_value('superiority_dice'), 0)
        self.assertFalse(self.rogue.has_reaction(battle))
        self.assertTrue(any(item.get('maneuver') == 'riposte' for item in action.result))


if __name__ == '__main__':
    unittest.main()
