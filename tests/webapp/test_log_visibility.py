import os
import sys


WEBAPP_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'webapp')
if WEBAPP_DIR not in sys.path:
    sys.path.insert(0, WEBAPP_DIR)

from utils import SocketIOOutputLogger


class FakeSocketIO:
    def __init__(self):
        self.calls = []

    def emit(self, event_name, payload, to=None, **kwargs):
        self.calls.append({'event_name': event_name, 'payload': payload, 'to': to})


class FakeEntity:
    def __init__(self, entity_uid, name=None):
        self.entity_uid = entity_uid
        self.name = name or entity_uid

    def label(self):
        return self.name


class FakeMap:
    def __init__(self, entities, visible_pairs=None, in_range=None):
        self.entities = entities
        self.visible_pairs = set(visible_pairs or [])
        self.in_range = in_range or {}

    def can_see(self, viewer, subject):
        if viewer == subject:
            return True
        return (viewer.entity_uid, subject.entity_uid) in self.visible_pairs

    def entities_in_range(self, source, distance_ft):
        return list(self.in_range.get((source.entity_uid, distance_ft), []))


class FakeGame:
    def __init__(self, battle_map, username_to_sid):
        self._battle_map = battle_map
        self.username_to_sid = username_to_sid

    def get_map_for_entity(self, entity):
        return self._battle_map


def build_logger(entities_by_user, roles_by_user, battle_map):
    socketio = FakeSocketIO()
    game = FakeGame(
        battle_map,
        {
            'source_user': ['sid-source'],
            'target_user': ['sid-target'],
            'watcher_user': ['sid-watcher'],
            'bystander_user': ['sid-bystander'],
            'dm': ['sid-dm'],
        },
    )
    logger = SocketIOOutputLogger(socketio)
    logger.configure_visibility(
        game_getter=lambda: game,
        role_lookup=lambda username: roles_by_user.get(username, []),
        controlled_entities_lookup=lambda username: entities_by_user.get(username, []),
    )
    return logger, socketio


def test_combat_logs_are_emitted_only_to_participants_observers_and_dm():
    source = FakeEntity('source', 'Source')
    target = FakeEntity('target', 'Target')
    watcher = FakeEntity('watcher', 'Watcher')
    bystander = FakeEntity('bystander', 'Bystander')
    battle_map = FakeMap(
        [source, target, watcher, bystander],
        visible_pairs={
            ('watcher', 'source'),
            ('watcher', 'target'),
        },
    )
    logger, socketio = build_logger(
        {
            'source_user': [source],
            'target_user': [target],
            'watcher_user': [watcher],
            'bystander_user': [bystander],
        },
        {
            'source_user': ['player'],
            'target_user': ['player'],
            'watcher_user': ['player'],
            'bystander_user': ['player'],
            'dm': ['dm'],
        },
        battle_map,
    )

    logger.log('Source attacks Target', event={'event': 'attacked', 'source': source, 'target': target})

    delivered_sids = {call['to'] for call in socketio.calls if call['payload'].get('type') == 'console'}
    assert delivered_sids == {'sid-source', 'sid-target', 'sid-watcher', 'sid-dm'}

    assert len(logger.get_all_logs(username='watcher_user', roles=['player'])) == 1
    assert logger.get_all_logs(username='bystander_user', roles=['player']) == []
    assert len(logger.get_all_logs(username='dm', roles=['dm'])) == 1


def test_conversation_logs_are_emitted_only_to_participants_overhearers_and_dm():
    speaker = FakeEntity('speaker', 'Speaker')
    target = FakeEntity('target', 'Target')
    listener = FakeEntity('listener', 'Listener')
    distant = FakeEntity('distant', 'Distant')
    battle_map = FakeMap(
        [speaker, target, listener, distant],
        visible_pairs={
            ('target', 'speaker'),
            ('listener', 'speaker'),
        },
        in_range={
            ('speaker', 30): [target, listener],
        },
    )
    logger, socketio = build_logger(
        {
            'source_user': [speaker],
            'target_user': [target],
            'watcher_user': [listener],
            'bystander_user': [distant],
        },
        {
            'source_user': ['player'],
            'target_user': ['player'],
            'watcher_user': ['player'],
            'bystander_user': ['player'],
            'dm': ['dm'],
        },
        battle_map,
    )

    logger.log(
        'Speaker says hello',
        event={
            'event': 'conversation',
            'source': speaker,
            'targets': [target],
            'distance_ft': 30,
            'message': 'hello',
            'language': 'common',
        },
    )

    delivered_sids = {call['to'] for call in socketio.calls if call['payload'].get('type') == 'console'}
    assert delivered_sids == {'sid-source', 'sid-target', 'sid-watcher', 'sid-dm'}

    assert len(logger.get_all_logs(username='source_user', roles=['player'])) == 1
    assert len(logger.get_all_logs(username='watcher_user', roles=['player'])) == 1
    assert logger.get_all_logs(username='bystander_user', roles=['player']) == []


def test_entity_scoped_log_visibility_matches_entity_view():
    source = FakeEntity('source', 'Source')
    target = FakeEntity('target', 'Target')
    watcher = FakeEntity('watcher', 'Watcher')
    bystander = FakeEntity('bystander', 'Bystander')
    battle_map = FakeMap(
        [source, target, watcher, bystander],
        visible_pairs={
            ('watcher', 'source'),
            ('watcher', 'target'),
        },
    )
    logger, _socketio = build_logger(
        {
            'source_user': [source],
            'target_user': [target],
            'watcher_user': [watcher],
            'bystander_user': [bystander],
        },
        {
            'source_user': ['player'],
            'target_user': ['player'],
            'watcher_user': ['player'],
            'bystander_user': ['player'],
            'dm': ['dm'],
        },
        battle_map,
    )

    logger.log('Source attacks Target', event={'event': 'attacked', 'source': source, 'target': target})

    assert logger.get_logs_for_entity(source) == logger.get_all_logs(username='source_user', roles=['player'])
    assert logger.get_logs_for_entity(watcher) == logger.get_all_logs(username='watcher_user', roles=['player'])
    assert logger.get_logs_for_entity(bystander) == []