"""GenericEventHandler campaign_event broadcasts to EventManager."""

from natural20.concern.generic_event_handler import GenericEventHandler
from natural20.event_manager import EventManager


def test_campaign_event_reaches_event_manager():
    seen = []
    manager = EventManager()
    manager.register_event_listener('plea_letter_delivered', seen.append)

    class _Session:
        event_manager = manager

        def t(self, text, options=None):
            return text

    class _Entity:
        def label(self):
            return 'Arrigal'

        def eval_if(self, *_args, **_kwargs):
            return True

    handler = GenericEventHandler(
        _Session(),
        None,
        {'campaign_event': 'plea_letter_delivered'},
    )
    handler.handle(_Entity(), opts={'speaker': 'pc'})
    assert len(seen) == 1
    assert seen[0]['event'] == 'plea_letter_delivered'
    assert seen[0]['speaker'] == 'pc'
