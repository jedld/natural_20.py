"""LLM handler initialization extracted from app.py.

Provides ``configure_llm_handler_from_environment()``, ``initialize_llm_from_env()``,
and ``register_game_context_functions()`` for wiring the LLM handler with game
context functions and the MCP bridge.
"""

import logging
import os

logger = logging.getLogger(__name__)


def configure_llm_handler_from_environment(handler):
    """Apply ``LLM_PROVIDER`` and related env vars to an existing handler.

    Used at process startup and when the DM UI asks to sync from server config.
    Returns True if a provider was initialized successfully.
    """
    llm_provider = os.environ.get('LLM_PROVIDER', 'llama_cpp').lower()

    if llm_provider == 'openai':
        api_key = os.environ.get('OPENAI_API_KEY')
        base_url = os.environ.get('OPENAI_BASE_URL')
        model = os.environ.get('OPENAI_MODEL', 'gpt-4o')

        if not api_key:
            logger.warning("OPENAI_API_KEY not set, LLM features will be disabled")
            return False

        config = {'api_key': api_key, 'model': model}
        if base_url:
            config['base_url'] = base_url

        success = handler.initialize_provider('openai', config)
        if success:
            logger.info(f"Initialized OpenAI provider with model: {model}")
        else:
            logger.error("Failed to initialize OpenAI provider")
        return success

    if llm_provider == 'anthropic':
        api_key = os.environ.get('ANTHROPIC_API_KEY')
        model = os.environ.get('ANTHROPIC_MODEL', 'claude-3-5-sonnet-20241022')

        if not api_key:
            logger.warning("ANTHROPIC_API_KEY not set, LLM features will be disabled")
            return False

        config = {'api_key': api_key, 'model': model}
        success = handler.initialize_provider('anthropic', config)
        if success:
            logger.info(f"Initialized Anthropic provider with model: {model}")
        else:
            logger.error("Failed to initialize Anthropic provider")
        return success

    if llm_provider == 'ollama':
        base_url = os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434')
        model = os.environ.get('OLLAMA_MODEL', 'gemma3:27b')
        config = {'base_url': base_url, 'model': model}
        success = handler.initialize_provider('ollama', config)
        if success:
            logger.info(f"Initialized Ollama provider with model: {model} at {base_url}")
        else:
            logger.error(f"Failed to initialize Ollama provider: {config}")
        return success

    if llm_provider in ('llama_cpp', 'llama.cpp', 'llamacpp'):
        base_url = os.environ.get('LLAMA_CPP_BASE_URL', 'http://localhost:8011')
        model = os.environ.get('LLAMA_CPP_MODEL', os.environ.get('N20_LLM_MODEL'))
        api_key = os.environ.get('LLAMA_CPP_API_KEY', 'llama-cpp')

        config = {'base_url': base_url, 'api_key': api_key}
        if model:
            config['model'] = model

        success = handler.initialize_provider('llama_cpp', config)
        if success:
            logger.info(
                f"Initialized llama.cpp provider with model: "
                f"{getattr(handler.current_provider, 'current_model', model)} at {base_url}"
            )
        else:
            logger.error(f"Failed to initialize llama.cpp provider: {config}")
        return success

    logger.warning(f"Unknown LLM provider: {llm_provider}, using mock provider")
    return handler.initialize_provider('mock', {})


def initialize_llm_from_env(llm_handler_class):
    """Construct a handler and configure it from environment variables.

    Args:
        llm_handler_class: The LLMHandler class to instantiate (passed in to
            avoid importing webapp.llm_handler here).
    """
    llm_handler = llm_handler_class()
    configure_llm_handler_from_environment(llm_handler)
    return llm_handler


def register_game_context_functions(llm_handler, game_context_provider, mcp_registry, mcp_context):
    """Register all game context functions with the LLM handler.

    Args:
        llm_handler: The active LLMHandler instance.
        game_context_provider: The GameContextProvider instance.
        mcp_registry: The MCP ToolRegistry instance.
        mcp_context: The MCPContext instance.
    """
    llm_handler.register_game_context_function(
        "get_map_info",
        game_context_provider.get_map_info,
        "Get current map information including terrain, layout, and basic details"
    )

    llm_handler.register_game_context_function(
        "get_entities",
        game_context_provider.get_entities,
        "Get all entities on the current map with their positions and basic information"
    )

    llm_handler.register_game_context_function(
        "get_player_characters",
        game_context_provider.get_player_characters,
        "Get information about player characters on the current map"
    )

    llm_handler.register_game_context_function(
        "get_npcs",
        game_context_provider.get_npcs,
        "Get information about NPCs on the current map"
    )

    # Create a proxy for get_entity_details that can handle function calling
    def get_entity_details_proxy(*args, **kwargs):
        """Proxy function for get_entity_details that can handle function calling."""
        return game_context_provider.get_entity_details(*args, **kwargs)

    llm_handler.register_game_context_function(
        "get_entity_details",
        get_entity_details_proxy,
        "Get detailed information about a specific entity by name"
    )

    llm_handler.register_game_context_function(
        "get_battle_status",
        game_context_provider.get_battle_status,
        "Get current battle information if combat is active"
    )

    # ── MCP bridge ────────────────────────────────────────────────────
    # Expose the full MCP tool registry to the DM AI assistant so it
    # uses the same tool surface as external MCP clients. The model
    # invokes [FUNCTION_CALL: mcp("tool.name", {"k": "v"})]. The bridge
    # delegates to the shared ToolRegistry and unwraps the MCP envelope.
    def mcp_call_bridge(tool_name, arguments=None):
        """Invoke an MCP tool by name and return its JSON payload (or error text)."""
        if isinstance(arguments, str):
            import json as _json
            try:
                arguments = _json.loads(arguments) if arguments.strip() else {}
            except Exception as exc:
                return f"Invalid JSON arguments: {exc}"
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return f"Arguments must be a JSON object, got: {type(arguments).__name__}"

        # Compatibility alias: several models emit `entity_name` for DM tools
        # that actually require `entity_uid`. Resolve it from live entities,
        # including fuzzy matching for minor typos.
        manifest = next((m for m in mcp_registry.list() if m.get('name') == tool_name), None)
        input_schema = (manifest or {}).get('inputSchema') or {}
        schema_props = input_schema.get('properties') or {}
        needs_entity_uid = 'entity_uid' in schema_props
        if needs_entity_uid and not arguments.get('entity_uid') and isinstance(arguments.get('entity_name'), str):
            raw_name = arguments.get('entity_name', '').strip()
            if raw_name:
                import difflib as _difflib

                candidates = []  # [(uid, name_key), ...]
                seen_uids = set()
                cg = mcp_context.current_game
                for battle_map in (getattr(cg, 'maps', {}) or {}).values():
                    for ent in (getattr(battle_map, 'entities', {}) or {}).keys():
                        uid = str(getattr(ent, 'entity_uid', '') or '').strip()
                        if not uid or uid in seen_uids:
                            continue
                        seen_uids.add(uid)
                        label = str((ent.label() if hasattr(ent, 'label') else getattr(ent, 'name', '')) or '').strip()
                        name = str(getattr(ent, 'name', '') or '').strip()
                        keys = [uid, label, name]
                        for key in keys:
                            if key:
                                candidates.append((uid, key.lower()))

                query = raw_name.lower()
                # Exact first
                exact = [uid for uid, key in candidates if key == query]
                resolved_uid = exact[0] if exact else None
                # Then substring match
                if resolved_uid is None:
                    contains = [uid for uid, key in candidates if query in key]
                    if len(contains) == 1:
                        resolved_uid = contains[0]
                # Finally fuzzy match
                if resolved_uid is None:
                    all_keys = sorted(set(key for _, key in candidates))
                    match = _difflib.get_close_matches(query, all_keys, n=1, cutoff=0.78)
                    if match:
                        for uid, key in candidates:
                            if key == match[0]:
                                resolved_uid = uid
                                break

                if resolved_uid:
                    arguments['entity_uid'] = resolved_uid
                else:
                    return f"MCP error: Could not resolve entity_name '{raw_name}' to an entity_uid"

        # Compatibility aliases: some models emit `target_uid` or
        # `near_entity` for the *_near tools. Normalize to the expected
        # fields used by the MCP schema.
        if tool_name in ('dm.spawn_npc_near', 'dm.spawn_object_near'):
            if (arguments.get('target_entity_uid') is None and
                    isinstance(arguments.get('target_uid'), str) and
                    arguments.get('target_uid').strip()):
                arguments['target_entity_uid'] = arguments.pop('target_uid').strip()
            if (arguments.get('target_name') is None and
                arguments.get('target_entity_uid') is None and
                    isinstance(arguments.get('near_entity'), str) and
                    arguments.get('near_entity').strip()):
                arguments['target_name'] = arguments.pop('near_entity').strip()

        # Guardrail: models sometimes hallucinate map_name="Unknown" when
        # context extraction fails. For spawn tools, normalize that to the
        # active map instead of hard-failing.
        if tool_name in ('dm.spawn_npc', 'dm.spawn_object'):
            map_name = arguments.get('map_name')
            if isinstance(map_name, str) and map_name.strip().lower() in ('unknown', 'none', 'null', ''):
                arguments.pop('map_name', None)

        envelope = mcp_registry.call(tool_name, arguments, context=mcp_context)
        if envelope.get('isError'):
            for item in envelope.get('content') or []:
                if item.get('type') == 'text':
                    return f"MCP error: {item.get('text')}"
            return "MCP error (unknown)"
        for item in envelope.get('content') or []:
            if item.get('type') == 'json':
                return item.get('json')
        return envelope

    llm_handler.register_game_context_function(
        "mcp",
        mcp_call_bridge,
        "Invoke any MCP tool by name. Args: tool_name (str), arguments (JSON object). "
        "Use this in preference to the legacy get_* functions for richer data."
    )
    # Stash the shared registry on the function-info dict so the LLM
    # system prompt can enumerate the *real* tool catalogue instead of
    # advertising hand-curated examples that may not exist.
    if 'mcp' in llm_handler.game_context_functions:
        llm_handler.game_context_functions['mcp']['mcp_registry'] = mcp_registry
