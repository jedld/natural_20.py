# Shim module to support tests importing `game_context` from this folder.
# Re-exports symbols from the app package.
from webapp.game_context import *  # noqa: F401,F403
