"""Counterspell as a real reaction: offered when a hostile creature casts."""

import random
import unittest

import numpy as np

from natural20.action import AsyncReactionHandler
from natural20.actions.spell_action import SpellAction
from natural20.battle import Battle
from natural20.controller import Controller
from natural20.event_manager import EventManager
from natural20.generic_controller import GenericController
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.utils.counterspell import choose_counterspell


class _ReactionController(Controller):
    """Records reaction prompts; picks the lowest slot when ``accept``."""

    def __init__(self, session, accept=True):
        self.state = {}
        self.session = session
        self.battle_data = {}
        self.user = None
        self.accept = accept
        self.prompts = []

    def select_reaction(self, entity, battle, map, valid_actions, event):
        self.prompts.append((event, list(valid_actions)))
        if not self.accept or not valid_actions:
            return None
        return valid_actions[0]


class _AsyncController(_ReactionController):
    """Mimics WebController: hands back a generator for a human to answer."""

    def select_reaction(self, entity, battle, map, valid_actions, event):
        self.prompts.append((event, list(valid_actions)))
        yield battle, entity, valid_actions


class TestCounterspellReaction(unittest.TestCase):
    def setUp(self):
        random.seed(4242)
        np.random.seed(4242)
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.battle_map = Map(self.session, 'large_map')
        self.battle = Battle(self.session, self.battle_map)
        self.wizard = PlayerCharacter.load(self.session, 'counterspell_wizard.yml')
        self.mage = self.session.npc('test_counter_mage', {'name': 'Hostile Mage'})
        self.battle.add(self.wizard, 'a', position=[2, 6])
        self.battle.add(self.mage, 'b', position=[6, 6])
        self.battle.start(combat_order=[self.mage, self.wizard])
        self.wizard.reset_turn(self.battle)
        self.mage.reset_turn(self.battle)
        self.battle.set_current_turn(self.mage)
        self.wizard_controller = _ReactionController(self.session)
        self.battle.set_controller_for(self.wizard, self.wizard_controller)
        self.battle.set_controller_for(self.mage, GenericController(self.session))

    def _cast(self, caster, spell, target, at_level=0):
        return SpellAction.build(self.session, caster)['next']([spell, at_level])['next'](target)

    def _mage_casts_magic_missile(self, at_level=0):
        action = self._cast(self.mage, 'magic_missile', [self.wizard], at_level)
        action.resolve(self.session, self.battle_map, {'battle': self.battle})
        return action

    def test_counterspell_auto_succeeds_against_lower_level_spell(self):
        hp = self.wizard.hp()
        action = self._mage_casts_magic_missile()
        types = [item['type'] for item in action.result]
        self.assertIn('spell_countered', types)
        self.assertNotIn('spell_damage', types)
        check = next(item for item in action.result if item['type'] == 'abjuration_check')
        self.assertTrue(check['success'])
        self.assertIsNone(check['roll'])

        self.battle.commit(action)
        self.assertEqual(self.wizard.hp(), hp)
        self.assertEqual(self.wizard.spell_slots_count(3, 'wizard'), 1)
        self.assertFalse(self.wizard.has_reaction(self.battle))
        # 2014: the countered caster's slot is still spent.
        self.assertEqual(self.mage.spell_slots_count(1), 3)

    def test_prompt_lists_every_usable_slot_level(self):
        self._mage_casts_magic_missile()
        event, actions = self.wizard_controller.prompts[0]
        self.assertEqual(event['type'], 'counterspell')
        self.assertIs(event['caster'], self.mage)
        self.assertEqual(event['target_spell_level'], 1)
        self.assertEqual([a.at_level for a in actions], [3])

    def test_declining_lets_the_spell_resolve(self):
        self.wizard_controller.accept = False
        action = self._mage_casts_magic_missile()
        types = [item['type'] for item in action.result]
        self.assertNotIn('spell_countered', types)
        self.assertIn('spell_damage', types)
        self.assertEqual(self.wizard.spell_slots_count(3, 'wizard'), 2)
        self.assertTrue(self.wizard.has_reaction(self.battle))

    def test_higher_level_spell_requires_ability_check(self):
        action = self._mage_casts_magic_missile(at_level=4)
        check = next(item for item in action.result if item['type'] == 'abjuration_check')
        self.assertIsNotNone(check['roll'])
        self.assertEqual(check['dc'], 14)
        countered = any(item['type'] == 'spell_countered' for item in action.result)
        self.assertEqual(countered, check['success'])
        self.battle.commit(action)

    def test_no_prompt_out_of_range(self):
        self.battle_map.move_to(self.mage, 20, 6, self.battle)
        self._mage_casts_magic_missile()
        self.assertEqual(self.wizard_controller.prompts, [])

    def test_no_prompt_for_allied_caster(self):
        ally = PlayerCharacter.load(self.session, 'counterspell_wizard.yml')
        self.battle.add(ally, 'a', position=[4, 6])
        ally.reset_turn(self.battle)
        self.battle.set_controller_for(ally, _ReactionController(self.session))
        action = self._cast(ally, 'magic_missile', [self.mage])
        action.resolve(self.session, self.battle_map, {'battle': self.battle})
        self.assertEqual(self.wizard_controller.prompts, [])

    def test_no_prompt_without_reaction(self):
        self.battle.consume(self.wizard, 'reaction')
        self._mage_casts_magic_missile()
        self.assertEqual(self.wizard_controller.prompts, [])

    def test_async_player_prompt_then_resume(self):
        controller = _AsyncController(self.session)
        self.battle.set_controller_for(self.wizard, controller)
        action = self._cast(self.mage, 'magic_missile', [self.wizard])
        with self.assertRaises(AsyncReactionHandler) as ctx:
            action.resolve(self.session, self.battle_map, {'battle': self.battle})
        handler = ctx.exception
        self.assertEqual(handler.reaction_type, 'counterspell')
        for _, _, valid_actions in handler.resolve():
            handler.send(valid_actions[0])

        action.resolve(self.session, self.battle_map, {'battle': self.battle})
        self.assertIn('spell_countered', [item['type'] for item in action.result])
        self.battle.commit(action)
        self.assertEqual(self.wizard.spell_slots_count(3, 'wizard'), 1)

    def test_resolve_again_does_not_double_charge_counterspeller(self):
        action = self._mage_casts_magic_missile()
        action.resolve(self.session, self.battle_map, {'battle': self.battle})
        self.assertEqual(self.wizard.spell_slots_count(3, 'wizard'), 1)
        self.assertEqual(len(self.wizard_controller.prompts), 1)

    def test_npc_counterspells_player_spell(self):
        self.battle.set_current_turn(self.wizard)
        hp = self.mage.hp()
        action = self._cast(self.wizard, 'magic_missile', [self.mage])
        action.resolve(self.session, self.battle_map, {'battle': self.battle})
        self.assertIn('spell_countered', [item['type'] for item in action.result])
        self.battle.commit(action)
        self.assertEqual(self.mage.hp(), hp)
        self.assertEqual(self.mage.spell_slots_count(3), 2)

    def test_combat_log_messages_for_auto_success(self):
        logged = []
        self.session.event_manager.standard_cli()
        self.session.event_manager.output_logger.log = lambda msg, **_: logged.append(msg)
        action = self._mage_casts_magic_missile()
        self.battle.commit(action)
        self.assertTrue(any('casts Counterspell' in msg and 'succeeds' in msg for msg in logged))
        self.assertTrue(any('counters' in msg and 'Magic Missile' in msg for msg in logged))

    def test_combat_log_message_for_ability_check(self):
        logged = []
        self.session.event_manager.standard_cli()
        self.session.event_manager.output_logger.log = lambda msg, **_: logged.append(msg)
        action = self._mage_casts_magic_missile(at_level=4)
        self.battle.commit(action)
        line = next(msg for msg in logged if 'casts Counterspell' in msg)
        self.assertTrue(line.startswith('Ilsabet casts Counterspell at Hostile Mage'))
        self.assertIn('vs DC 14', line)

    def test_ai_ignores_cantrips_and_upcasts_to_auto_succeed(self):
        actions = [type('A', (), {'at_level': lvl})() for lvl in (3, 4, 5)]
        self.assertIsNone(choose_counterspell(self.mage, self.battle, actions, {'target_spell_level': 0}))
        self.assertEqual(choose_counterspell(self.mage, self.battle, actions, {'target_spell_level': 2}).at_level, 3)
        self.assertEqual(choose_counterspell(self.mage, self.battle, actions, {'target_spell_level': 4}).at_level, 4)
        self.assertEqual(choose_counterspell(self.mage, self.battle, actions, {'target_spell_level': 7}).at_level, 3)


if __name__ == '__main__':
    unittest.main()
