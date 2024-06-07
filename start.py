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
    def __init__(self, session, persistent_state = {}):
        super(CustomController, self).__init__(session)
        self.persistent_state = persistent_state
    
    def begin_turn(self, entity):
        print(f"\n=========================")
        print(f"{entity.name} begins turn")
        print(f"he is at {entity.hp()} / {entity.max_hp()} health")
        print(f"=========================")

    def select_action(self, environment, entity, available_actions)-> Action:
        print(environment)
        print(f"{entity.name} ({entity.hp()}/{entity.max_hp()}) looks around and sees the following objects:")
        for obj in environment.objects:
            print(f" - {obj} equipped with {obj.weapons}")
        # print(f"{entity.name} ({entity.hp()}/{entity.max_hp()}) has the following available actions:")
        # for action in available_actions:
        #     print(f" - {action}")

        if len(available_actions) > 0:
            action = random.choice(available_actions)
            print(f"{entity.name} ({entity.hp()}/{entity.max_hp()}) does the following action: {action}")
            return action
        # print(f"{entity.name} ({entity.hp()}/{entity.max_hp()}) ends turn.")
        # no action, end turn
        return None
    
    def begin_trial(self, environment, entity):
        print(f"{entity.name} begins the trial.")

    def end_trial(self, environment, entity):
        print(f"{entity.name} ends the trial.")


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


persistent_state_gomerin = {}
persistent_state_rogin = {}

gomerin_wins = 0
rogin_wins = 0
draws = 0

for i in range(TRIALS):
    print("============")
    print(f"Trial {i + 1}")
    print("============\n\n")

    session = Session('templates')
    map = Map(session, 'templates/maps/game_map.yml')
    battle = Battle(session, map)
    fighter = PlayerCharacter(session, 'templates/characters/high_elf_fighter.yml', name="Gomerin")
    rogue = PlayerCharacter(session, 'templates/characters/halfling_rogue.yml', name="Rogin")
    map_renderer = MapRenderer(map)

    controller_gomerin=CustomController(session, persistent_state_gomerin)
    controller_gomerin.register_handlers_on(fighter)

    controller_rogin=CustomController(session, persistent_state_rogin)
    controller_rogin.register_handlers_on(rogue)

    # add fighter to the battle at position (0, 0) with token 'G' and group 'a'
    battle.add(fighter, 'a', position=[0, 0], token='G', add_to_initiative=True, controller=controller_gomerin)
    battle.add(rogue, 'b', position=[5, 5], token='R', add_to_initiative=True, controller=controller_rogin)
    print(map_renderer.render(battle))

    battle.start()
    print("Combat Initiative Order:")
    for index, entity in zip(range(len(battle.combat_order)),battle.combat_order):
        print(f"{index + 1}. {entity.name}")
    
    controller_gomerin.begin_trial(map, fighter)
    controller_rogin.begin_trial(map, rogue)

    result = battle.while_active(max_rounds=100, block=game_loop)

    print("simulation done.")
    if (fighter.hp() > 0 and rogue.hp() > 0):
        print(f"Both fighters are still standing!")
        draws += 1
    else:
        if (fighter.hp() > 0):
            print(f"Gomerin wins!")
            gomerin_wins += 1
        elif (rogue.hp() > 0):
            print(f"Rogin wins!")
            rogin_wins += 1
        else:
            print(f"Both fighters are down!")
            print(f"{fighter.name} has {fighter.hp()} HP")
            print(f"{rogue.name} has {rogue.hp()} HP")
            draws += 1

    controller_gomerin.end_trial(map, fighter)
    controller_rogin.end_trial(map, rogue)

print(f"Gomerin wins: {gomerin_wins}")
print(f"Rogin wins: {rogin_wins}")
print(f"Draws: {draws}")