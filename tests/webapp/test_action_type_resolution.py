import os
import sys

WEBAPP_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'webapp')
if WEBAPP_DIR not in sys.path:
    sys.path.insert(0, WEBAPP_DIR)

template_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'templates'))
os.environ.setdefault('TEMPLATE_DIR', template_root)

from webapp.app import resolve_requested_action_type
from natural20.actions.use_item_action import UseItemAction


class FakeAction:
    def __init__(self, action_type):
        self.action_type = action_type


class FakeEntity:
    def __init__(self, actions):
        self._actions = actions

    def available_actions(self, session, battle, auto_target=False, map=None):
        return self._actions


class FakeUseItemAction(UseItemAction):
    pass


def test_resolve_requested_action_type_prefers_explicit_request():
    entity = FakeEntity([FakeUseItemAction(None, None, 'use_item')])

    resolved = resolve_requested_action_type(
        entity,
        session=None,
        battle=None,
        battle_map=None,
        action_class=FakeUseItemAction,
        requested_action_type='explicit_use_item',
    )

    assert resolved == 'explicit_use_item'


def test_resolve_requested_action_type_infers_from_available_actions():
    entity = FakeEntity([FakeUseItemAction(None, None, 'use_item')])

    resolved = resolve_requested_action_type(
        entity,
        session=None,
        battle=None,
        battle_map=None,
        action_class=FakeUseItemAction,
        requested_action_type=None,
    )

    assert resolved == 'use_item'
