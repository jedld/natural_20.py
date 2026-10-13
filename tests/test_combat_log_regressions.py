"""Regressions found by reviewing a VTT combat log against a vampire boss."""
import random
import unittest
from types import SimpleNamespace

from natural20.actions.attack_action import AttackAction
from natural20.actions.hide_action import HideAction
from natural20.actions.spell_action import SpellAction
from natural20.actions.wrath_of_the_storm_action import WrathOfTheStormAction
from natural20.battle import Battle
from natural20.controller import Controller
from natural20.die_roll import DieRoll
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.spell.polymorph_spell import PolymorphSpell
from natural20.spell.shield_spell import ShieldSpell
from natural20.utils import polymorph
from natural20.utils.combat_roster import condition_summary
from natural20.utils.dispel import spells_on, worth_dispelling
from natural20.utils.pointless_actions import is_pointless


class AlwaysReact(Controller):
    def __init__(self, session):
        self.state = {}
        self.session = session
        self.battle_data = {}
        self.user = None

    def select_reaction(self, entity, battle, map, valid_actions, event):
        return valid_actions[0]


def _session(events=None):
    em = EventManager()
    em.standard_cli()
    if events is not None:
        original = em.received_event

        def record(event):
            events.append(event)
            return original(event)
        em.received_event = record
    return Session(root_path='tests/fixtures', event_manager=em)


def _attack(session, attacker, target, attack=4, damage_die='1d6+2', **extra):
    action = AttackAction(session, attacker, 'attack')
    action.target = target
    action.npc_action = {
        'name': 'Claw', 'type': 'melee_attack', 'range': 5, 'targets': 1,
        'attack': attack, 'damage': 5, 'damage_die': damage_die,
        'damage_type': 'slashing', **extra,
    }
    return action


class ShieldReactionTest(unittest.TestCase):
    def setUp(self):
        random.seed(7000)
        self.session = _session()
        self.mage = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.map)
        self.battle.add(self.mage, 'a', position=[0, 5])
        self.battle.set_controller_for(self.mage, AlwaysReact(self.session))
        self.skeleton = self.session.npc('skeleton')
        self.battle.add(self.skeleton, 'b', position=[1, 6])
        self.battle.start()
        self.mage.reset_turn(self.battle)
        self.skeleton.reset_turn(self.battle)

    def _swing(self):
        DieRoll.fudge(10)
        try:
            self.battle.execute_action(_attack(self.session, self.skeleton, self.mage))
        finally:
            DieRoll.unfudge()

    def test_shield_spends_slot_and_reaction(self):
        slots = self.mage.spell_slots_count(1, 'wizard')
        self._swing()
        self.assertTrue(ShieldSpell.is_active_on(self.mage))
        self.assertEqual(self.mage.spell_slots_count(1, 'wizard'), slots - 1)
        self.assertFalse(self.mage.has_reaction(self.battle))

    def test_shield_does_not_stack(self):
        self._swing()
        self.battle.entity_state_for(self.mage)['reaction'] = 1
        slots = self.mage.spell_slots_count(1, 'wizard')
        DieRoll.fudge(15)
        try:
            self.battle.execute_action(_attack(self.session, self.skeleton, self.mage))
        finally:
            DieRoll.unfudge()
        self.assertEqual(self.mage.spell_slots_count(1, 'wizard'), slots)
        self.assertEqual(len([e for e in self.mage.effects.get('ac_bonus', [])
                              if e['handler'] is ShieldSpell]), 1)

    def test_no_shield_without_slots(self):
        for level in list(self.mage.spell_slots.get('wizard', {})):
            self.mage.spell_slots['wizard'][level] = 0
        self._swing()
        self.assertFalse(ShieldSpell.is_active_on(self.mage))


class DispelMagicTest(unittest.TestCase):
    def setUp(self):
        random.seed(4242)
        self.events = []
        self.session = _session(self.events)
        self.map = Map(self.session, 'battle_sim')
        self.battle = Battle(self.session, self.map)
        self.cleric = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.ally = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.enemy_caster = PlayerCharacter.load(self.session, 'high_elf_mage.yml', {'name': 'Hostile Mage'})
        self.map.add(self.cleric, 0, 0)
        self.map.add(self.ally, 1, 0)
        self.map.add(self.enemy_caster, 0, 3)
        self.battle.add(self.cleric, 'a', add_to_initiative=True)
        self.battle.add(self.ally, 'a', add_to_initiative=True)
        self.battle.add(self.enemy_caster, 'b', add_to_initiative=True)
        self.battle.start(combat_order=[self.cleric, self.ally, self.enemy_caster])
        self.cleric.reset_turn(self.battle)

    def _polymorph_ally(self, level=4):
        spell = PolymorphSpell(self.session, self.enemy_caster, 'polymorph',
                               self.session.load_spell('polymorph'))
        spell.action = SimpleNamespace(target=self.ally, at_level=level)
        roll = SimpleNamespace(result=lambda: 1, prob=lambda dc: 0.0)
        self.ally.save_throw = lambda *a, **k: roll
        for item in spell.resolve(self.enemy_caster, self.battle, spell.action, self.map):
            PolymorphSpell.apply(self.battle, item, self.session)
        del self.ally.save_throw
        self.assertTrue(polymorph.is_polymorphed(self.ally))
        return spell

    def _dispel(self, target, at_level=3):
        action = SpellAction.build(self.session, self.cleric)['next'](['dispel_magic', at_level])['next'](target)
        action.resolve(self.session, self.map, {'battle': self.battle})
        self.battle.commit(action)
        return action

    def test_spells_on_target_not_on_caster(self):
        spell = self._polymorph_ally()
        self.assertEqual([e for e, _ in spells_on(self.ally, self.battle)], [spell])
        self.assertEqual(spells_on(self.enemy_caster, self.battle), [])

    def test_dispel_ends_polymorph_with_higher_slot(self):
        self._polymorph_ally()
        self._dispel(self.ally, at_level=4)
        self.assertFalse(polymorph.is_polymorphed(self.ally))
        self.assertIsNone(self.enemy_caster.concentration)
        logged = [e for e in self.events if e.get('event') == 'dispel_magic']
        self.assertTrue(logged and logged[0]['outcomes'][0]['ended'])

    def test_dispel_check_against_higher_level_spell(self):
        self._polymorph_ally()
        DieRoll.fudge(1)
        try:
            self._dispel(self.ally, at_level=3)
        finally:
            DieRoll.unfudge()
        self.assertTrue(polymorph.is_polymorphed(self.ally))
        outcome = [e for e in self.events if e.get('event') == 'dispel_magic'][0]['outcomes'][0]
        self.assertFalse(outcome['ended'])
        self.assertEqual(outcome['dc'], 14)

    def test_ai_only_dispels_hostile_spells(self):
        self._polymorph_ally()
        self.assertTrue(worth_dispelling(self.battle, self.cleric, self.ally))
        self.assertFalse(worth_dispelling(self.battle, self.cleric, self.enemy_caster))
        on_caster = SpellAction.build(self.session, self.cleric)['next'](['dispel_magic', 3])['next'](self.enemy_caster)
        on_ally = SpellAction.build(self.session, self.cleric)['next'](['dispel_magic', 3])['next'](self.ally)
        self.assertTrue(is_pointless(self.battle, self.cleric, on_caster))
        self.assertFalse(is_pointless(self.battle, self.cleric, on_ally))


class UncannyDodgeTest(unittest.TestCase):
    def test_halves_rider_damage(self):
        random.seed(11)
        session = _session()
        bmap = Map(session, 'battle_sim')
        battle = Battle(session, bmap)
        rogue = PlayerCharacter.load(session, 'elf_rogue.yml', {'class_features': ['uncanny_dodge']})
        brute = session.npc('skeleton')
        battle.add(rogue, 'a', position=[0, 0])
        battle.add(brute, 'b', position=[1, 0])
        battle.start()
        rogue.reset_turn(battle)
        brute.reset_turn(battle)
        rogue.attributes['hp'] = 100
        rogue.properties['max_hp'] = 100
        action = _attack(session, brute, rogue, attack=20, damage_die='10',
                         additional_damage=[{'damage_die': '20', 'damage_type': 'necrotic'}])
        battle.execute_action(action)
        self.assertEqual(rogue.hp(), 100 - 5 - 10)


class WrathOfTheStormTest(unittest.TestCase):
    def setUp(self):
        random.seed(99)
        self.events = []
        self.session = _session(self.events)
        bmap = Map(self.session, 'battle_sim')
        self.battle = Battle(self.session, bmap)
        self.cleric = PlayerCharacter.load(self.session, 'dwarf_cleric.yml',
                                           {'class_features': ['wrath_of_the_storm']})
        self.cleric._init_wrath_of_the_storm()
        self.brute = self.session.npc('skeleton')
        self.battle.add(self.cleric, 'a', position=[0, 0])
        self.battle.add(self.brute, 'b', position=[1, 0])
        self.battle.set_controller_for(self.cleric, AlwaysReact(self.session))
        self.battle.start()
        self.cleric.reset_turn(self.battle)
        self.brute.reset_turn(self.battle)

    def test_triggers_on_melee_hit(self):
        uses = self.cleric.wrath_of_the_storm_uses
        hp = self.brute.hp()
        self.battle.execute_action(_attack(self.session, self.brute, self.cleric, attack=30, damage_die='1'))
        self.assertEqual(self.cleric.wrath_of_the_storm_uses, uses - 1)
        self.assertFalse(self.cleric.has_reaction(self.battle))
        self.assertTrue(any(e.get('event') == 'wrath_of_the_storm' for e in self.events))
        self.assertLess(self.brute.hp(), hp)

    def test_turn_action_is_free_and_skipped_by_ai(self):
        action = WrathOfTheStormAction(self.session, self.cleric, 'wrath_of_the_storm')
        uses = self.cleric.wrath_of_the_storm_uses
        self.battle.execute_action(action)
        self.assertEqual(self.cleric.wrath_of_the_storm_uses, uses)
        self.assertTrue(self.cleric.has_reaction(self.battle))
        self.assertTrue(is_pointless(self.battle, self.cleric, action))


class HideAndLogTest(unittest.TestCase):
    def setUp(self):
        self.session = _session()
        bmap = Map(self.session, 'battle_sim')
        self.battle = Battle(self.session, bmap)
        self.rogue = PlayerCharacter.load(self.session, 'elf_rogue.yml')
        self.foe = self.session.npc('skeleton')
        self.battle.add(self.rogue, 'a', position=[0, 0])
        self.battle.add(self.foe, 'b', position=[3, 0])
        self.battle.start()
        self.rogue.reset_turn(self.battle)

    def test_hide_while_hidden_is_pointless(self):
        hide = HideAction(self.session, self.rogue, 'hide')
        self.rogue.do_hide(25)
        self.assertTrue(is_pointless(self.battle, self.rogue, hide))

    def test_hide_in_view_of_sharp_eyed_foe_is_pointless(self):
        hide = HideAction(self.session, self.rogue, 'hide')
        self.foe.properties['passive_perception'] = 40
        self.assertTrue(is_pointless(self.battle, self.rogue, hide))
        self.foe.properties['passive_perception'] = 10
        self.assertFalse(is_pointless(self.battle, self.rogue, hide))

    def test_conditions_are_deduplicated(self):
        self.rogue.statuses.extend(['stable', 'stable'])
        parts = condition_summary(self.battle, self.rogue)
        self.assertEqual(len(parts), len(set(parts)))

    def test_consolidated_move_log_keeps_every_step(self):
        em = self.session.event_manager
        logged = []
        em.output_logger = SimpleNamespace(log=logged.append)
        em.movement_consolidation = True
        em.received_event({'event': 'move', 'source': self.rogue, 'path': [[0, 0], [1, 0]],
                           'position': [1, 0], 'move_cost': 1})
        em.received_event({'event': 'move', 'source': self.rogue, 'path': [[1, 0], [2, 1], [3, 2]],
                           'position': [3, 2], 'move_cost': 2})
        em.received_event({'event': 'stand', 'source': self.rogue})
        self.assertIn('[[0, 0], [1, 0], [2, 1], [3, 2]] 15 feet', logged[0])


if __name__ == '__main__':
    unittest.main()


class MirrorImageExpiryTest(unittest.TestCase):
    def test_expired_duplicates_vanish_with_their_status(self):
        from natural20.spell.mirror_image_spell import MirrorImageSpell
        session = _session()
        mage = PlayerCharacter.load(session, 'high_elf_mage.yml')
        battle = Battle(session, Map(session, 'battle_sim_objects'))
        battle.add(mage, 'a', position=[0, 5])
        battle.start()
        props = session.load_spell('mirror_image')
        spell = MirrorImageSpell(session, mage, 'mirror_image', props)
        MirrorImageSpell.apply(battle, {'type': 'mirror_image', 'source': mage, 'target': mage,
                                        'effect': spell, 'spell': {'duration_seconds': 60}})
        self.assertEqual(MirrorImageSpell.images_remaining_for(mage), 3)
        session.game_time += 61
        self.assertEqual(MirrorImageSpell.images_remaining_for(mage), 0)
        mage._cleanup_effects()
        self.assertNotIn('mirror_image', mage.statuses)


class SlotHealingTest(unittest.TestCase):
    def setUp(self):
        random.seed(7000)
        self.session = _session()
        self.cleric = PlayerCharacter.load(self.session, 'dwarf_cleric.yml')
        self.cleric.properties['prepared_spells'].append('healing_word')

    def _heal_dice(self, spell, at_level):
        action = SpellAction.build(self.session, self.cleric)['next']([spell, at_level])
        action = action['next'](self.cleric)
        heal = action.spell_action._heal(None)
        return len(heal.rolls), heal.die_sides

    def test_cure_wounds_scales_with_slot_not_character_level(self):
        self.assertEqual(self._heal_dice('cure_wounds', 1), (1, 8))
        self.assertEqual(self._heal_dice('cure_wounds', 3), (3, 8))

    def test_healing_word_scales_with_slot(self):
        self.assertEqual(self._heal_dice('healing_word', 2), (2, 4))

    def test_2024_doubles_the_dice(self):
        from natural20.spell.cure_wounds_spell import CureWoundsSpell
        from natural20.spell.healing_word_spell import HealingWordSpell
        from natural20.spell.cure_wounds_spell import slot_healing_dice
        props = {'level': 1, 'heal_dice': '2d8', 'heal_dice_per_slot': '2d8'}
        spell = CureWoundsSpell(self.session, self.cleric, 'cure_wounds', props)
        spell.action = SimpleNamespace(at_level=2)
        self.assertEqual(slot_healing_dice(spell, '1d8'), '4d8')
        word = HealingWordSpell(self.session, self.cleric, 'healing_word',
                                {'level': 1, 'heal_dice': '2d4', 'heal_dice_per_slot': '2d4'})
        word.action = SimpleNamespace(at_level=1)
        self.assertEqual(slot_healing_dice(word, '1d4'), '2d4')


class SpellsPerTurnTest(unittest.TestCase):
    def setUp(self):
        self.session = _session()
        self.cleric = PlayerCharacter.load(self.session, 'dwarf_cleric.yml')
        self.cleric.properties['prepared_spells'].append('healing_word')
        self.battle = Battle(self.session, Map(self.session, 'battle_sim_objects'))
        self.battle.add(self.cleric, 'a', position=[0, 5])
        self.goblin = self.session.npc('goblin')
        self.battle.add(self.goblin, 'b', position=[3, 5])
        self.battle.start()
        self.cleric.reset_turn(self.battle)
        self.battle.set_current_turn(self.cleric)

    def _cast_healing_word(self):
        action = SpellAction.build(self.session, self.cleric)['next'](['healing_word', 1])
        self.battle.execute_action(action['next'](self.cleric))

    def test_2014_cantrip_after_bonus_action_spell(self):
        self._cast_healing_word()
        self.assertTrue(SpellAction.can_cast(self.cleric, self.battle, 'sacred_flame'))
        self.assertFalse(SpellAction.can_cast(self.cleric, self.battle, 'guiding_bolt'))

    def test_2024_one_slot_per_turn(self):
        from natural20.ruleset.ruleset_2024 import Ruleset2024
        self.session.ruleset = Ruleset2024()
        self._cast_healing_word()
        self.assertTrue(SpellAction.can_cast(self.cleric, self.battle, 'sacred_flame'))
        self.assertFalse(SpellAction.can_cast(self.cleric, self.battle, 'guiding_bolt'))

    def test_2014_no_bonus_action_spell_after_leveled_action_spell(self):
        action = SpellAction.build(self.session, self.cleric)['next'](['guiding_bolt', 1])
        self.battle.execute_action(action['next'](self.goblin))
        self.cleric.reset_turn(self.battle)
        self.battle.entity_state_for(self.cleric)['casted_spells'] = [{'level': 1, 'resource': 'action'}]
        self.assertFalse(SpellAction.can_cast(self.cleric, self.battle, 'healing_word'))


class DeathLogOrderTest(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.session = _session(self.events)
        self.fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle = Battle(self.session, Map(self.session, 'battle_sim_objects'))
        self.battle.add(self.fighter, 'a', position=[0, 5])
        self.goblin = self.session.npc('goblin')
        self.battle.add(self.goblin, 'b', position=[1, 5])
        self.battle.start()
        self.fighter.reset_turn(self.battle)

    def _names(self):
        return [e['event'] for e in self.events]

    def test_final_death_save_is_logged_before_death(self):
        self.fighter.attributes['hp'] = 0
        self.fighter.make_unconscious()
        self.fighter.death_fails = 2
        DieRoll.fudge(3)
        try:
            self.fighter.death_saving_throw(self.battle)
        finally:
            DieRoll.unfudge()
        names = self._names()
        self.assertLess(names.index('death_fail'), names.index('died'))
        fail = next(e for e in self.events if e['event'] == 'death_fail')
        self.assertEqual(fail['fails'], 3)

    def test_damage_is_logged_before_falling_unconscious(self):
        dispatched = []
        self.session.event_manager.register_event_listener(
            ['damage', 'unconscious'], lambda e: dispatched.append(e['event']))
        self.fighter.take_damage(self.fighter.hp() + 1, battle=self.battle, damage_type='slashing')
        self.assertEqual(dispatched, ['damage', 'unconscious'])

    def test_dead_creature_gets_no_start_of_turn(self):
        self.fighter.attributes['hp'] = 0
        self.fighter.make_unconscious()
        self.fighter.death_fails = 2
        self.battle.set_current_turn(self.fighter)
        del self.events[:]
        DieRoll.fudge(3)
        try:
            self.battle.start_turn()
        finally:
            DieRoll.unfudge()
        self.assertTrue(self.fighter.dead())
        self.assertNotIn('start_of_turn', self._names())


class SpellLabelLogTest(unittest.TestCase):
    def test_buff_and_dismiss_lines_use_spell_labels(self):
        lines = []
        em = EventManager()
        em.standard_cli()
        em.output_logger = SimpleNamespace(log=lambda msg, *a, **k: lines.append(msg))
        session = Session(root_path='tests/fixtures', event_manager=em)
        mage = PlayerCharacter.load(session, 'high_elf_mage.yml')
        shield = ShieldSpell(session, mage, 'ShieldSpell', session.load_spell('shield'))
        em.received_event({'event': 'spell_buf', 'spell': shield, 'source': mage, 'target': mage})
        em.received_event({'event': 'dismiss_effect', 'effect': shield, 'source': mage})
        self.assertIn('cast Shield on', lines[0])
        self.assertIn('Shield effect has been dismissed', lines[1])


def _logging_session():
    lines = []
    em = EventManager()
    em.standard_cli()
    em.output_logger = SimpleNamespace(log=lambda msg, *a, **k: lines.append(msg))
    return Session(root_path='tests/fixtures', event_manager=em), lines


class SpareTheDyingAfterHealTest(unittest.TestCase):
    def setUp(self):
        random.seed(11)
        self.session = _session()
        self.cleric = PlayerCharacter.load(self.session, 'dwarf_cleric.yml')
        self.cleric.properties['prepared_spells'] += ['healing_word', 'spare_the_dying']
        self.fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle = Battle(self.session, Map(self.session, 'battle_sim_objects'))
        self.battle.add(self.cleric, 'a', position=[0, 5])
        self.battle.add(self.fighter, 'a', position=[1, 5])
        self.battle.add(self.session.npc('goblin'), 'b', position=[6, 5])
        self.battle.start()
        self.cleric.reset_turn(self.battle)
        self.battle.set_current_turn(self.cleric)
        self.fighter.take_damage(self.fighter.hp() + 1, battle=self.battle)

    def _spare(self):
        return SpellAction.build(self.session, self.cleric)['next'](['spare_the_dying', 0])['next'](self.fighter)

    def test_no_effect_on_a_creature_healed_this_turn(self):
        heal = SpellAction.build(self.session, self.cleric)['next'](['healing_word', 1])['next'](self.fighter)
        self.battle.execute_action(heal)
        self.assertGreater(self.fighter.hp(), 0)
        spare = self._spare()
        self.assertTrue(is_pointless(self.battle, self.cleric, spare))
        self.battle.execute_action(spare)
        self.assertFalse(self.fighter.stable())

    def test_still_stabilizes_a_dying_creature(self):
        spare = self._spare()
        self.assertFalse(is_pointless(self.battle, self.cleric, spare))
        self.battle.execute_action(spare)
        self.assertTrue(self.fighter.stable())

    def test_dropping_again_clears_stable(self):
        self.battle.execute_action(self._spare())
        self.fighter.heal(5)
        self.fighter.take_damage(20, battle=self.battle)
        self.assertTrue(self.fighter.unconscious())
        self.assertFalse(self.fighter.stable())


class PolymorphedPcLosesFeaturesTest(unittest.TestCase):
    def test_no_class_features_in_a_polymorph_form(self):
        session = _session()
        rogue = PlayerCharacter.load(session, 'halfling_rogue.yml')
        rogue.properties.setdefault('class_features', []).append('uncanny_dodge')
        self.assertTrue(rogue.class_feature('uncanny_dodge'))
        polymorph.transform(rogue, 'cat')
        self.assertFalse(rogue.class_feature('uncanny_dodge'))
        polymorph.revert(rogue)
        self.assertTrue(rogue.class_feature('uncanny_dodge'))


class OwnPolymorphTargetTest(unittest.TestCase):
    def test_attacks_on_a_foe_we_polymorphed_are_dominated(self):
        from natural20.utils.pointless_actions import filter_actions
        session = _session()
        battle = Battle(session, Map(session, 'battle_sim_objects'))
        wolf = session.npc('wolf')
        rogue = PlayerCharacter.load(session, 'halfling_rogue.yml')
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        battle.add(wolf, 'b', position=[2, 5])
        battle.add(rogue, 'a', position=[3, 5])
        battle.add(fighter, 'a', position=[1, 5])
        battle.start()
        polymorph.transform(rogue, 'cat', caster=wolf)
        on_cat = _attack(session, wolf, rogue)
        on_fighter = _attack(session, wolf, fighter)
        self.assertEqual(filter_actions(battle, wolf, [on_cat, on_fighter]), [on_fighter])
        self.assertEqual(filter_actions(battle, wolf, [on_cat]), [on_cat])


class CombatLogVisibilityTest(unittest.TestCase):
    def test_potion_use_is_logged_with_hit_points(self):
        from natural20.actions.use_item_action import UseItemAction
        session, lines = _logging_session()
        rogue = PlayerCharacter.load(session, 'halfling_rogue.yml')
        rogue.add_item('healing_potion', 1)
        rogue.take_damage(10, session=session)
        action = UseItemAction.build_self_use(session, rogue, 'healing_potion')
        action.resolve(session)
        UseItemAction.apply(None, action.result[0], session=session)
        line = next(l for l in lines if 'uses' in l)
        self.assertIn('regaining', line)
        self.assertIn('hit points', line)

    def test_shield_shows_until_next_turn_and_is_gone_by_turn_status(self):
        session, lines = _logging_session()
        battle = Battle(session, Map(session, 'battle_sim_objects'))
        mage = PlayerCharacter.load(session, 'high_elf_mage.yml')
        battle.add(mage, 'a', position=[0, 5])
        battle.add(session.npc('goblin'), 'b', position=[5, 5])
        battle.start()
        mage.reset_turn(battle)
        shield = ShieldSpell(session, mage, 'ShieldSpell', session.load_spell('shield'))
        ShieldSpell.apply(battle, {'type': 'shield', 'source': mage, 'target': mage, 'effect': shield})
        self.assertIn('effect: Shield (until the start of its next turn)', condition_summary(battle, mage))
        del lines[:]
        mage.reset_turn(battle)
        status = next(l for l in lines if 'starts the turn at' in l)
        self.assertNotIn('Shield', status)

    def test_legendary_resistance_concentration_line(self):
        session, lines = _logging_session()
        mage = PlayerCharacter.load(session, 'high_elf_mage.yml')
        roll = DieRoll.roll('1d20+4')
        roll.metadata = {'legendary_resistance': True}
        session.event_manager.received_event({'source': mage, 'event': 'concentration_check',
                                              'result': 'success', 'roll': roll, 'dc': 10, 'effect': None})
        self.assertIn('keeps concentration through Legendary Resistance', lines[-1])


class DashAfterShootingTest(unittest.TestCase):
    def test_skirmisher_dash_after_its_action_is_pointless(self):
        from natural20.actions.dash import DashAction
        session = _session()
        battle = Battle(session, Map(session, 'battle_sim_objects'))
        rogue = PlayerCharacter.load(session, 'halfling_rogue.yml')
        rogue.properties.setdefault('class_features', []).append('cunning_action')
        battle.add(rogue, 'a', position=[0, 5])
        battle.add(session.npc('goblin'), 'b', position=[7, 5])
        battle.start()
        rogue.reset_turn(battle)
        dash = DashAction(session, rogue, 'dash_bonus')
        self.assertFalse(is_pointless(battle, rogue, dash))
        battle.consume(rogue, 'action')
        self.assertTrue(is_pointless(battle, rogue, dash))


class RegenerationContextTest(unittest.TestCase):
    def test_state_names_regeneration_and_what_stops_it(self):
        from natural20.utils.jev_decision import _creature_details
        from natural20.utils.monster_traits import note_damage_for_regeneration
        session = _session()
        goblin = session.npc('goblin')
        goblin.properties['regeneration'] = {'hp': 20, 'suppressed_by': ['radiant']}
        text = _creature_details(None, goblin)
        self.assertIn('regenerates 20 hp each turn unless it took radiant damage', text)
        note_damage_for_regeneration(goblin, 'radiant')
        self.assertIn('blocked next turn', _creature_details(None, goblin))
