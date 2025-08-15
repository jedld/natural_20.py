import types

from natural20.session import Session
from natural20.battle import Battle
from natural20.llm_controller import LlmMcpController


def test_llm_mcp_controller_fallback():
    # Use test fixtures session
    session = Session('tests/fixtures')
    any_map = next(iter(session.maps.values()))
    battle = Battle(session, any_map)

    goblin = session.npc('goblin', {"group": "b"})
    hero = session.npc('goblin', {"group": "a"})

    battle.add(goblin, 'b', controller=LlmMcpController, position=(0, 0))
    battle.add(hero, 'a', position=(1, 0))

    battle.start(combat_order=[goblin, hero])

    controller = battle.controller_for(goblin)
    actions = goblin.available_actions(session, battle)

    choice = controller.select_action(battle, goblin, actions)
    assert choice is None or choice in actions
