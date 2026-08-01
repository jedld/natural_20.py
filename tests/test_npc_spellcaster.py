import random
import unittest

from natural20.actions.spell_action import SpellAction
from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.generic_controller import GenericController
from natural20.llm_controller import LlmMcpController
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session


class TestNpcSpellcaster(unittest.TestCase):
    def setUp(self):
        random.seed(7000)
        event_manager = EventManager()
        event_manager.standard_cli()
        self.session = Session(root_path='tests/fixtures', event_manager=event_manager)
        self.battle_map = Map(self.session, 'battle_sim')
        self.session.register_map('test_map', self.battle_map)

    def _start_battle(self):
        battle = Battle(self.session, self.battle_map)
        wizard = self.session.npc('test_wizard', {'name': 'Noke'})
        fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle_map.add(wizard, 1, 1)
        self.battle_map.add(fighter, 1, 2)
        battle.add(wizard, 'b', add_to_initiative=True)
        battle.add(fighter, 'a', add_to_initiative=True)
        battle.start(combat_order=[wizard, fighter])
        wizard.reset_turn(battle)
        fighter.reset_turn(battle)
        battle.set_current_turn(wizard)
        return battle, wizard, fighter

    def test_npc_spellcaster_exposes_spell_action(self):
        battle, wizard, _fighter = self._start_battle()

        actions = wizard.available_actions(self.session, battle, auto_target=False)
        spell_actions = [action for action in actions if isinstance(action, SpellAction)]

        self.assertTrue(wizard.has_spells())
        self.assertEqual(spell_actions, [SpellAction(self.session, wizard, 'spell')][:1])
        self.assertEqual(len(spell_actions), 1)
        self.assertEqual(spell_actions[0].action_type, 'spell')

    def test_npc_spellcaster_autobuilds_targeted_spells(self):
        battle, wizard, fighter = self._start_battle()

        actions = wizard.available_actions(self.session, battle, auto_target=True)
        spell_actions = [action for action in actions if isinstance(action, SpellAction)]

        self.assertGreater(len(spell_actions), 0)
        self.assertTrue(any(getattr(action, 'target', None) == fighter for action in spell_actions))

    def test_npc_max_spell_slots_snapshot(self):
        wizard = self.session.npc('test_wizard')

        self.assertEqual(wizard.max_spell_slots(3), 2)
        self.assertEqual(wizard.max_spell_slots(4), 1)
        self.assertEqual(wizard.spell_slots_count(3), 2)

        wizard.consume_spell_slot(3)

        self.assertEqual(wizard.spell_slots_count(3), 1)
        self.assertEqual(wizard.max_spell_slots(3), 2)

    def test_npc_spell_attack_modifier_uses_proficiency_and_int(self):
        wizard = self.session.npc('test_wizard')

        self.assertEqual(wizard.spell_attack_modifier('wizard'), 5)

    def test_generic_controller_includes_npc_spells_in_moves(self):
        battle, wizard, fighter = self._start_battle()
        controller = GenericController(self.session)

        available_moves = controller._compute_available_moves(wizard, battle)
        spell_actions = [action for action in available_moves if isinstance(action, SpellAction)]

        self.assertGreater(len(spell_actions), 0)
        self.assertTrue(any(getattr(action, 'target', None) == fighter for action in spell_actions))

    def test_generic_controller_can_select_npc_spell(self):
        battle, wizard, fighter = self._start_battle()
        controller = GenericController(self.session)
        spell_actions = [
            action for action in wizard.available_actions(self.session, battle, auto_target=True)
            if isinstance(action, SpellAction)
        ]

        choice = controller.select_action(battle, wizard, spell_actions)

        self.assertIsInstance(choice, SpellAction)
        self.assertIn(choice.target, (wizard, fighter))

    def test_llm_controller_spell_slot_summary_for_npc(self):
        wizard = self.session.npc('test_wizard')
        controller = LlmMcpController(self.session)

        summary = controller._spell_slots_summary(wizard)

        self.assertIn('L3 2/2', summary)
        self.assertIn('L4 1/1', summary)

    def test_llm_controller_receives_npc_spell_actions(self):
        battle, wizard, _fighter = self._start_battle()
        controller = LlmMcpController(self.session, llm_provider='mock')

        actions = wizard.available_actions(self.session, battle, auto_target=True)
        spell_actions = [action for action in actions if isinstance(action, SpellAction)]

        self.assertGreater(len(spell_actions), 0)
        choice = controller.select_action(battle, wizard, actions)
        self.assertIn(choice, actions)


if __name__ == '__main__':
    unittest.main()
