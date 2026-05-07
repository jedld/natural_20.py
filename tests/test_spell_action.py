import unittest
import os
from natural20.actions.spell_action import SpellAction
from natural20.actions.find_familiar_action import FindFamiliarAction
from natural20.actions.summon_familiar_action import SummonFamiliarAction
from natural20.actions.attack_action import AttackAction
from natural20.spell.shield_spell import ShieldSpell
from natural20.spell.objects.mage_hand import MageHand
from natural20.session import Session
from natural20.event_manager import EventManager
from natural20.player_character import PlayerCharacter
from natural20.die_roll import DieRoll
from natural20.controller import Controller
from natural20.action import AsyncReactionHandler

from natural20.map import Map
from natural20.battle import Battle
from natural20.utils.action_builder import autobuild
from natural20.map_renderer import MapRenderer
from natural20.web.json_renderer import JsonRenderer
from natural20.weapons import target_advantage_condition
from natural20.utils.spell_attack_util import evaluate_spell_attack
import random
import pdb

class TestSpellAction(unittest.TestCase):
    def make_session(self):
        event_manager = EventManager()
        event_manager.standard_cli()
        return Session(root_path='tests/fixtures', event_manager=event_manager)
    
    def setUp(self):
        random.seed(7000)
        self.session = self.make_session()
        self.entity = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.battle_map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.battle_map)
        self.npc = self.battle_map.entity_at(5, 5)
        self.battle.add(self.entity, 'a', position=[0, 5])
        self.battle.start()
        self.entity.reset_turn(self.battle)
        DieRoll.die_rolls().clear()

    def test_firebolt(self):
        random.seed(7002)
        self.assertEqual(self.npc.hp(), 9)
        print(MapRenderer(self.battle_map).render())
        action = SpellAction.build(self.session, self.entity)['next'](['firebolt',0])['next'](self.npc)
        action.resolve(self.session, self.battle_map, { "battle": self.battle})
        self.assertEqual([s['type'] for s in action.result], ['spell_damage'])
        self.battle.commit(action)
        self.assertEqual(self.npc.hp(), 0)

    def test_ranged_spell_attack_with_disadvantage(self):
        self.assertEqual(self.npc.hp(), 9)
        self.npc2 = self.session.npc('skeleton')
        self.battle.add(self.npc2, 'b', position=[1, 6])
        print(MapRenderer(self.battle_map).render())
        firebolt_spell = self.session.load_spell('firebolt')
        _, _, advantage_mod, _, _, _ = evaluate_spell_attack(self.session, self.entity, self.npc, firebolt_spell, battle=self.battle)
        self.assertEqual(advantage_mod, -1)

    def test_shocking_grasp(self):
        self.npc = self.session.npc('skeleton')
        self.battle.add(self.npc, 'b', position=[0, 6])
        self.npc.reset_turn(self.battle)
        random.seed(7002)
        print(MapRenderer(self.battle_map).render())
        build = SpellAction.build(self.session, self.entity)['next'](['shocking_grasp', 0])
        action = build['next'](self.npc)
        DieRoll.die_rolls().clear()
        self.battle.action(action)
        self.assertEqual(list(DieRoll.die_rolls())[0].advantage, False)
        self.assertEqual([s['type'] for s in action.result], ['spell_damage', 'shocking_grasp'])
        self.assertTrue(self.npc.has_reaction(self.battle))
        self.battle.commit(action)
        self.assertFalse(self.npc.has_reaction(self.battle))
        self.assertEqual(self.npc.hp(), 12)

    def test_shocking_grasp_metallic(self):
        self.npc = self.session.npc('hobgoblin')
        self.assertTrue(self.npc.equipped_metallic_armor())
        self.battle.add(self.npc, 'b', position=[0, 6])
        self.npc.reset_turn(self.battle)
        random.seed(7002)
        print(MapRenderer(self.battle_map).render())

        action = SpellAction.build(self.session, self.entity)['next'](['shocking_grasp', 0])['next'](self.npc)
        DieRoll.die_rolls().clear()
        self.battle.action(action)
        self.assertEqual(list(DieRoll.die_rolls())[0].advantage, True)
        self.battle.commit(action)
        self.assertEqual(self.npc.hp(), 10)

    def setupMageArmor(self):
        action = SpellAction.build(self.session, self.entity)['next'](['mage_armor', 0])['next'](self.entity)
        action.resolve(self.session, self.battle_map, { "battle": self.battle})
        self.assertEqual([s['type'] for s in action.result], ['mage_armor'])
        self.battle.commit(action)
        self.assertEqual(self.entity.armor_class(), 15)
        return action

    def test_mage_armor(self):
        action = self.setupMageArmor()
        self.assertTrue(self.entity.dismiss_effect(action.spell_action))
        self.assertEqual(self.entity.armor_class(), 12)

    def test_mage_armor_cast_again(self):
        action = self.setupMageArmor()
        self.entity.reset_turn(self.battle)
        self.setupMageArmor()
        self.assertEqual(self.entity.armor_class(), 15)
        current_effects = [str(e['effect']) for e in self.entity.current_effects()]
        self.assertEqual(current_effects, ['mage_armor'])
    
    def test_equip_armor_cancels_effect(self):
        self.setupMageArmor()
        self.assertEqual(self.entity.armor_class(), 15)
        self.entity.equip('studded_leather', ignore_inventory=True)
        self.assertEqual(self.entity.armor_class(), 12)

    def test_chill_touch(self):
        random.seed(1002)
        self.assertEqual(self.npc.hp(), 9)
        print(MapRenderer(self.battle_map).render())
        action = SpellAction.build(self.session, self.entity)['next'](['chill_touch', 0])['next'](self.npc)
        action.resolve(self.session, self.battle_map, { "battle": self.battle})
        self.assertEqual([s['type'] for s in action.result], ['spell_damage', 'chill_touch'])
        self.battle.commit(action)
        self.assertEqual(self.npc.hp(), 2)
        self.assertTrue(self.npc.has_spell_effect('chill_touch'))

        # target cannot heal until effect ends
        self.npc.heal(100)
        self.assertEqual(self.npc.hp(), 2)

        # drop effect until next turn
        self.entity.reset_turn(self.battle)
        self.npc.heal(100)
        self.assertNotEqual(self.npc.hp(), 3)

    def test_true_strike(self):
        def cast_true_strike():
            action = SpellAction.build(self.session, self.entity)['next'](['true_strike', 0])['next'](self.npc)
            self.battle.execute_action(action)
            return action

        random.seed(1003)
        self.npc = self.session.npc('skeleton')
        self.battle.add(self.npc, 'b', position=[5, 5])
        self.assertEqual(self.npc.hp(), 13)
        print(MapRenderer(self.battle_map).render())
        cast_true_strike()
        self.assertEqual(target_advantage_condition(self.session, self.entity, self.npc, None, battle=self.battle), [0, [[], []]])
        self.entity.reset_turn(self.battle)
        self.assertEqual(target_advantage_condition(self.session, self.entity, self.npc, None, battle=self.battle), [1, [['true_strike_advantage'], []]])
        self.entity.resolve_trigger('end_of_turn')
        self.assertEqual(target_advantage_condition(self.session, self.entity, self.npc, None, battle=self.battle), [0, [[], []]])
        cast_true_strike()
        self.entity.reset_turn(self.battle)
        self.assertEqual(target_advantage_condition(self.session, self.entity, self.npc, None, battle=self.battle), [1, [['true_strike_advantage'], []]])

        # true strike should be dismissed after the first attack
        action = SpellAction.build(self.session, self.entity)['next'](['firebolt',0])['next'](self.npc)
        self.battle.execute_action(action)
        self.assertEqual(target_advantage_condition(self.session, self.entity, self.npc, None, battle=self.battle), [0, [[], []]])

    def test_chill_touch_undead(self):
        random.seed(1003)
        self.npc = self.session.npc('skeleton')
        self.battle.add(self.npc, 'b', position=[5, 5])
        self.assertEqual(self.npc.hp(), 13)
        print(MapRenderer(self.battle_map).render())
        action = SpellAction.build(self.session, self.entity)['next'](['chill_touch', 0])['next'](self.npc)
        action.resolve(self.session, self.battle_map, { "battle" : self.battle})
        self.battle.commit(action)
        self.assertEqual(self.npc.hp(), 5)
        self.assertEqual(target_advantage_condition(self.session, self.npc, self.entity, None, battle=self.battle), [-1, [[], ['chill_touch_disadvantage']]])

    def test_expeditious_retreat(self):
        action = SpellAction.build(self.session, self.entity)['next'](['expeditious_retreat', 0])
        action.resolve(self.session, self.battle_map, { "battle": self.battle})
        self.assertEqual([s['type'] for s in action.result], ['expeditious_retreat'])
        self.battle.commit(action)
        available_actions = [a.action_type for a in self.entity.available_actions(self.session, self.battle)]

        # can't cast another spell this turn
        self.assertNotIn('spell', available_actions)
        self.entity.reset_turn(self.battle)
        available_actions = [a.action_type for a in self.entity.available_actions(self.session, self.battle)]
        self.assertIn('spell', available_actions)
        self.assertIn('dash_bonus', available_actions)

    def test_magic_missile(self):
        random.seed(1003)
        self.npc = self.session.npc('skeleton')
        self.battle.add(self.npc, 'b', position=[0, 6])
        self.npc2 = self.session.npc('skeleton')
        self.battle.add(self.npc2, 'b', position=[2, 5])
        self.npc.reset_turn(self.battle)
        self.npc2.reset_turn(self.battle)
        print(MapRenderer(self.battle_map).render())
        action = SpellAction.build(self.session, self.entity)['next'](['magic_missile', 0])['next']([self.npc, self.npc2])
        valid_targets = self.battle.valid_targets_for(self.entity, action)
        print(valid_targets)
        self.assertEqual(len(valid_targets), 3)
        action.resolve(self.session, self.battle_map, { "battle": self.battle})
        starting_hp = [self.npc.hp(), self.npc2.hp()]
        self.assertEqual([s['type'] for s in action.result], ['spell_damage', 'spell_damage'])
        self.battle.commit(action)
        ending_hp = [self.npc.hp(), self.npc2.hp()]
        self.assertNotEqual(starting_hp, ending_hp)

    def test_ray_of_frost(self):
        self.npc = self.session.npc('skeleton')
        self.battle.add(self.npc, 'b', position=[0, 6])
        self.npc.reset_turn(self.battle)
        random.seed(1003)
        print(MapRenderer(self.battle_map).render())
        action = SpellAction.build(self.session, self.entity)['next'](['ray_of_frost', 0])['next'](self.npc)
        action.resolve(self.session, self.battle_map, { "battle": self.battle})
        self.assertEqual([s['type'] for s in action.result], ['spell_damage', 'ray_of_frost'])
        self.battle.commit(action)
        self.assertEqual(self.npc.hp(), 7)
        self.assertEqual(self.npc.speed(), 20)
        self.entity.reset_turn(self.battle)
        self.assertEqual(self.npc.speed(), 30)

    def test_burning_hands(self):
        self.npc = self.session.npc('skeleton')
        self.battle.add(self.npc, 'b', position=[0, 6])
        self.npc.reset_turn(self.battle)
        random.seed(1003)
        print(MapRenderer(self.battle_map).render())
        actions = autobuild(self.session,
                           SpellAction,
                           self.entity,
                           self.battle,
                           map=self.battle_map,
                           match={ 'select_spell': 'burning_hands' },
                           verbose=True,
                           auto_target=True,
                           )
        self.assertEqual([str(action) for action in actions], ['SpellAction: burning_hands to [0, 7]'])
        self.battle.execute_action(actions[0])
        # 5e: half damage on a successful save (3d6 → 10, half = 5).
        self.assertEqual(self.npc.hp(), 8)

    def test_burning_hands_base_damage_is_3d6(self):
        # PHB 2014: "3d6 fire damage on a failed save" at 1st-level slot.
        from natural20.spell.burning_hands_spell import BurningHandsSpell
        spell_props = self.session.load_spell('burning_hands')
        spell = BurningHandsSpell(self.session, self.entity, 'burning_hands', spell_props)
        roll = spell._damage(self.battle, opts={'at_level': 1})
        self.assertEqual(len(roll.rolls), 3)
        self.assertEqual(roll.die_sides, 6)

    def test_burning_hands_upcast_adds_d6_per_slot_above_1st(self):
        # PHB 2014: "the damage increases by 1d6 for each slot level above 1st."
        from natural20.spell.burning_hands_spell import BurningHandsSpell
        spell_props = self.session.load_spell('burning_hands')
        spell = BurningHandsSpell(self.session, self.entity, 'burning_hands', spell_props)
        for at_level, expected in ((2, 4), (3, 5), (5, 7), (9, 11)):
            roll = spell._damage(self.battle, opts={'at_level': at_level})
            self.assertEqual(len(roll.rolls), expected,
                             f"slot {at_level} should be {expected}d6")

    def test_burning_hands_save_dc_uses_int_for_wizard(self):
        # high_elf_mage has INT 18, WIS 12; the DC must use the higher
        # arcane casting ability (INT) rather than wisdom.
        from natural20.spell.burning_hands_spell import BurningHandsSpell
        spell_props = self.session.load_spell('burning_hands')
        spell = BurningHandsSpell(self.session, self.entity, 'burning_hands', spell_props)
        # 8 + prof(2) + INT mod(+4) = 14
        self.assertEqual(spell._save_dc(self.entity), 14)

    def test_burning_hands_failed_save_deals_full_damage(self):
        # Force the target to fail by mocking save_throw to return 0.
        from natural20.spell.burning_hands_spell import BurningHandsSpell
        spell_props = self.session.load_spell('burning_hands')
        spell = BurningHandsSpell(self.session, self.entity, 'burning_hands', spell_props)
        self.npc = self.session.npc('skeleton')
        self.battle.add(self.npc, 'b', position=[0, 6])
        self.npc.reset_turn(self.battle)

        class _FailRoll:
            def __lt__(self, other): return True
            def prob(self, _dc): return 1.0
        original_save = self.npc.save_throw
        self.npc.save_throw = lambda *a, **k: _FailRoll()
        try:
            action = SpellAction(self.session, self.entity, 'spell')
            action.spell_action = spell
            action.target = [0, 7]
            action.at_level = 1
            spell.action = action
            results = spell.resolve(self.entity, self.battle, action, self.battle_map)
        finally:
            self.npc.save_throw = original_save
        damage_results = [r for r in results if r['target'] is self.npc]
        self.assertEqual(len(damage_results), 1)
        # On a failed save, 'damage' equals the full roll (not halved).
        self.assertIs(damage_results[0]['damage'], damage_results[0]['damage_roll'])
        self.assertTrue(damage_results[0]['save_failed'])

    def test_chromatic_orb_selects_damage_type_and_hits(self):
        random.seed(7002)
        action_build = SpellAction.build(self.session, self.entity)['next'](['chromatic_orb', 0])
        self.assertEqual(action_build['param'][0]['type'], 'select_choice')

        target_build = action_build['next']('thunder')
        self.assertEqual(target_build['param'][0]['type'], 'select_target')

        action = target_build['next'](self.npc)
        action.resolve(self.session, self.battle_map, {"battle": self.battle})

        self.assertEqual([s['type'] for s in action.result], ['spell_damage'])
        self.assertEqual(action.result[0]['damage_type'], 'thunder')
        self.assertEqual(action.result[0]['spell']['damage_type'], 'thunder')

    def test_chromatic_orb_base_damage_is_3d8(self):
        from natural20.spell.chromatic_orb_spell import ChromaticOrbSpell

        spell_props = self.session.load_spell('chromatic_orb')
        spell = ChromaticOrbSpell(self.session, self.entity, 'chromatic_orb', spell_props)
        roll = spell._damage(self.battle, opts={'at_level': 1})
        self.assertEqual(len(roll.rolls), 3)
        self.assertEqual(roll.die_sides, 8)

    def test_chromatic_orb_upcast_adds_d8_per_slot_above_1st(self):
        from natural20.spell.chromatic_orb_spell import ChromaticOrbSpell

        spell_props = self.session.load_spell('chromatic_orb')
        spell = ChromaticOrbSpell(self.session, self.entity, 'chromatic_orb', spell_props)
        for at_level, expected in ((2, 4), (3, 5), (5, 7), (9, 11)):
            roll = spell._damage(self.battle, opts={'at_level': at_level})
            self.assertEqual(len(roll.rolls), expected,
                             f"slot {at_level} should be {expected}d8")

    def test_color_spray_pool_is_6d10_base(self):
        from natural20.spell.color_spray_spell import ColorSpraySpell

        spell_props = self.session.load_spell('color_spray')
        spell = ColorSpraySpell(self.session, self.entity, 'color_spray', spell_props)
        roll = spell._pool_roll(self.battle, opts={'at_level': 1})
        self.assertEqual(len(roll.rolls), 6)
        self.assertEqual(roll.die_sides, 10)

    def test_color_spray_upcast_adds_d10_per_slot_above_1st(self):
        from natural20.spell.color_spray_spell import ColorSpraySpell

        spell_props = self.session.load_spell('color_spray')
        spell = ColorSpraySpell(self.session, self.entity, 'color_spray', spell_props)
        for at_level, expected in ((2, 7), (3, 8), (5, 10), (9, 14)):
            roll = spell._pool_roll(self.battle, opts={'at_level': at_level})
            self.assertEqual(len(roll.rolls), expected,
                             f"slot {at_level} should be {expected}d10")

    def test_color_spray_applies_blinded_until_end_of_next_turn(self):
        random.seed(7002)
        self.npc = self.session.npc('skeleton')
        self.battle.add(self.npc, 'b', position=[0, 6])
        self.npc.reset_turn(self.battle)
        # Build against an explicit cone direction as done by cone spells.
        action = SpellAction.build(self.session, self.entity)['next'](['color_spray', 0])['next']([0, 7])
        action.resolve(self.session, self.battle_map, {"battle": self.battle})
        self.battle.commit(action)

        # One nearby enemy in cone should be blinded by the cast.
        self.assertTrue(self.npc.blinded())

        # Start of caster next turn: still blinded.
        self.entity.reset_turn(self.battle)
        self.assertTrue(self.npc.blinded())

        # End of caster next turn: effect expires.
        self.entity.resolve_trigger('end_of_turn')
        self.assertFalse(self.npc.blinded())

    def test_witch_bolt_initial_upcast_adds_d12_per_slot(self):
        from natural20.spell.witch_bolt_spell import WitchBoltSpell

        spell_props = self.session.load_spell('witch_bolt')
        spell = WitchBoltSpell(self.session, self.entity, 'witch_bolt', spell_props)
        for at_level, expected in ((1, 1), (2, 2), (3, 3), (5, 5), (9, 9)):
            roll = spell._initial_damage(self.battle, opts={'at_level': at_level})
            self.assertEqual(len(roll.rolls), expected,
                             f"slot {at_level} should be {expected}d12")

    def test_witch_bolt_sustain_action_available_and_deals_damage(self):
        self.npc = self.session.npc('skeleton')
        self.battle.add(self.npc, 'b', position=[0, 6])
        self.npc.reset_turn(self.battle)

        DieRoll.fudge(8)
        try:
            cast = SpellAction.build(self.session, self.entity)['next'](['witch_bolt', 0])['next'](self.npc)
            cast.resolve(self.session, self.battle_map, {'battle': self.battle})
            self.battle.commit(cast)
        finally:
            DieRoll.unfudge()

        self.assertIsNotNone(self.entity.current_concentration())

        self.entity.reset_turn(self.battle)
        sustain_action = next((a for a in self.entity.available_actions(self.session, self.battle)
                               if a.action_type == 'witch_bolt_sustain'), None)
        self.assertIsNotNone(sustain_action)

        hp_before = self.npc.hp()
        sustain_action.resolve(self.session, self.battle_map, {'battle': self.battle})
        self.battle.commit(sustain_action)
        self.assertLess(self.npc.hp(), hp_before)

    def test_witch_bolt_ends_if_action_used_for_something_else(self):
        self.npc = self.session.npc('skeleton')
        self.battle.add(self.npc, 'b', position=[0, 6])
        self.npc.reset_turn(self.battle)

        DieRoll.fudge(8)
        try:
            cast = SpellAction.build(self.session, self.entity)['next'](['witch_bolt', 0])['next'](self.npc)
            cast.resolve(self.session, self.battle_map, {'battle': self.battle})
            self.battle.commit(cast)
        finally:
            DieRoll.unfudge()

        self.assertIsNotNone(self.entity.current_concentration())

        self.entity.reset_turn(self.battle)
        dodge = next((a for a in self.entity.available_actions(self.session, self.battle)
                      if a.action_type == 'dodge'), None)
        self.assertIsNotNone(dodge)
        dodge.resolve(self.session, self.battle_map, {'battle': self.battle})
        self.battle.commit(dodge)

        self.entity.resolve_trigger('end_of_turn')
        self.assertIsNone(self.entity.current_concentration())

    def test_grease_build_uses_square_selector(self):
        build = SpellAction.build(self.session, self.entity)['next'](['grease', 0])
        self.assertEqual(build['param'][0]['type'], 'select_square')
        self.assertEqual(build['param'][0]['range'], 60)
        self.assertEqual(build['param'][0]['size'], 10)

    def test_grease_cast_creates_difficult_terrain_and_prones_on_failed_save(self):
        class _FailRoll:
            def result(self):
                return 1

        original_save = self.npc.save_throw
        self.npc.save_throw = lambda *a, **k: _FailRoll()
        try:
            action = SpellAction.build(self.session, self.entity)['next'](['grease', 0])['next']([5, 5])
            action.resolve(self.session, self.battle_map, {'battle': self.battle})
            self.battle.commit(action)
        finally:
            self.npc.save_throw = original_save

        self.assertTrue(self.npc.prone())
        self.assertTrue(self.battle_map.difficult_terrain(None, 5, 5))
        self.assertTrue(self.battle_map.difficult_terrain(None, 6, 6))
        self.assertEqual(len(self.battle.active_zones), 1)

    def test_grease_entry_save_triggers_when_moving_into_area(self):
        class _SuccessRoll:
            def result(self):
                return 99

        class _FailRoll:
            def result(self):
                return 1

        # Cast with an automatic success to avoid immediate prone.
        original_save = self.npc.save_throw
        self.npc.save_throw = lambda *a, **k: _SuccessRoll()
        try:
            cast = SpellAction.build(self.session, self.entity)['next'](['grease', 0])['next']([5, 5])
            cast.resolve(self.session, self.battle_map, {'battle': self.battle})
            self.battle.commit(cast)
        finally:
            self.npc.save_throw = original_save

        if self.npc.prone():
            self.npc.stand()

        self.battle_map.move_to(self.npc, 7, 5, self.battle)
        self.assertFalse(self.npc.prone())

        self.npc.save_throw = lambda *a, **k: _FailRoll()
        try:
            self.battle_map.move_to(self.npc, 6, 5, self.battle)
        finally:
            self.npc.save_throw = original_save

        self.assertTrue(self.npc.prone())

    def test_grease_end_of_turn_save_and_expiration_cleanup(self):
        class _SuccessRoll:
            def result(self):
                return 99

        class _FailRoll:
            def result(self):
                return 1

        original_save = self.npc.save_throw
        self.npc.save_throw = lambda *a, **k: _SuccessRoll()
        try:
            cast = SpellAction.build(self.session, self.entity)['next'](['grease', 0])['next']([5, 5])
            cast.resolve(self.session, self.battle_map, {'battle': self.battle})
            self.battle.commit(cast)
        finally:
            self.npc.save_throw = original_save

        if self.npc.prone():
            self.npc.stand()

        self.npc.save_throw = lambda *a, **k: _FailRoll()
        try:
            self.battle.trigger_event('end_of_turn', self.npc, {'target': self.npc})
        finally:
            self.npc.save_throw = original_save
        self.assertTrue(self.npc.prone())

        zone = self.battle.active_zones[0]
        zone.expiration_round = self.battle.current_round() - 1
        self.battle.trigger_event('start_of_turn', self.entity, {'target': self.entity})
        self.assertEqual(len(self.battle.active_zones), 0)
        for sx, sy in [(5, 5), (6, 5), (5, 6), (6, 6)]:
            grease_objects = [
                obj for obj in self.battle_map.objects_at(sx, sy)
                if getattr(obj, 'properties', {}).get('grease_surface')
            ]
            self.assertEqual(len(grease_objects), 0)

    def test_compute_hit_probability(self):
        self.npc = self.session.npc('skeleton')
        self.battle.add(self.npc, 'b', position=[0, 6])
        self.npc.reset_turn(self.battle)

        action = SpellAction.build(self.session, self.entity)['next'](['ray_of_frost', 0])['next'](self.npc)
        self.assertAlmostEqual(action.compute_hit_probability(self.battle), 0.49)
        self.assertAlmostEqual(action.avg_damage(self.battle), 4.5)

        action = SpellAction.build(self.session, self.entity)['next'](['firebolt', 0])['next'](self.npc)
        self.assertAlmostEqual(action.compute_hit_probability(self.battle), 0.49)
        self.assertAlmostEqual(action.avg_damage(self.battle), 5.5)

    def test_shield_spell(self):
        class CustomReactionController(Controller):
            def __init__(self, session):
                self.state = {}
                self.session = session
                self.battle_data = {}
                self.user = None

            def select_reaction(self, entity, battle, map, valid_actions, event):
                return valid_actions[0]
        self.battle.set_controller_for(self.entity, CustomReactionController(self.session))
        self.assertEqual(self.entity.armor_class(), 12)
        self.npc = self.session.npc('skeleton')
        self.battle.add(self.npc, 'b', position=[1, 6])
        self.npc.reset_turn(self.battle)
        random.seed(1003)
        print(MapRenderer(self.battle_map).render())
        # make the skeleton attack the mage
        DieRoll.fudge(10)
        action = AttackAction(self.session, self.npc, 'attack')
        action.target = self.entity
        action.npc_action = {
            "name": "Short Sword",
            "type": 'melee_attack',
            "range": 5,
            "targets": 1,
            "attack": 4,
            "damage": 5,
            "damage_die": "1d6+2",
            "damage_type": "piercing"
        }
        self.battle.execute_action(action)
        DieRoll.unfudge()
        self.assertEqual(self.entity.hp(), 0)

    def test_shield_spell_async(self):
        class CustomReactionController(Controller):
            def __init__(self, session):
                self.state = {}
                self.session = session
                self.battle_data = {}
                self.user = None

            def select_reaction(self, entity, battle, map, valid_actions, event):
                yield entity, event, valid_actions

        self.battle.set_controller_for(self.entity, CustomReactionController(self.session))
        self.assertEqual(self.entity.armor_class(), 12)
        self.npc = self.session.npc('skeleton')
        self.battle.add(self.npc, 'b', position=[1, 6])
        self.npc.reset_turn(self.battle)
        random.seed(1003)
        print(MapRenderer(self.battle_map).render())
        # make the skeleton attack the mage
        DieRoll.fudge(10)
        action = AttackAction(self.session, self.npc, 'attack')
        action.target = self.entity
        action.npc_action = {
            "name": "Short Sword",
            "type": 'melee_attack',
            "range": 5,
            "targets": 1,
            "attack": 4,
            "damage": 5,
            "damage_die": "1d6+2",
            "damage_type": "piercing"
        }
        try:
            self.battle.action(action)
        except AsyncReactionHandler as e:
            print("waiting for reaction")
            if (e.reaction_type == 'shield'):
                for _, _, valid_actions in e.resolve():
                    e.send(valid_actions[0])
                action = self.battle.action(action)
        self.battle.commit(action)
        DieRoll.unfudge()
        self.assertEqual(self.entity.hp(), 0)

    def test_autobuild(self):
        self.npc = self.session.npc('skeleton')
        self.battle.add(self.npc, 'b', position=[0, 6])
        auto_build_actions = autobuild(self.session, SpellAction, self.entity, self.battle)
        self.assertEqual(len(auto_build_actions), 4)
        action_list = [str(a) for a in  auto_build_actions]

        self.assertEqual(action_list, [
            'SpellAction: burning_hands to [0, 7]',
            'SpellAction: firebolt to Skeleton',
            'SpellAction: mage_armor to Crysania',
            'SpellAction: magic_missile to (Skeleton, Skeleton, Skeleton)'])

        self.assertEqual(self.entity.armor_class(), 12)
        # must be a valid action
        for a in auto_build_actions:
            a.resolve(self.session, self.battle_map, { "battle": self.battle})
            self.battle.commit(a)
        # mage armor should take effect
        self.assertEqual(self.entity.armor_class(), 15)

    def test_find_familiar(self):
        # Cast find familiar spell
        print(MapRenderer(self.battle_map).render())
        action = autobuild(self.session, SpellAction, self.entity, None, map=self.battle_map, match=['find_familiar', 'bat', [0, 6]], verbose=True)[0]
        self.battle.execute_action(action)
        entity = self.battle_map.entity_at(0, 6)
        self.assertEqual(entity.name, 'Bat')
        self.assertEqual(entity.owner, self.entity)
        print(MapRenderer(self.battle_map).render())

        self.assertEqual(len(self.entity.casted_effects), 1)
        # test dismiss

        for effect in self.entity.casted_effects:
            self.entity.remove_effect(effect['effect'], opts={'event': 'dismiss_familiar'})

        entity = self.battle_map.entity_at(0, 6)
        self.assertIsNone(entity)

        action = autobuild(self.session, SpellAction, self.entity, None, map=self.battle_map, match=['find_familiar', 'bat', [0, 6]], verbose=True)[0]
        self.battle.execute_action(action)

        # test send to pocket dimension

        action = autobuild(self.session, FindFamiliarAction, self.entity, None, map=self.battle_map, match=['dismiss_temporary'], verbose=True)[0]

        self.battle.execute_action(action)

        entity = self.battle_map.entity_at(0, 6)
        self.assertIsNone(entity)
        self.assertEqual(len(self.entity.pocket_dimension), 1)

        # resummon
        action = autobuild(self.session, SummonFamiliarAction, self.entity, self.battle, map=self.battle_map, match=[[3, 5]], verbose=True)[0]
        self.battle.execute_action(action)

        entity = self.battle_map.entity_at(3, 5)
        self.assertIsNotNone(entity)
        self.assertEqual(entity.name, 'Bat')
        self.assertEqual(entity.owner, self.entity)

    def test_mage_hand_uses_stable_token_image_in_json_renderer(self):
        mage_hand = MageHand(self.session, self.entity)
        self.battle_map.place((2, 5), mage_hand)

        rendered_tiles = JsonRenderer(self.battle_map, self.battle).render()
        mage_hand_tile = None
        for row in rendered_tiles:
            for tile in row:
                if isinstance(tile, dict) and tile.get('id') == mage_hand.entity_uid:
                    mage_hand_tile = tile
                    break
            if mage_hand_tile:
                break

        self.assertIsNotNone(mage_hand_tile)
        self.assertEqual(mage_hand.token_image(), 'token_mage_hand.png')
        self.assertEqual(mage_hand_tile.get('entity'), 'token_mage_hand.png')
        self.assertTrue(os.path.exists('webapp/static/assets/token_mage_hand.png'))


    def test_protection_from_poison(self):
        random.seed(1003)
        print(MapRenderer(self.battle_map).render())

        action = SpellAction.build(self.session, self.entity)['next'](['protection_from_poison', 0])['next'](self.entity)
        action.resolve(self.session, self.battle_map, { "battle": self.battle})
        self.battle.commit(action)
        self.assertEqual(self.entity.effective_resistances(), ['poison'])
        
if __name__ == '__main__':
    unittest.main()
