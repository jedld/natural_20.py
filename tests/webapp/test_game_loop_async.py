from unittest.mock import MagicMock

from webapp.utils import GameManagement


def _minimal_game_management():
    gm = GameManagement.__new__(GameManagement)
    gm.logger = MagicMock()
    gm.output_logger = MagicMock()
    gm.socketio = MagicMock()
    gm._game_loop_task_guard = __import__("threading").Lock()
    gm._game_loop_task_running = False
    gm.game_state_lock = __import__("threading").Lock()
    gm._run_game_loop_once = MagicMock()
    gm._game_loop_background = MagicMock()
    return gm


def test_schedule_game_loop_skips_when_already_running():
    gm = _minimal_game_management()
    gm._game_loop_task_running = True

    assert gm.schedule_game_loop() is False
    gm.socketio.start_background_task.assert_not_called()


def test_schedule_game_loop_starts_background_task():
    gm = _minimal_game_management()

    assert gm.schedule_game_loop(battle_start=True) is True
    gm.socketio.start_background_task.assert_called_once()
    assert gm._game_loop_task_running is True


def test_execute_game_loop_blocking_runs_inline():
    gm = _minimal_game_management()
    gm._run_game_loop_once = MagicMock()

    assert gm.execute_game_loop(blocking=True) is True
    gm._run_game_loop_once.assert_called_once_with(battle_start=True)
    gm.socketio.start_background_task.assert_not_called()
