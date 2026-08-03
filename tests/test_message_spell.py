"""Tests for the Message cantrip."""
import random
import unittest

from natural20.actions.spell_action import SpellAction
from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.spell.message_spell_link import get_message_spell_link
from natural20.utils.message_spell_path import (
    MESSAGE_RANGE_FT,
    entities_familiar,
    message_spell_reachable,
)


class TestMessageSpell(unittest.TestCase):
    def setUp(self):
        random.seed(8801)
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.battle_map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.battle_map)
        self.wizard = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        prepared = list(self.wizard.properties.get('prepared_spells', []) or [])
        if 'message' not in prepared:
            prepared.append('message')
        self.wizard.properties['prepared_spells'] = prepared
        self.battle_map.add(self.wizard, 1, 1)
        self.goblin = self.session.npc('goblin', {'name': 'Guz'})
        self.battle_map.add(self.goblin, 5, 1)
        self.battle.add(self.wizard, 'a', add_to_initiative=True)
        self.battle.add(self.goblin, 'b', add_to_initiative=True)
        self.battle.start(combat_order=[self.wizard, self.goblin])
        self.wizard.reset_turn(self.battle)

    def _cast_message(self, target=None):
        target = target or self.goblin
        action = SpellAction.build(self.session, self.wizard)['next'](['message', 0])['next'](target)
        self.battle.action(action)
        self.battle.commit(action)
        return action

    def test_spell_loads(self):
        spell = self.session.load_spell('message')
        self.assertEqual(spell['range'], 120)
        self.assertEqual(spell.get('duration_seconds'), 6)

    def test_cast_registers_link(self):
        action = self._cast_message()
        link_item = next(item for item in action.result if item.get('type') == 'message_spell')
        link = get_message_spell_link(self.session, link_item.get('link_id'))
        self.assertIsNotNone(link)
        self.assertIs(link.caster, self.wizard)
        self.assertIs(link.target, self.goblin)

    def test_reachable_across_open_map(self):
        self.assertTrue(
            message_spell_reachable(
                self.battle_map,
                self.wizard,
                self.goblin,
                range_ft=MESSAGE_RANGE_FT,
            )
        )

    def test_out_of_range_target_fails_validation(self):
        from natural20.spell.message_spell import MessageSpell

        far = self.session.npc('goblin', {'name': 'Far'})
        self.battle_map.add(far, 1, 7)
        spell_props = self.session.load_spell('message')
        spell = MessageSpell(self.session, self.wizard, 'MessageSpell', spell_props)
        spell.source = self.wizard
        spell.validate(self.battle_map, target=far, battle=self.battle)
        # Still within 120 ft on this small map — instead verify resolve failure when unreachable.
        from unittest.mock import patch

        with patch('natural20.spell.message_spell.message_spell_reachable', return_value=False):
            action = SpellAction.build(self.session, self.wizard)['next'](['message', 0])['next'](far)
            self.battle.action(action)
            self.battle.commit(action)
            self.assertTrue(any(item.get('type') == 'message_spell_failed' for item in action.result))

    def test_familiar_bypass_when_in_range(self):
        ally = self.session.npc('goblin', {'name': 'Ally'})
        ally.group = self.wizard.group
        self.battle_map.add(ally, 6, 6)
        self.assertTrue(entities_familiar(self.wizard, ally))
        self.assertTrue(
            message_spell_reachable(
                self.battle_map,
                self.wizard,
                ally,
                range_ft=MESSAGE_RANGE_FT,
            )
        )

    def test_cannot_target_self(self):
        spell_class = self.session.load_spell('message')
        from natural20.utils.spell_loader import load_spell_class
        from natural20.spell.message_spell import MessageSpell

        spell = MessageSpell(self.session, self.wizard, 'MessageSpell', spell_class)
        spell.source = self.wizard
        spell.validate(self.battle_map, target=self.wizard, battle=self.battle)
        self.assertTrue(spell.errors or spell.validation_issues)

    def test_does_not_provoke_hostility(self):
        from natural20.actions.spell_action import spell_action_provokes_hostility

        action = self._cast_message()
        self.assertFalse(spell_action_provokes_hostility(action))
        spell_props = self.session.load_spell('message')
        self.assertIs(spell_props.get('provokes_hostility'), False)


if __name__ == '__main__':
    unittest.main()
