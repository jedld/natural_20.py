"""Tests for the Silvery Barbs reaction spell."""

import random
import unittest

import numpy as np

from natural20.session import Session
from natural20.event_manager import EventManager
from natural20.player_character import PlayerCharacter
from natural20.battle import Battle
from natural20.map import Map
from natural20.actions.spell_action import SpellAction
from natural20.actions.attack_action import AttackAction
from natural20.controller import Controller
from natural20.die_roll import DieRoll
from natural20.spell.silvery_barbs_spell import (
    SilveryBarbsSpell,
    SilveryBarbsAdvantageEffect,
)


class _ReactionController(Controller):
    """Minimal controller — accepts the first reaction option."""

    def __init__(self, session, accept=True):
        self.state = {}
        self.session = session
        self.battle_data = {}
        self.user = None
        self.accept = accept

    def select_reaction(self, entity, battle, map, valid_actions, event):
        if not self.accept or not valid_actions:
            return None
        return valid_actions[0]


class TestSilveryBarbs(unittest.TestCase):
    def setUp(self):
        random.seed(9001)
        np.random.seed(9001)
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.battle_map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.battle_map)
        self.wizard = PlayerCharacter.load(self.session, 'silvery_barbs_wizard.yml')
        self.battle.add(self.wizard, 'a', position=[0, 5])
        self.wizard.reset_turn(self.battle)
        self.battle.set_controller_for(self.wizard, _ReactionController(self.session))

    # -- YAML / loader -------------------------------------------------------

    def test_spell_loads(self):
        spell = self.session.load_spell('silvery_barbs')
        self.assertEqual(spell['casting_time'], '1:reaction')
        self.assertEqual(spell['level'], 1)
        self.assertEqual(spell['range'], 60)
        self.assertTrue(spell.get('triggers_on_attack_success'))
        self.assertIn('Wizard', spell['spell_list_classes'])

    def test_wizard_has_silvery_barbs_prepared(self):
        self.assertIn('silvery_barbs', self.wizard.prepared_spells())

    # -- _pick_ally helper ---------------------------------------------------

    def test_pick_ally_falls_back_to_caster_when_alone(self):
        # Add an attacker but no other ally on the wizard's side.
        attacker = self.session.npc('skeleton')
        self.battle.add(attacker, 'b', position=[0, 6])
        attacker.reset_turn(self.battle)
        bmap = self.battle.map_for(self.wizard)
        spell = self.session.load_spell('silvery_barbs')
        ally = SilveryBarbsSpell._pick_ally(self.battle, self.wizard, attacker, bmap, spell)
        self.assertIs(ally, self.wizard)

    # -- Reaction trigger ----------------------------------------------------

    def _setup_attack_against_wizard(self):
        self.battle.start()
        self.wizard.reset_turn(self.battle)
        attacker = self.session.npc('skeleton')
        self.battle.add(attacker, 'b', position=[0, 6])
        attacker.reset_turn(self.battle)
        return attacker

    def test_reroll_replaces_higher_roll_with_lower(self):
        attacker = self._setup_attack_against_wizard()
        # Force the original to_hit to a guaranteed hit, then patch DieRoll.roll
        # so the reroll comes back lower.
        DieRoll.fudge(18)
        action = AttackAction(self.session, attacker, 'attack')
        action.target = self.wizard
        action.npc_action = {
            'name': 'Short Sword',
            'type': 'melee_attack',
            'range': 5,
            'targets': 1,
            'attack': 4,
            'damage': 5,
            'damage_die': '1d6+2',
            'damage_type': 'piercing',
        }
        # Patch DieRoll.roll so the *next* roll (the silvery barbs reroll) is a 1.
        original_roll = DieRoll.roll
        seen = {'count': 0}

        def patched_roll(roll_str, **kwargs):
            res = original_roll(roll_str, **kwargs)
            if 'silvery_barbs' in str(kwargs.get('description', '')):
                # Force the reroll d20 component down to 1.
                if res.rolls:
                    res.rolls = [1]
            return res

        DieRoll.roll = staticmethod(patched_roll)
        try:
            self.battle.execute_action(action)
        finally:
            DieRoll.roll = original_roll
            DieRoll.unfudge()

        # Reaction should have been consumed.
        self.assertFalse(self.wizard.has_reaction(self.battle))
        # Action result should contain the reroll event.
        rerolls = [r for r in action.result if r.get('type') == 'silvery_barbs_reroll']
        self.assertEqual(len(rerolls), 1)
        self.assertTrue(rerolls[0]['replaced'])
        # And the attack roll on the action object should now be the lower one.
        self.assertLess(action.attack_roll.result(), 18 + 4)

    def test_reroll_keeps_original_when_new_is_higher(self):
        attacker = self._setup_attack_against_wizard()
        DieRoll.fudge(15)  # original total = 15+4 = 19 (definite hit)
        action = AttackAction(self.session, attacker, 'attack')
        action.target = self.wizard
        action.npc_action = {
            'name': 'Short Sword',
            'type': 'melee_attack',
            'range': 5,
            'targets': 1,
            'attack': 4,
            'damage': 5,
            'damage_die': '1d6+2',
            'damage_type': 'piercing',
        }

        original_roll = DieRoll.roll

        def patched_roll(roll_str, **kwargs):
            res = original_roll(roll_str, **kwargs)
            if 'silvery_barbs' in str(kwargs.get('description', '')):
                if res.rolls:
                    res.rolls = [20]
            return res

        original_total = 15 + 4
        DieRoll.roll = staticmethod(patched_roll)
        try:
            self.battle.execute_action(action)
        finally:
            DieRoll.roll = original_roll
            DieRoll.unfudge()

        rerolls = [r for r in action.result if r.get('type') == 'silvery_barbs_reroll']
        self.assertEqual(len(rerolls), 1)
        self.assertFalse(rerolls[0]['replaced'])
        # Original attack roll preserved
        self.assertEqual(action.attack_roll.result(), original_total)

    def test_no_reaction_when_attack_misses(self):
        attacker = self._setup_attack_against_wizard()
        # Force a low roll that won't beat the wizard's AC.
        DieRoll.fudge(1)
        action = AttackAction(self.session, attacker, 'attack')
        action.target = self.wizard
        action.npc_action = {
            'name': 'Short Sword',
            'type': 'melee_attack',
            'range': 5,
            'targets': 1,
            'attack': 4,
            'damage': 5,
            'damage_die': '1d6+2',
            'damage_type': 'piercing',
        }
        try:
            self.battle.execute_action(action)
        finally:
            DieRoll.unfudge()
        self.assertTrue(self.wizard.has_reaction(self.battle))
        rerolls = [r for r in action.result if r.get('type') == 'silvery_barbs_reroll']
        self.assertEqual(len(rerolls), 0)

    def test_no_reaction_when_no_reaction_available(self):
        attacker = self._setup_attack_against_wizard()
        # Drain the wizard's reaction.
        self.battle.consume(self.wizard, 'reaction')
        self.assertFalse(self.wizard.has_reaction(self.battle))
        DieRoll.fudge(18)
        action = AttackAction(self.session, attacker, 'attack')
        action.target = self.wizard
        action.npc_action = {
            'name': 'Short Sword',
            'type': 'melee_attack',
            'range': 5,
            'targets': 1,
            'attack': 4,
            'damage': 5,
            'damage_die': '1d6+2',
            'damage_type': 'piercing',
        }
        try:
            self.battle.execute_action(action)
        finally:
            DieRoll.unfudge()
        rerolls = [r for r in action.result if r.get('type') == 'silvery_barbs_reroll']
        self.assertEqual(len(rerolls), 0)

    def test_advantage_effect_dismisses_after_one_attack(self):
        # Directly register the buff and ensure attack_resolved drops it.
        ally = self.wizard
        buff = SilveryBarbsAdvantageEffect(self.wizard, ally)
        ally.register_effect(
            'attack_advantage_modifier',
            SilveryBarbsAdvantageEffect,
            effect=buff,
            source=self.wizard,
            duration=60,
        )
        ally.register_event_hook(
            'attack_resolved',
            SilveryBarbsAdvantageEffect,
            effect=buff,
            source=self.wizard,
        )
        self.assertTrue(ally.has_effect('attack_advantage_modifier'))
        adv, dis = ally.eval_effect(
            'attack_advantage_modifier', {'target': ally}
        )
        self.assertIn('silvery_barbs_advantage', adv)

        # Trigger attack_resolved manually — yields a dismiss_effect event,
        # which our test then applies via dismiss_effect().
        results = ally.resolve_trigger('attack_resolved', {})
        self.assertTrue(any(r.get('type') == 'dismiss_effect' for r in results))
        for r in results:
            if r.get('type') == 'dismiss_effect':
                ally.dismiss_effect(r['effect'])
        self.assertFalse(ally.has_effect('attack_advantage_modifier'))
