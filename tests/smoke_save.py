import os
import pprint
from natural20.session import Session
from natural20.event_manager import EventManager
from webapp.utils import GameManagement

class DummySocket:
    def emit(self, *args, **kwargs):
        pass

class DummyLogger:
    def info(self, *a, **k):
        pass
    def warning(self, *a, **k):
        pass
    def error(self, *a, **k):
        pass

if __name__ == '__main__':
    em = EventManager()
    em.standard_cli()
    sess = Session(root_path='tests/fixtures', event_manager=em)
    gm = GameManagement(game_session=sess, map_location='maps/game_map', other_maps={}, socketio=DummySocket(), output_logger=DummyLogger(), tile_px=16, controllers=[], npc_controller=None, autosave=False, auto_battle=False, system_logger=DummyLogger(), soundtrack=[])
    print('save_dir:', gm.save_dir)
    gm.save_game(name='smoke test')
    print('After save, files:')
    try:
        for f in sorted(os.listdir(gm.save_dir)):
            print(' -', f)
    except Exception as e:
        print('List failed:', e)
