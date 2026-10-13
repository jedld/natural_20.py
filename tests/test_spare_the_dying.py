import random
import unittest

from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.spell.spare_the_dying_spell import SpareTheDyingSpell


class SpareTheDyingTestCase(unittest.TestCase):
    def setUp(self):
        random.seed(7000)
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.battle_map = Map(self.session, 'battle_sim')
        self.battle = Battle(self.session, self.battle_map)
        self.caster = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.dying = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle.add(self.caster, 'a', position=[2, 2])
        self.battle.add(self.dying, 'a', position=[3, 2])
        self.battle.start(combat_order=[self.caster, self.dying])
        self.caster.reset_turn(self.battle)
        self.dying.attributes['hp'] = 0
        self.dying.make_unconscious()

    def _result(self):
        spell = SpareTheDyingSpell(self.session, self.caster, 'spare_the_dying',
                                   self.session.load_spell('spare_the_dying'))
        action = type('A', (), {'target': self.dying})()
        return spell.resolve(self.caster, self.battle, action, self.battle_map)

    def test_apply_stabilizes_without_a_roll(self):
        events = []
        self.session.event_manager.register_event_listener('first_aid', events.append)
        actions_before = self.caster.total_actions(self.battle)

        for item in self._result():
            SpareTheDyingSpell.apply(self.battle, item, self.session)

        self.assertTrue(self.dying.stable())
        self.assertEqual(len(events), 1)
        self.assertIsNone(events[0]['roll'])
        self.assertEqual(events[0]['spell'], 'Spare the Dying')
        # The action is spent by SpellAction at resolve, not again here.
        self.assertEqual(self.caster.total_actions(self.battle), actions_before)

    def test_apply_outside_battle(self):
        for item in self._result():
            SpareTheDyingSpell.apply(None, item, self.session)
        self.assertTrue(self.dying.stable())


if __name__ == '__main__':
    unittest.main()
