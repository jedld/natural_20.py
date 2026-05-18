"""
LLM Handler for DM Chatbot Interface

This module provides a skeleton for interacting with large language models
in the DM console. It's designed to be extensible for different LLM providers.
"""

import os
import json
import logging
import inspect
import ast
import difflib
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Callable
import requests
from datetime import datetime
import re
import uuid
import pdb
import threading
from pathlib import Path

from natural20.concurrency import run_blocking

logger = logging.getLogger('werkzeug')
logger.setLevel(logging.INFO)

_PROMPTS_DIR = Path(__file__).resolve().parent / 'prompts'
_PROMPT_CACHE: Dict[str, str] = {}


def _load_prompt_file(filename: str) -> str:
    """Load UTF-8 text from ``webapp/prompts/<filename>`` (cached)."""
    if filename not in _PROMPT_CACHE:
        path = _PROMPTS_DIR / filename
        if not path.is_file():
            raise FileNotFoundError(f'Missing LLM prompt file: {path}')
        _PROMPT_CACHE[filename] = path.read_text(encoding='utf-8')
    return _PROMPT_CACHE[filename]


def _append_legacy_context_block(prompt: str, context: Optional[Dict[str, Any]]) -> str:
    """Append snapshot lines used by legacy provider ``_build_system_prompt`` helpers."""
    if context:
        prompt += f"\n\nCurrent Map: {context.get('current_map', 'Unknown')}"
        if context.get('battle'):
            prompt += f"\nBattle Status: Active (Current Turn: {context.get('current_turn', 'Unknown')})"
        else:
            prompt += "\nBattle Status: No active battle"

        if context.get('entities'):
            prompt += f"\nEntities on Map: {len(context['entities'])}"

        if context.get('pov_entity'):
            prompt += f"\nCurrent POV: {context['pov_entity']}"

    prompt += "\n\nHow can I help you with your D&D game today?"
    return prompt


_campaign_prompt_tls = threading.local()


def set_campaign_prompt_root(path: Optional[str]) -> None:
    """Bind the active campaign directory for per-campaign prompt overrides.

    The Flask app sets this from ``game_session.root_path`` on each request.
    When unset (tests, scripts), bundled defaults under ``webapp/prompts/`` apply.
    """
    if path:
        _campaign_prompt_tls.root = os.path.abspath(path)
    else:
        _campaign_prompt_tls.root = None


def get_campaign_prompt_root() -> Optional[str]:
    return getattr(_campaign_prompt_tls, 'root', None)


def read_prompt_with_campaign_override(bundled_filename: str, campaign_filename: str) -> str:
    """Return campaign override text if ``<campaign_root>/<campaign_filename>`` exists, else bundled."""
    root = get_campaign_prompt_root()
    if root:
        candidate = Path(root) / campaign_filename
        if candidate.is_file():
            try:
                return candidate.read_text(encoding='utf-8')
            except OSError as exc:
                logger.warning('[LLMHandler] Could not read campaign prompt %s: %s', candidate, exc)
    return _load_prompt_file(bundled_filename)


def read_npc_system_prompt(fallback_templates_dir: Optional[str] = None) -> str:
    """Load NPC conversation system template: active campaign first, then templates dir.

    Expected file name: ``npc_system_prompt.txt``. Uses :func:`get_campaign_prompt_root`
    first, then ``fallback_templates_dir`` (typically the app's ``LEVEL`` / ``TEMPLATE_DIR``).
    """
    roots: List[str] = []
    cr = get_campaign_prompt_root()
    if cr:
        roots.append(cr)
    fd = fallback_templates_dir or os.environ.get('TEMPLATE_DIR')
    if fd:
        abs_fd = os.path.abspath(fd)
        if abs_fd not in roots:
            roots.append(abs_fd)
    for root in roots:
        p = Path(root) / 'npc_system_prompt.txt'
        if p.is_file():
            try:
                return p.read_text(encoding='utf-8')
            except OSError as exc:
                logger.warning('[LLMHandler] Could not read NPC prompt %s: %s', p, exc)
    return ''


class SessionLogger:
    """Handles session-based logging for LLM interactions."""
    
    def __init__(self, log_dir: str = None):
        self.log_dir = log_dir
        self.session_id = str(uuid.uuid4())[:8]  # Short session ID
        self.session_start = datetime.now()

        # Create session log file
        if self.log_dir:
            # Create log directory if it doesn't exist
            os.makedirs(self.log_dir, exist_ok=True)
            self.log_file = os.path.join(self.log_dir, f"session_{self.session_id}_{self.session_start.strftime('%Y%m%d_%H%M%S')}.log")
            logger.info(f"[SessionLogger] Created session log: {self.log_file}")
            
            # Write session header
            with open(self.log_file, 'w') as f:
                f.write(f"=== LLM SESSION LOG ===\n")
                f.write(f"Session ID: {self.session_id}\n")
                f.write(f"Start Time: {self.session_start}\n")
                f.write(f"Log File: {self.log_file}\n")
                f.write("=" * 50 + "\n\n")
            logger.info(f"[SessionLogger] Created session log: {self.log_file}")
        else:
            self.log_file = None
        
        
    
    def log_interaction(self, interaction_type: str, content: str, metadata: Optional[Dict[str, Any]] = None):
        """Log an interaction with timestamp and metadata."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        
        if not self.log_file:
            return
        
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(f"\n--- {interaction_type.upper()} ---\n")
            f.write(f"Timestamp: {timestamp}\n")
            
            if metadata:
                f.write("Metadata:\n")
                for key, value in metadata.items():
                    f.write(f"  {key}: {value}\n")
            
            f.write("Content:\n")
            f.write("-" * 40 + "\n")
            f.write(content)
            f.write("\n" + "=" * 50 + "\n")
        
        logger.debug(f"[SessionLogger] Logged {interaction_type} to {self.log_file}")
    
    def log_request(self, messages: List[Dict[str, str]], provider_info: Dict[str, Any]):
        """Log a raw request to the LLM."""
        metadata = {
            "provider": provider_info.get("provider_type", "unknown"),
            "model": provider_info.get("current_model", "unknown"),
            "message_count": len(messages)
        }
        
        content = json.dumps(messages, indent=2, ensure_ascii=False)
        self.log_interaction("RAW REQUEST TO LLM", content, metadata)
    
    def log_response(self, response: str, provider_info: Dict[str, Any], partial: bool = False):
        """Log a raw response from the LLM."""
        metadata = {
            "provider": provider_info.get("provider_type", "unknown"),
            "model": provider_info.get("current_model", "unknown"),
            "response_length": len(response)
        }
        if partial:
            self.log_interaction("PARTIAL RESPONSE FROM LLM", response, metadata)
        else:
            self.log_interaction("RAW RESPONSE FROM LLM", response, metadata)
    
    def log_error(self, error: str, context: Optional[str] = None):
        """Log an error with context."""
        metadata = {"error_type": "LLM_ERROR"}
        if context:
            metadata["context"] = context
        
        self.log_interaction("ERROR", error, metadata)
    
    def log_function_call(self, function_name: str, args: List[Any], result: Any):
        """Log a function call execution."""
        metadata = {
            "function_name": function_name,
            "arguments": str(args),
            "result_type": type(result).__name__
        }
        
        content = f"Function: {function_name}\nArguments: {args}\nResult: {result}"
        self.log_interaction("FUNCTION_CALL", content, metadata)
    
    def get_session_info(self) -> Dict[str, Any]:
        """Get information about the current session."""
        return {
            "session_id": self.session_id,
            "log_file": self.log_file,
            "start_time": self.session_start.isoformat(),
            "duration": str(datetime.now() - self.session_start)
        }


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    @abstractmethod
    def initialize(self, config: Dict[str, Any]) -> bool:
        """Initialize the provider with configuration."""
        pass
    
    @abstractmethod
    def send_message(self, messages: List[Dict[str, str]]) -> str:
        """Send messages to the LLM and get a response."""
        pass
    
    @abstractmethod
    def get_available_models(self) -> List[str]:
        """Get list of available models."""
        pass
    
    @abstractmethod
    def set_model(self, model_name: str) -> bool:
        """Set the current model."""
        pass


class MockProvider(LLMProvider):
    """Mock provider for testing."""
    
    def __init__(self):
        self.initialized = False
        self.current_model = "mock-model"
        self.conversation_history = []
    
    def initialize(self, config: Dict[str, Any]) -> bool:
        self.initialized = True
        return True
    
    def send_message(self, messages: List[Dict[str, str]]) -> str:
        """Send messages to the mock provider."""
        # Extract the last user message
        user_message = None
        for msg in reversed(messages):
            if msg["role"] == "user":
                user_message = msg["content"]
                break
        
        if not user_message:
            return "No user message found"
        
        # Return responses that trigger function calls
        if "character" in user_message.lower() or "who" in user_message.lower():
            return """[FUNCTION_CALL: get_player_characters]
[FUNCTION_CALL: get_npcs]

Based on the current game state, here are the characters present:

**Player Characters:**
[RESPONSE: Function get_player_characters returned: [Mock data - would show actual PCs]]

**NPCs:**
[RESPONSE: Function get_npcs returned: [Mock data - would show actual NPCs]]

Would you like more details about any specific character?"""
        
        elif "map" in user_message.lower() or "where" in user_message.lower():
            return """[FUNCTION_CALL: get_map_info]
[FUNCTION_CALL: get_entities]

**Current Map Information:**
[RESPONSE: Function get_map_info returned: [Mock data - would show actual map details]]

**Entities on Map:**
[RESPONSE: Function get_entities returned: [Mock data - would show actual entities]]"""
        
        elif "battle" in user_message.lower() or "combat" in user_message.lower():
            return """[FUNCTION_CALL: get_battle_status]

**Battle Status:**
[RESPONSE: Function get_battle_status returned: [Mock data - would show actual battle status]]"""
        
        elif "entity" in user_message.lower() or "details" in user_message.lower():
            return """[FUNCTION_CALL: get_entity_details("Player1")]

**Entity Details:**
[RESPONSE: Function get_entity_details returned: [Mock data - would show actual entity details]]"""
        
        else:
            return """I'm here to help with your D&D game! I can provide information about characters, maps, battles, and more. What would you like to know?

Available functions:
- get_map_info()
- get_entities() 
- get_player_characters()
- get_npcs()
- get_entity_details(entity_name)
- get_battle_status()"""
    
    def get_available_models(self) -> List[str]:
        return ["mock-model"]
    
    def set_model(self, model_name: str) -> bool:
        self.current_model = model_name
        return True


class OpenAIProvider(LLMProvider):
    """OpenAI GPT provider."""
    
    def __init__(self):
        self.api_key = None
        self.client = None
        self.current_model = "gpt-4"
        self.conversation_history = []
    
    def initialize(self, config: Dict[str, Any]) -> bool:
        try:
            self.api_key = config.get('api_key')
            if not self.api_key:
                return False
            
            # Import OpenAI client
            try:
                from openai import OpenAI
                logger.info(f"[OpenAIProvider] Initializing OpenAI client with API key: {self.api_key}")
                self.client = OpenAI(api_key=self.api_key)
                logger.info(f"[OpenAIProvider] OpenAI client initialized")
            except ImportError:
                logger.error("OpenAI library not installed. Install with: pip install openai")
                return False
            
            return True
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI provider: {e}")
            return False
    
    def send_message(self, messages: List[Dict[str, str]]) -> str:
        if not self.client:
            return "OpenAI provider not initialized"
        
        try:
            # Build system prompt with RAG context
            # system_prompt = self._build_system_prompt()
            
            logger.info(f"Messages: {messages}")
            
            # Get timeout from environment or use default
            timeout = int(os.environ.get('OPENAI_TIMEOUT', '60'))
            
            response = self.client.chat.completions.create(
                model=self.current_model,
                messages=messages,
                max_tokens=1000,
                temperature=0.7,
                timeout=timeout
            )
            logger.info(f"Response: {response}")
            assistant_response = response.choices[0].message.content
            self.conversation_history.append({"role": "assistant", "content": assistant_response})
            
            return assistant_response
            
        except Exception as e:
            logger.error(f"Error sending message to OpenAI: {e}")
            return f"Error communicating with AI: {str(e)}"
    
    def get_available_models(self) -> List[str]:
        return ["gpt-4", "gpt-3.5-turbo", "gpt-4-turbo"]
    
    def set_model(self, model_name: str) -> bool:
        if model_name in self.get_available_models():
            self.current_model = model_name
            return True
        return False
    
    def _build_system_prompt(self, context: Optional[Dict[str, Any]] = None) -> str:
        """Build a strict system prompt enforcing function calling."""
        prompt = read_prompt_with_campaign_override(
            'dm_assistant_system_legacy.txt', 'dm_system_prompt_legacy.txt'
        ).rstrip()
        return _append_legacy_context_block(prompt, context)


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider."""
    
    def __init__(self):
        self.api_key = None
        self.current_model = "claude-3-sonnet-20240229"
        self.conversation_history = []
    
    def initialize(self, config: Dict[str, Any]) -> bool:
        try:
            self.api_key = config.get('api_key')
            if not self.api_key:
                return False
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Anthropic provider: {e}")
            return False
    
    def send_message(self, messages: List[Dict[str, str]]) -> str:
        if not self.api_key:
            return "Anthropic provider not initialized"
        
        try:
            # Build system prompt with RAG context
            system_prompt = self._build_system_prompt()
            
            # Add to conversation history
            self.conversation_history.append({"role": "user", "content": messages[-1]['content']})
            
            # Prepare messages for API call
            messages = [{"role": "system", "content": system_prompt}] + self.conversation_history
            
            headers = {
                "x-api-key": self.api_key,
                "content-type": "application/json",
                "anthropic-version": "2023-06-01"
            }
            
            data = {
                "model": self.current_model,
                "max_tokens": 1000,
                "messages": messages
            }
            
            # Get timeout from environment or use default
            timeout = int(os.environ.get('ANTHROPIC_TIMEOUT', '60'))
            
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=data,
                timeout=timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                assistant_response = result['content'][0]['text']
                self.conversation_history.append({"role": "assistant", "content": assistant_response})
                return assistant_response
            else:
                return f"API Error: {response.status_code} - {response.text}"
                
        except Exception as e:
            logger.error(f"Error sending message to Anthropic: {e}")
            return f"Error communicating with AI: {str(e)}"
    
    def get_available_models(self) -> List[str]:
        return ["claude-3-sonnet-20240229", "claude-3-haiku-20240307", "claude-3-opus-20240229"]
    
    def set_model(self, model_name: str) -> bool:
        if model_name in self.get_available_models():
            self.current_model = model_name
            return True
        return False
    
    def _build_system_prompt(self, context: Optional[Dict[str, Any]] = None) -> str:
        """Build a strict system prompt enforcing function calling."""
        prompt = read_prompt_with_campaign_override(
            'dm_assistant_system_legacy.txt', 'dm_system_prompt_legacy.txt'
        ).rstrip()
        return _append_legacy_context_block(prompt, context)


class OllamaProvider(LLMProvider):
    """Ollama local provider."""
    
    def __init__(self, opts = {}):
        self.base_url = opts.get('base_url', "http://localhost:11434")
        self.model = None
        self.context_window = opts.get('context_window', 8000)  # Default context window size
        self.conversation_history = []
    
    def initialize(self, config: Dict[str, Any]) -> bool:
        try:
            self.base_url = config.get('base_url', "http://localhost:11434")
            self.model = config.get('model')
            # Test connection
            logger.info(f"[OllamaProvider] Initializing Ollama provider with base URL: {self.base_url}")
            response = requests.get(f"{self.base_url}/api/tags", timeout=10)
            if response.status_code != 200:
                return False
            
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Ollama provider: {e}")
            return False
    
    def send_message(self, messages: List[Dict[str, str]]) -> str:
        """Send messages to Ollama."""
        if not self.model:
            return "Ollama provider not initialized or no model selected"
        
        try:
            # Extract the last user message
            user_message = None
            for msg in reversed(messages):
                if msg["role"] == "user":
                    user_message = msg["content"]
                    break
            
            if not user_message:
                return "No user message found"
            
            # Prepare the request payload
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": 0.1,  # Lower temperature for more deterministic responses
                    "num_predict": 500,  # Limit response length
                    "top_k": 10,         # Reduce randomness
                    "top_p": 0.9,        # Reduce randomness
                    "repeat_penalty": 1.1,  # Prevent repetition
                    "num_ctx": self.context_window,  # Set context window size
                    # Remove stop tokens that are too aggressive
                    "stop": []  # Let the model generate naturally
                }
            }
            print("Request:", payload)
            # Get timeout from environment or use default
            timeout = int(os.environ.get('OLLAMA_TIMEOUT', '60'))
            
            # Make the API call
            response = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=timeout
            )
            
            if response.status_code == 200:
                data = response.json()
                print("Response:", data)
                content = data.get("message", {}).get("content", "")
                # Handle empty responses
                if not content or content.strip() == "":
                    logger.warning("[OllamaProvider] Received empty response, trying with different prompt")
                    # Try a more direct approach
                    direct_payload = {
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": read_prompt_with_campaign_override(
                                'ollama_empty_response_system.txt', 'dm_ollama_empty_retry_system_prompt.txt'
                            ).strip()},
                            {"role": "user", "content": user_message}
                        ],
                        "stream": False,
                        "options": {
                            "temperature": 0.1,
                            "num_predict": 200,
                            "top_k": 10,
                            "top_p": 0.9,
                            "repeat_penalty": 1.1,
                            "num_ctx": self.context_window  # Set context window size
                        }
                    }

                    direct_response = requests.post(
                        f"{self.base_url}/api/chat",
                        json=direct_payload,
                        timeout=timeout
                    )
                    
                    if direct_response.status_code == 200:
                        direct_data = direct_response.json()
                        content = direct_data.get("message", {}).get("content", "")
                        if not content:
                            return "I'm here to help with your D&D game! I can provide information about the current map, entities, characters, and battle status. What would you like to know?"
                    else:
                        return "I'm here to help with your D&D game! I can provide information about the current map, entities, characters, and battle status. What would you like to know?"
                
                logger.debug(f"[OllamaProvider] Raw response content: '{content}'")
                return content
            else:
                print("Response:", response)
                logger.error(f"Ollama API error: {response.status_code} - {response.text}")
                return f"Error: Ollama API returned {response.status_code}"
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error sending message to Ollama: {e}")
            return f"Error communicating with Ollama: {str(e)}"
        except Exception as e:
            logger.error(f"Unexpected error in Ollama send_message: {e}")
            return f"Unexpected error: {str(e)}"
    
    def get_available_models(self) -> List[str]:
        try:
            # Get timeout from environment or use default for model listing
            timeout = int(os.environ.get('OLLAMA_TIMEOUT', '30'))
            response = requests.get(f"{self.base_url}/api/tags", timeout=timeout)
            if response.status_code == 200:
                data = response.json()
                return [model['name'] for model in data.get('models', [])]
            return []
        except Exception as e:
            logger.error(f"Error getting Ollama models: {e}")
            return []
    
    def set_model(self, model_name: str) -> bool:
        available_models = self.get_available_models()
        if model_name in available_models:
            self.model = model_name
            return True
        return False
    
    def set_context_window(self, context_window: int) -> bool:
        """Set the context window size for the model."""
        if context_window > 0:
            self.context_window = context_window
            logger.info(f"[OllamaProvider] Context window set to {context_window}")
            return True
        return False
    
    def get_context_window(self) -> int:
        """Get the current context window size."""
        return self.context_window
    
    def _build_system_prompt(self, context: Optional[Dict[str, Any]] = None) -> str:
        """Build a strict system prompt enforcing function calling."""
        prompt = read_prompt_with_campaign_override(
            'dm_assistant_system_legacy.txt', 'dm_system_prompt_legacy.txt'
        ).rstrip()
        return _append_legacy_context_block(prompt, context)


class LlamaCppProvider(LLMProvider):
    """llama.cpp server using the OpenAI-compatible API."""

    def __init__(self, opts=None):
        opts = opts or {}
        self.base_url = opts.get('base_url', 'http://localhost:8011')
        self.api_key = opts.get('api_key', 'llama-cpp')
        self.current_model = opts.get('model')
        self.conversation_history = []

    @staticmethod
    def _thinking_enabled() -> bool:
        value = os.environ.get('LLAMA_CPP_ENABLE_THINKING', 'false')
        return str(value).strip().lower() not in {'0', 'false', 'no', 'off', 'disabled'}

    @staticmethod
    def _extract_model_ids(data: Dict[str, Any]) -> List[str]:
        models = []

        if isinstance(data.get('data'), list):
            models.extend(data.get('data') or [])
        if isinstance(data.get('models'), list):
            models.extend(data.get('models') or [])

        model_ids = []
        for model in models:
            if not isinstance(model, dict):
                continue
            model_id = model.get('id') or model.get('model') or model.get('name')
            if model_id and model_id not in model_ids:
                model_ids.append(model_id)

        return model_ids

    @staticmethod
    def _extract_content_from_choice(choice: Dict[str, Any]) -> str:
        if not isinstance(choice, dict):
            return ''

        message = choice.get('message') or {}
        content = message.get('content')

        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, str):
                    text_parts.append(part)
                elif isinstance(part, dict):
                    part_text = part.get('text') or part.get('content')
                    if isinstance(part_text, str):
                        text_parts.append(part_text)
            return ''.join(text_parts)

        text = choice.get('text')
        if isinstance(text, str):
            return text

        message_text = message.get('text')
        if isinstance(message_text, str):
            return message_text

        return ''

    def initialize(self, config: Dict[str, Any]) -> bool:
        try:
            self.base_url = config.get('base_url', self.base_url or 'http://localhost:8011').rstrip('/')
            self.api_key = config.get('api_key', self.api_key or 'llama-cpp')
            requested_model = config.get('model')

            models = self.get_available_models()
            if requested_model:
                self.current_model = requested_model
            elif models:
                self.current_model = models[0]

            logger.info(f"[LlamaCppProvider] Initialized llama.cpp provider at {self.base_url} with model: {self.current_model}")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize llama.cpp provider: {e}")
            return False

    def send_message(self, messages: List[Dict[str, str]]) -> str:
        if not self.current_model:
            return "llama.cpp provider not initialized or no model selected"

        payload = {
            'model': self.current_model,
            'messages': messages,
            'temperature': 0.2,
            'max_tokens': 1000,
            'stream': False,
        }
        if not self._thinking_enabled():
            payload['chat_template_kwargs'] = {'enable_thinking': False}

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key or "llama-cpp"}',
        }

        try:
            timeout = int(os.environ.get('LLAMA_CPP_TIMEOUT', '60'))
            response = requests.post(
                f"{self.base_url}/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
            data = response.json()
            choice = (data.get('choices') or [{}])[0]
            content = self._extract_content_from_choice(choice)

            if not content:
                reasoning_content = ((choice.get('message') or {}).get('reasoning_content') or '').strip()
                if reasoning_content:
                    logger.warning(
                        "[LlamaCppProvider] Response contained reasoning_content but no assistant content; "
                        "consider increasing max_tokens or keep LLAMA_CPP_ENABLE_THINKING disabled. "
                        "finish_reason=%s",
                        choice.get('finish_reason')
                    )
            return content or ""
        except requests.exceptions.RequestException as e:
            logger.error(f"Error sending message to llama.cpp: {e}")
            return f"Error communicating with llama.cpp: {str(e)}"
        except Exception as e:
            logger.error(f"Unexpected error in llama.cpp send_message: {e}")
            return f"Unexpected error: {str(e)}"

    def get_available_models(self) -> List[str]:
        headers = {'Authorization': f'Bearer {self.api_key or "llama-cpp"}'}
        try:
            timeout = int(os.environ.get('LLAMA_CPP_TIMEOUT', '30'))
            response = requests.get(f"{self.base_url.rstrip('/')}/v1/models", headers=headers, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            return self._extract_model_ids(data)
        except Exception as e:
            logger.error(f"Error getting llama.cpp models: {e}")
            return []

    def set_model(self, model_name: str) -> bool:
        available_models = self.get_available_models()
        if not available_models:
            self.current_model = model_name
            return bool(model_name)
        if model_name in available_models:
            self.current_model = model_name
            return True
        return False


class LLMHandler:
    """Main handler for LLM interactions with RAG capabilities."""
    
    def __init__(self, opts = {}):
        self.providers = {
            'mock': MockProvider(),
            'openai': OpenAIProvider(),
            'anthropic': AnthropicProvider(),
            'ollama': OllamaProvider(opts),
            'llama_cpp': LlamaCppProvider(opts),
        }
        self.current_provider = None
        self.game_context_functions = {}
        self.conversation_history = []
        self.session_logger = SessionLogger()  # Create session logger
        self._send_lock = threading.Lock()

    @staticmethod
    def _only_first_message_may_be_system(messages: List[Dict[str, str]]) -> None:
        """Mutate roles in place.

        llama.cpp applies a Jinja chat template that raises unless every
        ``system`` message is at the beginning of the transcript. Function-call
        traces were previously stored as ``system``, which breaks the second
        LLM request after tool execution.
        """
        for i in range(1, len(messages)):
            if messages[i].get('role') == 'system':
                messages[i]['role'] = 'user'
    
    def initialize_provider(self, provider_name: str, config: Dict[str, Any]) -> bool:
        """Initialize a specific LLM provider."""
        if provider_name not in self.providers:
            logger.error(f"Unknown provider: {provider_name}")
            return False
        
        provider = self.providers[provider_name]
        if provider.initialize(config):
            self.current_provider = provider
            # Log provider initialization
            provider_info = self.get_provider_info()
            self.session_logger.log_interaction("PROVIDER_INITIALIZED", 
                                              f"Provider {provider_name} initialized successfully", 
                                              provider_info)
            return True
        return False
    
    def send_message(self, message, context: Optional[Dict[str, Any]] = None) -> str:
        """Send a message to the LLM and get a response, automatically handling truncated responses."""
        logger.debug(f"[LLMHandler] send_message called with message: {message}")
        with self._send_lock:
            return run_blocking(self._send_message_impl, message, context)

    def _send_message_impl(self, message, context: Optional[Dict[str, Any]] = None) -> str:
        if not self.current_provider:
            logger.error("[LLMHandler] No LLM provider initialized.")
            error_msg = "AI assistant is not initialized. Please initialize a provider first."
            self.session_logger.log_error(error_msg, "No provider initialized")
            return error_msg
        if isinstance(message, list):
            self.conversation_history = message
            # When a list is passed, we need to ensure system message is first
            # Check if the first message is already a system message
            if not message or message[0].get('role') != 'system':
                system_prompt = self._build_system_prompt(context)
                messages = [{"role": "system", "content": system_prompt}]
                messages.extend(self.conversation_history)
            else:
                messages = message
        else:
            self.conversation_history.append({"role": "user", "content": message})
            logger.debug(f"[LLMHandler] Conversation history: {self.conversation_history}")
            
            system_prompt = self._build_system_prompt(context)
            logger.debug(f"[LLMHandler] System prompt: {system_prompt}")
            
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(self.conversation_history)
            logger.debug(f"[LLMHandler] Messages sent to provider: {messages}")

        self._only_first_message_may_be_system(messages)
        
        provider_info = self.get_provider_info()
        self.session_logger.log_request(messages, provider_info)
        
        # --- CONTINUATION LOGIC START ---
        full_response = ""
        continuation_count = 0
        max_continuations = 5
        last_done_reason = None
        last_raw_response = None
        
        # Build a separate conversation for continuation that preserves message order
        # System message must always be first, followed by user/assistant pairs
        continuation_messages = list(messages)  # Copy the original messages
        
        while continuation_count < max_continuations:
            # Get response from provider
            raw_response = self.current_provider.send_message(continuation_messages)
            logger.info(f"[LLMHandler] Raw response from provider: {raw_response}")
            # self.session_logger.log_response(raw_response, provider_info, partial=True)

            # Try to detect done_reason if available (for OpenAI, Ollama, etc.)
            done_reason = None
            if isinstance(raw_response, dict):
                # Some providers may return a dict
                done_reason = raw_response.get('done_reason') or raw_response.get('finish_reason')
                content = raw_response.get('message', {}).get('content', '') or raw_response.get('content', '')
            else:
                content = raw_response
            
            # Append content to full_response
            full_response += (content if content else "")
            
            # Heuristic: If done_reason is 'length' or response ends abruptly, continue
            is_truncated = False
            if done_reason and done_reason == 'length':
                is_truncated = True
            elif content and len(content) > 0:
                # Check for various truncation indicators
                trimmed = content.strip()
                
                # If the content ends with ... or is very long without proper ending
                if len(trimmed) > 100 and not trimmed[-1] in ".!?]\n":
                    is_truncated = True
                # Check if response ends mid-sentence (no proper ending punctuation)
                elif len(trimmed) > 20 and not trimmed[-1] in ".!?]\n":
                    is_truncated = True
                # Check if thinking tags are incomplete (no closing tag)
                elif "<think>" in content and "</think>" not in content:
                    is_truncated = True
                # Check if the response seems incomplete (ends with common incomplete phrases)
                elif any(trimmed.endswith(phrase) for phrase in [
                    "To determine", "I need to", "Let me", "Based on", "The user",
                    "This shows", "We can see", "It appears", "The data", "Looking at"
                ]):
                    is_truncated = True
            
            if not is_truncated:
                break
            
            # For continuation, add the assistant response and a user prompt to continue
            # This maintains proper message ordering: system -> user/assistant pairs -> user
            continuation_messages.append({"role": "assistant", "content": content})
            continuation_messages.append({"role": "user", "content": "Please continue your response from where you left off."})

            continuation_count += 1
            logger.info(f"[LLMHandler] Requesting continuation from LLM (count: {continuation_count})")
        
        # --- CONTINUATION LOGIC END ---
        # Clean the full response
        cleaned_response = self._clean_response(full_response)
        logger.info(f"[LLMHandler] Cleaned response: {cleaned_response}")

        # Check if the response contains function calls
        has_function_calls = "[FUNCTION_CALL:" in cleaned_response

        if has_function_calls:
            logger.info("[LLMHandler] Found function calls, processing...")
            logger.info(f"[LLMHandler] Function calls found in: {cleaned_response}")
            function_calls = self._process_function_calls(cleaned_response, context)
            
            # Check if any function calls were actually processed
            if function_calls:
                mutation_fallback = self._maybe_execute_entity_mutation_from_context(message, function_calls)
                if mutation_fallback:
                    function_calls.append(mutation_fallback)
                item_fallback = self._maybe_execute_dm_add_item_from_context(message, function_calls)
                if item_fallback:
                    function_calls.append(item_fallback)
                self.conversation_history.extend(function_calls)
                # Format the function results into a user-friendly response
                formatted_response = self._format_function_results(function_calls, context, message)
                self.conversation_history.append({"role": "assistant", "content": formatted_response})
                return formatted_response
            else:
                # Function calls were found but none were processed (e.g., unknown functions)
                logger.info("[LLMHandler] No valid function calls processed, returning original response")
                self.conversation_history.append({"role": "assistant", "content": cleaned_response})
                self.session_logger.log_response(cleaned_response, provider_info, partial=False)
                return cleaned_response
        else:
            # No function calls, return the cleaned response directly
            self.conversation_history.append({"role": "assistant", "content": cleaned_response})
            self.session_logger.log_response(cleaned_response, provider_info, partial=False)
            return cleaned_response

    def _format_function_results(self, processed_response: List[Dict[str, str]], context: Optional[Dict[str, Any]] = None, original_message: str = None) -> str:
        """Send function results back to the LLM for formatting with continuation support."""
      
        # Handle empty response list
        if not processed_response:
            logger.warning("[LLMHandler] _format_function_results called with empty response list")
            return "No function results to format."

        # Deterministic short-circuit for count queries so we don't depend on
        # a second model pass for simple arithmetic over already-returned MCP
        # payloads.
        parsed_payloads: List[Dict[str, Any]] = []
        for msg in processed_response:
            content = str(msg.get('content', ''))
            marker = ' returned: '
            idx = content.find(marker)
            if idx < 0:
                continue
            payload_str = content[idx + len(marker):].strip()
            try:
                payload = ast.literal_eval(payload_str)
            except Exception:
                continue
            if isinstance(payload, dict):
                parsed_payloads.append(payload)

        if original_message:
            lowered = original_message.lower()
            is_count_query = any(tok in lowered for tok in (
                'how many', 'count', 'number of', 'how much'
            ))
            if is_count_query:
                subject = 'matches'
                m = re.search(r'how many\s+([a-zA-Z_\- ]+?)\s+(?:are|is)\b', lowered)
                if m:
                    subject = m.group(1).strip()

                for payload in parsed_payloads:
                    if isinstance(payload.get('count'), int):
                        n = int(payload['count'])
                        noun = subject
                        if n == 1 and noun.endswith('s'):
                            noun = noun[:-1]
                        return f"There {'is' if n == 1 else 'are'} {n} {noun} on the current map."
                    if isinstance(payload.get('entities'), list):
                        n = len(payload['entities'])
                        noun = subject
                        if n == 1 and noun.endswith('s'):
                            noun = noun[:-1]
                        return f"There {'is' if n == 1 else 'are'} {n} {noun} on the current map."

        # Build a proper messages list for the formatting request. Without the
        # original user question and a system prompt the model has no idea
        # what was asked and tends to hallucinate (e.g. treating the raw
        # function output as a programming-error report and offering generic
        # debugging advice). We therefore prepend a formatting-focused system
        # prompt, restate the original user question, and supply the function
        # results as system context for the model to summarise.
        format_system_prompt = read_prompt_with_campaign_override(
            'function_results_format_system.txt', 'dm_function_results_system_prompt.txt'
        ).strip()
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": format_system_prompt}
        ]
        if original_message:
            messages.append({"role": "user", "content": original_message})
        # Some model backends under-weight or mishandle synthetic `system`
        # messages from tool traces; provide an explicit user-side block.
        function_results_block = "\n".join(
            str(msg.get('content', '')) for msg in processed_response
        )
        messages.append({
            "role": "user",
            "content": "Function results:\n" + function_results_block,
        })
        if original_message:
            messages.append({
                "role": "user",
                "content": (
                    "Using only the function results above, answer my "
                    "previous question concisely."
                ),
            })

        # Log the formatting request
        provider_info = self.get_provider_info()
        self.session_logger.log_request(messages, provider_info)
        
        # --- CONTINUATION LOGIC FOR FORMATTING ---
        full_response = ""
        continuation_count = 0
        max_continuations = 5
        
        # Build a separate conversation for continuation that preserves message order
        # System message must always be first, followed by user/assistant pairs
        continuation_messages = list(messages)  # Copy the original messages
        
        while continuation_count < max_continuations:
            # Get response from provider
            raw_response = self.current_provider.send_message(continuation_messages)
            logger.info(f"[LLMHandler] Formatting response from provider: {raw_response}")
            self.session_logger.log_response(raw_response, provider_info, partial=True)
            # Try to detect done_reason if available
            done_reason = None
            if isinstance(raw_response, dict):
                done_reason = raw_response.get('done_reason') or raw_response.get('finish_reason')
                content = raw_response.get('message', {}).get('content', '') or raw_response.get('content', '')
            else:
                content = raw_response

            # Append content to full_response
            full_response += (content if content else "")

            # Heuristic: If done_reason is 'length' or response ends abruptly, continue
            is_truncated = False
            if done_reason and done_reason == 'length':
                is_truncated = True
            elif content and len(content) > 0:
                # Check for various truncation indicators
                trimmed = content.strip()
                # If the content ends with ... or is very long without proper ending
                if trimmed.endswith("..."):
                    is_truncated = True
                elif len(trimmed) > 100 and not trimmed[-1] in ".!?\n":
                    is_truncated = True
                # Check if response ends mid-sentence (no proper ending punctuation)
                elif len(trimmed) > 20 and not trimmed[-1] in ".!?\n":
                    is_truncated = True
                # Check if thinking tags are incomplete (no closing tag)
                elif "<think>" in content and "</think>" not in content:
                    is_truncated = True
                # Check if the response seems incomplete (ends with common incomplete phrases)
                elif any(trimmed.endswith(phrase) for phrase in [
                    "To determine", "I need to", "Let me", "Based on", "The user",
                    "This shows", "We can see", "It appears", "The data", "Looking at"
                ]):
                    is_truncated = True
            
            if not is_truncated:
                break
            
            # For continuation, add the assistant response and a user prompt to continue
            # This maintains proper message ordering: system -> user/assistant pairs -> user
            continuation_messages.append({"role": "assistant", "content": content})
            continuation_messages.append({"role": "user", "content": "Please continue your response from where you left off."})
            continuation_count += 1
            logger.info(f"[LLMHandler] Requesting continuation for formatting (count: {continuation_count})")
        
        # Clean the full formatting response
        formatted_response = self._clean_response(full_response)
        
        logger.info(f"[LLMHandler] Final formatted response: {formatted_response}")
        return formatted_response

    def _extract_function_calls(self, response: str) -> List[tuple]:
        """Find all [FUNCTION_CALL: name(args)] tokens in `response`.

        Supports dotted MCP-style names (``world.list_entities``) and
        argument bodies that contain nested parens, brackets, braces or
        quoted strings (e.g. JSON object literals as a single argument).
        Returns a list of ``(name, raw_arg_string)`` tuples.
        """
        results: List[tuple] = []
        marker = '[FUNCTION_CALL:'
        idx = 0
        n = len(response)
        while True:
            start = response.find(marker, idx)
            if start < 0:
                break
            i = start + len(marker)
            # Skip whitespace, then read the dotted identifier.
            while i < n and response[i].isspace():
                i += 1
            name_start = i
            while i < n and (response[i].isalnum() or response[i] in '._'):
                i += 1
            name = response[name_start:i]
            while i < n and response[i].isspace():
                i += 1
            arg_str = ''
            if i < n and response[i] == '(':
                depth = 1
                i += 1
                arg_start = i
                in_quotes = False
                quote_char = None
                while i < n and depth > 0:
                    ch = response[i]
                    if in_quotes:
                        if ch == '\\' and i + 1 < n:
                            i += 2
                            continue
                        if ch == quote_char:
                            in_quotes = False
                    else:
                        if ch in ('"', "'"):
                            in_quotes = True
                            quote_char = ch
                        elif ch in '([{':
                            depth += 1
                        elif ch in ')]}':
                            depth -= 1
                            if depth == 0:
                                break
                    i += 1
                arg_str = response[arg_start:i]
                if i < n and response[i] in ')]}':
                    i += 1
            elif i < n and response[i] == ',':
                # Compatibility syntax occasionally emitted by models:
                # [FUNCTION_CALL: tool.name, {"k": "v"}]
                i += 1
                while i < n and response[i].isspace():
                    i += 1
                arg_start = i
                depth = 0
                in_quotes = False
                quote_char = None
                while i < n:
                    ch = response[i]
                    if in_quotes:
                        if ch == '\\' and i + 1 < n:
                            i += 2
                            continue
                        if ch == quote_char:
                            in_quotes = False
                    else:
                        if ch in ('"', "'"):
                            in_quotes = True
                            quote_char = ch
                        elif ch in '([{':
                            depth += 1
                        elif ch in ')]}' and depth > 0:
                            depth -= 1
                        elif ch == ']' and depth == 0:
                            break
                    i += 1
                arg_str = response[arg_start:i]
            # Tolerate a trailing ``]`` or skip ahead to one.
            while i < n and response[i] != ']':
                if not response[i].isspace():
                    break
                i += 1
            if i < n and response[i] == ']':
                i += 1
            if name:
                results.append((name, arg_str.strip()))
            idx = i if i > start else start + len(marker)
        return results

    def _parse_function_args(self, arg_str: str) -> tuple:
        """Parse an argument string into ``(args, kwargs)``.

        Handles quoted strings, JSON object/array literals, ``key=value``
        kwargs, booleans, ints and floats. Falls back to the raw token
        for anything that doesn't parse as JSON.
        """
        args: List[Any] = []
        kwargs: Dict[str, Any] = {}
        if not arg_str or not arg_str.strip():
            return args, kwargs

        parts: List[str] = []
        current = ''
        depth = 0
        in_quotes = False
        quote_char = None
        for ch in arg_str:
            if in_quotes:
                current += ch
                if ch == '\\':
                    continue
                if ch == quote_char:
                    in_quotes = False
                continue
            if ch in ('"', "'"):
                in_quotes = True
                quote_char = ch
                current += ch
            elif ch in '([{':
                depth += 1
                current += ch
            elif ch in ')]}':
                depth -= 1
                current += ch
            elif ch == ',' and depth == 0:
                if current.strip():
                    parts.append(current.strip())
                current = ''
            else:
                current += ch
        if current.strip():
            parts.append(current.strip())

        def _coerce(token: str) -> Any:
            t = token.strip()
            if not t:
                return t
            if (t.startswith('"') and t.endswith('"')) or \
               (t.startswith("'") and t.endswith("'")):
                # Try JSON-decoding double-quoted strings to handle escapes;
                # fall back to a naive strip for single quotes.
                if t.startswith('"'):
                    try:
                        import json as _json
                        return _json.loads(t)
                    except Exception:
                        return t[1:-1]
                return t[1:-1]
            if t[0] in '{[':
                try:
                    import json as _json
                    return _json.loads(t)
                except Exception:
                    return t
            low = t.lower()
            if low in ('true', 'false'):
                return low == 'true'
            if low == 'null' or low == 'none':
                return None
            try:
                return int(t)
            except ValueError:
                pass
            try:
                return float(t)
            except ValueError:
                pass
            return t

        for part in parts:
            # key=value detection (only at depth 0; the splitter above
            # already guarantees that).
            eq = -1
            in_q = False
            qc = None
            d = 0
            for k, ch in enumerate(part):
                if in_q:
                    if ch == qc:
                        in_q = False
                    continue
                if ch in ('"', "'"):
                    in_q = True
                    qc = ch
                    continue
                if ch in '([{':
                    d += 1
                elif ch in ')]}':
                    d -= 1
                elif ch == '=' and d == 0:
                    eq = k
                    break
            if eq > 0 and part[:eq].strip().isidentifier():
                key = part[:eq].strip()
                kwargs[key] = _coerce(part[eq + 1:])
            else:
                args.append(_coerce(part))
        return args, kwargs

    def _process_function_calls(self, response: str, context: Optional[Dict[str, Any]] = None) -> List[Dict[str, str]]:
        """Process function calls in the LLM response."""
        function_results_list = []
        logger.info(f"[LLMHandler] _process_function_calls called with: {response}")

        matches = self._extract_function_calls(response)
        logger.info(f"[LLMHandler] Found {len(matches)} function call matches: {matches}")

        if not matches:
            logger.info("[LLMHandler] No function calls found, returning empty list")
            return []
        
        # Track unique function calls and their results
        function_results = {}
        logger.info(f"[LLMHandler] Available functions: {list(self.game_context_functions.keys())}")
        
        # Process each unique function call
        for func_name, arg_str in matches:
            # Create unique key for function+args combination
            call_key = f"{func_name}:{arg_str}"
            
            # Skip if we've already processed this exact function call
            if call_key in function_results:
                continue
                
            logger.info(f"[LLMHandler] Processing function: {func_name} with args: '{arg_str}'")
            try:
                # Compatibility shim: if the model emits a bare dotted MCP
                # tool name (e.g. world.list_entities(...)) instead of
                # mcp("world.list_entities", {...}), route it via `mcp`.
                execute_name = func_name
                execute_args = []
                execute_kwargs = {}

                if func_name in self.game_context_functions:
                    execute_args, execute_kwargs = self._parse_function_args(arg_str)
                elif '.' in func_name and 'mcp' in self.game_context_functions:
                    args, kwargs = self._parse_function_args(arg_str)
                    if kwargs:
                        mcp_args = kwargs
                    elif len(args) == 0:
                        mcp_args = {}
                    elif len(args) == 1 and isinstance(args[0], dict):
                        mcp_args = args[0]
                    else:
                        raise ValueError(
                            f"Invalid MCP arguments for {func_name}. "
                            "Use a JSON object or keyword arguments."
                        )
                    execute_name = 'mcp'
                    execute_args = [func_name, mcp_args]

                if execute_name in self.game_context_functions:
                    logger.info(f"[LLMHandler] Calling function {execute_name} with args: {execute_args} kwargs: {execute_kwargs}")
                    # Execute the function
                    result = self.game_context_functions[execute_name]['function'](*execute_args, **execute_kwargs)
                    logger.info(f"[LLMHandler] Function {execute_name} returned: {result}")

                    # Log the original requested function name for traceability.
                    self.session_logger.log_function_call(func_name, execute_args, result)

                    function_results[call_key] = f"Function {func_name} returned: {result}"
                else:
                    logger.info(f"[LLMHandler] Unknown function: {func_name}")
                    self.session_logger.log_error(f"Unknown function: {func_name}", "Function not found in registry")
                    function_results[call_key] = f"Unknown function: {func_name}"
            except Exception as e:
                logger.error(f"[LLMHandler] Error executing {func_name}: {str(e)}")
                self.session_logger.log_error(f"Error executing {func_name}: {str(e)}", "Function execution error")
                function_results[call_key] = f"Error executing {func_name}: {str(e)}"

        for func_name, arg_str in matches:
            call_key = f"{func_name}:{arg_str}"
            if call_key in function_results:
                function_results_list.append({"role": "user", "content": f"[FUNCTION_CALL: {func_name}({arg_str})]: {function_results[call_key]}"})
        return function_results_list

    def _maybe_execute_entity_mutation_from_context(self, original_message: str,
                                                    function_results_list: List[Dict[str, str]]) -> Optional[Dict[str, str]]:
        """Recover a missed entity mutation when model only called read tools.

        Handles intents like:
        - set <entity> hp to <n>          -> dm.set_hp
        - set <entity> temp hp to <n>     -> dm.set_resource(temp_hp)
        - set <entity> <attribute> to <v> -> dm.set_property
        """
        if not original_message:
            return None
        lower_msg = original_message.lower()
        if not any(tok in lower_msg for tok in ('set', 'make', 'change', 'adjust')):
            return None
        if any('dm.set_' in str(item.get('content', '')) for item in function_results_list):
            return None

        entities_payload = None
        for item in function_results_list:
            content = str(item.get('content', ''))
            if 'Function get_entities returned:' not in content:
                continue
            marker = 'Function get_entities returned:'
            payload_str = content.split(marker, 1)[1].strip()
            try:
                parsed = ast.literal_eval(payload_str)
            except Exception:
                parsed = None
            if isinstance(parsed, list):
                entities_payload = parsed
                break
        if not entities_payload:
            return None

        # Pattern B first: set <attribute> of/for <entity> to <value>
        # (Before Pattern A so "Set temp hp for Alice to 7" is not parsed as
        # entity "temp" + attribute "hp for Alice".)
        match = re.search(
            r"set\s+([a-zA-Z_ ]+?)\s+(?:of|for)\s+(.+?)\s+(?:to|=)\s+(.+)$",
            original_message,
            flags=re.IGNORECASE,
        )
        if match:
            attr_name = match.group(1).strip().lower()
            raw_name = match.group(2).strip().strip('"\'')
            raw_value = match.group(3).strip()
        else:
            # Pattern A: set <entity> <attribute> to <value>
            match = re.search(
                r"set\s+(.+?)\s+([a-zA-Z_ ]+?)\s+(?:to|=)\s+(.+)$",
                original_message,
                flags=re.IGNORECASE,
            )
            if not match:
                return None
            raw_name = match.group(1).strip().strip('"\'')
            attr_name = match.group(2).strip().lower()
            raw_value = match.group(3).strip()

        if not attr_name or raw_value is None:
            return None

        if raw_name.lower().endswith("'s"):
            raw_name = raw_name[:-2].strip()

        def _coerce_value(text: str):
            t = text.strip().strip('"\'')
            low = t.lower()
            if low in ('true', 'yes', 'on'):
                return True
            if low in ('false', 'no', 'off'):
                return False
            try:
                return int(t)
            except Exception:
                pass
            try:
                return float(t)
            except Exception:
                pass
            return t

        value = _coerce_value(raw_value)

        query = raw_name.lower()
        candidates: List[tuple] = []
        for ent in entities_payload:
            if not isinstance(ent, dict):
                continue
            uid = str(ent.get('entity_uid') or '').strip()
            if not uid:
                continue
            for key in (ent.get('name'), ent.get('entity_uid')):
                if key:
                    candidates.append((uid, str(key).lower()))

        if not candidates:
            return None

        resolved_uid = None
        exact = [uid for uid, key in candidates if key == query]
        if exact:
            resolved_uid = exact[0]
        if resolved_uid is None:
            contains = [uid for uid, key in candidates if query in key]
            if len(contains) == 1:
                resolved_uid = contains[0]
        if resolved_uid is None:
            keys = sorted(set(key for _, key in candidates))
            near = difflib.get_close_matches(query, keys, n=1, cutoff=0.78)
            if near:
                for uid, key in candidates:
                    if key == near[0]:
                        resolved_uid = uid
                        break
        if resolved_uid is None:
            return None

        mcp_info = self.game_context_functions.get('mcp')
        if not mcp_info or 'function' not in mcp_info:
            return None

        normalized_attr = re.sub(r'\s+', '_', attr_name.strip().lower())
        if normalized_attr in ('hit_points', 'hit_point'):
            normalized_attr = 'hp'

        tool_name = None
        tool_args: Dict[str, Any] = {}
        if normalized_attr == 'hp':
            if not isinstance(value, (int, float)):
                return None
            tool_name = 'dm.set_hp'
            tool_args = {'entity_uid': resolved_uid, 'hp': int(value)}
        elif normalized_attr in ('temp_hp', 'temporary_hp', 'temp_hit_points', 'temporary_hit_points'):
            if not isinstance(value, (int, float)):
                return None
            tool_name = 'dm.set_resource'
            tool_args = {
                'entity_uid': resolved_uid,
                'resource_type': 'temp_hp',
                'op': 'set',
                'value': int(value),
            }
        else:
            tool_name = 'dm.set_property'
            tool_args = {
                'entity_uid': resolved_uid,
                'key': normalized_attr,
                'value': value,
            }

        try:
            result = mcp_info['function'](tool_name, tool_args)
        except Exception as exc:
            result = f'Error executing {tool_name} fallback: {exc}'

        args_repr = json.dumps(tool_args, ensure_ascii=False)
        return {
            'role': 'user',
            'content': (
                f"[FUNCTION_CALL: mcp(\"{tool_name}\", {args_repr})]: "
                f"Function mcp returned: {result}"
            ),
        }

    def _entities_from_function_results(self,
                                        function_results_list: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """Parse entity lists from get_entities or MCP world.list_entities traces."""
        collected: List[Dict[str, Any]] = []
        seen_uid: set = set()
        for item in function_results_list:
            content = str(item.get('content', ''))
            for prefix in (
                'Function get_entities returned: ',
                'Function mcp returned: ',
            ):
                if prefix not in content:
                    continue
                payload_str = content.split(prefix, 1)[1].strip()
                try:
                    parsed = ast.literal_eval(payload_str)
                except Exception:
                    continue
                if isinstance(parsed, dict) and isinstance(parsed.get('entities'), list):
                    for ent in parsed['entities']:
                        if isinstance(ent, dict):
                            uid = str(ent.get('entity_uid') or '').strip()
                            if uid and uid not in seen_uid:
                                seen_uid.add(uid)
                                collected.append(ent)
                elif isinstance(parsed, list):
                    for ent in parsed:
                        if isinstance(ent, dict):
                            uid = str(ent.get('entity_uid') or '').strip()
                            if uid and uid not in seen_uid:
                                seen_uid.add(uid)
                                collected.append(ent)
                break
        return collected

    def _maybe_execute_dm_add_item_from_context(
        self,
        original_message: str,
        function_results_list: List[Dict[str, str]],
    ) -> Optional[Dict[str, str]]:
        """Recover dm.add_item when the model only ran read tools for a potion grant."""
        if not original_message:
            return None
        lower_msg = original_message.lower()
        grant_words = ('give', 'grant', 'hand', 'add')
        if not any(w in lower_msg for w in grant_words):
            return None
        potion_intent = (
            'health potion' in lower_msg
            or 'healing potion' in lower_msg
            or 'potion of healing' in lower_msg
            or (
                'potion' in lower_msg
                and any(k in lower_msg for k in ('healing', 'health'))
            )
        )
        if not potion_intent:
            return None
        if any('dm.add_item' in str(item.get('content', '')) for item in function_results_list):
            return None

        entities_payload = self._entities_from_function_results(function_results_list)
        if not entities_payload:
            return None

        qty = 1
        qm = re.search(
            r'(\d+)\s*(?:x\s*)?(?:health|healing)?\s*(?:potion|potions)\b',
            lower_msg,
        )
        if qm:
            qty = max(1, int(qm.group(1)))

        item_name = 'healing_potion'

        def _resolve_uid_for_grant() -> Optional[str]:
            if len(entities_payload) == 1:
                uid = str(entities_payload[0].get('entity_uid') or '').strip()
                return uid or None

            raw_query = None
            gm = re.search(
                r"(?i)(?:give|grant|hand|add)\s+['\"]?([a-zA-Z0-9][a-zA-Z0-9'\- ]{0,48}?)['\"]?\s+"
                r'(?:a|the|their)\s+(?:health\s+|healing\s+)?potion',
                original_message,
            )
            if gm:
                raw_query = gm.group(1).strip()
            if not raw_query:
                gm2 = re.search(
                    r'(?i)(?:give|grant|hand|add)\s+([a-zA-Z0-9][a-zA-Z0-9\'\-]+)',
                    original_message,
                )
                if gm2:
                    tail = gm2.group(1).strip().lower()
                    if tail not in ('to', 'a', 'the', 'me', 'us', 'them'):
                        raw_query = gm2.group(1).strip()
            if not raw_query:
                return None
            if raw_query.lower().endswith("'s"):
                raw_query = raw_query[:-2].strip()

            query = raw_query.lower()
            candidates: List[tuple] = []
            for ent in entities_payload:
                uid = str(ent.get('entity_uid') or '').strip()
                if not uid:
                    continue
                for key in (ent.get('name'), ent.get('label'), ent.get('entity_uid')):
                    if key:
                        candidates.append((uid, str(key).lower()))

            if not candidates:
                return None

            exact = [uid for uid, key in candidates if key == query]
            if exact:
                return exact[0]
            contains = [uid for uid, key in candidates if query in key]
            if len(contains) == 1:
                return contains[0]
            keys = sorted(set(key for _, key in candidates))
            near = difflib.get_close_matches(query, keys, n=1, cutoff=0.72)
            if near:
                for uid, key in candidates:
                    if key == near[0]:
                        return uid
            return None

        resolved_uid = _resolve_uid_for_grant()
        if not resolved_uid:
            return None

        mcp_info = self.game_context_functions.get('mcp')
        if not mcp_info or 'function' not in mcp_info:
            return None

        tool_name = 'dm.add_item'
        tool_args: Dict[str, Any] = {
            'entity_uid': resolved_uid,
            'item_name': item_name,
            'qty': qty,
        }
        try:
            result = mcp_info['function'](tool_name, tool_args)
        except Exception as exc:
            result = f'Error executing {tool_name} fallback: {exc}'

        args_repr = json.dumps(tool_args, ensure_ascii=False)
        return {
            'role': 'user',
            'content': (
                f"[FUNCTION_CALL: mcp(\"{tool_name}\", {args_repr})]: "
                f"Function mcp returned: {result}"
            ),
        }

    def get_available_models(self) -> List[str]:
        """Get available models for the current provider."""
        if not self.current_provider:
            return []
        return self.current_provider.get_available_models()
    
    def set_model(self, model_name: str) -> bool:
        """Set the model for the current provider."""
        if not self.current_provider:
            return False
        return self.current_provider.set_model(model_name)
    
    def set_context_window(self, context_window: int) -> bool:
        """Set the context window size for the current provider (Ollama only)."""
        if not self.current_provider:
            return False
        
        # Only Ollama provider supports context window setting
        if hasattr(self.current_provider, 'set_context_window'):
            return self.current_provider.set_context_window(context_window)
        else:
            logger.warning(f"[LLMHandler] Provider {type(self.current_provider).__name__} does not support context window setting")
            return False
    
    def get_context_window(self) -> Optional[int]:
        """Get the current context window size for the current provider (Ollama only)."""
        if not self.current_provider:
            return None
        
        # Only Ollama provider supports context window getting
        if hasattr(self.current_provider, 'get_context_window'):
            return self.current_provider.get_context_window()
        else:
            logger.warning(f"[LLMHandler] Provider {type(self.current_provider).__name__} does not support context window getting")
            return None
    
    def get_provider_info(self) -> Dict[str, Any]:
        """Get information about the current provider."""
        if not self.current_provider:
            return {"initialized": False}
        
        info = {
            "initialized": True,
            "provider_type": type(self.current_provider).__name__,
            "available_models": self.get_available_models()
        }
        
        # Add provider-specific info
        if hasattr(self.current_provider, 'current_model'):
            info['current_model'] = self.current_provider.current_model
        
        # Add context window info for Ollama provider
        if hasattr(self.current_provider, 'get_context_window'):
            context_window = self.current_provider.get_context_window()
            if context_window:
                info['context_window'] = context_window
        
        return info
    
    def clear_history(self):
        """Clear conversation history."""
        self.conversation_history = []
        if self.current_provider and hasattr(self.current_provider, 'conversation_history'):
            self.current_provider.conversation_history = []
    
    def get_session_info(self) -> Dict[str, Any]:
        """Get information about the current session."""
        return self.session_logger.get_session_info()
    
    def clear_session(self):
        """Clear the current session and start a new one."""
        self.clear_history()
        self.session_logger = SessionLogger()
        logger.info("[LLMHandler] Started new session")
    
    def get_conversation_history(self) -> List[Dict[str, Any]]:
        """Get the conversation history."""
        return self.conversation_history
    
    def register_game_context_function(self, name: str, function: Callable, description: str):
        """Register a function that can be called to get game context."""
        logger.debug(f"[LLMHandler] Registering game context function: {name}")
        self.game_context_functions[name] = {
            'function': function,
            'description': description
        }
        logger.debug(f"[LLMHandler] Current game_context_functions: {list(self.game_context_functions.keys())}")

    def get_game_context(self) -> Dict[str, Any]:
        """Get comprehensive game context using registered functions."""
        context = {}
        # One snapshot per context build: GameContextProvider walks the map once for
        # get_entities / get_player_characters / get_npcs instead of three passes.
        for func_info in self.game_context_functions.values():
            fn = func_info.get('function')
            inst = getattr(fn, '__self__', None)
            if inst is not None and hasattr(inst, 'begin_chat_context_snapshot'):
                try:
                    inst.begin_chat_context_snapshot()
                except Exception:
                    logger.exception('[LLMHandler] begin_chat_context_snapshot failed')
                break

        for name, func_info in self.game_context_functions.items():
            try:
                fn = func_info['function']
                sig = inspect.signature(fn)
                params = list(sig.parameters.values())
                has_varargs = any(
                    p.kind in (
                        inspect.Parameter.VAR_POSITIONAL,
                        inspect.Parameter.VAR_KEYWORD,
                    )
                    for p in params
                )
                required_params = [
                    p for p in params
                    if p.kind in (
                        inspect.Parameter.POSITIONAL_ONLY,
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        inspect.Parameter.KEYWORD_ONLY,
                    ) and p.default is inspect._empty
                ]

                # Only call plain zero-arg snapshot-safe functions.
                if not has_varargs and not required_params:
                    result = fn()
                    context[name] = result
                else:
                    logger.debug(f"[LLMHandler] Skipping function {name} in context snapshot (requires arguments)")
            except Exception as e:
                logger.error(f"Error calling game context function {name}: {e}")
                context[name] = {"error": str(e)}
        
        return context

    def _format_compact_entity_roster(self, entities: List[Dict[str, Any]]) -> str:
        """Bounded name/uid/position/HP lines for the DM system prompt (reduces redundant get_entities)."""
        if not entities:
            return ""
        try:
            max_chars = int(os.getenv("N20_DM_ENTITY_ROSTER_MAX_CHARS", "6000"))
        except ValueError:
            max_chars = 6000
        try:
            max_rows = int(os.getenv("N20_DM_ENTITY_ROSTER_MAX_ROWS", "120"))
        except ValueError:
            max_rows = 120

        sorted_ents = sorted(
            [e for e in entities if isinstance(e, dict)],
            key=lambda e: (
                str(e.get('name') or e.get('entity_uid') or '').lower(),
                str(e.get('entity_uid') or ''),
            ),
        )
        if not sorted_ents:
            return ""

        rows: List[str] = []
        total = len(sorted_ents)
        for ent in sorted_ents[:max_rows]:
            name = str(ent.get('name') or '?').replace('\n', ' ')
            uid = str(ent.get('entity_uid') or '?').replace('\n', ' ')
            typ = str(ent.get('type') or '?').replace('\n', ' ')
            pos = ent.get('position')
            pos_s = str(pos) if pos is not None else '?'
            hp = ent.get('hp')
            max_hp = ent.get('max_hp')
            parts = [f"- {name}", f"uid={uid}", typ, f"pos={pos_s}"]
            if hp is not None and max_hp is not None:
                parts.append(f"{hp}/{max_hp} HP")
            elif hp is not None:
                parts.append(f"{hp} HP")
            rows.append(' | '.join(parts))

        lines = [
            'Current map entity roster (use `entity_uid` for dm.* / MCP; inventory, spells, '
            'other maps, or full detail still require tools):',
        ]
        lines.extend(rows)
        if total > max_rows:
            lines.append(
                f'... and {total - max_rows} more not listed '
                f'(set N20_DM_ENTITY_ROSTER_MAX_ROWS or use get_entities / world.get_map).'
            )

        body = '\n'.join(lines)
        if len(body) > max_chars:
            trimmed = body[:max_chars]
            cut = trimmed.rsplit('\n', 1)[0]
            body = cut + '\n... [entity roster truncated by N20_DM_ENTITY_ROSTER_MAX_CHARS]'

        return '\n\n' + body

    def _build_system_prompt(self, context: Optional[Dict[str, Any]] = None) -> str:
        """Build a strict system prompt enforcing function calling."""
        # Build the MCP tool catalogue from the registry that backs the
        # `mcp` bridge function (registered by webapp.app). This guarantees
        # the model only ever sees tools that actually exist, preventing
        # hallucinations like `world.create_entity` which then silently
        # error out and get summarised as a fake success.
        mcp_catalog_lines: List[str] = []
        mcp_info = self.game_context_functions.get('mcp')
        if mcp_info and mcp_info.get('mcp_registry') is not None:
            try:
                for manifest in mcp_info['mcp_registry'].list():
                    name = manifest.get('name', '')
                    desc = (manifest.get('description') or '').strip().splitlines()[0] if manifest.get('description') else ''
                    if desc:
                        mcp_catalog_lines.append(f"- mcp(\"{name}\", {{...}}) — {desc}")
                    else:
                        mcp_catalog_lines.append(f"- mcp(\"{name}\", {{...}})")
            except Exception:  # noqa: BLE001
                logger.exception("[LLMHandler] Failed to enumerate MCP registry for system prompt")

        if mcp_catalog_lines:
            mcp_section = (
                "You ALSO have access to the full MCP tool surface via:\n"
                "- mcp(\"tool.name\", { \"arg\": value, ... })\n\n"
                "ALL available MCP tools (use ONLY these names; do not invent\n"
                "tool names like world.create_entity):\n"
                + "\n".join(mcp_catalog_lines)
            )
        else:
            mcp_section = (
                "You ALSO have access to the full MCP tool surface via:\n"
                "- mcp(\"tool.name\", { \"arg\": value, ... })\n"
                "(MCP tool catalogue not available; rely on the legacy get_* helpers above.)"
            )

        template = read_prompt_with_campaign_override(
            'dm_assistant_system.template.txt', 'dm_system_prompt.txt'
        )
        prompt = template.replace('<<<MCP_SECTION>>>', mcp_section)

        if context:
            # Context can be provided in different shapes depending on caller.
            session_ctx = context.get('session') if isinstance(context.get('session'), dict) else {}
            map_info_ctx = context.get('get_map_info') if isinstance(context.get('get_map_info'), dict) else {}
            current_map = (
                context.get('current_map')
                or session_ctx.get('current_map')
                or map_info_ctx.get('name')
                or 'Unknown'
            )
            prompt += f"\n\nCurrent Map: {current_map}"

            battle_ctx = context.get('battle')
            battle_status_ctx = context.get('get_battle_status') if isinstance(context.get('get_battle_status'), dict) else {}
            battle_active = bool(battle_ctx) or bool(battle_status_ctx.get('active'))
            current_turn = context.get('current_turn') or battle_status_ctx.get('current_turn') or 'Unknown'
            if battle_active:
                prompt += f"\nBattle Status: Active (Current Turn: {current_turn})"
            else:
                prompt += "\nBattle Status: No active battle"
            
            entities_ctx = context.get('entities') or context.get('get_entities')
            if isinstance(entities_ctx, list):
                prompt += f"\nEntities on Map: {len(entities_ctx)}"
                roster_block = self._format_compact_entity_roster(entities_ctx)
                if roster_block:
                    prompt += roster_block
            
            pov_ctx = context.get('pov_entity')
            if pov_ctx is None and isinstance(session_ctx, dict):
                pov_ctx = session_ctx.get('pov_entity')
            if pov_ctx:
                prompt += f"\nCurrent POV uids: {pov_ctx}"
        
        prompt += "\n\nHow can I help you with your D&D game today?"
        return prompt

    def parse_and_execute_function_calls(self, response: str) -> dict:
        """Parse all [FUNCTION_CALL: ...] in the response and execute them."""
        matches = self._extract_function_calls(response)
        results = {}

        for func_name, arg_str in matches:
            func_name = func_name.strip()
            args, kwargs = self._parse_function_args(arg_str)
            execute_name = func_name
            execute_args = args
            execute_kwargs = kwargs

            if func_name not in self.game_context_functions and '.' in func_name and 'mcp' in self.game_context_functions:
                if kwargs:
                    mcp_args = kwargs
                elif len(args) == 0:
                    mcp_args = {}
                elif len(args) == 1 and isinstance(args[0], dict):
                    mcp_args = args[0]
                else:
                    mcp_args = None
                if mcp_args is not None:
                    execute_name = 'mcp'
                    execute_args = [func_name, mcp_args]
                    execute_kwargs = {}

            # Check if function exists in registry
            if execute_name not in self.game_context_functions:
                result = f'Unknown function: {func_name}'
            else:
                func_info = self.game_context_functions[execute_name]
                if 'function' not in func_info:
                    result = f'Invalid function info for: {execute_name}'
                else:
                    try:
                        # Call the function with parsed arguments
                        func = func_info['function']
                        result = func(*execute_args, **execute_kwargs)
                    except Exception as e:
                        logger.error(f"Error executing function {execute_name}: {e}")
                        result = f'Error executing {func_name}: {str(e)}'
            
            # Store result with function signature for clarity
            func_signature = f"{func_name}({', '.join(str(arg) for arg in args)})"
            results[func_signature] = result
        
        return results

    def _clean_response(self, response: str) -> str:
        """Clean the response by removing thinking tags and unwanted content."""
        original_response = response
        
        # Remove thinking tags and their content
        response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL)
        response = re.sub(r'<reasoning>.*?</reasoning>', '', response, flags=re.DOTALL)
        response = re.sub(r'<thought>.*?</thought>', '', response, flags=re.DOTALL)
        
        # Remove reasoning blocks that start with "Okay, so" or similar
        response = re.sub(r'Okay, so.*?(?=\[FUNCTION_CALL:|$)', '', response, flags=re.DOTALL)
        response = re.sub(r'Let me.*?(?=\[FUNCTION_CALL:|$)', '', response, flags=re.DOTALL)
        response = re.sub(r'I need to.*?(?=\[FUNCTION_CALL:|$)', '', response, flags=re.DOTALL)
        
        # Check if there are function calls in the response
        has_function_calls = "[FUNCTION_CALL:" in response
        
        if has_function_calls:
            # If there are function calls, only keep content from the first function call onwards
            function_call_match = re.search(r'\[FUNCTION_CALL:', response)
            if function_call_match:
                response = response[function_call_match.start():]
        else:
            # If no function calls, preserve all content after removing thinking tags
            # This allows for natural language responses when no function calls are needed
            pass
        
        # Clean up extra whitespace and newlines
        response = re.sub(r'\n\s*\n', '\n', response)
        response = response.strip()
        
        # If we removed all content and there are no function calls, return a fallback
        if not response.strip() and "[FUNCTION_CALL:" not in response:
            logger.warning(f"[LLMHandler] Cleaned response is empty, original was: {repr(original_response)}")
            # Check if the original response had any useful content after thinking tags
            # Remove thinking tags from original to check for remaining content
            cleaned_original = re.sub(r'<think>.*?</think>', '', original_response, flags=re.DOTALL)
            cleaned_original = re.sub(r'<reasoning>.*?</reasoning>', '', cleaned_original, flags=re.DOTALL)
            cleaned_original = re.sub(r'<thought>.*?</thought>', '', cleaned_original, flags=re.DOTALL)
            cleaned_original = cleaned_original.strip()
            
            if cleaned_original and len(cleaned_original) > 10:
                # There's useful content after thinking tags, return it
                logger.info(f"[LLMHandler] Found useful content after thinking tags: {cleaned_original[:100]}...")
                response = cleaned_original
            elif "function" in original_response.lower() or "call" in original_response.lower():
                # Try to extract any function-like patterns
                function_patterns = re.findall(r'\[.*?\]', original_response)
                if function_patterns:
                    response = '\n'.join(function_patterns)
                else:
                    response = "I'm here to help with your D&D game! What would you like to know?"
            else:
                response = "I'm here to help with your D&D game! What would you like to know?"
        
        logger.debug(f"[LLMHandler] Cleaned response: {repr(response)}")
        return response


# Global instance
llm_handler = LLMHandler() 