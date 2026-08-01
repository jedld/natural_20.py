import random
import unittest

from natural20.actions.find_familiar_action import FindFamiliarAction
from natural20.actions.spell_action import SpellAction
from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.spell.find_familiar_spell import FindFamiliarEffect
from natural20.utils.action_builder import autobuild


class TestFindFamiliarAction(unittest.TestCase):
    def setUp(self):
        random.seed(7000)
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.entity = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.battle_map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.battle_map)
        self.battle.add(self.entity, 'a', position=[0, 5])
        self.battle.start()
        self.entity.reset_turn(self.battle)

    def _append_bardic_inspiration_effect(self, entity):
        entity.casted_effects.append({
            'effect': 'bardic_inspiration',
            'source': entity,
            'die': '1d6',
            'duration': 100,
        })

    def test_can_tolerates_string_casted_effects(self):
        """Regression: mixed casted_effects must not crash action availability."""
        self._append_bardic_inspiration_effect(self.entity)
        self.assertFalse(FindFamiliarAction.can(self.entity, self.battle))

    def test_can_with_familiar_and_string_casted_effects(self):
        action = autobuild(
            self.session,
            SpellAction,
            self.entity,
            None,
            map=self.battle_map,
            match=['find_familiar', 'bat', [0, 6]],
        )[0]
        self.battle.execute_action(action)

        self._append_bardic_inspiration_effect(self.entity)
        self.assertTrue(FindFamiliarAction.can(self.entity, self.battle))

    def test_familiar_effect_entry_ignores_string_effects(self):
        self._append_bardic_inspiration_effect(self.entity)
        self.assertIsNone(FindFamiliarAction._familiar_effect_entry(self.entity))

        familiar = self.session.npc('bat')
        self.entity.casted_effects.append({
            'target': [0, 6],
            'effect': FindFamiliarEffect(self.entity, familiar, self.battle_map),
        })
        entry = FindFamiliarAction._familiar_effect_entry(self.entity)
        self.assertIsNotNone(entry)
        self.assertIsInstance(entry['effect'], FindFamiliarEffect)


if __name__ == '__main__':
    unittest.main()
