from natural20.map import Map, Terrain
from natural20.battle import Battle
from natural20.player_character import PlayerCharacter
from natural20.map_renderer import MapRenderer
from natural20.die_roll import DieRoll

map = Map('templates/maps/game_map.yml')
battle = Battle(map)
fighter = PlayerCharacter('templates/characters/high_elf_fighter.yml', name="Gomerin")
map_renderer = MapRenderer(map)

# add fighter to the battle at position (0, 0) with token 'G' and group 'a'
battle.add(fighter, 'a', position=[0, 0], token='G', add_to_initiative=True)
print(map_renderer.render(battle))
battle.start()
print(battle.combat_order)
print("simulation done.")
# controller.register_battle_listeners(@battle)

# @fighter = Natural20::PlayerCharacter.load(session, File.join('fixtures', 'high_elf_fighter.yml'))
# @npc1 = session.npc(:goblin)
# @npc2 = session.npc(:ogre)

# @battle.add(@fighter, :a, position: :spawn_point_1, token: 'G')
# @battle.add(@npc1, :b, position: :spawn_point_2, token: 'g')
# @battle.add(@npc2, :b, position: :spawn_point_3, token: 'g')