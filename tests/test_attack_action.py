import unittest
from natural20.utils.utils import Session
from natural20.battle import Battle
from natural20.player_character import PlayerCharacter
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.actions.attack_action import AttackAction
from natural20.map_renderer import MapRenderer
from pdb import set_trace

class TestAttackAction(unittest.TestCase):
    def make_session(self):
        event_manager = EventManager()
        event_manager.standard_cli()
        return Session(root_path='tests/fixtures', event_manager=event_manager)

    def test_attack_action(self):
        session = self.make_session()
        battle_map = Map(session, 'battle_sim')
        battle = Battle(session, battle_map)
        character = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        npc = session.npc('ogre')
        npc2 = session.npc('goblin')

        battle.add(character, 'a', position='spawn_point_1', token='G')
        battle.add(npc, 'b', position='spawn_point_2', token='g')

        character.reset_turn(battle)
        npc.reset_turn(battle)

        battle_map.move_to(character, 0, 0, battle)
        battle_map.move_to(npc, 1, 0, battle)
        battle.add(character, 'a', token='G')
        battle.add(npc, 'b', token='g')

        character.reset_turn(battle)
        npc.reset_turn(battle)

        ptr = AttackAction.build(session, character)

        while True:
            param = [None for _ in ptr['param']]
            if ptr['param'][0]['type'] == 'select_target':
                param[0] = npc
            elif ptr['param'][0]['type'] == 'select_weapon':
                param[0] = 'vicious_rapier'
            ptr = ptr['next'](*param)

            if ptr['param'] is None:
               ptr = ptr['next']()
               break

        self.assertEqual(ptr.target, npc)
        self.assertEqual(ptr.source, character)
        self.assertEqual(ptr.using, 'vicious_rapier')

    def test_two_weapon_fighting(self):
        session = self.make_session()
        battle_map = Map(session, 'battle_sim')
        battle = Battle(session, battle_map)
        character = PlayerCharacter.load(session, 'elf_rogue.yml', { "equipped" : ['dagger', 'dagger'] })
        npc = session.npc('goblin')
        battle.add(character, 'a', position='spawn_point_1', token='G')
        battle.add(npc, 'b', position='spawn_point_2', token='g')

        


        battle.add(character, 'a', token='R')
        battle.add(npc, 'b', token='g')

        battle_map.move_to(character, 0, 0, battle)
        battle_map.move_to(npc, 1, 0, battle)

        character.reset_turn(battle)
        npc.reset_turn(battle)

        map_renderer = MapRenderer(battle_map)
        map_renderer.render(battle)
        self.assertEqual(AttackAction.build(session, character)['next'](npc)['next']('dagger')['next']().action_type, 'attack')


if __name__ == '__main__':
    unittest.main()
