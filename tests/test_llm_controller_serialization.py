"""Saving a battle with an LLM/JEV combat controller (live provider handles)."""
import random

import pytest

from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.llm_controller import LlmMcpController
from natural20.map import Map
from natural20.session import Session
from natural20.utils.serialization import Serialization


class _UnserializableProvider:
    """Stands in for ``webapp.llm_handler.JevProvider`` (not YAML-representable)."""


@pytest.fixture
def battle_with_llm_controller():
    em = EventManager()
    em.standard_cli()
    random.seed(1234)
    session = Session(root_path='tests/fixtures', event_manager=em)
    battle_map = Map(session, 'tests/fixtures/battle_sim.yml')
    session.maps['test'] = battle_map
    battle = Battle(session, battle_map)
    goblin = session.npc('goblin', {"name": "Gruk"})
    controller = LlmMcpController(session, llm_provider=_UnserializableProvider())
    controller.add_memory_note(goblin, 'the elf has a longbow')
    battle.add(goblin, 'b', position=(2, 2), token='g', controller=controller)
    battle.start()
    return session, battle, battle_map, goblin


@pytest.fixture
def resolver():
    saved = LlmMcpController.provider_resolver
    yield
    LlmMcpController.provider_resolver = saved


def test_battle_with_llm_controller_saves_and_restores(battle_with_llm_controller, resolver):
    session, battle, battle_map, goblin = battle_with_llm_controller
    ser = Serialization()
    yaml_str = ser.serialize(session, battle, [battle_map])
    assert '!llm_mcp_controller' in yaml_str
    assert '_UnserializableProvider' not in yaml_str

    _session, new_battle, _maps = ser.deserialize(yaml_str)
    new_goblin = new_battle.session.entity_by_uid(goblin.entity_uid)
    restored = new_battle.controller_for(new_goblin)
    assert isinstance(restored, LlmMcpController)
    assert restored.get_memory_notes_summary(new_goblin) == ['the elf has a longbow']

    rebound = _UnserializableProvider()
    seen = []
    LlmMcpController.provider_resolver = staticmethod(lambda entity: seen.append(entity) or rebound)
    restored.begin_turn(new_goblin)
    assert restored.llm_provider is rebound
    assert seen == [new_goblin]


def test_deferred_provider_falls_back_to_default(battle_with_llm_controller, resolver, monkeypatch):
    session, *_ = battle_with_llm_controller
    LlmMcpController.provider_resolver = None
    fallback = object()
    monkeypatch.setattr(LlmMcpController, '_default_provider', lambda self: fallback)
    controller = LlmMcpController(session, defer_provider=True)
    assert controller._provider_pending
    assert controller.llm_provider is fallback
