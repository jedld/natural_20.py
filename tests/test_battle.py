from natural20.battle import Battle
from natural20.map import Map
from natural20.utils.utils import Session
from natural20.player_character import PlayerCharacter
from natural20.event_manager import EventManager
from natural20.die_roll import DieRoll
from natural20.map_renderer import MapRenderer
import unittest
import random
import pdb


class TestBattle(unittest.TestCase):
    def test_battle(self):
        session = Session(root_path='tests/fixtures')
        battle_map = Map(session, 'tests/fixtures/battle_sim.yml')
        battle = Battle(session, battle_map)
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        npc = session.npc('goblin', {"name": 'a'})
        npc2 = session.npc('goblin', {"name":'b'})
        npc3 = session.npc('ogre', {"name" :'c'})
        battle.add(fighter, 'a', position=(0, 0), token='G')
        battle.add(npc, 'b', position=(0, 1), token='g')
        battle.add(npc2, 'b', position=(0, 2), token='O')
        fighter.reset_turn(battle)
        npc.reset_turn(battle)
        npc2.reset_turn(battle)
        
        EventManager.register_event_listener(['died'], lambda event: print(f"{event['source'].name} died."))
        EventManager.register_event_listener(['unconscious'], lambda event: print(f"{event['source'].name} unconscious."))
        EventManager.register_event_listener(['initiative'], lambda event: print(f"{event['source'].name} rolled a {event['roll']} = ({event['value']}) with dex tie break for initiative."))
        random.seed(7000)

        battle.start()
        random.seed(1337)
        action = battle.resolve_action(fighter, 'attack', {"target": npc, "using": 'vicious_rapier'})
        assert fighter.item_count('arrows') == 20
        battle.commit(action)
        assert fighter.item_count('arrows') == 20
        assert npc.hp() == 0, "Goblin should be dead but has hp: %s" % npc.hp()

        assert npc.dead()
        action = battle.resolve_action(npc2, 'attack', {"target": fighter, "npc_action" : npc2.npc_actions[1]})
        battle.commit(action)

        battle.add(npc3, 'c', position=(0, 0))

        assert [x.name for x in battle.combat_order] == ['Gomerin', 'b', 'a'], [x.name for x in battle.combat_order]

    def test_death_saving_throws_failure(self):
        session = Session(root_path='tests/fixtures')
        battle_map = Map(session, 'tests/fixtures/battle_sim_objects')
        battle = Battle(session, battle_map)
        map_renderer = MapRenderer(battle_map)
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        npc2 = session.npc('goblin', { "name":'b'})
        battle.add(fighter, 'a')
        battle.add(npc2, 'b')

        EventManager.standard_cli()
        random.seed(3000)
        battle.start()
        fighter.take_damage(DieRoll([20], 80).result())
        assert fighter.unconscious()
        assert battle.ongoing()
        battle.while_active(3, lambda entity: False)
        assert not battle.ongoing()
        assert fighter.dead()

    def test_death_saving_throws_success(self):
        session = Session(root_path='tests/fixtures')
        battle_map = Map(session, 'tests/fixtures/battle_sim_objects')
        battle = Battle(session, battle_map)
        map_renderer = MapRenderer(battle_map)
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        npc2 = session.npc('goblin', { "name":'b'})
        battle.add(fighter, 'a')
        battle.add(npc2, 'b')

        EventManager.standard_cli()
        random.seed(2003)
        battle.start()
        fighter.take_damage(DieRoll([20], 80).result())
        assert fighter.unconscious()
        battle.while_active(3, lambda entity: False)
        assert fighter.stable()

    def test_death_saving_throws_critical_success(self):
        session = Session(root_path='tests/fixtures')
        battle_map = Map(session, 'tests/fixtures/battle_sim_objects')
        battle = Battle(session, battle_map)
        map_renderer = MapRenderer(battle_map)
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        npc2 = session.npc('goblin', { "name":'b'})
        battle.add(fighter, 'a')
        battle.add(npc2, 'b')
    
        EventManager.standard_cli()
        random.seed(1004)
        battle.start()
        fighter.take_damage(DieRoll([20], 80).result())
        assert fighter.unconscious()
        battle.while_active(3, lambda entity: False)
        assert fighter.conscious()

    # def test_valid_targets_for():
    #     session = Session()
    #     battle_map = BattleMap(session, 'fixtures/battle_sim_objects')
    #     battle = Battle(session, battle_map)
    #     map_renderer = MapRenderer(battle_map)
    #     fighter = PlayerCharacter.load(session, 'fixtures/high_elf_fighter.yml')
    #     npc = session.npc('goblin', name='a')
    #     battle_map.place(0, 5, fighter, 'G')
    #     battle.add(fighter, 'a')
    #     door = battle_map.object_at(1, 4)

    #     action = AttackAction(session, fighter, 'attack')
    #     action.using = 'vicious_rapier'
    #     print(map_renderer.render())
    #     assert battle.valid_targets_for(fighter, action) == []
    #     battle.add(npc, 'b', position=(1, 5))
    #     print(map_renderer.render())
    #     assert battle.valid_targets_for(fighter, action) == [npc]
    #     assert npc in battle.valid_targets_for(fighter, action, include_objects=True)

    # def test_has_controller_for():
    #     session = Session()
    #     battle_map = BattleMap(session, 'fixtures/battle_sim_objects')
    #     battle = Battle(session, battle_map)
    #     fighter = PlayerCharacter.load(session, 'fixtures/high_elf_fighter.yml')
    #     npc = session.npc('goblin', name='a')
    #     battle.add(npc, 'b', position=(1, 5))
    #     battle.add(fighter, 'a', position=(0, 5), controller='manual')

    #     assert battle.has_controller_for(npc)
    #     assert not battle.has_controller_for(fighter)
