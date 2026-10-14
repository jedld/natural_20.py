"""Dancing Sword: bonus-action toss, hover-and-strike, return after the last strike."""
import random
import unittest
from unittest import mock

from natural20.actions.dancing_weapon_action import (
    DancingWeaponAction, dancing_state, end_dancing,
)
from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.item_library.dancing_weapon_tile import DancingWeaponTile
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.utils.serialization import Serialization


class DancingWeaponTest(unittest.TestCase):
    def setUp(self):
        random.seed(7)
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.map = Map(self.session, 'tests/fixtures/jev_arena.yml')
        self.battle = Battle(self.session, self.map)
        self.fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.fighter.properties['equipped'] = ['dancing_scimitar', 'leather_armor']
        self.goblin = self.session.npc('goblin', {'name': 'Goblin'})
        self.goblin.attributes['hp'] = self.goblin.properties['max_hp'] = 200
        self.map.add(self.fighter, 0, 0)
        self.map.add(self.goblin, 5, 5)
        self.battle.add(self.fighter, 'a', add_to_initiative=True)
        self.battle.add(self.goblin, 'b', add_to_initiative=True)
        self.battle.start(combat_order=[self.fighter, self.goblin])
        self.fighter.reset_turn(self.battle)

    def dancing_actions(self, mode=None):
        return [a for a in self.fighter.available_actions(self.session, self.battle)
                if isinstance(a, DancingWeaponAction) and (mode is None or a.mode == mode)]

    def strike(self, mode, target=None):
        self.fighter.reset_turn(self.battle)
        action = self.dancing_actions(mode)[0].build_map()['next'](target or self.goblin)
        action.validate(self.map, action.target)
        self.assertEqual(action.errors, [])
        action.resolve(self.session, self.map, {'battle': self.battle})
        self.battle.commit(action)
        return action

    def tile(self):
        return next((o for o in self.map.interactable_objects if isinstance(o, DancingWeaponTile)), None)

    def test_toss_flies_next_to_target_and_attacks_as_bonus_action(self):
        self.assertEqual([a.mode for a in self.dancing_actions()], ['toss'])
        action = self.strike('toss')
        state = dancing_state(self.fighter)['dancing_scimitar']
        self.assertEqual(state['attacks'], 1)
        self.assertLessEqual(max(abs(state['position'][0] - 5), abs(state['position'][1] - 5)), 1)
        self.assertNotIn('dancing_scimitar', self.fighter.properties['equipped'])
        self.assertEqual(self.battle.entity_state_for(self.fighter)['bonus_action'], 0)
        self.assertEqual(self.battle.entity_state_for(self.fighter)['action'], 1)
        attack_items = [r for r in action.result if r.get('type') in ('damage', 'miss')]
        self.assertEqual(len(attack_items), 1)
        self.assertEqual(attack_items[0]['source'], self.fighter)
        self.assertEqual(self.map.position_of(self.tile()), state['position'])

    def test_toss_needs_bonus_action_and_attunement(self):
        self.battle.consume(self.fighter, 'bonus_action')
        self.assertEqual(self.dancing_actions(), [])
        self.fighter.reset_turn(self.battle)
        self.fighter.properties['attuned'] = []
        self.assertEqual(self.dancing_actions(), [])
        self.fighter.properties['attuned'] = ['dancing_scimitar']
        self.assertEqual(len(self.dancing_actions('toss')), 1)

    def test_hovering_weapon_moves_and_attacks_then_returns_after_fourth(self):
        self.strike('toss')
        self.map.move_to(self.goblin, 6, 1, self.battle)
        self.strike('command')
        state = dancing_state(self.fighter)['dancing_scimitar']
        self.assertEqual(state['attacks'], 2)
        self.assertLessEqual(max(abs(state['position'][0] - 6), abs(state['position'][1] - 1)), 1)
        self.assertEqual(self.map.position_of(self.tile()), state['position'])
        self.strike('command')
        self.strike('command')
        self.assertEqual(dancing_state(self.fighter), {})
        self.assertIn('dancing_scimitar', self.fighter.properties['equipped'])
        self.assertIsNone(self.tile())
        self.fighter.reset_turn(self.battle)
        self.assertEqual([a.mode for a in self.dancing_actions()], ['toss'])

    def test_target_out_of_reach_is_rejected(self):
        self.map.move_to(self.goblin, 9, 7, self.battle)
        action = self.dancing_actions('toss')[0].build_map()['next'](self.goblin)
        action.validate(self.map, self.goblin)
        self.assertTrue(action.errors)

    def test_falls_when_wielder_strays_too_far(self):
        self.map.move_to(self.goblin, 5, 1, self.battle)
        self.strike('toss')
        self.assertEqual(dancing_state(self.fighter)['dancing_scimitar']['position'], [4, 0])
        self.map.move_to(self.fighter, 0, 7, self.battle)
        self.fighter.reset_turn(self.battle)
        action = self.dancing_actions('command')[0].build_map()['next'](self.goblin)
        action.resolve(self.session, self.map, {'battle': self.battle})
        self.battle.commit(action)
        self.assertEqual(dancing_state(self.fighter), {})
        self.assertNotIn('dancing_scimitar', self.fighter.properties['equipped'])
        self.assertIsNone(self.tile())

    def test_catch_and_end_dancing_return_it_to_hand(self):
        self.strike('toss')
        end_dancing(self.fighter, self.map)
        self.assertIn('dancing_scimitar', self.fighter.properties['equipped'])
        self.assertIsNone(self.tile())

    def test_action_type_round_trips_mode_and_item(self):
        action = DancingWeaponAction(self.session, self.fighter, 'dancing_weapon:command:dancing_scimitar')
        self.assertEqual((action.mode, action.item_key), ('command', 'dancing_scimitar'))
        built = DancingWeaponAction(self.session, self.fighter, 'dancing_weapon',
                                    {'item': 'dancing_scimitar', 'mode': 'toss'})
        self.assertEqual(built.action_type, 'dancing_weapon:toss:dancing_scimitar')

    def test_npc_wielder_gets_targeted_options(self):
        self.goblin.properties['equipped'] = ['dancing_scimitar']
        self.map.move_to(self.goblin, 3, 3, self.battle)
        self.goblin.reset_turn(self.battle)
        with mock.patch.object(self.battle, 'current_turn', return_value=self.goblin):
            options = [a for a in self.goblin.available_actions(self.session, self.battle, map=self.map)
                       if isinstance(a, DancingWeaponAction)]
        self.assertTrue(options)
        self.assertTrue(all(a.target is self.fighter for a in options))

    def test_save_load_keeps_hovering_weapon(self):
        self.strike('toss')
        position = dancing_state(self.fighter)['dancing_scimitar']['position']
        dump = Serialization().serialize(self.session, self.battle, {'jev_arena': self.map})
        session2, battle2, maps2 = Serialization().deserialize(dump)
        fighter2 = session2.entity_by_uid(self.fighter.entity_uid)
        map2 = maps2['jev_arena']
        self.assertEqual(dancing_state(fighter2)['dancing_scimitar']['attacks'], 1)
        tile = next(o for o in map2.interactable_objects if isinstance(o, DancingWeaponTile))
        self.assertEqual(list(map2.position_of(tile)), list(position))
        self.assertEqual(tile.token_image(), 'items/dancing_scimitar.png')

        fighter2.reset_turn(battle2)
        goblin2 = session2.entity_by_uid(self.goblin.entity_uid)
        action = [a for a in fighter2.available_actions(session2, battle2)
                  if isinstance(a, DancingWeaponAction) and a.mode == 'command'][0]
        action = action.build_map()['next'](goblin2)
        action.resolve(session2, map2, {'battle': battle2})
        battle2.commit(action)
        self.assertEqual(dancing_state(fighter2)['dancing_scimitar']['attacks'], 2)


if __name__ == '__main__':
    unittest.main()
