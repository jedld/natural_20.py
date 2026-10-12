import random
import unittest

from natural20.actions.attack_action import AttackAction
from natural20.battle import Battle
from natural20.die_roll import DieRoll
from natural20.event_manager import EventManager
from natural20.generic_controller import GenericController
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session


CLAW_WITH_NECROTIC = {
    'name': 'claw',
    'type': 'melee_attack',
    'range': 5,
    'targets': 1,
    'attack': 30,
    'damage': 2,
    'damage_die': '2',
    'damage_type': 'slashing',
    'additional_damage': [{'damage_die': '1', 'damage_type': 'necrotic'}],
}


class TestCombatTurnRules(unittest.TestCase):
    def setUp(self):
        random.seed(4321)
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.map = Map(self.session, 'tests/fixtures/jev_arena.yml')
        self.session.register_map('arena', self.map)
        self.battle = Battle(self.session, self.map)
        self.controller = GenericController(self.session)

    def _add_pc(self, pos):
        pc = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle.add(pc, 'a', position=pos, add_to_initiative=True)
        pc.reset_turn(self.battle)
        return pc

    def _add_brute(self, pos):
        brute = self.session.npc('legendary_brute')
        self.map.add(brute, *pos)
        self.battle.add(brute, 'b', controller=self.controller, add_to_initiative=True)
        brute.reset_turn(self.battle)
        return brute

    def _knock_out(self, pc):
        pc.attributes['hp'] = 0
        pc.make_unconscious()
        self.assertTrue(pc.unconscious())

    def _claw(self, brute, target, natural=10):
        action = AttackAction(self.session, brute, 'attack')
        action.target = target
        action.npc_action = dict(CLAW_WITH_NECROTIC)
        action.attack_roll = DieRoll([natural], 30, 20)
        self.battle.execute_action(action)
        return action

    def test_dead_combatants_have_no_turn(self):
        pc1 = self._add_pc([5, 3])
        pc2 = self._add_pc([5, 4])
        brute = self._add_brute([5, 5])
        self.battle.start()
        self.battle.combat_order = [pc1, pc2, brute]
        pc2.make_dead()

        self.battle.set_current_turn(pc2)
        self.assertIs(self.battle.skip_dead_turns(), brute)

        self.battle.set_current_turn(pc1)
        self.assertIs(self.battle.skip_dead_turns(), pc1)

    def test_end_of_turn_event_fires_once_per_turn(self):
        pc = self._add_pc([5, 3])
        self._add_brute([5, 5])
        self.battle.start()
        self.battle.set_current_turn(pc)

        fired = []
        original = self.battle.trigger_event

        def spy(event, source, opt=None):
            if event == 'end_of_turn':
                fired.append(opt.get('target') if opt else None)
            return original(event, source, opt)

        self.battle.trigger_event = spy
        self.battle.end_turn()
        self.battle.next_turn()
        self.assertEqual(fired, [pc])

        # Engine loops that skip end_turn() still get the event from next_turn().
        fired.clear()
        current = self.battle.current_turn()
        self.battle.next_turn()
        self.assertEqual(fired, [current])

    def test_melee_hit_on_unconscious_target_is_critical(self):
        pc = self._add_pc([5, 4])
        brute = self._add_brute([5, 5])
        self.battle.start()
        self._knock_out(pc)

        action = self._claw(brute, pc, natural=10)

        self.assertTrue(action.hit_result['critical'])
        # Crit = two failures; the necrotic rider is the same hit, so no third.
        self.assertFalse(pc.dead())
        self.assertEqual(pc.death_fails, 2)

    def test_damage_rider_does_not_add_a_death_save_failure(self):
        pc = self._add_pc([5, 4])
        brute = self._add_brute([5, 5])
        self.battle.start()

        pc.attributes['hp'] = 1
        self._claw(brute, pc)
        # The slashing part drops the PC; its necrotic rider belongs to the
        # same hit, so it is not damage "while at 0 HP".
        self.assertTrue(pc.unconscious())
        self.assertEqual(pc.death_fails, 0)

    def test_massive_damage_counts_rider_overflow(self):
        pc = self._add_pc([5, 4])
        brute = self._add_brute([5, 5])
        self.battle.start()

        max_hp = pc.properties['max_hp']
        pc.attributes['hp'] = 1
        action = AttackAction(self.session, brute, 'attack')
        action.target = pc
        npc_action = dict(CLAW_WITH_NECROTIC)
        # Each part alone leaves less than max HP of overflow; together they kill.
        npc_action['damage_die'] = str(max_hp // 2 + 1)
        npc_action['additional_damage'] = [{'damage_die': str(max_hp // 2 + 1), 'damage_type': 'necrotic'}]
        action.npc_action = npc_action
        action.attack_roll = DieRoll([10], 30, 20)
        self.battle.execute_action(action)

        self.assertTrue(pc.dead())

    def test_npc_cantrips_scale_with_spellcaster_level_not_cr(self):
        brute = self.session.npc('legendary_brute')
        self.assertEqual(brute.cantrip_level(), brute.level())
        brute.properties = dict(brute.properties, spellcaster_level=9)
        self.assertEqual(brute.cantrip_level(), 9)


if __name__ == '__main__':
    unittest.main()
