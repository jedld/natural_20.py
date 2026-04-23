"""Test that check_and_notify_map_change emits the triggering entity_uid.

This guarantees the web UI can auto-focus on the character that just
stepped onto a teleporter / stairs / ladder once the new map renders.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from webapp.utils import GameManagement


def _make_minimal_gm():
    """Construct a GameManagement-like shell without running __init__."""
    gm = GameManagement.__new__(GameManagement)
    gm.game_state_lock = MagicMock()
    gm.game_state_lock.__enter__ = MagicMock(return_value=None)
    gm.game_state_lock.__exit__ = MagicMock(return_value=False)
    gm.logger = MagicMock()
    gm.socketio = MagicMock()
    gm.username_to_sid = {"alice": ["sid-1", "sid-2"]}
    gm.switch_map_for_user = MagicMock()
    return gm


def test_switch_map_emit_includes_entity_uid():
    gm = _make_minimal_gm()
    pov_map = SimpleNamespace(name="dungeon-1")
    new_map = SimpleNamespace(name="dungeon-2")
    pov_entity = SimpleNamespace(entity_uid="ent-42")

    gm.get_map_for_entity = MagicMock(return_value=new_map)

    gm.check_and_notify_map_change(pov_map, pov_entity, "alice")

    gm.switch_map_for_user.assert_called_once_with("alice", "dungeon-2")
    assert gm.socketio.emit.call_count == 2
    for call in gm.socketio.emit.call_args_list:
        event_name, payload = call.args[0], call.args[1]
        assert event_name == "message"
        assert payload["type"] == "switch_map"
        assert payload["message"] == {"map": "dungeon-2", "entity_uid": "ent-42"}


def test_switch_map_emit_handles_entity_without_uid():
    gm = _make_minimal_gm()
    pov_map = SimpleNamespace(name="a")
    new_map = SimpleNamespace(name="b")
    pov_entity = object()  # no entity_uid attribute

    gm.get_map_for_entity = MagicMock(return_value=new_map)
    gm.check_and_notify_map_change(pov_map, pov_entity, "alice")

    payload = gm.socketio.emit.call_args.args[1]
    assert payload["message"]["map"] == "b"
    assert payload["message"]["entity_uid"] is None


def test_no_emit_when_map_unchanged():
    gm = _make_minimal_gm()
    same_map = SimpleNamespace(name="same")
    gm.get_map_for_entity = MagicMock(return_value=same_map)

    gm.check_and_notify_map_change(same_map, SimpleNamespace(entity_uid="x"), "alice")

    gm.switch_map_for_user.assert_not_called()
    gm.socketio.emit.assert_not_called()
