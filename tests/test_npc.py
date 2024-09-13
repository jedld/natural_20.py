import unittest
from natural20.map import Map
from natural20.battle import Battle
from natural20.session import Session
from natural20.map_renderer import MapRenderer
from natural20.event_manager import EventManager
from natural20.player_character import PlayerCharacter
from natural20.entity import Entity
import pdb


import random

class TestNpc(unittest.TestCase):
    def make_session(self):
        event_manager = EventManager()
        event_manager.register_event_listener(['died'], lambda event: print(f"{event['source'].name} died."))
        event_manager.register_event_listener(['unconscious'], lambda event: print(f"{event['source'].name} unconscious."))
        event_manager.register_event_listener(['initiative'], lambda event: print(f"{event['source'].name} rolled a {event['roll']} = ({event['value']}) with dex tie break for initiative."))
        return Session(root_path='tests/fixtures', event_manager=event_manager)
    
    def test_npc(self):
        session = self.make_session()

        # skeleton npc
        npc = session.npc('skeleton')
        assert npc.damage_vulnerabilities == ['bludgeoning']

        # bat npc
        battle_map = Map(session, 'tests/fixtures/battle_sim.yml')
        npc = session.npc('bat', { "name" : 'Screech', "familiar" : True })
        battle = Battle(session, battle_map)
        battle.add(npc, 'b', position=[1, 1])

        assert npc.speed() == 5

        npc.fly()
        assert npc.speed() == 30
        assert npc.flying

        assert npc.can_fly()

        map_render = MapRenderer(battle_map, battle)
        assert map_render.render() == (
            "g···#·\n"
            "·v·##·\n"
            "····#·\n"
            "······\n"
            "·##oo·\n"
            "·····Î\n"
            "······\n"
        ), map_render.render()

        npc.take_damage(100, battle=battle)
        assert map_render.render() == (
            "g···#·\n"
            "···##·\n"
            "····#·\n"
            "······\n"
            "·##oo·\n"
            "·····Î\n"
            "······\n"
        )

        # goblin npc
        npc = session.npc('goblin', { "name" : 'Spark'})
        battle = Battle(session, battle_map)
        battle.add(npc, 'a', position=[2, 2])
        assert npc.darkvision(60)
        assert 2 <= npc.hp() <= 12
        assert npc.name == 'Spark'
        assert npc.armor_class() == 15
        assert npc.passive_perception() == 9
        assert [item["name"] for item in npc.equipped_items()] == ['scimitar', 'shortbow', 'leather_armor', 'shield']

        npc.unequip('scimitar')
        assert not npc.equipped('scimitar')
        assert npc.item_count('scimitar') > 0

        npc.unequip('scimitar')
        assert not npc.equipped('scimitar')
        npc.equip('scimitar')
        assert npc.equipped('scimitar')
        npc.reset_turn(battle)
        available_actions = [action.name() for action in npc.available_actions(session, battle, map=battle_map)]
        assert len(available_actions) == 9, len(available_actions)
        
        self.assertListEqual(available_actions, ['disengage', 'dodge', 'move', 'move', 'move', 'move', 'move', 'move', 'move'])

        assert npc.hit_die() == {6: 2}, npc.hit_die()

        random.seed(7000)
        npc.take_damage(4)
        assert npc.hit_die() == {6: 2}
        npc.short_rest(battle)
        assert npc.hp() == 6, npc.hp()
        assert npc.hit_die() == {6: 1}

        result = [npc.saving_throw(attribute) for attribute in Entity.ATTRIBUTE_TYPES]
        assert [dr.roller.roll_str for dr in result] == ['d20-1', 'd20+2', 'd20+0', 'd20+0', 'd20-1', 'd20-1']

        roll = npc.stealth_check(battle)
        assert roll.roller.roll_str == '1d20+6'

        assert npc.apply_effect('status:prone') == {'battle': None, 'source': npc, 'type': 'prone', 'flavor': None}

        # owlbear npc
        npc = session.npc('owlbear', { "name" : 'Grunt'})
        battle = Battle(session, battle_map)
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        battle.add(fighter, 'a', position=[0,5], token='G')
        battle.add(npc, 'b', position='spawn_point_2', token='G')
        npc.reset_turn(battle)
        fighter.reset_turn(battle)
        battle.start()
        self.assertTrue(npc.darkvision(60))

        self.assertEqual(len(npc.available_actions(session, None, map=battle_map)), 3)
        available_actions = [action.name() for action in npc.available_actions(session, None, map=battle_map)]
        self.assertEqual(available_actions, ['attack', 'attack', 'move'])

        first_attack = [a for a in npc.available_actions(session, battle, map=battle_map) if a.name() == 'attack'][0]
        first_attack.target = fighter
        battle.action(first_attack)
        battle.commit(first_attack)

        available_actions = [action.name() for action in npc.available_actions(session, battle)]

        assert available_actions == ['attack', 'move'], available_actions
