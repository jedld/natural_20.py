import random
import unittest

from natural20.session import Session
from natural20.event_manager import EventManager
from natural20.player_character import PlayerCharacter
from natural20.map import Map
from natural20.battle import Battle
from natural20.actions.spell_action import SpellAction


class TestMistyStepSpell(unittest.TestCase):
    def make_session(self):
        em = EventManager()
        em.standard_cli()
        return Session(root_path='tests/fixtures', event_manager=em)

    def setUp(self):
        random.seed(8723)
        self.session = self.make_session()
        self.warlock = PlayerCharacter.load(self.session, 'human_warlock.yml')
        # Ensure the warlock knows Misty Step for the test
        self.warlock.properties.setdefault('cantrips', ['eldritch_blast'])
        prepared = self.warlock.properties.setdefault('prepared_spells', [])
        if 'misty_step' not in prepared:
            prepared.append('misty_step')
        if hasattr(self.warlock, 'initialize_warlock'):
            self.warlock.initialize_warlock()

        self.map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.map)
        self.battle.add(self.warlock, 'a', position=[2, 5])
        self.battle.start()
        self.warlock.reset_turn(self.battle)

    def test_misty_step_moves_caster_to_target_square(self):
        builder = SpellAction.build(self.session, self.warlock)
        self.assertIsNotNone(builder)

        # Choose a valid empty square within 30 feet (6 tiles) in front of the caster
        cur_x, cur_y = self.map.position_of(self.warlock)
        target = [cur_x + 3, cur_y]
        # Ensure selected square is placeable; pick an alternate if occupied
        if not self.map.placeable(self.warlock, target[0], target[1], self.battle):
            target = [cur_x + 2, cur_y + 1]
        self.assertTrue(self.map.placeable(self.warlock, target[0], target[1], self.battle))

        action = builder['next'](['misty_step', 2])['next'](target)
        action.resolve(self.session, self.map, {'battle': self.battle})

        misty_events = [item for item in action.result if item.get('type') == 'misty_step']
        self.assertEqual(len(misty_events), 1)
        self.assertEqual(misty_events[0]['target'], [int(target[0]), int(target[1])])

        start_position = list(self.map.position_of(self.warlock))
        self.assertNotEqual(start_position, target)

        self.battle.commit(action)

        # Verify the caster is now at the teleported square
        new_position = list(self.map.position_of(self.warlock))
        self.assertEqual(new_position, [int(target[0]), int(target[1])])

        # Ensure a misty_step event was logged for downstream consumers
        events = list(self.session.event_manager.event_buffer)
        self.assertTrue(any(evt.get('event') == 'misty_step' for evt in events))


if __name__ == '__main__':
    unittest.main()
