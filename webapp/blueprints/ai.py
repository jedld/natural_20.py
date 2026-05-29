"""AI Chatbot Blueprint.

Contains all routes under /ai/ for DM AI assistant functionality.
"""
import requests

from flask import Blueprint, request, jsonify, session

from webapp.blueprints.helpers.runtime_state import (
    get_current_game,
    get_game_context_provider,
    get_llm_handler,
    get_logger,
)
from webapp.blueprints.helpers.llm_init import configure_llm_handler_from_environment

ai_bp = Blueprint('ai', __name__)

DM_AI_CHAT_SESSION_KEY = 'dm_ai_chat_history'


def _user_role():
    """Return the roles for the current user."""
    from webapp.blueprints.helpers.runtime_state import get_logins
    username = session.get('username')
    if not username:
        return []
    logins = get_logins()
    for login in logins:
        if isinstance(login, dict) and login.get('name', '').lower() == username:
            return login.get('role', [])
    return []


def _restore_dm_ai_history_from_session():
    """Reload in-memory DM assistant history after page refresh or worker swap."""
    if 'dm' not in _user_role():
        return
    llm_handler = get_llm_handler()
    if llm_handler.get_conversation_history():
        return
    stored = session.get(DM_AI_CHAT_SESSION_KEY)
    if stored:
        llm_handler.conversation_history = list(stored)
        return
    current_game = get_current_game()
    db = getattr(current_game, 'campaign_log_db', None)
    if db is not None:
        try:
            rows = db.dm_assistant_history_for_llm()
            if rows:
                llm_handler.conversation_history = rows
        except Exception as exc:
            logger = get_logger()
            logger.debug(f"DM assistant history restore from DB skipped: {exc}")


def _persist_dm_ai_history_to_session():
    if 'dm' not in _user_role():
        return
    llm_handler = get_llm_handler()
    from webapp.llm_handler import LLMHandler
    session[DM_AI_CHAT_SESSION_KEY] = LLMHandler.conversation_history_for_storage(
        llm_handler.get_conversation_history()
    )
    session.modified = True


def _log_dm_assistant_turn(role, content):
    current_game = get_current_game()
    db = getattr(current_game, 'campaign_log_db', None)
    if db is None:
        return
    try:
        db.append_dm_turn(role, content, username=session.get('username'))
    except Exception as exc:
        logger = get_logger()
        logger.debug(f"DM assistant campaign log skipped: {exc}")


@ai_bp.route('/ai/initialize', methods=['POST'], endpoint='ai_initialize')
def ai_initialize():
    """Initialize the AI provider."""
    if 'dm' not in _user_role():
        return jsonify({'success': False, 'error': 'DM access required'}), 403

    try:
        llm_handler = get_llm_handler()
        logger = get_logger()
        provider = request.form.get('provider')
        api_key = request.form.get('api_key')
        base_url = request.form.get('base_url')
        model = request.form.get('model')

        if not provider:
            return jsonify({'success': False, 'error': 'Provider is required'})

        config = {}
        if api_key:
            config['api_key'] = api_key
        if base_url:
            config['base_url'] = base_url
        if model:
            config['model'] = model

        success = llm_handler.initialize_provider(provider, config)

        if success:
            provider_info = llm_handler.get_provider_info()
            response_data = {'success': True}

            if provider_info.get('current_model'):
                response_data['model'] = provider_info['current_model']
            if provider_info.get('available_models'):
                response_data['available_models'] = provider_info['available_models']

            return jsonify(response_data)
        else:
            return jsonify({'success': False, 'error': f'Failed to initialize {provider} provider'})

    except Exception as e:
        logger = get_logger()
        logger.error(f"Error initializing AI: {e}")
        return jsonify({'success': False, 'error': str(e)})


@ai_bp.route('/ai/initialize-from-env', methods=['POST'], endpoint='ai_initialize_from_env')
def ai_initialize_from_env():
    """Re-apply ``LLM_PROVIDER`` / API keys to the shared handler (same as NPC/dialog LLM)."""
    if 'dm' not in _user_role():
        return jsonify({'success': False, 'error': 'DM access required'}), 403
    try:
        llm_handler = get_llm_handler()
        logger = get_logger()
        if getattr(llm_handler, 'current_provider', None):
            info = llm_handler.get_provider_info()
            return jsonify({'success': bool(info.get('initialized')), 'info': info})
        ok = configure_llm_handler_from_environment(llm_handler)
        info = llm_handler.get_provider_info()
        return jsonify({
            'success': bool(ok and info.get('initialized')),
            'info': info,
        })
    except Exception as e:
        logger = get_logger()
        logger.error(f"Error syncing LLM from environment: {e}")
        return jsonify({'success': False, 'error': str(e)})


@ai_bp.route('/ai/chat', methods=['POST'], endpoint='ai_chat')
def ai_chat():
    """Send a message to the AI and get a response."""
    if 'dm' not in _user_role():
        return jsonify({'success': False, 'error': 'DM access required'}), 403

    try:
        llm_handler = get_llm_handler()
        current_game = get_current_game()
        logger = get_logger()
        message = request.form.get('message')

        if not message:
            return jsonify({'success': False, 'error': 'Message is required'})

        _restore_dm_ai_history_from_session()
        _log_dm_assistant_turn('user', message)

        context = llm_handler.get_game_context()
        username = session.get('username')
        current_pov_entity = current_game.get_pov_entity_for_user(username)
        context['session'] = {
            'username': session.get('username'),
            'role': _user_role(),
            'current_map': current_game.get_map_for_user(session['username']).name,
            'pov_entity': current_pov_entity.entity_uid if current_pov_entity else None
        }
        response = llm_handler.send_message(message, context)
        _log_dm_assistant_turn('assistant', response)
        _persist_dm_ai_history_to_session()

        return jsonify({'success': True, 'response': response})

    except Exception as e:
        logger = get_logger()
        logger.error(f"Error in AI chat: {e}")
        return jsonify({'success': False, 'error': str(e)})


@ai_bp.route('/ai/context', methods=['GET'], endpoint='ai_get_context')
def ai_get_context():
    """Get current game context for the AI."""
    if 'dm' not in _user_role():
        return jsonify({'success': False, 'error': 'DM access required'}), 403

    try:
        llm_handler = get_llm_handler()
        logger = get_logger()
        context = llm_handler.get_game_context()

        context['session'] = {
            'username': session.get('username'),
            'role': _user_role()
        }

        return jsonify({'success': True, 'context': context})

    except Exception as e:
        logger = get_logger()
        logger.error(f"Error getting game context: {e}")
        return jsonify({'success': False, 'error': str(e)})


@ai_bp.route('/ai/clear-history', methods=['POST'], endpoint='ai_clear_history')
def ai_clear_history():
    """Clear the AI conversation history."""
    if 'dm' not in _user_role():
        return jsonify({'success': False, 'error': 'DM access required'}), 403

    try:
        llm_handler = get_llm_handler()
        current_game = get_current_game()
        logger = get_logger()
        llm_handler.clear_history()
        session.pop(DM_AI_CHAT_SESSION_KEY, None)
        session.modified = True
        db = getattr(current_game, 'campaign_log_db', None)
        if db is not None:
            db.clear_category('dm_assistant')
        return jsonify({'success': True})

    except Exception as e:
        logger = get_logger()
        logger.error(f"Error clearing AI history: {e}")
        return jsonify({'success': False, 'error': str(e)})


@ai_bp.route('/ai/history', methods=['GET'], endpoint='ai_get_history')
def ai_get_history():
    """Get the AI conversation history."""
    if 'dm' not in _user_role():
        return jsonify({'success': False, 'error': 'DM access required'}), 403

    try:
        llm_handler = get_llm_handler()
        logger = get_logger()
        _restore_dm_ai_history_from_session()
        from webapp.llm_handler import LLMHandler
        history = LLMHandler.displayable_conversation_history(
            llm_handler.get_conversation_history()
        )
        return jsonify({'success': True, 'history': history})

    except Exception as e:
        logger = get_logger()
        logger.error(f"Error getting AI history: {e}")
        return jsonify({'success': False, 'error': str(e)})


@ai_bp.route('/ai/ollama/models', methods=['GET'], endpoint='ai_get_ollama_models')
def ai_get_ollama_models():
    """Get available Ollama models."""
    if 'dm' not in _user_role():
        return jsonify({'success': False, 'error': 'DM access required'}), 403

    try:
        logger = get_logger()
        base_url = request.args.get('base_url', 'http://localhost:11434')

        response = requests.get(f"{base_url}/api/tags", timeout=10)
        if response.status_code == 200:
            data = response.json()
            models = [model['name'] for model in data.get('models', [])]
            return jsonify({'success': True, 'models': models})
        else:
            return jsonify({'success': False, 'error': f'Ollama API error: {response.status_code}'})

    except requests.exceptions.RequestException as e:
        logger = get_logger()
        logger.error(f"Error connecting to Ollama: {e}")
        return jsonify({'success': False, 'error': f'Failed to connect to Ollama: {str(e)}'})
    except Exception as e:
        logger = get_logger()
        logger.error(f"Error getting Ollama models: {e}")
        return jsonify({'success': False, 'error': str(e)})


@ai_bp.route('/ai/llama_cpp/models', methods=['GET'], endpoint='ai_get_llama_cpp_models')
def ai_get_llama_cpp_models():
    """Get available llama.cpp models from an OpenAI-compatible server."""
    if 'dm' not in _user_role():
        return jsonify({'success': False, 'error': 'DM access required'}), 403

    try:
        logger = get_logger()
        base_url = request.args.get('base_url', 'http://localhost:8011').rstrip('/')
        api_key = request.args.get('api_key', 'llama-cpp')
        headers = {'Authorization': f'Bearer {api_key}'}

        response = requests.get(f"{base_url}/v1/models", headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            from webapp.llm_handler import LlamaCppProvider
            models = LlamaCppProvider._extract_model_ids(data)
            return jsonify({'success': True, 'models': models})
        return jsonify({'success': False, 'error': f'llama.cpp API error: {response.status_code}'})

    except requests.exceptions.RequestException as e:
        logger = get_logger()
        logger.error(f"Error connecting to llama.cpp: {e}")
        return jsonify({'success': False, 'error': f'Failed to connect to llama.cpp: {str(e)}'})
    except Exception as e:
        logger = get_logger()
        logger.error(f"Error getting llama.cpp models: {e}")
        return jsonify({'success': False, 'error': str(e)})


@ai_bp.route('/ai/set-model', methods=['POST'], endpoint='ai_set_model')
def ai_set_model():
    """Set the model for the current AI provider."""
    if 'dm' not in _user_role():
        return jsonify({'success': False, 'error': 'DM access required'}), 403

    try:
        llm_handler = get_llm_handler()
        logger = get_logger()
        model_name = request.form.get('model')

        if not model_name:
            return jsonify({'success': False, 'error': 'Model name is required'})

        success = llm_handler.set_model(model_name)

        if success:
            return jsonify({'success': True, 'model': model_name})
        else:
            return jsonify({'success': False, 'error': f'Failed to set model: {model_name}'})

    except Exception as e:
        logger = get_logger()
        logger.error(f"Error setting AI model: {e}")
        return jsonify({'success': False, 'error': str(e)})


@ai_bp.route('/ai/provider-info', methods=['GET'], endpoint='ai_get_provider_info')
def ai_get_provider_info():
    """Get information about the current AI provider."""
    if 'dm' not in _user_role():
        return jsonify({'success': False, 'error': 'DM access required'}), 403

    try:
        llm_handler = get_llm_handler()
        logger = get_logger()
        info = llm_handler.get_provider_info()
        return jsonify({'success': True, 'info': info})

    except Exception as e:
        logger = get_logger()
        logger.error(f"Error getting provider info: {e}")
        return jsonify({'success': False, 'error': str(e)})


@ai_bp.route('/ai/entity-details', methods=['GET'], endpoint='ai_get_entity_details')
def ai_get_entity_details():
    """Get detailed information about a specific entity for RAG."""
    if 'dm' not in _user_role():
        return jsonify({'success': False, 'error': 'DM access required'}), 403

    try:
        game_context_provider = get_game_context_provider()
        logger = get_logger()
        entity_name = request.args.get('entity_name')
        if not entity_name:
            return jsonify({'success': False, 'error': 'Entity name is required'})

        details = game_context_provider.get_entity_details(entity_name)
        return jsonify({'success': True, 'details': details})

    except Exception as e:
        logger = get_logger()
        logger.error(f"Error getting entity details: {e}")
        return jsonify({'success': False, 'error': str(e)})


@ai_bp.route('/ai/terrain-info', methods=['GET'], endpoint='ai_get_terrain_info')
def ai_get_terrain_info():
    """Get terrain information for a specific location for RAG."""
    if 'dm' not in _user_role():
        return jsonify({'success': False, 'error': 'DM access required'}), 403

    try:
        game_context_provider = get_game_context_provider()
        logger = get_logger()
        x = request.args.get('x', type=int)
        y = request.args.get('y', type=int)

        if x is None or y is None:
            return jsonify({'success': False, 'error': 'X and Y coordinates are required'})

        terrain_info = game_context_provider.get_map_terrain_info(x, y)
        return jsonify({'success': True, 'terrain_info': terrain_info})

    except Exception as e:
        logger = get_logger()
        logger.error(f"Error getting terrain info: {e}")
        return jsonify({'success': False, 'error': str(e)})


@ai_bp.route('/ai/available-actions', methods=['GET'], endpoint='ai_get_available_actions')
def ai_get_available_actions():
    """Get available actions for a specific entity for RAG."""
    if 'dm' not in _user_role():
        return jsonify({'success': False, 'error': 'DM access required'}), 403

    try:
        game_context_provider = get_game_context_provider()
        logger = get_logger()
        entity_name = request.args.get('entity_name')
        if not entity_name:
            return jsonify({'success': False, 'error': 'Entity name is required'})

        actions = game_context_provider.get_available_actions(entity_name)
        return jsonify({'success': True, 'actions': actions})

    except Exception as e:
        logger = get_logger()
        logger.error(f"Error getting available actions: {e}")
        return jsonify({'success': False, 'error': str(e)})
