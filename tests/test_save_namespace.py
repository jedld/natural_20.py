import os
import tempfile
import shutil
from natural20.event_manager import EventManager
from natural20.session import Session


class DummySocket:
    def emit(self, *a, **k):
        pass


class DummyLogger:
    def info(self, *a, **k):
        pass

    def warning(self, *a, **k):
        pass

    def error(self, *a, **k):
        pass

    def get_log_snapshot(self):
        return []

    def restore_log_snapshot(self, snapshot):
        pass


def make_game_management(tmp_save_dir, game_name):
    # set env var for SAVE_DIR so GameManagement will use it
    os.environ['SAVE_DIR'] = tmp_save_dir
    em = EventManager()
    em.standard_cli()
    sess = Session(root_path='tests/fixtures', event_manager=em)
    # override the game_properties name for namespacing
    sess.game_properties = sess.game_properties or {}
    sess.game_properties['name'] = game_name

    from webapp.utils import GameManagement

    gm = GameManagement(game_session=sess,
                        map_location='maps/game_map',
                        other_maps={},
                        socketio=DummySocket(),
                        output_logger=DummyLogger(),
                        tile_px=16,
                        controllers=[],
                        npc_controller=None,
                        autosave=False,
                        auto_battle=False,
                        system_logger=DummyLogger(),
                        soundtrack=[])
    return gm


def test_namespaced_save_created(tmp_path):
    tmpdir = str(tmp_path)
    gm = make_game_management(tmpdir, 'Test Game One')
    # directory should be created and include sanitized game name
    assert os.path.isdir(gm.save_dir)
    gm.save_game(name='my-save')
    files = os.listdir(gm.save_dir)
    assert any('my-save' in f for f in files)


def test_two_games_different_dirs(tmp_path):
    tmpdir = str(tmp_path)
    gm1 = make_game_management(tmpdir, 'Game A')
    gm1.save_game(name='a')
    gm2 = make_game_management(tmpdir, 'Game B')
    gm2.save_game(name='b')

    assert os.path.isdir(gm1.save_dir)
    assert os.path.isdir(gm2.save_dir)
    assert gm1.save_dir != gm2.save_dir
    # ensure each directory contains the respective named save
    files1 = os.listdir(gm1.save_dir)
    files2 = os.listdir(gm2.save_dir)
    assert any('a' in f for f in files1)
    assert any('b' in f for f in files2)
