import unittest
from natural20.actions.stand_action import StandAction
from natural20.session import Session
from natural20.battle import Battle
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.event_manager import EventManager

class TestStandAction(unittest.TestCase):
    def setUp(self):
        self.event_manager = EventManager()
        self.session = Session(root_path='tests/fixtures', event_manager=self.event_manager)
        self.map = Map(self.session, 'battle_sim')
        self.battle = Battle(self.session, self.map)
        self.entity = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle.add(self.entity, 'a', position='spawn_point_1', token='G')
        self.entity.reset_turn(self.battle)

    def test_can_stand(self):
        # Entity should not be able to stand if not prone
        self.assertFalse(StandAction.can(self.entity, self.battle))

        # Make entity prone
        self.entity.do_prone()
        self.assertTrue(self.entity.prone())

        # Entity should be able to stand if prone and has enough movement
        self.assertTrue(StandAction.can(self.entity, self.battle))

        # Entity should not be able to stand if movement is consumed
        self.battle.consume(self.entity, "movement", self.entity.speed())
        self.assertFalse(StandAction.can(self.entity, self.battle))

    def test_required_movement(self):
        # Required movement should be half of entity's speed
        self.assertEqual(StandAction.required_movement(self.entity), self.entity.speed() // 2)

    def test_outside_of_battle(self):
        self.assertFalse(StandAction.can(self.entity, None))
        self.entity.do_prone()
        self.assertTrue(self.entity.prone())
        self.assertTrue(StandAction.can(self.entity, None))
        stand_action = StandAction(self.session, self.entity,  'stand')
        stand_action.resolve(self.session, self.map)
        stand_action.apply(None, stand_action.result[0])
        self.assertFalse(self.entity.prone())

    def test_apply(self):
        # Make entity prone
        self.entity.do_prone()
        self.assertTrue(self.entity.prone())

        # Apply stand action
        StandAction.apply(self.battle, {
            "type": "stand",
            "source": self.entity
        })

        # Entity should no longer be prone
        self.assertFalse(self.entity.prone())

        # Movement should be consumed
        self.assertEqual(self.entity.available_movement(self.battle), 
                        self.entity.speed() - (self.entity.speed() // 2))

if __name__ == '__main__':
    unittest.main()
