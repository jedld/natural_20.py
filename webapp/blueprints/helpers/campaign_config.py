"""Load campaign ``index.json`` settings for the webapp bootstrap."""
import json
import os


def load_campaign_config(level=None):
    """Return campaign settings dict from ``index.json`` under ``level``."""
    level = level or os.getenv('TEMPLATE_DIR', '../templates')
    with open(os.path.join(level, 'index.json')) as f:
        index_data = json.load(f)

    return {
        'LEVEL': level,
        'index_data': index_data,
        'TITLE': index_data['title'],
        'TILE_PX': int(index_data['tile_size']),
        'LOGIN_BACKGROUND': index_data['login_background'],
        'CHARACTER_SELECTION_BACKGROUND': index_data.get(
            'character_selection_background',
            index_data['login_background'],
        ),
        'BATTLEMAP': index_data['map'],
        'OTHERMAPS': index_data.get('other_maps', {}),
        'SOUNDTRACKS': index_data['soundtracks'],
        'LOGINS': index_data['logins'],
        'DEFAULT_NPC_CONTROLLER': index_data.get('npc_default_controller', 'ai'),
        'CONTROLLERS': index_data['default_controllers'],
        'AUTOSAVE': index_data.get('autosave', False),
        'DEFER_PLAYER_SPAWN': index_data.get('defer_player_spawn', False),
        'EXTENSIONS': [],
        'MAP_PADDING': [6, 15],
    }
