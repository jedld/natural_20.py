import unittest
from natural20.actions.prone_action import ProneAction
from natural20.session import Session
from natural20.battle import Battle
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.event_manager import EventManager


class TestProneAction(unittest.TestCase):
    def setUp(self):
        self.event_manager = EventManager()
        self.session = Session(root_path='tests/fixtures', event_manager=self.event_manager)
        self.map = Map(self.session, 'battle_sim')
        self.battle = Battle(self.session, self.map)
        self.entity = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle.add(self.entity, 'a', position='spawn_point_1', token='G')
        self.entity.reset_turn(self.battle)

    def test_can_go_prone_in_battle(self):
        self.assertTrue(ProneAction.can(self.entity, self.battle))
        self.entity.do_prone()
        self.assertFalse(ProneAction.can(self.entity, self.battle))

    def test_can_go_prone_outside_battle(self):
        # Going prone is not combat-only: the VTT action bar must offer it
        # while exploring, mirroring StandAction's out-of-battle branch.
        self.assertTrue(ProneAction.can(self.entity, None))
        self.entity.do_prone()
        self.assertFalse(ProneAction.can(self.entity, None))

    def test_apply_outside_battle(self):
        # Out-of-combat commits call apply with battle=None; it must not
        # touch battle.event_manager.
        action = ProneAction(self.session, self.entity, 'prone')
        action.resolve(self.session, self.map)
        ProneAction.apply(None, action.result[0])
        self.assertTrue(self.entity.prone())

    def test_apply_in_battle(self):
        ProneAction.apply(self.battle, {
            "type": "prone",
            "source": self.entity,
        })
        self.assertTrue(self.entity.prone())

    def test_labels(self):
        # Action.label() pluralizes action_type by default, which produced
        # "prones"/"stands" tooltips in the action bar.
        self.assertEqual(ProneAction(self.session, self.entity, 'prone').label(), 'Go Prone')


if __name__ == '__main__':
    unittest.main()
