from natural20.battle import Battle
from natural20.map import Map
from natural20.session import Session
from natural20.player_character import PlayerCharacter
from natural20.event_manager import EventManager
from natural20.die_roll import DieRoll
from natural20.map_renderer import MapRenderer
from natural20.actions.attack_action import AttackAction
from natural20.actions.move_action import MoveAction
import unittest
import random
import pdb
from natural20.controller import Controller
from natural20.action import AsyncReactionHandler


class TestBattle(unittest.TestCase):

    def make_session(self):
        event_manager = EventManager()
        event_manager.standard_cli()
        event_manager.register_event_listener(['died'], lambda event: print(f"{event['source'].name} died."))
        event_manager.register_event_listener(['unconscious'], lambda event: print(f"{event['source'].name} unconscious."))
        event_manager.register_event_listener(['initiative'], lambda event: print(f"{event['source'].name} rolled a {event['roll']} = ({event['value']}) with dex tie break for initiative."))
        return Session(root_path='tests/fixtures', event_manager=event_manager)
    
    def test_battle(self):
        session = self.make_session()
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
        session = self.make_session()
        battle_map = Map(session, 'tests/fixtures/battle_sim_objects')
        battle = Battle(session, battle_map)
        map_renderer = MapRenderer(battle_map)
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        mage = PlayerCharacter.load(session, 'high_elf_mage.yml')
        npc2 = session.npc('goblin', { "name":'b'})
        battle.add(fighter, 'a')
        battle.add(npc2, 'b')
        battle.add(mage, 'a')

        random.seed(3001)
        battle.start()
        fighter.take_damage(DieRoll([20], 80).result())
        self.assertTrue(fighter.unconscious())
        self.assertTrue(battle.ongoing())
        random.seed(3004)
        battle.while_active(8, lambda entity: False)
        self.assertTrue(fighter.dead())

    def test_death_saving_throws_success(self):
        session = self.make_session()
        battle_map = Map(session, 'tests/fixtures/battle_sim_objects')
        battle = Battle(session, battle_map)
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')

        # need an ally so that it won't trigger a game over
        mage = PlayerCharacter.load(session, 'high_elf_mage.yml')
        npc2 = session.npc('goblin', { "name":'b'})
        battle.add(fighter, 'a')
        battle.add(npc2, 'b')
        battle.add(mage, 'a')

        random.seed(2010)
        battle.start(combat_order=[fighter, npc2, mage])
        fighter.take_damage(DieRoll([40], 80).result())
        self.assertTrue(fighter.unconscious())
        self.assertFalse(fighter.stable())
        random.seed(1333)
        battle.while_active(5, lambda entity: False)
        self.assertTrue(fighter.stable())

    def test_death_saving_throws_critical_success(self):
        session = self.make_session()
        battle_map = Map(session, 'tests/fixtures/battle_sim_objects')
        battle = Battle(session, battle_map)
        map_renderer = MapRenderer(battle_map)
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        npc2 = session.npc('goblin', { "name":'b'})
        battle.add(fighter, 'a')
        battle.add(npc2, 'b')
    

        random.seed(1004)
        battle.start()
        fighter.take_damage(DieRoll([20], 80).result())
        assert fighter.unconscious()
        battle.while_active(3, lambda entity: False)
        assert fighter.conscious()

    def test_valid_targets_for(self):
        session = self.make_session()
        battle_map = Map(session, 'battle_sim_objects')
        battle = Battle(session, battle_map)
        map_renderer = MapRenderer(battle_map)
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        npc = session.npc('goblin', { "name" : 'a'})
        battle_map.place((0, 5), fighter, 'G')
        battle.add(fighter, 'a')
        door = battle_map.object_at(1, 4)

        action = AttackAction(session, fighter, 'attack')
        action.using = 'vicious_rapier'
        print(map_renderer.render())
        self.assertEqual(battle.valid_targets_for(fighter, action), [])
        battle.add(npc, 'b', position=(1, 5))
        print(map_renderer.render())
        assert battle.valid_targets_for(fighter, action) == [npc]
        assert npc in battle.valid_targets_for(fighter, action, include_objects=True)

    def test_valid_targets_for_line_of_sight(self):
        session = self.make_session()
        battle_map = Map(session, 'battle_sim_4')
        battle = Battle(session, battle_map)
        map_renderer = MapRenderer(battle_map)
        fighter1 = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        battle_map.place((1, 1), fighter1, 'A')
        battle.add(fighter1, 'a')
        fighter2 = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        battle_map.place((1, 5), fighter2, 'B')
        battle.add(fighter2, 'b')
        fighter3 = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        battle_map.place((5, 1), fighter3, 'C')
        battle.add(fighter3, 'b')
        print(map_renderer.render())
        action = AttackAction(session, fighter1, 'attack')
        action.using = 'longbow'
        valid_targets = battle.valid_targets_for(fighter1, action)
        print(valid_targets)
        assert fighter2 not in valid_targets, valid_targets
        assert fighter3 in valid_targets, valid_targets
        action = AttackAction(session, fighter2, 'attack')
        action.using = 'longbow'
        valid_targets2 = battle.valid_targets_for(fighter2, action)
        print(valid_targets2)
        assert fighter1 not in valid_targets2, valid_targets2

    # Tests that an action can have reactions attached to it
    # and can be resolved
    def test_opportunity_attack_reactions(self):
        class CustomReactionController(Controller):
            def __init__(self, session):
                self.state = {}
                self.session = session
                self.battle_data = {}
                self.user = None

            def opportunity_attack_listener(self, battle, session, entity, map, event):
                self.reaction = event
                actions = [s for s in entity.available_actions(session, battle, opportunity_attack=True)]

                valid_actions = []
                for action in actions:
                    valid_targets = battle.valid_targets_for(entity, action)
                    if event['target'] in valid_targets:
                        action.target = event['target']
                        action.as_reaction = True
                        valid_actions.append(action)

                yield battle, entity, valid_actions


        session = self.make_session()
        battle_map = Map(session, 'battle_sim_objects')
        battle = Battle(session, battle_map)
        map_renderer = MapRenderer(battle_map)
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml', override={"token": '1'})
        npc = session.npc('goblin', { "name" : 'a'})
        battle_map.place((0, 5), fighter, 'G')
        controller = CustomReactionController(session)
        battle.add(fighter, 'a', controller=controller, token = '1')
        controller.register_handlers_on(fighter)
        battle.add(npc, 'b', position=(1, 5), token='2')
        battle.start(combat_order=[fighter, npc])
        fighter.reset_turn(battle)
        npc.reset_turn(battle)
        self.assertTrue(fighter.has_reaction(battle))
        move_action = MoveAction(session, npc, 'move')
        move_action.move_path = [[1,5],[2, 5]]
        try:
            move_action = battle.action(move_action)
        except AsyncReactionHandler as e:
            print("waiting for reaction")
            if (e.reaction_type == 'opportunity_attack'):
                for battle, entity, valid_actions in e.resolve():
                    print(f"{valid_actions}")
                    # return value to the generator
                    e.send(valid_actions[0])
                move_action = battle.action(move_action)
        battle.commit(move_action)

        # fighter should have taken an opportunity attack
        self.assertFalse(fighter.has_reaction(battle))
        print(map_renderer.render())


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
