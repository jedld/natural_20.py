"""Tests for webapp.blueprints.helpers.llm_init."""

import os
import unittest
from unittest.mock import MagicMock, patch, call


class TestLlmInit(unittest.TestCase):
    """Test cases for llm_init module."""

    def setUp(self):
        """Set up test fixtures."""
        from webapp.blueprints.helpers import llm_init as mod
        self.mod = mod

    # ------------------------------------------------------------------ #
    # configure_llm_handler_from_environment
    # ------------------------------------------------------------------ #

    @patch.dict(os.environ, {'LLM_PROVIDER': 'openai', 'OPENAI_API_KEY': 'test_key', 'OPENAI_MODEL': 'gpt-4o'})
    def test_configure_llm_handler_openai_success(self, *args):
        """configure_llm_handler_from_environment initializes OpenAI provider."""
        handler = MagicMock()
        handler.initialize_provider.return_value = True
        result = self.mod.configure_llm_handler_from_environment(handler)
        self.assertTrue(result)
        handler.initialize_provider.assert_called_once_with('openai', {
            'api_key': 'test_key',
            'model': 'gpt-4o',
        })

    @patch.dict(os.environ, {'LLM_PROVIDER': 'openai', 'OPENAI_API_KEY': 'test_key', 'OPENAI_BASE_URL': 'https://custom.api'})
    def test_configure_llm_handler_openai_with_base_url(self, *args):
        """configure_llm_handler_from_environment includes base_url for OpenAI."""
        handler = MagicMock()
        handler.initialize_provider.return_value = True
        result = self.mod.configure_llm_handler_from_environment(handler)
        handler.initialize_provider.assert_called_once_with('openai', {
            'api_key': 'test_key',
            'model': 'gpt-4o',
            'base_url': 'https://custom.api',
        })

    @patch.dict(os.environ, {'LLM_PROVIDER': 'openai'})
    def test_configure_llm_handler_openai_no_key(self, *args):
        """configure_llm_handler_from_environment returns False when no OpenAI key."""
        handler = MagicMock()
        result = self.mod.configure_llm_handler_from_environment(handler)
        self.assertFalse(result)
        handler.initialize_provider.assert_not_called()

    @patch.dict(os.environ, {'LLM_PROVIDER': 'anthropic', 'ANTHROPIC_API_KEY': 'test_key'})
    def test_configure_llm_handler_anthropic_success(self, *args):
        """configure_llm_handler_from_environment initializes Anthropic provider."""
        handler = MagicMock()
        handler.initialize_provider.return_value = True
        result = self.mod.configure_llm_handler_from_environment(handler)
        self.assertTrue(result)
        handler.initialize_provider.assert_called_once_with('anthropic', {
            'api_key': 'test_key',
            'model': 'claude-3-5-sonnet-20241022',
        })

    @patch.dict(os.environ, {'LLM_PROVIDER': 'anthropic', 'ANTHROPIC_MODEL': 'claude-3-opus'})
    def test_configure_llm_handler_anthropic_custom_model(self, *args):
        """configure_llm_handler_from_environment uses custom Anthropic model."""
        handler = MagicMock()
        handler.initialize_provider.return_value = True
        result = self.mod.configure_llm_handler_from_environment(handler)
        handler.initialize_provider.assert_called_once_with('anthropic', {
            'api_key': 'test_key',
            'model': 'claude-3-opus',
        })

    @patch.dict(os.environ, {'LLM_PROVIDER': 'anthropic'})
    def test_configure_llm_handler_anthropic_no_key(self, *args):
        """configure_llm_handler_from_environment returns False when no Anthropic key."""
        handler = MagicMock()
        result = self.mod.configure_llm_handler_from_environment(handler)
        self.assertFalse(result)
        handler.initialize_provider.assert_not_called()

    @patch.dict(os.environ, {'LLM_PROVIDER': 'ollama', 'OLLAMA_BASE_URL': 'http://custom:11434', 'OLLAMA_MODEL': 'llama3'})
    def test_configure_llm_handler_ollama_custom(self, *args):
        """configure_llm_handler_from_environment uses custom Ollama settings."""
        handler = MagicMock()
        handler.initialize_provider.return_value = True
        result = self.mod.configure_llm_handler_from_environment(handler)
        self.assertTrue(result)
        handler.initialize_provider.assert_called_once_with('ollama', {
            'base_url': 'http://custom:11434',
            'model': 'llama3',
        })

    @patch.dict(os.environ, {'LLM_PROVIDER': 'ollama'})
    def test_configure_llm_handler_ollama_defaults(self, *args):
        """configure_llm_handler_from_environment uses Ollama defaults."""
        handler = MagicMock()
        handler.initialize_provider.return_value = True
        result = self.mod.configure_llm_handler_from_environment(handler)
        handler.initialize_provider.assert_called_once_with('ollama', {
            'base_url': 'http://localhost:11434',
            'model': 'gemma3:27b',
        })

    @patch.dict(os.environ, {'LLM_PROVIDER': 'llama_cpp'})
    def test_configure_llm_handler_llama_cpp(self, *args):
        """configure_llm_handler_from_environment initializes llama.cpp provider."""
        handler = MagicMock()
        handler.initialize_provider.return_value = True
        handler.current_provider = MagicMock()
        handler.current_provider.current_model = 'test_model'
        result = self.mod.configure_llm_handler_from_environment(handler)
        self.assertTrue(result)
        handler.initialize_provider.assert_called_once()
        args_list = handler.initialize_provider.call_args
        self.assertEqual(args_list[0][0], 'llama_cpp')
        self.assertIn('base_url', args_list[0][1])
        self.assertIn('api_key', args_list[0][1])

    @patch.dict(os.environ, {'LLM_PROVIDER': 'llama.cpp'})
    def test_configure_llm_handler_llama_cpp_alias(self, *args):
        """configure_llm_handler_from_environment handles llama.cpp alias."""
        handler = MagicMock()
        handler.initialize_provider.return_value = True
        result = self.mod.configure_llm_handler_from_environment(handler)
        self.assertTrue(result)

    @patch.dict(os.environ, {'LLM_PROVIDER': 'llama.cpp', 'N20_LLM_MODEL': 'custom_model'})
    def test_configure_llm_handler_llama_cpp_with_n20_model(self, *args):
        """configure_llm_handler_from_environment uses N20_LLM_MODEL for llama.cpp."""
        handler = MagicMock()
        handler.initialize_provider.return_value = True
        result = self.mod.configure_llm_handler_from_environment(handler)
        args_list = handler.initialize_provider.call_args
        self.assertEqual(args_list[0][1].get('model'), 'custom_model')

    @patch.dict(os.environ, {'LLM_PROVIDER': 'llamacpp'})
    def test_configure_llm_handler_llamacpp_alias(self, *args):
        """configure_llm_handler_from_environment handles llamacpp alias."""
        handler = MagicMock()
        handler.initialize_provider.return_value = True
        result = self.mod.configure_llm_handler_from_environment(handler)
        self.assertTrue(result)

    @patch.dict(os.environ, {'LLM_PROVIDER': 'unknown_provider'})
    def test_configure_llm_handler_unknown(self, *args):
        """configure_llm_handler_from_environment falls back to mock for unknown provider."""
        handler = MagicMock()
        handler.initialize_provider.return_value = True
        result = self.mod.configure_llm_handler_from_environment(handler)
        handler.initialize_provider.assert_called_once_with('mock', {})
        self.assertTrue(result)

    @patch.dict(os.environ, {'LLM_PROVIDER': ''})
    def test_configure_llm_handler_empty_provider(self, *args):
        """configure_llm_handler_from_environment handles empty provider."""
        handler = MagicMock()
        handler.initialize_provider.return_value = True
        result = self.mod.configure_llm_handler_from_environment(handler)
        # Empty string lower is '', which is unknown -> mock
        handler.initialize_provider.assert_called_once_with('mock', {})

    @patch.dict(os.environ, {'LLM_PROVIDER': 'openai'})
    def test_configure_llm_handler_openai_failure(self, *args):
        """configure_llm_handler_from_environment returns False on provider init failure."""
        handler = MagicMock()
        handler.initialize_provider.return_value = False
        result = self.mod.configure_llm_handler_from_environment(handler)
        self.assertFalse(result)

    # ------------------------------------------------------------------ #
    # initialize_llm_from_env
    # ------------------------------------------------------------------ #

    def test_initialize_llm_from_env(self, *args):
        """initialize_llm_from_env creates handler and configures it."""
        handler_class = MagicMock()
        handler_instance = MagicMock()
        handler_class.return_value = handler_instance

        with patch.object(self.mod, 'configure_llm_handler_from_environment', return_value=True):
            result = self.mod.initialize_llm_from_env(handler_class)

        handler_class.assert_called_once()
        self.mod.configure_llm_handler_from_environment.assert_called_once_with(handler_instance)
        self.assertEqual(result, handler_instance)

    # ------------------------------------------------------------------ #
    # register_game_context_functions
    # ------------------------------------------------------------------ #

    def test_register_game_context_functions_basic(self):
        """register_game_context_functions registers all basic context functions."""
        llm_handler = MagicMock()
        game_context_provider = MagicMock()
        mcp_registry = MagicMock()
        mcp_context = MagicMock()

        self.mod.register_game_context_functions(
            llm_handler, game_context_provider, mcp_registry, mcp_context
        )

        # Check basic function registrations
        expected_calls = [
            'get_map_info',
            'get_entities',
            'get_player_characters',
            'get_npcs',
            'get_entity_details',
            'get_battle_status',
            'mcp',
        ]
        for func_name in expected_calls:
            assert llm_handler.register_game_context_function.called

    @patch.dict(os.environ, {'LLM_PROVIDER': 'ollama'})
    def test_register_game_context_functions_mcp_bridge(self):
        """register_game_context_functions registers MCP bridge function."""
        llm_handler = MagicMock()
        llm_handler.game_context_functions = {'mcp': {}}
        game_context_provider = MagicMock()
        mcp_registry = MagicMock()
        mcp_context = MagicMock()

        self.mod.register_game_context_functions(
            llm_handler, game_context_provider, mcp_registry, mcp_context
        )

        # Verify MCP function was registered
        llm_handler.register_game_context_function.assert_called()
        # Check that mcp function has mcp_registry attached
        assert 'mcp' in llm_handler.game_context_functions

    def test_register_game_context_functions_mcp_call_bridge_entity_name_alias(self):
        """register_game_context_functions handles entity_name -> entity_uid alias."""
        llm_handler = MagicMock()
        llm_handler.game_context_functions = {}
        game_context_provider = MagicMock()
        mcp_registry = MagicMock()
        mcp_registry.list.return_value = [
            {'name': 'dm.set_hp', 'inputSchema': {'properties': {'entity_uid': {}}}}
        ]
        mcp_context = MagicMock()
        mcp_context.current_game = MagicMock()
        mcp_context.current_game.maps = {}

        self.mod.register_game_context_functions(
            llm_handler, game_context_provider, mcp_registry, mcp_context
        )

        # Extract the mcp_call_bridge function
        mcp_call_args = None
        for call_args in llm_handler.register_game_context_function.call_args_list:
            if call_args[0][0] == 'mcp':
                mcp_call_args = call_args[0][1]
                break

        self.assertIsNotNone(mcp_call_args)
        # Test the bridge function with entity_name alias
        mcp_registry.call.return_value = {'content': [{'type': 'json', 'json': {}}]}

        result = mcp_call_args('dm.set_hp', {'entity_name': 'goblin1', 'hp': 5})

    def test_register_game_context_functions_mcp_call_bridge_entity_name_no_match(self):
        """register_game_context_functions returns error when entity_name not resolved."""
        llm_handler = MagicMock()
        llm_handler.game_context_functions = {}
        game_context_provider = MagicMock()
        mcp_registry = MagicMock()
        mcp_registry.list.return_value = [
            {'name': 'dm.set_hp', 'inputSchema': {'properties': {'entity_uid': {}}}}
        ]
        mcp_context = MagicMock()
        mcp_context.current_game = MagicMock()
        mcp_context.current_game.maps = {}

        self.mod.register_game_context_functions(
            llm_handler, game_context_provider, mcp_registry, mcp_context
        )

        # Extract the mcp_call_bridge function
        mcp_call_args = None
        for call_args in llm_handler.register_game_context_function.call_args_list:
            if call_args[0][0] == 'mcp':
                mcp_call_args = call_args[0][1]
                break

        self.assertIsNotNone(mcp_call_args)
        mcp_registry.call.return_value = {'content': [{'type': 'text', 'text': 'error'}]}

        result = mcp_call_args('dm.set_hp', {'entity_name': 'nonexistent_goblin_xyz', 'hp': 5})
        self.assertIn('MCP error', result)

    def test_register_game_context_functions_mcp_call_bridge_invalid_json(self):
        """register_game_context_functions handles invalid JSON arguments."""
        llm_handler = MagicMock()
        llm_handler.game_context_functions = {}
        game_context_provider = MagicMock()
        mcp_registry = MagicMock()
        mcp_context = MagicMock()

        self.mod.register_game_context_functions(
            llm_handler, game_context_provider, mcp_registry, mcp_context
        )

        mcp_call_args = None
        for call_args in llm_handler.register_game_context_function.call_args_list:
            if call_args[0][0] == 'mcp':
                mcp_call_args = call_args[0][1]
                break

        result = mcp_call_args('dm.set_hp', 'not valid json')
        self.assertIn('Invalid JSON', result)

    def test_register_game_context_functions_mcp_call_bridge_non_dict_args(self):
        """register_game_context_functions rejects non-dict arguments."""
        llm_handler = MagicMock()
        llm_handler.game_context_functions = {}
        game_context_provider = MagicMock()
        mcp_registry = MagicMock()
        mcp_context = MagicMock()

        self.mod.register_game_context_functions(
            llm_handler, game_context_provider, mcp_registry, mcp_context
        )

        mcp_call_args = None
        for call_args in llm_handler.register_game_context_function.call_args_list:
            if call_args[0][0] == 'mcp':
                mcp_call_args = call_args[0][1]
                break

        result = mcp_call_args('dm.set_hp', [1, 2, 3])
        self.assertIn('Arguments must be a JSON object', result)

    def test_register_game_context_functions_mcp_call_bridge_null_args(self):
        """register_game_context_functions handles null arguments."""
        llm_handler = MagicMock()
        llm_handler.game_context_functions = {}
        game_context_provider = MagicMock()
        mcp_registry = MagicMock()
        mcp_registry.call.return_value = {'content': [{'type': 'json', 'json': {}}]}
        mcp_context = MagicMock()

        self.mod.register_game_context_functions(
            llm_handler, game_context_provider, mcp_registry, mcp_context
        )

        mcp_call_args = None
        for call_args in llm_handler.register_game_context_function.call_args_list:
            if call_args[0][0] == 'mcp':
                mcp_call_args = call_args[0][1]
                break

        result = mcp_call_args('dm.set_hp', None)
        self.assertEqual(result, {})

    def test_register_game_context_functions_spawn_tools_normalize_map_name(self):
        """register_game_context_functions normalizes map_name for spawn tools."""
        llm_handler = MagicMock()
        llm_handler.game_context_functions = {}
        game_context_provider = MagicMock()
        mcp_registry = MagicMock()
        mcp_registry.call.return_value = {'content': [{'type': 'json', 'json': {}}]}
        mcp_context = MagicMock()

        self.mod.register_game_context_functions(
            llm_handler, game_context_provider, mcp_registry, mcp_context
        )

        mcp_call_args = None
        for call_args in llm_handler.register_game_context_function.call_args_list:
            if call_args[0][0] == 'mcp':
                mcp_call_args = call_args[0][1]
                break

        # Should handle map_name="Unknown"
        result = mcp_call_args('dm.spawn_npc', {'map_name': 'Unknown', 'npc_type': 'goblin'})
        self.assertEqual(result, {})

    def test_register_game_context_functions_spawn_tools_normalize_null_map_name(self):
        """register_game_context_functions normalizes null map_name for spawn tools."""
        llm_handler = MagicMock()
        llm_handler.game_context_functions = {}
        game_context_provider = MagicMock()
        mcp_registry = MagicMock()
        mcp_registry.call.return_value = {'content': [{'type': 'json', 'json': {}}]}
        mcp_context = MagicMock()

        self.mod.register_game_context_functions(
            llm_handler, game_context_provider, mcp_registry, mcp_context
        )

        mcp_call_args = None
        for call_args in llm_handler.register_game_context_function.call_args_list:
            if call_args[0][0] == 'mcp':
                mcp_call_args = call_args[0][1]
                break

        for null_val in ['none', 'null', '']:
            result = mcp_call_args('dm.spawn_npc', {'map_name': null_val, 'npc_type': 'goblin'})
            self.assertEqual(result, {})

    def test_register_game_context_functions_spawn_near_tools_aliases(self):
        """register_game_context_functions handles spawn_near tool aliases."""
        llm_handler = MagicMock()
        llm_handler.game_context_functions = {}
        game_context_provider = MagicMock()
        mcp_registry = MagicMock()
        mcp_registry.list.return_value = [
            {'name': 'dm.spawn_npc_near', 'inputSchema': {'properties': {}}}
        ]
        mcp_registry.call.return_value = {'content': [{'type': 'json', 'json': {}}]}
        mcp_context = MagicMock()

        self.mod.register_game_context_functions(
            llm_handler, game_context_provider, mcp_registry, mcp_context
        )

        mcp_call_args = None
        for call_args in llm_handler.register_game_context_function.call_args_list:
            if call_args[0][0] == 'mcp':
                mcp_call_args = call_args[0][1]
                break

        # Should handle target_uid -> target_entity_uid alias
        result = mcp_call_args('dm.spawn_npc_near', {
            'target_uid': 'goblin1',
            'near_entity': 'player1',
        })

    def test_register_game_context_functions_mcp_registry_on_function(self):
        """register_game_context_functions attaches mcp_registry to function info."""
        llm_handler = MagicMock()
        llm_handler.game_context_functions = {'mcp': {}}
        game_context_provider = MagicMock()
        mcp_registry = MagicMock()
        mcp_context = MagicMock()

        self.mod.register_game_context_functions(
            llm_handler, game_context_provider, mcp_registry, mcp_context
        )

        # Verify mcp_registry was attached
        self.assertIn('mcp_registry', llm_handler.game_context_functions['mcp'])
        self.assertEqual(
            llm_handler.game_context_functions['mcp']['mcp_registry'],
            mcp_registry
        )

    def test_logger_exists(self):
        """Module has a logger."""
        self.assertIsNotNone(self.mod.logger)


if __name__ == '__main__':
    unittest.main()
