from types import SimpleNamespace
from unittest.mock import MagicMock

from natural20.web.web_controller import ManualControl
from webapp.utils import GameManagement


def _make_battle(current_turn):
    battle = MagicMock()
    battle.current_turn.return_value = current_turn
    battle.current_turn_index = 3
    battle.battle_ends.return_value = False
    return battle


def test_game_loop_emits_turn_state_before_manual_handoff():
    current_turn = MagicMock()
    current_turn.reset_turn = MagicMock()
    current_turn.dead.return_value = False
    current_turn.unconscious.return_value = False

    battle = _make_battle(current_turn)

    gm = GameManagement.__new__(GameManagement)
    gm.logger = MagicMock()
    gm.socketio = MagicMock()
    gm.battle = battle
    gm.get_current_battle = MagicMock(return_value=battle)
    gm.ai_loop = MagicMock(side_effect=ManualControl())

    gm.game_loop()

    emitted = [call.args[1] for call in gm.socketio.emit.call_args_list]
    assert emitted[:2] == [
        {'type': 'initiative', 'message': {'index': 3}},
        {'type': 'turn', 'message': {}},
    ]
    current_turn.reset_turn.assert_called_once_with(battle)
    gm.logger.info.assert_called_once_with('waiting for user to end turn.')