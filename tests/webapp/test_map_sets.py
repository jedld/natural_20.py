"""Webapp map-set helpers: activate, place party, persist, NPC ticks."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import yaml

from natural20.map_set import place_entity_instance
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from tests.test_map_set import _write_campaign


class _FakeSocket:
    def __init__(self):
        self.emits = []

    def emit(self, event, payload, to=None):
        self.emits.append((event, payload, to))


class _FakeGame:
    def __init__(self, session, pc=None):
        self.game_session = session
        self.maps = session.maps
        self.username_to_sid = {"alice": ["sid-alice"]}
        self.pov_entity_for_user = {"alice": pc} if pc is not None else {}
        self.socketio = _FakeSocket()
        self.switched = []
        self._battle = None
        self.deferred_players = {}

    def get_current_battle(self):
        return self._battle

    def get_pov_entity_for_user(self, username):
        return self.pov_entity_for_user.get(username)

    def get_map_for_entity(self, entity):
        return self.game_session.map_for_entity(entity)

    def switch_map_for_user(self, username, map_name):
        self.switched.append((username, map_name))

    def bump_render_epoch(self, username=None):
        return 1


@pytest.fixture
def dual_set_session(tmp_path: Path):
    _write_campaign(
        tmp_path,
        map_sets={
            "root": {"label": "Town", "maps": ["town"]},
            "wilds": {"label": "Wilds", "maps": ["woods"]},
        },
    )
    return Session(root_path=str(tmp_path)), tmp_path


def test_activate_map_set_emits_switch_map(dual_set_session):
    from webapp.blueprints.helpers.map_sets import activate_map_set

    session, _root = dual_set_session
    pc = PlayerCharacter.load(session, "characters/high_elf_fighter")
    session.maps["town"].add(pc, 1, 1, group="a")
    place_entity_instance(session, pc, session.maps["woods"], 2, 2, group="a")
    game = _FakeGame(session, pc)

    result = activate_map_set(game, "wilds")

    assert session.active_map_set == "wilds"
    assert game.switched == [("alice", "woods")]
    assert game.socketio.emits
    event, payload, to = game.socketio.emits[0]
    assert event == "message"
    assert payload["type"] == "switch_map"
    assert payload["message"]["map"] == "woods"
    assert to == "sid-alice"
    assert result["skipped"] == []


def test_activate_map_set_skips_missing_instance(dual_set_session):
    from webapp.blueprints.helpers.map_sets import activate_map_set

    session, _root = dual_set_session
    pc = PlayerCharacter.load(session, "characters/high_elf_fighter")
    session.maps["town"].add(pc, 1, 1, group="a")
    game = _FakeGame(session, pc)

    result = activate_map_set(game, "wilds")

    assert session.active_map_set == "wilds"
    assert game.switched == []
    assert result["skipped"]
    assert result["skipped"][0]["username"] == "alice"


def test_activate_blocked_during_battle(dual_set_session):
    from webapp.blueprints.helpers.map_sets import activate_map_set

    session, _root = dual_set_session
    game = _FakeGame(session)
    game._battle = SimpleNamespace(started=True)
    with pytest.raises(ValueError, match="battle"):
        activate_map_set(game, "wilds")
    assert session.active_map_set == "root"


def test_create_map_set_persists_game_yml(dual_set_session):
    from webapp.blueprints.helpers.map_sets import create_map_set

    session, root = dual_set_session
    game = _FakeGame(session)
    created = create_map_set(game, "forest_ambush", label="Forest Ambush")
    assert created["id"] == "forest_ambush"
    yml = yaml.safe_load((root / "game.yml").read_text(encoding="utf-8"))
    assert "forest_ambush" in yml["map_sets"]
    assert "root" in yml["map_sets"]
    assert "town" in yml["map_sets"]["root"]["maps"]


def test_place_party_helper_keeps_other_set(dual_set_session):
    from webapp.blueprints.helpers.map_sets import place_party

    session, _root = dual_set_session
    pc = PlayerCharacter.load(session, "characters/high_elf_fighter")
    session.maps["town"].add(pc, 1, 1, group="a")
    game = _FakeGame(session, pc)
    result = place_party(game, "woods", x=2, y=2)
    assert result["placed"]
    assert pc in session.maps["town"].entities
    assert pc in session.maps["woods"].entities
    assert session.active_map_set == "root"


def test_travel_party_to_map_places_missing_and_activates(dual_set_session):
    from webapp.blueprints.helpers.map_sets import travel_party_to_map

    session, _root = dual_set_session
    pc = PlayerCharacter.load(session, "characters/high_elf_fighter")
    session.maps["town"].add(pc, 1, 1, group="a")
    game = _FakeGame(session, pc)

    result = travel_party_to_map(game, "woods")

    assert session.active_map_set == "wilds"
    assert pc in session.maps["town"].entities
    assert pc in session.maps["woods"].entities
    assert result["map"] == "woods"
    assert result["map_set"] == "wilds"
    assert game.switched == [("alice", "woods")]
    refresh = [payload for event, payload, _to in game.socketio.emits if payload.get("type") == "refresh_map"]
    assert refresh


def test_travel_party_only_if_absent_keeps_existing_token(dual_set_session):
    from webapp.blueprints.helpers.map_sets import travel_party_to_map

    session, _root = dual_set_session
    pc = PlayerCharacter.load(session, "characters/high_elf_fighter")
    session.maps["town"].add(pc, 1, 1, group="a")
    place_entity_instance(session, pc, session.maps["woods"], 3, 3, group="a")
    game = _FakeGame(session, pc)

    travel_party_to_map(game, "woods")

    assert list(session.maps["woods"].position_of(pc)) == [3, 3]


def test_party_travel_prompt_yes_calls_travel(dual_set_session, monkeypatch):
    from webapp.blueprints.helpers import party_travel as party_travel_mod

    session, _root = dual_set_session
    pc = PlayerCharacter.load(session, "characters/high_elf_fighter")
    session.maps["town"].add(pc, 1, 1, group="a")
    game = _FakeGame(session, pc)
    captured = {}

    def _prompt(message, callback=None, options=None, usernames=None, title=None):
        captured["message"] = message
        captured["title"] = title
        captured["options"] = options
        callback({"response": "Yes"})

    game.prompt = _prompt
    monkeypatch.setattr(party_travel_mod, "get_current_game", lambda: game)

    party_travel_mod.handle_party_travel_prompt({
        "source": pc,
        "target_map": "woods",
        "title": "Leave town?",
        "message": "The entire party will be transported to woods. Continue?",
    })

    assert captured["title"] == "Leave town?"
    assert captured["options"] == ["Yes", "No"]
    assert session.active_map_set == "wilds"
    assert pc in session.maps["woods"].entities
    pending = (session.session_state.get("_party_travel") or {}).get("pending") or {}
    assert str(pc.entity_uid) not in pending


def test_party_travel_prompt_no_does_not_travel(dual_set_session, monkeypatch):
    from webapp.blueprints.helpers import party_travel as party_travel_mod

    session, _root = dual_set_session
    pc = PlayerCharacter.load(session, "characters/high_elf_fighter")
    session.maps["town"].add(pc, 1, 1, group="a")
    game = _FakeGame(session, pc)
    game.prompt = lambda message, callback=None, options=None, usernames=None, title=None: callback({"response": "No"})
    monkeypatch.setattr(party_travel_mod, "get_current_game", lambda: game)

    party_travel_mod.handle_party_travel_prompt({
        "source": pc,
        "target_map": "woods",
        "message": "Leave?",
    })

    assert session.active_map_set == "root"
    assert pc not in session.maps["woods"].entities
    declined = (session.session_state.get("_party_travel") or {}).get("declined") or {}
    assert declined[str(pc.entity_uid)] == "woods"


def test_iter_dialog_npcs_skips_inactive_set(dual_set_session):
    from webapp.long_rest_npc_simulation import iter_dialog_npcs

    session, _root = dual_set_session
    town_npc = session.npc("goblin", {"name": "Townie", "overrides": {"entity_uid": "townie"}})
    town_npc.entity_uid = "townie"
    town_npc.dialog = True
    woods_npc = session.npc("goblin", {"name": "Bandit", "overrides": {"entity_uid": "bandit"}})
    woods_npc.entity_uid = "bandit"
    woods_npc.dialog = True
    session.maps["town"].add(town_npc, 1, 1, group="b")
    session.maps["woods"].add(woods_npc, 1, 1, group="b")
    session.active_map_set = "root"
    game = SimpleNamespace(maps=session.maps, game_session=session)
    uids = {str(getattr(n, "entity_uid", "")) for n in iter_dialog_npcs(game)}
    assert "townie" in uids
    assert "bandit" not in uids


def test_switch_map_for_user_does_not_move_companions():
    from webapp.game_management_components import GameEntityRegistry

    manager = SimpleNamespace(
        logger=MagicMock(),
        maps={"town": object()},
        current_map_for_user={},
        game_session=SimpleNamespace(game_properties={"companions": [{"entity_uid": "x"}]}),
    )
    registry = GameEntityRegistry(manager)
    registry.switch_map_for_user("alice", "town")
    assert manager.current_map_for_user["alice"][0] == "town"


def test_mcp_registry_includes_dm_map_set():
    from webapp.mcp.routes import build_default_registry

    names = {tool['name'] for tool in build_default_registry().list()}
    assert 'dm.map_set' in names
    assert 'dm.notebook' in names
    world_list = next(t for t in build_default_registry().list() if t['name'] == 'world.list_maps')
    assert world_list['name'] == 'world.list_maps'


def test_dm_llm_registers_map_set_functions():
    from webapp.blueprints.helpers.llm_init import register_game_context_functions
    from webapp.llm_handler import LLMHandler

    handler = LLMHandler()
    provider = SimpleNamespace(
        get_map_info=lambda: {},
        get_entities=lambda: [],
        get_player_characters=lambda: [],
        get_npcs=lambda: [],
        get_entity_details=lambda *a, **k: {},
        get_battle_status=lambda: {},
        run_rest=lambda *a, **k: {},
        rest_all_player_characters=lambda *a, **k: {},
        run_npc_long_rest_simulation=lambda *a, **k: {},
        start_battle=lambda *a, **k: {},
        end_battle=lambda *a, **k: {},
        manage_battle=lambda *a, **k: {},
        set_entity_group=lambda *a, **k: {},
        configure_group_relationship=lambda *a, **k: {},
        list_campaign_groups=lambda: {},
        list_map_sets=lambda: {'active': 'root'},
        manage_map_set=lambda *a, **k: {'success': True},
        get_time_of_day=lambda: {},
        list_campaign_notes=lambda *a, **k: {},
        get_campaign_note=lambda *a, **k: {},
        search_campaign_notes=lambda *a, **k: {},
    )
    registry = SimpleNamespace(list=lambda: [{'name': 'dm.map_set', 'description': 'map sets'}], call=lambda *a, **k: {})
    register_game_context_functions(handler, provider, registry, SimpleNamespace(current_game=None))
    assert 'list_map_sets' in handler.game_context_functions
    assert 'manage_map_set' in handler.game_context_functions
    prompt = handler._build_system_prompt({'get_map_info': {'name': 'town', 'map_set': 'root', 'active_map_set': 'root'}})
    assert 'manage_map_set' in prompt
    assert 'list_map_sets' in prompt
    assert 'dm.map_set' in prompt
    assert 'Active Map Set: root' in prompt


def test_manage_map_set_lists_and_activates(dual_set_session):
    from webapp.game_context import GameContextProvider

    session, _root = dual_set_session
    pc = PlayerCharacter.load(session, "characters/high_elf_fighter")
    session.maps["town"].add(pc, 1, 1, group="a")
    game = _FakeGame(session, pc)
    game.get_current_battle_map = lambda: session.maps["town"]
    provider = GameContextProvider(session, game)
    listed = provider.list_map_sets()
    assert listed['success'] is True
    assert listed['active'] == 'root'
    ids = {item['id'] for item in listed['sets']}
    assert ids == {'root', 'wilds'}
    activated = provider.manage_map_set('activate', map_set='wilds')
    assert activated['success'] is True
    assert session.active_map_set == 'wilds'
