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
from natural20.utils.monster_traits import (
    apply_regeneration,
    in_mist_form,
    is_charmed_by,
    legendary_resistance_remaining,
)


class MonsterTraitsTestBase(unittest.TestCase):
    def setUp(self):
        random.seed(4321)
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.map = Map(self.session, 'tests/fixtures/jev_arena.yml')
        self.session.register_map('arena', self.map)
        self.battle = Battle(self.session, self.map)
        self.controller = GenericController(self.session)
        self.pc = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle.add(self.pc, 'a', position=[5, 4], add_to_initiative=True)
        self.vampire = self.session.npc('vampire_lord')
        self.map.add(self.vampire, 5, 5)
        self.battle.add(self.vampire, 'b', controller=self.controller, add_to_initiative=True)
        self.battle.start()
        self.battle.set_current_turn(self.vampire)
        self.vampire.reset_turn(self.battle)
        self.pc.reset_turn(self.battle)

    def tearDown(self):
        DieRoll.unfudge(20)

    def npc_action(self, name):
        return next(a for a in self.vampire.npc_actions if a['name'] == name)

    def attack(self, name, target=None, grapple_instead=False, d20=15):
        action = AttackAction(self.session, self.vampire, 'attack')
        action.npc_action = self.npc_action(name)
        action.target = target or self.pc
        action.grapple_instead = grapple_instead
        if d20 is not None:
            DieRoll.fudge(d20)
        self.battle.action(action)
        self.battle.commit(action)
        return action


class TestLegendaryResistance(MonsterTraitsTestBase):
    def test_failed_save_becomes_success(self):
        DieRoll.fudge(1)
        roll = self.vampire.save_throw('strength', self.battle, {'dc': 25})
        self.assertGreaterEqual(roll.result(), 25)
        self.assertEqual(legendary_resistance_remaining(self.vampire), 2)

    def test_save_without_dc_does_not_spend_a_use(self):
        DieRoll.fudge(1)
        self.vampire.save_throw('strength', self.battle)
        self.assertEqual(legendary_resistance_remaining(self.vampire), 3)

    def test_uses_run_out_and_reset_on_long_rest(self):
        self.vampire.attributes['legendary_resistance_used'] = 3
        DieRoll.fudge(1)
        roll = self.vampire.save_throw('strength', self.battle, {'dc': 25})
        self.assertLess(roll.result(), 25)
        self.vampire.long_rest(force=True)
        self.assertEqual(legendary_resistance_remaining(self.vampire), 3)


class TestRegeneration(MonsterTraitsTestBase):
    def test_regains_hit_points_at_start_of_turn(self):
        self.vampire.attributes['hp'] = 100
        self.assertEqual(apply_regeneration(self.vampire, self.battle), 20)
        self.assertEqual(self.vampire.hp(), 120)

    def test_radiant_damage_suppresses_next_regeneration_only(self):
        self.vampire.attributes['hp'] = 100
        self.vampire.take_damage(10, battle=self.battle, damage_type='radiant')
        self.assertEqual(apply_regeneration(self.vampire, self.battle), 0)
        self.assertEqual(apply_regeneration(self.vampire, self.battle), 20)

    def test_sunlight_blocks_regeneration(self):
        self.vampire.attributes['hp'] = 100
        self.vampire.statuses.append('in_sunlight')
        self.assertEqual(apply_regeneration(self.vampire, self.battle), 0)

    def test_start_turn_triggers_regeneration(self):
        self.vampire.attributes['hp'] = 100
        self.battle.start_turn()
        self.assertEqual(self.vampire.hp(), 120)

    def test_regeneration_reaches_the_session_combat_log(self):
        events = []
        self.session.event_manager.register_event_listener(
            ['regeneration', 'regeneration_blocked'], lambda event: events.append(event))

        self.vampire.attributes['hp'] = 100
        self.battle.start_turn()
        self.vampire.take_damage(10, battle=self.battle, damage_type='radiant')
        apply_regeneration(self.vampire, self.battle)

        self.assertEqual([e['event'] for e in events], ['regeneration', 'regeneration_blocked'])
        self.assertEqual(events[0]['value'], 20)
        self.assertEqual(events[1]['reason'], 'took radiant damage')


class TestMistyEscape(MonsterTraitsTestBase):
    def test_turns_to_mist_instead_of_dying(self):
        self.vampire.take_damage(400, battle=self.battle, damage_type='slashing')
        self.assertFalse(self.vampire.dead())
        self.assertTrue(in_mist_form(self.vampire))
        self.assertNotIn(self.vampire, self.battle.entities)
        self.assertIsNone(self.map.entity_or_object_pos(self.vampire) if self.vampire in self.map.entities else None)

        self.session.increment_game_time(3600)
        self.assertEqual(self.vampire.hp(), 1)
        self.assertFalse(in_mist_form(self.vampire))

    def test_destroyed_in_sunlight(self):
        self.vampire.statuses.append('in_sunlight')
        self.vampire.take_damage(400, battle=self.battle, damage_type='slashing')
        self.assertTrue(self.vampire.dead())


class TestVampireAttacks(MonsterTraitsTestBase):
    def test_multiattack_combo_narrows_follow_ups(self):
        state = self.battle.entity_state_for(self.vampire)
        self.assertEqual(set(state['multiattack'][1]), {'unarmed_strike', 'unarmed_strike2', 'bite'})
        self.attack('unarmed_strike')
        self.assertEqual(set(state['multiattack'][1]), {'unarmed_strike2', 'bite'})
        self.pc.do_grappled_by(self.vampire)
        self.attack('bite')
        self.assertFalse(any(state['multiattack'].values()))
        self.assertFalse(AttackAction.can(self.vampire, self.battle, {'npc_action': self.npc_action('unarmed_strike2')}))

    def test_additional_damage_rider(self):
        hp_before = self.pc.hp()
        action = self.attack('unarmed_strike2')
        riders = [r for r in action.result if r['type'] == 'additional_damage']
        self.assertEqual(len(riders), 1)
        self.assertEqual(riders[0]['damage_type'], 'necrotic')
        self.assertLess(self.pc.hp(), hp_before)

    def test_grapple_instead_of_primary_damage(self):
        action = self.attack('unarmed_strike', grapple_instead=True)
        self.assertTrue(self.pc.grappled_by(self.vampire))
        self.assertEqual(self.pc.attributes['grapple_escape_dcs'][self.vampire.entity_uid], 18)
        damage_item = next(r for r in action.result if r['type'] == 'damage')
        self.assertEqual(damage_item['damage'].result(), 0)

    def test_bite_requires_grappled_or_willing_target(self):
        bite = AttackAction(self.session, self.vampire, 'attack')
        bite.npc_action = self.npc_action('bite')
        bite.validate(self.map, target=self.pc, battle=self.battle)
        self.assertIn('validation.attack.target_condition', bite.errors)
        self.pc.do_grappled_by(self.vampire)
        bite.validate(self.map, target=self.pc, battle=self.battle)
        self.assertEqual(bite.errors, [])

    def test_bite_drains_hit_point_maximum_and_heals(self):
        self.pc.do_grappled_by(self.vampire)
        self.vampire.attributes['hp'] = 100
        max_before = self.pc.max_hp()
        self.attack('bite')
        drained = max_before - self.pc.max_hp()
        self.assertGreater(drained, 0)
        self.assertEqual(self.vampire.hp(), 100 + drained)
        self.pc.long_rest(force=True)
        self.assertEqual(self.pc.max_hp(), max_before)

    def test_charm_then_repeat_save_when_harmed(self):
        DieRoll.fudge(1)
        self.attack('charm', d20=None)
        self.assertTrue(is_charmed_by(self.pc, self.vampire))
        self.assertIn('charmed', self.pc.statuses)

        strike = AttackAction(self.session, self.pc, 'attack')
        strike.using = 'longsword'
        strike.validate(self.map, target=self.vampire, battle=self.battle)
        self.assertIn('validation.attack.charmed_by_target', strike.errors)

        DieRoll.fudge(20)
        self.pc.take_damage(1, battle=self.battle, damage_type='slashing',
                            item={'source': self.vampire})
        self.assertFalse(is_charmed_by(self.pc, self.vampire))
        self.assertNotIn('charmed', self.pc.statuses)

    def test_charmed_target_is_a_willing_bite_target(self):
        DieRoll.fudge(1)
        self.attack('charm', d20=None)
        bite = AttackAction(self.session, self.vampire, 'attack')
        bite.npc_action = self.npc_action('bite')
        bite.validate(self.map, target=self.pc, battle=self.battle)
        self.assertEqual(bite.errors, [])

    def test_grapple_instead_survives_serialization(self):
        action = AttackAction(self.session, self.vampire, 'attack')
        action.npc_action = self.npc_action('unarmed_strike')
        action.grapple_instead = True
        restored = AttackAction.from_dict(action.to_dict())
        self.assertTrue(restored.grapple_instead)
        self.assertTrue(action.to_h()['grapple_instead'])


class TestVampireAi(MonsterTraitsTestBase):
    def test_heuristic_multiattacks_and_never_picks_speak(self):
        picks = []
        for _ in range(6):
            actions = self.vampire.available_actions(self.session, self.battle)
            action = self.controller.select_action(self.battle, self.vampire, actions)
            if action is None or not isinstance(action, AttackAction):
                if action is not None:
                    self.assertNotEqual(action.action_type, 'speak')
                break
            picks.append(action)
            self.battle.action(action)
            self.battle.commit(action)
        self.assertGreaterEqual(len(picks), 2)
        self.assertTrue(all(p.npc_action.get('multiattack_group') for p in picks))

    def test_grapple_variant_offered_and_valued_for_bite_follow_up(self):
        actions = self.vampire.available_actions(self.session, self.battle)
        grapples = [a for a in actions if isinstance(a, AttackAction) and a.grapple_instead]
        self.assertEqual(len(grapples), 1)
        plain = next(a for a in actions if isinstance(a, AttackAction)
                     and not a.grapple_instead and a.npc_action['name'] == 'unarmed_strike')
        self.assertGreater(grapples[0].ai_value(self.battle), plain.ai_value(self.battle))


if __name__ == '__main__':
    unittest.main()
