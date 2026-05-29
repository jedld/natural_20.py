"""Lazy accessors for app-level global state.

These functions return the mutable globals that live on ``webapp.app``
(Flask app, SocketIO server, current game, session, LLM handler, etc.).
Blueprints call these instead of importing the globals directly so that
the helper modules remain importable without pulling in the entire app.
"""

# All globals are accessed through a lazy registry to avoid circular imports.
# ``webapp.app`` calls ``register_globals()`` at module load time.

_globals = {}


def register_globals(**kwargs):
    """Bind app-level globals so helper functions can access them.

    Call once from ``webapp.app`` after all globals are initialized.
    """
    _globals.update(kwargs)


def get_app():
    """Return the Flask app instance."""
    return _globals['app']


def get_socketio():
    """Return the Flask-SocketIO server instance."""
    return _globals['socketio']


def get_current_game():
    """Return the current ``GameManagement`` instance."""
    return _globals['current_game']


def get_game_session():
    """Return the current ``Session`` instance."""
    return _globals['game_session']


def set_game_session(session):
    """Replace the module-level ``game_session`` reference (e.g. after load)."""
    _globals['game_session'] = session
    try:
        import webapp.app as app_module
        app_module.game_session = session
    except Exception:
        pass


def get_perf_lock():
    """Return the performance-stats threading lock."""
    return _globals['perf_lock']


def get_perf_stats():
    """Return the mutable performance-stats dict."""
    return _globals['perf_stats']


def get_llm_handler():
    """Return the shared LLM handler."""
    return _globals['llm_handler']


def get_logins():
    """Return the mutable ``LOGINS`` list."""
    return _globals['LOGINS']


def get_controllers():
    """Return the mutable ``CONTROLLERS`` list."""
    return _globals['CONTROLLERS']


def get_index_data():
    """Return the loaded ``index_data`` dict."""
    return _globals['index_data']


def get_active_effects():
    """Return the module-level ``active_effects`` dict."""
    return _globals['active_effects']


def get_active_effects_map():
    """Return the module-level ``active_effects_map`` dict."""
    return _globals['active_effects_map']


def get_output_logger():
    """Return the ``SocketIOOutputLogger`` instance."""
    return _globals['output_logger']


def get_level():
    """Return the ``LEVEL`` (template directory) string."""
    return _globals['LEVEL']


def get_builder_only_mode():
    """Return the ``builder_only_mode`` flag (calls the function if needed)."""
    val = _globals.get('builder_only_mode', False)
    if callable(val):
        return val()
    return val


def get_event_manager():
    """Return the ``EventManager`` instance."""
    return _globals['event_manager']


def get_othermaps():
    """Return the mutable ``OTHERMAPS`` dict."""
    return _globals['OTHERMAPS']


def get_logger():
    """Return the Flask/werkzeug logger instance."""
    return _globals.get('logger')


def get_title():
    """Return the campaign title string."""
    return _globals.get('TITLE', '')


def get_login_background():
    """Return the login background image path."""
    return _globals.get('LOGIN_BACKGROUND', '')


def get_character_selection_background():
    """Return the character selection background image path."""
    return _globals.get('CHARACTER_SELECTION_BACKGROUND', '')


def get_game_context_provider():
    """Return the ``GameContextProvider`` instance."""
    return _globals.get('game_context_provider')


def get_tile_px():
    """Return the tile size in pixels from index.json."""
    return _globals.get('TILE_PX', 70)


def get_map_padding():
    """Return the map renderer padding tuple."""
    return _globals.get('MAP_PADDING', [6, 15])


def get_entity_rag_handler():
    """Return the ``EntityRAGHandler`` instance."""
    return _globals.get('entity_rag_handler')
