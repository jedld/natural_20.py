import unittest
from natural20.map import Map
from natural20.battle import Battle
from natural20.utils.utils import Session
from natural20.map_renderer import MapRenderer
from natural20.event_manager import EventManager
from natural20.player_character import PlayerCharacter


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
        available_actions = [action.name for action in npc.available_actions(session, None)]
        assert len(available_actions) == 6, len(available_actions)
        
        # assert available_actions == [
        #     'attack', 'attack', 'look', 'move', 'grapple', 'use_item', 'interact', 'ground_interact', 'inventory'
        # ] 

        assert npc.hit_die == {6: 2}

        random.seed(7000)
        EventManager.standard_cli()
        npc.take_damage(4)
        assert npc.hit_die == {6: 2}
        npc.short_rest(battle)
        assert npc.hp == 7
        assert npc.hit_die == {6: 1}

        result = [npc.saving_throw(attribute) for attribute in natural_20.Entity.ATTRIBUTE_TYPES]
        assert [dr.roller.roll_str for dr in result] == ['d20-1', 'd20+2', 'd20+0', 'd20+0', 'd20-1', 'd20-1']

        roll = npc.stealth_check(battle)
        assert roll.roller.roll_str == '1d20+6'

        assert npc.apply_effect('status:prone') == {'battle': None, 'source': npc, 'type': 'prone', 'flavor': None}

        # owlbear npc
        npc = session.npc('owlbear', name='Grunt')
        battle = Battle(session, map)
        fighter = PlayerCharacter.load(session, 'fixtures/high_elf_fighter.yml')
        battle.add(fighter, 'a', position='spawn_point_1', token='G')
        battle.add(npc, 'a', position='spawn_point_2', token='G')
        npc.reset_turn(battle)
        fighter.reset_turn(battle)
        battle.start()

        assert npc.darkvision(60)

        assert len(npc.available_actions(session, None)) == 9
        assert [action.name for action in npc.available_actions(session, None)] == [
            'attack', 'attack', 'look', 'move', 'grapple', 'use_item', 'interact', 'ground_interact', 'inventory'
        ]

        first_attack = next(a for a in npc.available_actions(session, battle) if a.name == 'attack')
        first_attack.target = fighter
        battle.action(first_attack)
        battle.commit(first_attack)

        assert [action.name for action in npc.available_actions(session, battle)] == [
            'attack', 'look', 'move', 'interact', 'inventory'
        ]