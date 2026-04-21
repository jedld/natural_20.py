from natural20.event_manager import EventManager
from natural20.session import Session


class DummySocket:
    def emit(self, *args, **kwargs):
        pass


class DummyLogger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


def make_game_management(force_llm_npc_combat=False, npc_controller='ai'):
    event_manager = EventManager()
    event_manager.standard_cli()
    session = Session(root_path='tests/fixtures', event_manager=event_manager)

    from webapp.utils import GameManagement

    return GameManagement(game_session=session,
                          map_location='maps/game_map',
                          other_maps={},
                          socketio=DummySocket(),
                          output_logger=DummyLogger(),
                          tile_px=16,
                          controllers=[],
                          npc_controller=npc_controller,
                          force_llm_npc_combat=force_llm_npc_combat,
                          autosave=False,
                          auto_battle=False,
                          system_logger=DummyLogger(),
                          soundtrack=[])


def test_effective_npc_combat_controller_uses_configured_default_when_flag_off():
    game = make_game_management(force_llm_npc_combat=False, npc_controller='ai')

    assert game.effective_npc_combat_controller() == 'ai'


def test_effective_npc_combat_controller_forces_llm_when_flag_on():
    game = make_game_management(force_llm_npc_combat=True, npc_controller='ai')

    assert game.effective_npc_combat_controller() == 'llm'


def test_build_combat_controller_for_npc_uses_llm_when_flag_on(monkeypatch):
    game = make_game_management(force_llm_npc_combat=True, npc_controller='ai')
    npc = game.game_session.npc('goblin')

    class FakeLlmController:
        def __init__(self, session, llm_provider=None):
            self.session = session
            self.llm_provider = llm_provider

        def register_handlers_on(self, entity):
            pass

    monkeypatch.setattr('webapp.utils.LlmMcpController', FakeLlmController)

    controller = game.build_combat_controller_for_entity(npc)

    assert isinstance(controller, FakeLlmController)


def test_entity_owners_uses_entity_uid_when_owner_is_none():
    game = make_game_management(force_llm_npc_combat=False, npc_controller='ai')
    npc = game.game_session.npc('goblin')
    game.controllers = [{
        'entity_uid': npc.entity_uid,
        'controllers': ['dm'],
    }]

    assert game.entity_owners(npc) == ['dm']
