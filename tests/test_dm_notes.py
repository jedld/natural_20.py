"""DM-only map notes: session_state CRUD, isolation from landmarks."""

from __future__ import annotations

from types import SimpleNamespace

from natural20.dm_notes import delete_note, find_note, list_notes, move_note, upsert_note
from natural20.map_annotations import format_current_location_for_llm, list_map_annotations


def _session(**kwargs):
    return SimpleNamespace(session_state={}, game_time=kwargs.get('game_time', 12))


def test_upsert_list_update_delete():
    session = _session()
    created = upsert_note(session, 'tavern', x=8, y=12, text='Secret door behind the barrels.')
    assert created['id']
    assert created['map'] == 'tavern'
    assert created['x'] == 8
    assert created['y'] == 12
    assert created['title'] == 'Secret door behind the barrels.'
    assert created['created_at'] == 12

    listed = list_notes(session, 'tavern')
    assert len(listed) == 1
    assert listed[0]['text'] == 'Secret door behind the barrels.'

    updated = upsert_note(
        session,
        'tavern',
        x=9,
        y=12,
        text='Moved: still a secret door.',
        title='Secret door',
        note_id=created['id'],
    )
    assert updated['id'] == created['id']
    assert updated['x'] == 9
    assert updated['title'] == 'Secret door'
    assert len(list_notes(session, 'tavern')) == 1

    assert delete_note(session, created['id']) is True
    assert list_notes(session, 'tavern') == []
    assert delete_note(session, created['id']) is False


def test_notes_are_scoped_by_map():
    session = _session()
    upsert_note(session, 'tavern', x=1, y=1, text='Taproom reminder')
    upsert_note(session, 'cellar', x=2, y=3, text='Wine casks')
    tavern = list_notes(session, 'tavern')
    cellar = list_notes(session, 'cellar')
    assert [n['text'] for n in tavern] == ['Taproom reminder']
    assert [n['text'] for n in cellar] == ['Wine casks']
    all_notes = list_notes(session, None)
    assert {n['map'] for n in all_notes} == {'tavern', 'cellar'}


def test_move_note_and_find():
    session = _session()
    created = upsert_note(session, 'tavern', x=0, y=0, text='Trapdoor')
    moved = move_note(session, created['id'], 4, 5)
    assert moved['x'] == 4
    assert moved['y'] == 5
    found = find_note(session, created['id'])
    assert found['map'] == 'tavern'
    assert found['x'] == 4


def test_rejects_empty_text_and_negative_coords():
    session = _session()
    try:
        upsert_note(session, 'tavern', x=1, y=1, text='   ')
        assert False, 'expected ValueError'
    except ValueError:
        pass
    try:
        upsert_note(session, 'tavern', x=-1, y=0, text='ok')
        assert False, 'expected ValueError'
    except ValueError:
        pass


def test_save_load_roundtrip_via_session_state():
    session = _session()
    upsert_note(session, 'tavern', x=3, y=4, text='Keep the lantern lit.')
    snapshot = {'dm_notes': session.session_state['dm_notes']}
    restored = SimpleNamespace(session_state=snapshot, game_time=0)
    notes = list_notes(restored, 'tavern')
    assert len(notes) == 1
    assert notes[0]['text'] == 'Keep the lantern lit.'
    assert notes[0]['x'] == 3
    assert notes[0]['y'] == 4


def test_dm_notes_are_not_map_annotations():
    session = _session()
    upsert_note(session, 'tavern', x=8, y=12, text='DM only: ambush here')
    map_properties = {'map_annotations': []}
    assert list_map_annotations(map_properties) == []
    line = format_current_location_for_llm([], map_name='tavern', position=(8, 12))
    assert 'ambush' not in (line or '')
    assert 'DM only' not in (line or '')
    # Landmarks still come only from YAML properties, never session_state.
    assert session.session_state.get('dm_notes')
    assert 'map_annotations' not in session.session_state
