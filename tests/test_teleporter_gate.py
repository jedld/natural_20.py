"""Tests for Teleporter requires_session gating."""

from unittest.mock import MagicMock

from natural20.item_library.teleporter import Teleporter


def _make_teleporter(props, session=None):
    session = session or MagicMock()
    session.session_state = getattr(session, 'session_state', {})
    session.event_manager = MagicMock()
    tp = Teleporter(session, None, {
        'name': 'gate',
        'label': 'Cathedral Doors',
        'target_map': 'cathedral',
        'target_position': [1, 1],
        **props,
    })
    return tp, session


def test_teleporter_open_without_requires():
    tp, session = _make_teleporter({})
    entity = MagicMock(name='hero')
    source_map = MagicMock()
    source_map.session = session
    source_map.linked_maps = {}
    assert tp._session_gate_allows(entity, source_map) is True


def test_teleporter_any_of_min_count():
    tp, session = _make_teleporter({
        'requires_session': {
            'any_of': ['a', 'b', 'c'],
            'min_count': 2,
        },
        'deny_message': 'Need more proof.',
    })
    session.session_state = {'a': True}
    entity = MagicMock()
    entity.name = 'hero'
    source_map = MagicMock()
    source_map.session = session
    source_map.name = 'streets'
    source_map.linked_maps = {'cathedral': MagicMock()}
    assert tp._session_gate_allows(entity, source_map) is False

    session.session_state['b'] = True
    assert tp._session_gate_allows(entity, source_map) is True


def test_teleporter_all_of_and_legacy_visibility_flag():
    tp, session = _make_teleporter({
        'requires_session': {'all_of': ['ledger']},
    })
    session.session_state = {}
    entity = MagicMock()
    source_map = MagicMock(session=session)
    assert tp._session_gate_allows(entity, source_map) is False
    session.session_state['ledger'] = True
    assert tp._session_gate_allows(entity, source_map) is True

    tp2, session2 = _make_teleporter({'visibility_flag': 'rose'})
    session2.session_state = {}
    source_map2 = MagicMock(session=session2)
    assert tp2._session_gate_allows(entity, source_map2) is False
    session2.session_state['rose'] = True
    assert tp2._session_gate_allows(entity, source_map2) is True


def test_teleporter_denied_emits_message_and_skips_place():
    tp, session = _make_teleporter({
        'requires_session': {'any_of': ['proof'], 'min_count': 1},
        'deny_message': 'Doors refuse you.',
        'deny_title': 'Sealed',
    })
    session.session_state = {}
    entity = MagicMock()
    entity.name = 'hero'
    source_map = MagicMock()
    source_map.session = session
    source_map.name = 'streets'
    target = MagicMock()
    source_map.linked_maps = {'cathedral': target}

    tp.on_enter(entity, source_map)
    target.place.assert_not_called()
    assert session.event_manager.received_event.called


def test_teleporter_bypass_any_and_inventory_proof():
    tp, session = _make_teleporter({
        'requires_session': {
            'any_of': ['a', 'b'],
            'min_count': 2,
            'bypass_any': ['ophelia_invitation'],
            'inventory_proofs': ['black_rose_pin'],
        },
    })
    session.session_state = {}
    entity = MagicMock()
    entity.inventory = {}
    entity.equipped = []
    source_map = MagicMock(session=session)
    assert tp._session_gate_allows(entity, source_map) is False

    session.session_state = {'ophelia_invitation': True}
    assert tp._session_gate_allows(entity, source_map) is True

    session.session_state = {'a': True}
    entity.inventory = {'black_rose_pin': {'qty': 1}}
    assert tp._session_gate_allows(entity, source_map) is True


def test_teleporter_destination_label_uses_map_name():
    session = MagicMock()
    dest_map = MagicMock()
    dest_map.name = 'Woodland Path to the Tower'
    session.maps = {'woodland_path': dest_map}
    tp, _ = _make_teleporter({'label': 'Road to Town'}, session=session)
    tp.target_map = 'woodland_path'
    assert tp.destination_label() == 'Road to Town → Woodland Path to the Tower'


def test_teleporter_destination_label_same_map_square():
    tp, _ = _make_teleporter({'label': ''})
    tp.target_map = None
    tp.target_position = [4, 7]
    assert tp.destination_label() == 'Square (4, 7)'
