"""GenericEventHandler campaign_event broadcasts to EventManager."""

from natural20.concern.generic_event_handler import GenericEventHandler, normalize_session_flags
from natural20.event_manager import EventManager
from natural20.session import Session


class _Session:
    def __init__(self, manager=None):
        self.event_manager = manager or EventManager()
        self.session_state = {}

    def t(self, text, options=None):
        return text

    def update_state(self, state):
        self.session_state.update(state)


class _Entity:
    def label(self):
        return 'Arrigal'

    def eval_if(self, *_args, **_kwargs):
        return True


def test_campaign_event_reaches_event_manager():
    seen = []
    manager = EventManager()
    manager.register_event_listener('plea_letter_delivered', seen.append)

    handler = GenericEventHandler(
        _Session(manager),
        None,
        {'campaign_event': 'plea_letter_delivered'},
    )
    handler.handle(_Entity(), opts={'speaker': 'pc'})
    assert len(seen) == 1
    assert seen[0]['event'] == 'plea_letter_delivered'
    assert seen[0]['speaker'] == 'pc'


def test_normalize_session_flags_shapes():
    assert normalize_session_flags('dungeon_cleared') == {'dungeon_cleared': True}
    assert normalize_session_flags({'a': True, 'b': 1}) == {'a': True, 'b': 1}
    assert normalize_session_flags(['a', {'b': False}]) == {'a': True, 'b': False}
    assert normalize_session_flags(None) == {}


def test_set_session_runs_before_campaign_event():
    seen = []
    session = _Session()

    def _listener(event):
        seen.append(dict(session.session_state))

    session.event_manager.register_event_listener('dungeon_cleared', _listener)
    handler = GenericEventHandler(
        session,
        None,
        {
            'set_session': {'dungeon_cleared': True},
            'campaign_event': 'dungeon_cleared',
        },
    )
    handler.handle(_Entity())
    assert session.session_state['dungeon_cleared'] is True
    assert seen == [{'dungeon_cleared': True}]


def test_update_state_target_session_accepts_string_flag():
    session = _Session()
    handler = GenericEventHandler(
        session,
        None,
        {'update_state': {'target': 'session', 'state': 'door_open'}},
    )
    handler.handle(_Entity())
    assert session.session_state['door_open'] is True


def test_npc_died_sets_session_flag_and_campaign_event():
    seen = []
    session = Session(root_path='tests/fixtures', event_manager=EventManager())
    session.event_manager.register_event_listener('boss_defeated', seen.append)
    npc = session.npc('goblin', {
        'overrides': {
            'events': [
                {
                    'event': 'died',
                    'set_session': {'boss_defeated': True},
                    'campaign_event': 'boss_defeated',
                }
            ]
        }
    })
    npc.make_dead()
    assert session.session_state.get('boss_defeated') is True
    assert len(seen) == 1
    assert seen[0]['event'] == 'boss_defeated'
    assert seen[0]['source'] is npc
