"""Webapp sidekick invite gating and join UI notify."""

from types import SimpleNamespace

from natural20.sidekick import join_party
from webapp.blueprints.helpers.sidekick_control import can_invite_entity


def test_can_invite_regular_npc():
    session = SimpleNamespace(session_state={})
    npc = SimpleNamespace(
        entity_uid='npc_guide',
        group='c',
        is_npc=lambda: True,
        dead=lambda: False,
    )
    assert can_invite_entity(session, npc) is True
    join_party(session, npc, ['alice'])
    assert can_invite_entity(session, npc) is False


def test_cannot_invite_non_npc():
    session = SimpleNamespace(session_state={})
    pc = SimpleNamespace(entity_uid='pc1', is_npc=lambda: False)
    assert can_invite_entity(session, pc) is False


def _npc(uid='npc_sister_anya', name='Sister Anya'):
    return SimpleNamespace(
        entity_uid=uid,
        name=name,
        group='c',
        is_npc=lambda: True,
        dead=lambda: False,
        properties={},
        update_state=lambda *_a, **_k: None,
        label=lambda: name,
    )


def test_join_party_and_control_emits_refresh_and_membership(monkeypatch):
    from webapp.blueprints.helpers import sidekick_control as sc

    session = SimpleNamespace(session_state={})
    npc = _npc()
    emitted = []
    logs = []
    socketio = SimpleNamespace(emit=lambda event, payload=None, **_k: emitted.append((event, payload)))
    game = SimpleNamespace(
        socketio=socketio,
        controllers=[],
        controller_registry=None,
        web_controllers={},
        bump_render_epoch=lambda username=None: None,
        realtime_ui_suppressed=lambda: False,
    )
    monkeypatch.setattr(sc, 'get_game_session', lambda: session)
    monkeypatch.setattr(sc, 'get_current_game', lambda: game)
    monkeypatch.setattr(sc, 'get_socketio', lambda: socketio)
    monkeypatch.setattr(sc, 'get_output_logger', lambda: SimpleNamespace(log=lambda msg, **_k: logs.append(msg)))

    rec = sc.join_party_and_control(npc, ['keo'])
    assert rec.get('status') == 'in_party'
    types = [payload.get('type') for _event, payload in emitted if isinstance(payload, dict)]
    assert 'refresh_map' in types
    membership = next(payload for _event, payload in emitted if isinstance(payload, dict) and payload.get('type') == 'party_membership')
    assert membership['message']['action'] == 'join'
    assert membership['message']['entity_uid'] == 'npc_sister_anya'
    assert 'Sister Anya joined the party.' in membership['message']['text']
    assert logs == ['Sister Anya joined the party.']


def test_join_party_and_control_can_skip_notify(monkeypatch):
    from webapp.blueprints.helpers import sidekick_control as sc

    session = SimpleNamespace(session_state={})
    npc = _npc()
    emitted = []
    socketio = SimpleNamespace(emit=lambda event, payload=None, **_k: emitted.append((event, payload)))
    game = SimpleNamespace(
        socketio=socketio,
        controllers=[],
        controller_registry=None,
        web_controllers={},
        bump_render_epoch=lambda username=None: None,
        realtime_ui_suppressed=lambda: False,
    )
    monkeypatch.setattr(sc, 'get_game_session', lambda: session)
    monkeypatch.setattr(sc, 'get_current_game', lambda: game)
    monkeypatch.setattr(sc, 'get_socketio', lambda: socketio)
    monkeypatch.setattr(sc, 'get_output_logger', lambda: SimpleNamespace(log=lambda *_a, **_k: None))

    sc.join_party_and_control(npc, ['keo'], notify=False)
    assert emitted == []


def _labeled(uid, name):
    return SimpleNamespace(entity_uid=uid, name=name, label=lambda: name)


def test_in_party_sidekick_prompt_overrides_join_backstory(monkeypatch):
    from webapp.npc_situational_context import in_party_sidekick_prompt_block

    npc = _labeled('npc_sister_anya', 'Sister Anya')
    pc = _labeled('pc-keo', 'Keo')
    session = SimpleNamespace(
        session_state={
            'sidekicks': {
                'npc_sister_anya': {'status': 'in_party', 'owners': ['keo']},
            }
        },
        entity_by_uid=lambda uid: npc if uid == 'npc_sister_anya' else None,
    )
    monkeypatch.setattr(
        'natural20.sidekick.iter_party_members',
        lambda _session: [pc, npc],
    )

    text = in_party_sidekick_prompt_block(session, npc, speaker=pc)
    assert 'already joined this adventuring party' in text
    assert 'You travel with: Keo.' in text
    assert 'The speaker (Keo) is a member of your party' in text
    assert 'still deciding' in text
    assert in_party_sidekick_prompt_block(session, pc) == ''


def test_in_party_sidekick_prompt_empty_when_not_joined():
    from webapp.npc_situational_context import in_party_sidekick_prompt_block

    npc = _labeled('npc_sister_anya', 'Sister Anya')
    session = SimpleNamespace(session_state={})
    assert in_party_sidekick_prompt_block(session, npc) == ''
