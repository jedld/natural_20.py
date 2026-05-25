"""Flask bootstrap — composition root for the Natural 20 web VTT."""
import atexit
import logging
import os

import i18n
import natural20.session as GameSession
from flask import Flask, jsonify
from flask_cors import CORS
from flask_session import Session
from flask_socketio import SocketIO
from natural20.event_manager import EventManager

from natural20.player_character import PlayerCharacter
from utils import GameManagement, SocketIOOutputLogger
from webapp.blueprints.ai import ai_bp
from webapp.blueprints.assets import assets_bp
from webapp.blueprints.auth import auth_bp
from webapp.blueprints.battle import battle_bp
from webapp.blueprints.character import character_bp
from webapp.blueprints.dm import dm_bp
from webapp.blueprints.helpers.auth_utils import logged_in, roles_for_username, user_role
from webapp.blueprints.helpers.action_utils import action_type_to_class
from webapp.blueprints.helpers.campaign_config import load_campaign_config
from webapp.blueprints.helpers.conversation_wiring import wire_conversation_service
from webapp.blueprints.helpers.cors_config import (
    get_allowed_origins,
    origin_allowed,
    socketio_async_mode,
)
from webapp.blueprints.helpers.effects import register_effect_listeners
from webapp.blueprints.helpers.journal_utils import _record_narration_for_pcs
from webapp.blueprints.helpers.llm_init import (
    initialize_llm_from_env,
    register_game_context_functions,
)
from webapp.blueprints.helpers.perf import register_perf_instrumentation
from webapp.blueprints.helpers.runtime_state import register_globals
from webapp.blueprints.helpers.special_effects import (
    filter_effect_payload,
    has_enabled_effect_payloads,
    map_default_effect_payloads,
)
from webapp.blueprints.helpers.template_globals import (
    entities_controlled_by,
    entity_owners,
    register_template_globals,
)
from webapp.blueprints.helpers.pvp import autofill_pvp_battle_turn_order, pvp_team_config
from webapp.blueprints.navigation import navigation_bp
from webapp.blueprints.socketio_handlers import register_socketio_handlers
from webapp.entity_rag_handler import EntityRAGHandler
from webapp.game_context import GameContextProvider
from webapp.llm_conversation_controller import LLMConversationController
from webapp.llm_handler import LLMHandler, set_campaign_prompt_root
from webapp.mcp import MCPContext, register_mcp_blueprint

try:
    from dotenv import load_dotenv

    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
    else:
        parent_env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
        if os.path.exists(parent_env_path):
            load_dotenv(parent_env_path)
except ImportError:
    pass


def _env_flag(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return str(value).strip().lower() not in {'0', 'false', 'no', 'off', 'disabled'}


app = Flask(__name__, static_folder='static', static_url_path='/')
app.config['CHARACTER_BUILDER_ONLY'] = os.environ.get('CHARACTER_BUILDER_ONLY', 'false').lower() == 'true'

try:
    from flask_compress import Compress

    app.config.setdefault('COMPRESS_MIMETYPES', [
        'text/html', 'text/css', 'text/xml', 'text/plain',
        'application/json', 'application/javascript', 'application/xml',
        'image/svg+xml',
    ])
    app.config.setdefault('COMPRESS_LEVEL', 6)
    app.config.setdefault('COMPRESS_MIN_SIZE', 500)
    app.config.setdefault('COMPRESS_STREAMS', False)
    Compress(app)
except ImportError:
    logging.getLogger(__name__).warning("Flask-Compress not installed; responses will not be compressed")

try:
    _static_max_age = int(os.environ.get('N20_STATIC_MAX_AGE', 60 * 60 * 24))
except (TypeError, ValueError):
    _static_max_age = 60 * 60 * 24
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = _static_max_age

app.config['SPECIAL_EFFECTS_ENABLED'] = _env_flag('SPECIAL_EFFECTS_ENABLED', False)
app.config['NPC_LLM_COMBAT_ENABLED'] = _env_flag('NPC_LLM_COMBAT_ENABLED', False)

logger = logging.getLogger('werkzeug')
logger.setLevel(logging.INFO)
conversation_logger = logging.getLogger('n20.conversation')
conversation_logger.setLevel(logging.INFO)
for _handler in logger.handlers:
    conversation_logger.addHandler(_handler)
conversation_logger.propagate = False

allowed_origins = get_allowed_origins()
CORS(app, resources={r"/*": {"origins": allowed_origins, "supports_credentials": True}})

app.config['SECRET_KEY'] = 'fe9707b4704da2a96d0fd3cbbb465756e124b8c391c72a27ff32a062110de589'
app.config['SESSION_TYPE'] = 'filesystem'

socketio = SocketIO(
    app,
    cors_allowed_origins=lambda origin, environ=None: origin_allowed(origin, allowed_origins),
    async_mode=socketio_async_mode(),
    ping_timeout=120,
    ping_interval=30,
    max_http_buffer_size=1e8,
    logger=True,
    engineio_logger=True,
    manage_session=True,
    cookie='io',
    always_connect=True,
    message_queue=None,
    transports=['websocket', 'polling'],
    allow_upgrades=True,
    upgrade_timeout=10,
)
Session(app)


def builder_only_mode():
    return app.config.get('CHARACTER_BUILDER_ONLY', False)


_campaign = load_campaign_config()
LEVEL = _campaign['LEVEL']
index_data = _campaign['index_data']
TITLE = _campaign['TITLE']
TILE_PX = _campaign['TILE_PX']
LOGIN_BACKGROUND = _campaign['LOGIN_BACKGROUND']
CHARACTER_SELECTION_BACKGROUND = _campaign['CHARACTER_SELECTION_BACKGROUND']
BATTLEMAP = _campaign['BATTLEMAP']
OTHERMAPS = _campaign['OTHERMAPS']
SOUNDTRACKS = _campaign['SOUNDTRACKS']
LOGINS = _campaign['LOGINS']
DEFAULT_NPC_CONTROLLER = _campaign['DEFAULT_NPC_CONTROLLER']
CONTROLLERS = _campaign['CONTROLLERS']
AUTOSAVE = _campaign['AUTOSAVE']
DEFER_PLAYER_SPAWN = _campaign['DEFER_PLAYER_SPAWN']
EXTENSIONS = _campaign['EXTENSIONS']
MAP_PADDING = _campaign['MAP_PADDING']

active_effects = {}
active_effects_map = {}


@app.route('/health')
def health():
    return jsonify({"status": "ok"}), 200


output_logger = SocketIOOutputLogger(socketio)
output_logger.log("Server started", visibility='public')

event_manager = EventManager(output_logger=output_logger, movement_consolidation=True)
event_manager.standard_cli()

game_session = GameSession.Session(LEVEL, event_manager=event_manager)
game_session.render_for_text = False

current_game = GameManagement(
    game_session=game_session,
    map_location=BATTLEMAP,
    other_maps=OTHERMAPS,
    socketio=socketio,
    output_logger=output_logger,
    tile_px=TILE_PX,
    controllers=CONTROLLERS,
    npc_controller=DEFAULT_NPC_CONTROLLER,
    force_llm_npc_combat=app.config['NPC_LLM_COMBAT_ENABLED'],
    autosave=AUTOSAVE,
    system_logger=logger,
    soundtrack=SOUNDTRACKS,
    defer_player_spawn=DEFER_PLAYER_SPAWN,
)

_pvp_cfg = index_data.get('pvp_teams') or {}
current_game.pvp_enabled = bool(_pvp_cfg.get('enabled'))

output_logger.configure_persistence(
    campaign_log_db_getter=lambda: getattr(current_game, 'campaign_log_db', None)
)


@app.before_request
def _n20_bind_campaign_prompt_root():
    try:
        gs = getattr(current_game, 'game_session', None)
        rp = getattr(gs, 'root_path', None) if gs else None
        set_campaign_prompt_root(rp)
    except Exception:
        set_campaign_prompt_root(None)


_mcp_context = MCPContext(
    game_session_getter=lambda: game_session,
    current_game_getter=lambda: current_game,
    socketio_getter=lambda: socketio,
    output_logger_getter=lambda: output_logger,
    action_class_resolver=lambda action_type: action_type_to_class(action_type),
)
from webapp.mcp import build_default_registry as _mcp_build_default_registry  # noqa: E402

_mcp_registry = _mcp_build_default_registry()
try:
    register_mcp_blueprint(
        app,
        _mcp_context,
        registry=_mcp_registry,
        user_role_fn=lambda: user_role(),
    )
except Exception as _mcp_exc:  # noqa: BLE001
    logger.warning(f"Failed to register MCP blueprint: {_mcp_exc}")


def _shutdown_flush():
    try:
        getattr(current_game, 'shutdown_save_worker', lambda timeout=2.0: None)(timeout=3.0)
    except Exception:
        pass


atexit.register(_shutdown_flush)

game_context_provider = GameContextProvider(game_session, current_game)
i18n.set('locale', 'en')

for extension in EXTENSIONS:
    extension.init(app, current_game, game_session)

llm_handler = initialize_llm_from_env(LLMHandler)
register_game_context_functions(llm_handler, game_context_provider, _mcp_registry, _mcp_context)
llm_conversation_handler = LLMConversationController(llm_handler)
entity_rag_handler = EntityRAGHandler(game_session, current_game)

register_globals(
    app=app,
    socketio=socketio,
    current_game=current_game,
    game_session=game_session,
    llm_handler=llm_handler,
    LOGINS=LOGINS,
    CONTROLLERS=CONTROLLERS,
    index_data=index_data,
    active_effects=active_effects,
    active_effects_map=active_effects_map,
    output_logger=output_logger,
    LEVEL=LEVEL,
    builder_only_mode=builder_only_mode,
    event_manager=event_manager,
    OTHERMAPS=OTHERMAPS,
    logger=logger,
    TITLE=TITLE,
    LOGIN_BACKGROUND=LOGIN_BACKGROUND,
    CHARACTER_SELECTION_BACKGROUND=CHARACTER_SELECTION_BACKGROUND,
    game_context_provider=game_context_provider,
    TILE_PX=TILE_PX,
    MAP_PADDING=MAP_PADDING,
    entity_rag_handler=entity_rag_handler,
)

register_template_globals(app)

for blueprint in (assets_bp, auth_bp, ai_bp, navigation_bp, character_bp, battle_bp, dm_bp):
    app.register_blueprint(blueprint)

register_effect_listeners(_record_narration_for_pcs)

conversation_service, _conversation_exports = wire_conversation_service(
    app,
    current_game_getter=lambda: current_game,
    game_session=game_session,
    socketio=socketio,
    entity_rag_handler_getter=lambda: entity_rag_handler,
    llm_conversation_handler_getter=lambda: llm_conversation_handler,
    roles_for_username_getter=lambda: roles_for_username,
    entity_owners_getter=lambda: entity_owners,
    entities_controlled_by_getter=lambda: entities_controlled_by,
    logins_getter=lambda: LOGINS,
    logger=logger,
    level=LEVEL,
)
globals().update(_conversation_exports)

output_logger.configure_visibility(
    game_getter=lambda: current_game,
    role_lookup=roles_for_username,
    controlled_entities_lookup=entities_controlled_by,
)

register_perf_instrumentation(app, socketio, logger)
register_socketio_handlers(socketio)


if __name__ == '__main__':
    socketio.run(
        app,
        debug=False,
        host='0.0.0.0',
        port=5001,
        allow_unsafe_werkzeug=True,
        use_reloader=False,
        log_output=True,
    )
