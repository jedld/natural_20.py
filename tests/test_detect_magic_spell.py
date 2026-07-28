"""Tests for Detect Magic spell."""

from __future__ import annotations

import unittest

from natural20.actions.spell_action import SpellAction
from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.utils.magical_aura import viewer_has_detect_magic


class TestDetectMagicSpell(unittest.TestCase):
    def make_session(self):
        event_manager = EventManager()
        event_manager.standard_cli()
        return Session(root_path='tests/fixtures', event_manager=event_manager)

    def setUp(self):
        self.session = self.make_session()
        self.mage = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        prepared = list(self.mage.properties.get('prepared_spells') or [])
        if 'detect_magic' not in prepared:
            prepared.append('detect_magic')
            self.mage.properties['prepared_spells'] = prepared
        self.map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.map)
        self.battle.add(self.mage, 'a', position=[2, 2])
        self.battle.start()
        self.mage.reset_turn(self.battle)

    def cast_detect_magic(self):
        action = SpellAction.build(self.session, self.mage)['next'](['detect_magic', 0])['next'](self.mage)
        resolved = action.resolve(self.session, self.map, {'battle': self.battle})
        for item in resolved.result:
            SpellAction.apply(self.battle, item, self.session)
        return resolved

    def test_detect_magic_registers_concentration_effect(self):
        self.cast_detect_magic()
        self.assertTrue(self.mage.has_effect('detect_magic'))
        self.assertTrue(viewer_has_detect_magic(self.mage))
        self.assertEqual(self.mage.current_concentration().id, 'detect_magic')

    def test_detect_magic_self_targets_caster(self):
        resolved = self.cast_detect_magic()
        item = resolved.result[0]
        self.assertEqual(item['type'], 'detect_magic')
        self.assertIs(item['target'], self.mage)


if __name__ == '__main__':
    unittest.main()
