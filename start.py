from natural20.map import Map, Terrain
from natural20.battle import Battle
from natural20.player_character import PlayerCharacter
from natural20.map_renderer import MapRenderer
from natural20.die_roll import DieRoll
from natural20.generic_controller import GenericController



# Number of RL episodes to run
TRIALS = 5

class CustomController(GenericController):
    def __init__(self):
        super(CustomController, self).__init__()
    
    def select_action(self, entity, battle):
        return 'attack'


def game_loop(entity):
    start_combat = False
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


for _ in range(TRIALS):
    map = Map('templates/maps/game_map.yml')
    battle = Battle(map)
    fighter = PlayerCharacter('templates/characters/high_elf_fighter.yml', name="Gomerin")
    rogue = PlayerCharacter('templates/characters/halfling_rogue.yml', name="Rogin")
    map_renderer = MapRenderer(map)

    # add fighter to the battle at position (0, 0) with token 'G' and group 'a'
    battle.add(fighter, 'a', position=[0, 0], token='G', add_to_initiative=True, controller=CustomController())
    battle.add(rogue, 'b', position=[5, 5], token='R', add_to_initiative=True, controller=CustomController())
    print(map_renderer.render(battle))
    battle.start()
    print("Combat Initiative Order:")
    for index, entity in zip(range(len(battle.combat_order)),battle.combat_order):
        print(f"{index + 1}. {entity.name}")
    
    result = battle.while_active(max_rounds=10, block=game_loop)

    print("simulation done.")