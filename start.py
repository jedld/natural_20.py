from natural20.map import Map, Terrain
from natural20.battle import Battle
from natural20.player_character import PlayerCharacter
from natural20.map_renderer import MapRenderer
from natural20.die_roll import DieRoll
from natural20.generic_controller import GenericController
from natural20.utils.utils import Session
from natural20.actions.move_action import MoveAction
from natural20.action import Action
import random

# Number of RL episodes to run
TRIALS = 1

class CustomController(GenericController):
    def __init__(self, session):
        super(CustomController, self).__init__(session)
    
    def begin_turn(self, entity):
        print(f"=========================")
        print(f"{entity.name} begins turn")
        print(f"he is at {entity.hp()} / {entity.max_hp()} health")
        print(f"=========================")

    def select_action(self, environment, entity, available_actions)-> Action:
        print(environment)
        print(f"{entity.name} looks around and sees the following objects:")
        for obj in environment.objects:
            print(f"{obj} equipped with {obj.weapons}")
        
        if len(available_actions) > 0:
            action = random.choice(available_actions)
            print(f"{entity.name} does the following action: {action}")
            return action
        print(f"{entity.name} ends turn.")
        # no action, end turn
        return None


def game_loop(battle: Battle, entity):
    start_combat = False
    print(map_renderer.render(battle))
    if battle.has_controller_for(entity):
        cycles = 0
        move_path = []
        while True:
            cycles += 1
            # session.save_game(battle)
            action = battle.move_for(entity)

            if action is None:
                move_path = []
                break

            if isinstance(action, MoveAction):
                move_path += action.move_path

            battle.action(action)
            battle.commit(action)

            if battle.check_combat():
                start_combat = True
                break

            if action is None or entity.unconscious():
                break
    return None


for _ in range(TRIALS):
    session = Session('templates')
    map = Map('templates/maps/game_map.yml')
    battle = Battle(session, map)
    fighter = PlayerCharacter(session, 'templates/characters/high_elf_fighter.yml', name="Gomerin")
    rogue = PlayerCharacter(session, 'templates/characters/halfling_rogue.yml', name="Rogin")
    map_renderer = MapRenderer(map)


    # add fighter to the battle at position (0, 0) with token 'G' and group 'a'
    battle.add(fighter, 'a', position=[0, 0], token='G', add_to_initiative=True, controller=CustomController(session))
    battle.add(rogue, 'b', position=[5, 5], token='R', add_to_initiative=True, controller=CustomController(session))
    print(map_renderer.render(battle))
    battle.start()
    print("Combat Initiative Order:")
    for index, entity in zip(range(len(battle.combat_order)),battle.combat_order):
        print(f"{index + 1}. {entity.name}")
    
    result = battle.while_active(max_rounds=10, block=game_loop)

    print("simulation done.")