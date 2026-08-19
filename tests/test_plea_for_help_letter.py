"""Plea for Help: Arrigal's letter grant, journal/memory, and UI notify."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from natural20.event_manager import EventManager
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from webapp.entity_rag_handler import EntityRAGHandler

_LISTENERS_PATH = Path(__file__).resolve().parents[1] / 'user_levels' / 'death_house' / 'webapp' / 'custom_listeners.py'
_spec = importlib.util.spec_from_file_location('death_house_custom_listeners', _LISTENERS_PATH)
listeners = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(listeners)


def _make_pc():
    session = Session(root_path='tests/fixtures', event_manager=EventManager())
    return PlayerCharacter.load(session, 'high_elf_fighter.yml')


def test_keyword_source_includes_aside():
    text = EntityRAGHandler.conversation_keyword_source_text(
        None,
        {
            'message': 'I have been sent to you to deliver this message.',
            'narrative': [
                'He pulls from his tunic a sealed letter and drops it on the table.',
            ],
        },
    )
    assert 'sealed letter' in text
    assert 'deliver this message' in text


def test_plea_letter_grants_item_journal_memory_and_toaster():
    pc = _make_pc()
    pc.entity_uid = 'pc_hero'
    sidekick = SimpleNamespace(
        entity_uid='npc_jarek_volkov',
        journal=[],
        label=lambda: 'Jarek',
    )
    arrigal = SimpleNamespace(
        entity_uid='npc_arrigal',
        inventory={
            'sealed_plea_letter': {'qty': 1},
            'kolyan_letter_forged': {'qty': 1},
        },
    )

    def item_count(slug):
        return int((arrigal.inventory.get(slug) or {}).get('qty') or 0)

    def deduct_item(slug, qty):
        arrigal.inventory[slug]['qty'] = max(0, item_count(slug) - qty)
        return {'type': slug, 'qty': qty}

    arrigal.item_count = item_count
    arrigal.deduct_item = deduct_item

    tavern = SimpleNamespace(entities={}, position_of=lambda _entity: (4, 6))
    session = SimpleNamespace(
        campaign_flags={},
        maps={'tavern': tavern},
        game_time=12,
        entity_by_uid=lambda uid: {
            'npc_arrigal': arrigal,
            'pc_hero': pc,
            'npc_jarek_volkov': sidekick,
        }.get(uid),
        map_for_entity=lambda ent: tavern,
        load_equipment=lambda slug: {'name': 'Sealed Letter'} if slug == 'sealed_plea_letter' else {},
    )
    memory = SimpleNamespace(created=[])

    def list_summaries(_uid, limit=10, query=None):
        return []

    def create(entity_uid, **kwargs):
        item = {'entity_uid': entity_uid, **kwargs}
        memory.created.append(item)
        return item

    memory.list_summaries = list_summaries
    memory.create = create
    socketio = MagicMock()
    current_game = SimpleNamespace(
        game_session=session,
        npc_memory_store=memory,
    )

    with patch.object(listeners, '_iter_player_characters', return_value=[pc]), \
         patch.object(listeners, '_iter_plea_witnesses', return_value=[pc, sidekick]), \
         patch('webapp.blueprints.helpers.runtime_state.get_current_game', return_value=current_game), \
         patch('webapp.blueprints.helpers.runtime_state.get_socketio', return_value=socketio):
        listeners.handle_plea_letter_delivered({'speaker': pc})
        listeners.handle_plea_letter_delivered({'speaker': pc})

    assert pc.item_count('sealed_plea_letter') >= 1
    assert any(entry.get('seed_id') == 'plea_for_help' for entry in pc.journal)
    journal_text = next(entry['text'] for entry in pc.journal if entry.get('seed_id') == 'plea_for_help')
    assert 'west road' in journal_text
    assert 'five hours' in journal_text
    assert 'Svalich Woods' in journal_text
    assert memory.created
    assert memory.created[0]['entity_uid'] == 'npc_jarek_volkov'
    assert 'west road' in memory.created[0]['body']

    payloads = [
        call.args[1]
        for call in socketio.emit.call_args_list
        if call.args and call.args[0] == 'message' and isinstance(call.args[1], dict)
    ]
    emitted_types = [payload.get('type') for payload in payloads]
    assert 'message_toaster' in emitted_types
    assert 'journal_update' in emitted_types
    assert 'refresh_map' in emitted_types
    toaster = next(payload for payload in payloads if payload.get('type') == 'message_toaster')
    assert 'Sealed Letter' in toaster['message']
    assert session.campaign_flags.get('plea_letter_given') is True
    assert sum(1 for entry in pc.journal if entry.get('seed_id') == 'plea_for_help') == 1


def test_plea_letter_schedules_arrigal_exit_walk():
    pc = _make_pc()
    pc.entity_uid = 'pc_hero'
    arrigal = SimpleNamespace(entity_uid='npc_arrigal', inventory={})
    arrigal.item_count = lambda slug: 0
    arrigal.deduct_item = lambda *a, **k: None
    annotation = {'id': 'landmark_arringal_exit', 'kind': 'point', 'pos': [36, 23]}
    tavern = SimpleNamespace(
        position_of=lambda _entity: [34, 23],
        map_annotation_by_id=lambda _id: annotation,
        name='tavern',
    )
    session = SimpleNamespace(
        campaign_flags={},
        maps={'tavern': tavern},
        game_time=12,
        entity_by_uid=lambda uid: arrigal if uid == 'npc_arrigal' else pc if uid == 'pc_hero' else None,
        map_for_entity=lambda ent: tavern,
        load_equipment=lambda slug: {},
    )
    scheduled = []
    current_game = SimpleNamespace(
        game_session=session,
        npc_memory_store=SimpleNamespace(list_summaries=lambda *a, **k: [], create=lambda *a, **k: {}),
        schedule_npc_move_to=lambda *args, **kwargs: scheduled.append((args, kwargs)) or {'status': 'active'},
        active_battle=None,
    )

    with patch.object(listeners, '_iter_player_characters', return_value=[pc]), \
         patch.object(listeners, '_iter_plea_witnesses', return_value=[pc]), \
         patch('webapp.blueprints.helpers.runtime_state.get_current_game', return_value=current_game), \
         patch('webapp.blueprints.helpers.runtime_state.get_socketio', return_value=MagicMock()), \
         patch('webapp.blueprints.helpers.runtime_state.get_entity_rag_handler', return_value=None):
        listeners.handle_plea_letter_delivered({'speaker': pc})

    assert session.campaign_flags.get('plea_arrigal_exiting') is True
    assert scheduled
    _args, kwargs = scheduled[0]
    assert kwargs.get('on_arrival_event') == 'plea_arrigal_depart'
    assert _args[1]['target_spec'] == 'landmark_arringal_exit'


def test_plea_arrigal_depart_waits_until_exit_then_removes():
    arrigal = SimpleNamespace(entity_uid='npc_arrigal')
    present = {'arrigal': True}

    def remove(_ent):
        present['arrigal'] = False

    tavern = SimpleNamespace(
        position_of=lambda _entity: [28, 15] if present['arrigal'] else None,
        map_annotation_by_id=lambda _id: {'id': 'landmark_arringal_exit', 'kind': 'point', 'pos': [36, 23]},
        name='tavern',
        remove=remove,
    )

    def map_for_entity(ent):
        if ent is arrigal and present['arrigal']:
            return tavern
        return None

    session = SimpleNamespace(
        campaign_flags={},
        maps={'tavern': tavern},
        entity_by_uid=lambda uid: arrigal if uid == 'npc_arrigal' else None,
        map_for_entity=map_for_entity,
    )
    scheduled = []
    current_game = SimpleNamespace(
        game_session=session,
        schedule_npc_move_to=lambda *args, **kwargs: scheduled.append(kwargs) or {'status': 'active'},
        active_battle=None,
    )

    with patch('webapp.blueprints.helpers.runtime_state.get_current_game', return_value=current_game), \
         patch('webapp.blueprints.helpers.runtime_state.get_socketio', return_value=MagicMock()), \
         patch('webapp.blueprints.helpers.runtime_state.get_entity_rag_handler', return_value=None):
        listeners.handle_plea_arrigal_depart({})
        assert present['arrigal'] is True
        assert session.campaign_flags.get('plea_arrigal_exiting') is True
        assert scheduled[0].get('on_arrival_event') == 'plea_arrigal_depart'

        listeners.handle_plea_arrigal_depart({'arrived': True})

    assert present['arrigal'] is False
    assert session.campaign_flags.get('plea_arrigal_gone') is True
