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


class _FakeMovementManager:
    """Just enough of NpcMovementManager for the auto-follow sync tests."""

    def __init__(self, session):
        import threading
        self.game_session = session
        self.npc_movements = {}
        self.game_state_lock = threading.RLock()
        self.kicked = []
        self.cancelled = []

    def get_task(self, entity):
        uid = entity if isinstance(entity, str) else str(getattr(entity, 'entity_uid', '') or '')
        return self.npc_movements.get(uid)

    def schedule_follow(self, entity, target, distance_ft=5, speaker=None):
        uid = str(entity.entity_uid)
        task = {
            'mode': 'follow',
            'status': 'active',
            'target_uid': str(getattr(target, 'entity_uid', '') or ''),
            'distance_ft': distance_ft,
            'attempts': 0,
            'stuck_ticks': 0,
        }
        self.npc_movements[uid] = task
        return task

    def cancel(self, entity, reason=None, mode=None):
        uid = str(entity.entity_uid)
        self.cancelled.append((uid, reason))
        self.npc_movements.pop(uid, None)
        return self.get_task(entity)

    def kick(self, entity=None):
        self.kicked.append(str(getattr(entity, 'entity_uid', '') or ''))

    def get_entity_by_uid(self, uid):
        return self.game_session.entity_by_uid(uid) if uid in self.game_session.uids else None


def _follow_session(session_state, uids):
    class _S:
        pass
    s = _S()
    s.session_state = session_state
    s.uids = set(uids)
    s.entity_by_uid = lambda uid: SimpleNamespace(entity_uid=uid)
    return s


def test_sync_auto_follow_creates_and_retargets_tasks():
    from webapp import sidekick_follow

    session = _follow_session(
        {'sidekicks': {'sk_a': {'status': 'in_party', 'owners': ['keo'], 'auto_follow': True},
                       'sk_b': {'status': 'in_party', 'owners': [], 'auto_follow': True}}},
        uids={'sk_a', 'sk_b', 'pc-keo'},
    )
    manager = _FakeMovementManager(session)
    pc = SimpleNamespace(entity_uid='pc-keo')
    pc2 = SimpleNamespace(entity_uid='pc-keo2')
    game = SimpleNamespace(
        game_session=session,
        movement_manager=manager,
        get_pov_entity_for_user=lambda user: pc if user == 'keo' else None,
    )

    changed = sidekick_follow.sync_sidekick_auto_follows(game)
    assert set(changed) == {'sk_a', 'sk_b'}
    # Chained line: first sidekick follows the POV, second follows the first.
    assert manager.get_task('sk_a')['target_uid'] == 'pc-keo'
    assert manager.get_task('sk_b')['target_uid'] == 'sk_a'
    assert manager.get_task('sk_a')['distance_ft'] == 5

    # No-op when nothing changed.
    assert sidekick_follow.sync_sidekick_auto_follows(game) == []

    # Leader POV change retargets only the head of the line.
    session.uids.add('pc-keo2')
    game.get_pov_entity_for_user = lambda user: pc2 if user == 'keo' else None
    changed = sidekick_follow.sync_sidekick_auto_follows(game)
    assert 'sk_a' in changed
    assert manager.get_task('sk_a')['target_uid'] == 'pc-keo2'
    assert 'sk_b' not in changed  # still trailing sk_a


def test_sync_auto_follow_cancels_when_disabled():
    from webapp import sidekick_follow

    session = _follow_session(
        {'sidekicks': {'sk_a': {'status': 'in_party', 'owners': ['keo'], 'auto_follow': False}}},
        uids={'sk_a'},
    )
    manager = _FakeMovementManager(session)
    # Seed a stale auto-follow task.
    manager.npc_movements['sk_a'] = {
        'mode': 'follow', 'status': 'active', 'target_uid': 'pc-keo',
        'sidekick_follow': True, 'attempts': 0, 'stuck_ticks': 0,
    }
    game = SimpleNamespace(
        game_session=session,
        movement_manager=manager,
        get_pov_entity_for_user=lambda user: None,
    )

    changed = sidekick_follow.sync_sidekick_auto_follows(game)
    assert changed == ['sk_a']
    assert 'sk_a' not in manager.npc_movements
    assert manager.cancelled and manager.cancelled[0][0] == 'sk_a'


def test_set_auto_follow_and_control_emits_membership(monkeypatch):
    from webapp.blueprints.helpers import sidekick_control as sc

    session = SimpleNamespace(session_state={
        'sidekicks': {'npc_sister_anya': {'status': 'in_party', 'owners': ['keo'], 'auto_follow': False}},
    })
    npc = _npc()
    emitted = []
    socketio = SimpleNamespace(emit=lambda event, payload=None, **_k: emitted.append((event, payload)))
    game = SimpleNamespace(
        game_session=session,
        movement_manager=None,
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

    rec = sc.set_auto_follow_and_control(npc, True)
    assert rec['auto_follow'] is True
    membership = next(payload for _event, payload in emitted
                      if isinstance(payload, dict) and payload.get('type') == 'party_membership')
    assert membership['message']['action'] == 'auto_follow'
    assert 'auto-follow' in membership['message']['text']

    # Non-sidekick raises.
    stranger = SimpleNamespace(entity_uid='npc_stranger', is_npc=lambda: True, dead=lambda: False)
    try:
        sc.set_auto_follow_and_control(stranger, True)
        assert False, 'expected ValueError'
    except ValueError:
        pass
