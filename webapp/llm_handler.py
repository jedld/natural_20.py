"""
LLM Handler for DM Chatbot Interface

This module provides a skeleton for interacting with large language models
in the DM console. It's designed to be extensible for different LLM providers.
"""

import os
import json
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Callable
import requests
from datetime import datetime
import re
import uuid

logger = logging.getLogger('werkzeug')
logger.setLevel(logging.INFO)


class SessionLogger:
    """Handles session-based logging for LLM interactions."""
    
    def __init__(self, log_dir: str = "llm_logs"):
        self.log_dir = log_dir
        self.session_id = str(uuid.uuid4())[:8]  # Short session ID
        self.session_start = datetime.now()
        
        # Create log directory if it doesn't exist
        os.makedirs(self.log_dir, exist_ok=True)
        
        # Create session log file
        self.log_file = os.path.join(self.log_dir, f"session_{self.session_id}_{self.session_start.strftime('%Y%m%d_%H%M%S')}.log")
        
        # Write session header
        with open(self.log_file, 'w') as f:
            f.write(f"=== LLM SESSION LOG ===\n")
            f.write(f"Session ID: {self.session_id}\n")
            f.write(f"Start Time: {self.session_start}\n")
            f.write(f"Log File: {self.log_file}\n")
            f.write("=" * 50 + "\n\n")
        
        logger.info(f"[SessionLogger] Created session log: {self.log_file}")
    
    def log_interaction(self, interaction_type: str, content: str, metadata: Optional[Dict[str, Any]] = None):
        """Log an interaction with timestamp and metadata."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        
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
    
    def log_response(self, response: str, provider_info: Dict[str, Any]):
        """Log a raw response from the LLM."""
        metadata = {
            "provider": provider_info.get("provider_type", "unknown"),
            "model": provider_info.get("current_model", "unknown"),
            "response_length": len(response)
        }
        
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
                self.client = OpenAI(api_key=self.api_key)
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
            system_prompt = self._build_system_prompt(messages)
            
            # Add to conversation history
            self.conversation_history.append({"role": "user", "content": messages[-1]['content']})
            
            # Prepare messages for API call
            messages = [{"role": "system", "content": system_prompt}] + self.conversation_history
            
            response = self.client.chat.completions.create(
                model=self.current_model,
                messages=messages,
                max_tokens=1000,
                temperature=0.7
            )
            
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
        prompt = '''You are an AI assistant for a D&D Virtual Tabletop (VTT).
You have access to the following functions:
- get_map_info()
- get_entities()
- get_player_characters()
- get_npcs()
- get_entity_details(entity_name)
- get_battle_status()

IMPORTANT RULES:
1. **NEVER use thinking tags like <think> or reasoning blocks**
2. **NEVER explain your reasoning or thought process**
3. **For any question about the game state, respond ONLY with function calls in this exact format:**
   [FUNCTION_CALL: function_name(arguments_if_any)]
4. **Do NOT answer from your own knowledge or make up information**
5. **Do NOT provide explanations or context - just the function calls**
6. **If multiple functions are needed, list each on a separate line**
7. **For general questions, use get_map_info() and get_entities() to provide context**
8. **For entity details, use get_entity_details("entity_name") with quotes around the name**

EXAMPLES:
User: "Who are the characters?"
Assistant: [FUNCTION_CALL: get_player_characters()]
[FUNCTION_CALL: get_npcs()]

User: "What is the current map?"
Assistant: [FUNCTION_CALL: get_map_info()]

User: "Tell me about the entity named 'Goblin King'"
Assistant: [FUNCTION_CALL: get_entity_details("Goblin King")]

User: "What's the battle status?"
Assistant: [FUNCTION_CALL: get_battle_status()]

User: "Please describe yourself"
Assistant: [FUNCTION_CALL: get_map_info()]
[FUNCTION_CALL: get_entities()]

User: "Hello"
Assistant: [FUNCTION_CALL: get_map_info()]
[FUNCTION_CALL: get_entities()]

User: "Give me basic information about the current game"
Assistant: [FUNCTION_CALL: get_map_info()]
[FUNCTION_CALL: get_entities()]

REMEMBER: 
- Respond ONLY with function calls, no explanations, no thinking, no reasoning
- Use quotes around string arguments like entity names
- Always use the exact function names listed above'''
        
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
            system_prompt = self._build_system_prompt(messages)
            
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
            
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=data,
                timeout=30
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
        prompt = '''You are an AI assistant for a D&D Virtual Tabletop (VTT).
You have access to the following functions:
- get_map_info()
- get_entities()
- get_player_characters()
- get_npcs()
- get_entity_details(entity_name)
- get_battle_status()

IMPORTANT RULES:
1. **NEVER use thinking tags like <think> or reasoning blocks**
2. **NEVER explain your reasoning or thought process**
3. **For any question about the game state, respond ONLY with function calls in this exact format:**
   [FUNCTION_CALL: function_name(arguments_if_any)]
4. **Do NOT answer from your own knowledge or make up information**
5. **Do NOT provide explanations or context - just the function calls**
6. **If multiple functions are needed, list each on a separate line**
7. **For general questions, use get_map_info() and get_entities() to provide context**
8. **For entity details, use get_entity_details("entity_name") with quotes around the name**

EXAMPLES:
User: "Who are the characters?"
Assistant: [FUNCTION_CALL: get_player_characters()]
[FUNCTION_CALL: get_npcs()]

User: "What is the current map?"
Assistant: [FUNCTION_CALL: get_map_info()]

User: "Tell me about the entity named 'Goblin King'"
Assistant: [FUNCTION_CALL: get_entity_details("Goblin King")]

User: "What's the battle status?"
Assistant: [FUNCTION_CALL: get_battle_status()]

User: "Please describe yourself"
Assistant: [FUNCTION_CALL: get_map_info()]
[FUNCTION_CALL: get_entities()]

User: "Hello"
Assistant: [FUNCTION_CALL: get_map_info()]
[FUNCTION_CALL: get_entities()]

User: "Give me basic information about the current game"
Assistant: [FUNCTION_CALL: get_map_info()]
[FUNCTION_CALL: get_entities()]

REMEMBER: 
- Respond ONLY with function calls, no explanations, no thinking, no reasoning
- Use quotes around string arguments like entity names
- Always use the exact function names listed above'''
        
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


class OllamaProvider(LLMProvider):
    """Ollama local provider."""
    
    def __init__(self):
        self.base_url = "http://localhost:11434"
        self.model = None
        self.conversation_history = []
    
    def initialize(self, config: Dict[str, Any]) -> bool:
        try:
            self.base_url = config.get('base_url', 'http://localhost:11434')
            self.model = config.get('model')
            
            # Test connection
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
                    # Remove stop tokens that are too aggressive
                    "stop": []  # Let the model generate naturally
                }
            }
            print("Request:", payload)
            # Make the API call
            response = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=30
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
                            {"role": "system", "content": "You are a D&D VTT assistant. Respond with function calls in format [FUNCTION_CALL: function_name()]. No explanations."},
                            {"role": "user", "content": user_message}
                        ],
                        "stream": False,
                        "options": {
                            "temperature": 0.1,
                            "num_predict": 200,
                            "top_k": 10,
                            "top_p": 0.9,
                            "repeat_penalty": 1.1
                        }
                    }

                    direct_response = requests.post(
                        f"{self.base_url}/api/chat",
                        json=direct_payload,
                        timeout=30
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
            response = requests.get(f"{self.base_url}/api/tags", timeout=10)
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
    
    def _build_system_prompt(self, context: Optional[Dict[str, Any]] = None) -> str:
        """Build a strict system prompt enforcing function calling."""
        prompt = '''You are an AI assistant for a D&D Virtual Tabletop (VTT).
You have access to the following functions:
- get_map_info()
- get_entities()
- get_player_characters()
- get_npcs()
- get_entity_details(entity_name)
- get_battle_status()

IMPORTANT RULES:
1. **NEVER use thinking tags like <think> or reasoning blocks**
2. **NEVER explain your reasoning or thought process**
3. **For any question about the game state, respond ONLY with function calls in this exact format:**
   [FUNCTION_CALL: function_name(arguments_if_any)]
4. **Do NOT answer from your own knowledge or make up information**
5. **Do NOT provide explanations or context - just the function calls**
6. **If multiple functions are needed, list each on a separate line**
7. **For general questions, use get_map_info() and get_entities() to provide context**
8. **For entity details, use get_entity_details("entity_name") with quotes around the name**

EXAMPLES:
User: "Who are the characters?"
Assistant: [FUNCTION_CALL: get_player_characters()]
[FUNCTION_CALL: get_npcs()]

User: "What is the current map?"
Assistant: [FUNCTION_CALL: get_map_info()]

User: "Tell me about the entity named 'Goblin King'"
Assistant: [FUNCTION_CALL: get_entity_details("Goblin King")]

User: "What's the battle status?"
Assistant: [FUNCTION_CALL: get_battle_status()]

User: "Please describe yourself"
Assistant: [FUNCTION_CALL: get_map_info()]
[FUNCTION_CALL: get_entities()]

User: "Hello"
Assistant: [FUNCTION_CALL: get_map_info()]
[FUNCTION_CALL: get_entities()]

User: "Give me basic information about the current game"
Assistant: [FUNCTION_CALL: get_map_info()]
[FUNCTION_CALL: get_entities()]

REMEMBER: 
- Respond ONLY with function calls, no explanations, no thinking, no reasoning
- Use quotes around string arguments like entity names
- Always use the exact function names listed above'''
        
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


class LLMHandler:
    """Main handler for LLM interactions with RAG capabilities."""
    
    def __init__(self):
        self.providers = {
            'mock': MockProvider(),
            'openai': OpenAIProvider(),
            'anthropic': AnthropicProvider(),
            'ollama': OllamaProvider()
        }
        self.current_provider = None
        self.game_context_functions = {}
        self.conversation_history = []
    
    def initialize_provider(self, provider_name: str, config: Dict[str, Any]) -> bool:
        """Initialize a specific LLM provider."""
        if provider_name not in self.providers:
            logger.error(f"Unknown provider: {provider_name}")
            return False
        
        provider = self.providers[provider_name]
        if provider.initialize(config):
            self.current_provider = provider
            return True
        return False
    
    def send_message(self, message: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Send a message to the LLM and get a response."""
        logger.debug(f"[LLMHandler] send_message called with message: {message}")
        if not self.current_provider:
            logger.error("[LLMHandler] No LLM provider initialized.")
            return "AI assistant is not initialized. Please initialize a provider first."
        
        # Add message to conversation history
        self.conversation_history.append({"role": "user", "content": message})
        logger.debug(f"[LLMHandler] Conversation history: {self.conversation_history}")
        
        # Build system prompt with context
        system_prompt = self._build_system_prompt(context)
        logger.debug(f"[LLMHandler] System prompt: {system_prompt}")
        
        # Prepare messages for the LLM
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(self.conversation_history)
        logger.debug(f"[LLMHandler] Messages sent to provider: {messages}")
        
        try:
            # For thinking models, we need to handle back-and-forth conversation
            max_iterations = 5  # Reduced from 10 to prevent long loops
            iteration = 0
            thinking_count = 0  # Track consecutive thinking responses
            previous_responses = []  # Track previous responses to detect loops
            
            while iteration < max_iterations:
                iteration += 1
                logger.debug(f"[LLMHandler] Iteration {iteration}")

                # Get response from provider
                raw_response = self.current_provider.send_message(messages)
                logger.info(f"[LLMHandler] Raw response from provider: {raw_response}")

                # Clean the response
                cleaned_response = self._clean_response(raw_response)
                logger.info(f"[LLMHandler] Cleaned response: {cleaned_response}")
                
                # Check for repeated responses (loop detection)
                if cleaned_response in previous_responses:
                    logger.warning(f"[LLMHandler] Detected repeated response, breaking loop")
                    # Try a direct approach with a simpler prompt
                    direct_messages = [
                        {"role": "system", "content": "You are a D&D VTT assistant. Respond ONLY with function calls in format [FUNCTION_CALL: function_name()]. No explanations, no thinking."},
                        {"role": "user", "content": message}
                    ]
                    response = self.current_provider.send_message(direct_messages)
                    cleaned_response = self._clean_response(response)
                    
                    if cleaned_response.strip() and "[FUNCTION_CALL:" in cleaned_response:
                        processed_response = self._process_function_calls(cleaned_response, context)
                        formatted_response = self._format_function_results(processed_response, message)
                        self.conversation_history.append({"role": "assistant", "content": formatted_response})
                        return formatted_response
                    else:
                        # Provide fallback response
                        fallback = "I'm here to help with your D&D game! I can provide information about the current map, entities, characters, and battle status. What would you like to know?"
                        self.conversation_history.append({"role": "assistant", "content": fallback})
                        return fallback
                
                # Also check raw response for repeated patterns
                if raw_response in previous_responses:
                    logger.warning(f"[LLMHandler] Detected repeated raw response, breaking loop")
                    # Try a direct approach with a simpler prompt
                    direct_messages = [
                        {"role": "system", "content": "You are a D&D VTT assistant. Respond ONLY with function calls in format [FUNCTION_CALL: function_name()]. No explanations, no thinking."},
                        {"role": "user", "content": message}
                    ]
                    response = self.current_provider.send_message(direct_messages)
                    cleaned_response = self._clean_response(response)
                    
                    if cleaned_response.strip() and "[FUNCTION_CALL:" in cleaned_response:
                        processed_response = self._process_function_calls(cleaned_response, context)
                        formatted_response = self._format_function_results(processed_response, message)
                        self.conversation_history.append({"role": "assistant", "content": formatted_response})
                        return formatted_response
                    else:
                        # Provide fallback response
                        fallback = "I'm here to help with your D&D game! I can provide information about the current map, entities, characters, and battle status. What would you like to know?"
                        self.conversation_history.append({"role": "assistant", "content": fallback})
                        return fallback
                
                # Check for similar responses (partial match)
                for prev_response in previous_responses:
                    if prev_response and len(prev_response) > 10:  # Only check substantial responses
                        # Check if current response is very similar to a previous one
                        if (cleaned_response and len(cleaned_response) > 10 and 
                            (cleaned_response in prev_response or prev_response in cleaned_response)):
                            logger.warning(f"[LLMHandler] Detected similar response, breaking loop")
                            # Try a direct approach with a simpler prompt
                            direct_messages = [
                                {"role": "system", "content": "You are a D&D VTT assistant. Respond ONLY with function calls in format [FUNCTION_CALL: function_name()]. No explanations, no thinking."},
                                {"role": "user", "content": message}
                            ]
                            response = self.current_provider.send_message(direct_messages)
                            cleaned_response = self._clean_response(response)
                            
                            if cleaned_response.strip() and "[FUNCTION_CALL:" in cleaned_response:
                                processed_response = self._process_function_calls(cleaned_response, context)
                                formatted_response = self._format_function_results(processed_response, message)
                                self.conversation_history.append({"role": "assistant", "content": formatted_response})
                                return formatted_response
                            else:
                                # Provide fallback response
                                fallback = "I'm here to help with your D&D game! I can provide information about the current map, entities, characters, and battle status. What would you like to know?"
                                self.conversation_history.append({"role": "assistant", "content": fallback})
                                return fallback
                
                # Check if conversation history is getting too long
                if len(self.conversation_history) > 10:
                    logger.warning(f"[LLMHandler] Conversation history too long ({len(self.conversation_history)}), trimming history")
                    # Remove oldest entries to keep the length at 10
                    self.conversation_history = self.conversation_history[-10:]
                    # No need to break the loop, just continue
                
                previous_responses.append(cleaned_response)
                previous_responses.append(raw_response)
                
                # Check if the response contains thinking patterns
                has_thinking = re.search(r'<think>|<reasoning>|<thought>|Okay, so|Let me|I need to', raw_response, re.IGNORECASE)
                
                # Check if the response contains function calls
                has_function_calls = "[FUNCTION_CALL:" in cleaned_response
                
                # If we have function calls, process them and provide results as context
                if has_function_calls:
                    logger.info("[LLMHandler] Found function calls, processing...")
                    logger.info(f"[LLMHandler] Function calls found in: {cleaned_response}")
                    processed_response = self._process_function_calls(cleaned_response, context)
                    logger.info(f"[LLMHandler] Function call results: {processed_response}")
                    
                    # Add the function results as context for the next iteration
                    context_message = f"Here is the game data I gathered: {processed_response}\n\nPlease provide a complete, user-friendly response based on this information."
                    self.conversation_history.append({"role": "assistant", "content": cleaned_response})
                    self.conversation_history.append({"role": "user", "content": context_message})
                    
                    # Update messages for next iteration
                    messages = [{"role": "system", "content": system_prompt}]
                    messages.extend(self.conversation_history)
                    continue
                
                # If we have thinking patterns but no function calls, handle thinking loop
                elif has_thinking and not has_function_calls:
                    thinking_count += 1
                    logger.debug(f"[LLMHandler] Detected thinking patterns (count: {thinking_count}), continuing conversation...")
                    
                    # If we've had too many consecutive thinking responses, break the loop
                    if thinking_count >= 2:
                        logger.warning(f"[LLMHandler] Too many consecutive thinking responses ({thinking_count}), breaking loop")
                        # Try a direct approach with a simpler prompt
                        direct_messages = [
                            {"role": "system", "content": "You are a D&D VTT assistant. Respond ONLY with function calls in format [FUNCTION_CALL: function_name()]. No explanations, no thinking."},
                            {"role": "user", "content": message}
                        ]
                        response = self.current_provider.send_message(direct_messages)
                        cleaned_response = self._clean_response(response)
                        
                        if cleaned_response.strip() and "[FUNCTION_CALL:" in cleaned_response:
                            processed_response = self._process_function_calls(cleaned_response, context)
                            formatted_response = self._format_function_results(processed_response, message)
                            self.conversation_history.append({"role": "assistant", "content": formatted_response})
                            return formatted_response
                        else:
                            # Provide fallback response
                            fallback = "I'm here to help with your D&D game! I can provide information about the current map, entities, characters, and battle status. What would you like to know?"
                            self.conversation_history.append({"role": "assistant", "content": fallback})
                            return fallback
                    
                    # Add the current response to conversation history
                    self.conversation_history.append({"role": "assistant", "content": cleaned_response})
                    
                    # Add a follow-up message to encourage function calls
                    follow_up = "Please respond with function calls in the format [FUNCTION_CALL: function_name()] to gather the necessary information."
                    self.conversation_history.append({"role": "user", "content": follow_up})
                    
                    # Update messages for next iteration
                    messages = [{"role": "system", "content": system_prompt}]
                    messages.extend(self.conversation_history)
                    continue
                
                # If we have a clean response without thinking or function calls, we're done
                elif cleaned_response.strip() and not has_thinking and not has_function_calls:
                    logger.info("[LLMHandler] Got clean final response")
                    self.conversation_history.append({"role": "assistant", "content": cleaned_response})
                    return cleaned_response
                
                # If we have an empty response, try direct prompt
                else:
                    logger.debug("[LLMHandler] Empty response, trying direct prompt...")
                    direct_messages = [
                        {"role": "system", "content": "You are a D&D VTT assistant. Respond ONLY with function calls in format [FUNCTION_CALL: function_name()]. No explanations, no thinking."},
                        {"role": "user", "content": message}
                    ]
                    response = self.current_provider.send_message(direct_messages)
                    cleaned_response = self._clean_response(response)
                    
                    if cleaned_response.strip() and "[FUNCTION_CALL:" in cleaned_response:
                        processed_response = self._process_function_calls(cleaned_response, context)
                        formatted_response = self._format_function_results(processed_response, message)
                        self.conversation_history.append({"role": "assistant", "content": formatted_response})
                        return formatted_response
                    else:
                        # Provide fallback response
                        fallback = "I'm here to help with your D&D game! I can provide information about the current map, entities, characters, and battle status. What would you like to know?"
                        self.conversation_history.append({"role": "assistant", "content": fallback})
                        return fallback
            
            # If we've exceeded max iterations, provide a fallback
            logger.warning(f"[LLMHandler] Exceeded max iterations ({max_iterations}), providing fallback")
            fallback = "I'm here to help with your D&D game! I can provide information about the current map, entities, characters, and battle status. What would you like to know?"
            self.conversation_history.append({"role": "assistant", "content": fallback})
            return fallback
            
        except Exception as e:
            logger.error(f"[LLMHandler] Error communicating with AI: {str(e)}", exc_info=True)
            self.conversation_history.append({"role": "assistant", "content": str(e)})
            return f"Error communicating with AI: {str(e)}"

    def _format_function_results(self, processed_response: str, original_message: str) -> str:
        """Send function results back to the LLM for formatting."""
        formatting_messages = [
            {"role": "system", "content": """You are a helpful D&D VTT assistant. 
The user asked a question, and I've gathered the relevant game data for you. 
Please format this data into a clear, user-friendly response. 
Focus on the most important information and present it in an organized way.
Do not mention that you're formatting data - just provide the information naturally."""},
            {"role": "user", "content": f"Original question: {original_message}\n\nGame data: {processed_response}\n\nPlease provide a user-friendly response based on this data."}
        ]
        
        formatted_response = self.current_provider.send_message(formatting_messages)
        logger.info(f"[LLMHandler] Formatted response: {formatted_response}")
        return formatted_response

    def _process_function_calls(self, response: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Process function calls in the LLM response."""
        logger.info(f"[LLMHandler] _process_function_calls called with: {response}")
        
        # Find all function calls in the response - improved regex to handle arguments better
        function_call_pattern = r'\[FUNCTION_CALL:\s*(\w+)(?:\(([^)]*)\))?\]'
        matches = re.findall(function_call_pattern, response)
        logger.info(f"[LLMHandler] Found {len(matches)} function call matches: {matches}")
        
        if not matches:
            logger.info("[LLMHandler] No function calls found, returning original response")
            return response
        
        # Execute each function call
        function_results = []
        logger.info(f"[LLMHandler] Available functions: {list(self.game_context_functions.keys())}")
        for func_name, arg_str in matches:
            logger.info(f"[LLMHandler] Processing function: {func_name} with args: '{arg_str}'")
            try:
                if func_name in self.game_context_functions:
                    # Parse arguments using improved logic
                    args = []
                    kwargs = {}
                    
                    if arg_str and arg_str.strip():
                        # Handle quoted strings and simple arguments
                        arg_parts = []
                        current_part = ""
                        in_quotes = False
                        quote_char = None
                        
                        for char in arg_str:
                            if char in ['"', "'"] and not in_quotes:
                                in_quotes = True
                                quote_char = char
                            elif char == quote_char and in_quotes:
                                in_quotes = False
                                quote_char = None
                            elif char == ',' and not in_quotes:
                                if current_part.strip():
                                    arg_parts.append(current_part.strip())
                                current_part = ""
                            else:
                                current_part += char
                        
                        if current_part.strip():
                            arg_parts.append(current_part.strip())
                        
                        # Convert arguments to appropriate types
                        for part in arg_parts:
                            part = part.strip()
                            if part.startswith('"') and part.endswith('"'):
                                args.append(part[1:-1])
                            elif part.startswith("'") and part.endswith("'"):
                                args.append(part[1:-1])
                            elif part.lower() in ['true', 'false']:
                                args.append(part.lower() == 'true')
                            elif part.isdigit():
                                args.append(int(part))
                            elif part.replace('.', '').isdigit():
                                args.append(float(part))
                            else:
                                args.append(part)
                    
                    logger.info(f"[LLMHandler] Calling function {func_name} with args: {args}")
                    # Execute the function
                    result = self.game_context_functions[func_name]['function'](*args, **kwargs)
                    logger.info(f"[LLMHandler] Function {func_name} returned: {result}")
                    function_results.append(f"Function {func_name} returned: {result}")
                else:
                    logger.info(f"[LLMHandler] Unknown function: {func_name}")
                    function_results.append(f"Unknown function: {func_name}")
            except Exception as e:
                logger.error(f"[LLMHandler] Error executing {func_name}: {str(e)}")
                function_results.append(f"Error executing {func_name}: {str(e)}")
        
        # Replace function calls with results
        processed_response = response
        for i, (func_name, arg_str) in enumerate(matches):
            if i < len(function_results):
                # Replace the function call with the result
                # Handle both cases: with arguments and without arguments
                if arg_str and arg_str.strip():
                    old_text = f"[FUNCTION_CALL: {func_name}({arg_str})]"
                else:
                    old_text = f"[FUNCTION_CALL: {func_name}()]"
                logger.info(f"[LLMHandler] Replacing '{old_text}' with '{function_results[i]}'")
                processed_response = processed_response.replace(old_text, function_results[i], 1)
        
        logger.info(f"[LLMHandler] Final processed response: {processed_response}")
        return processed_response
    
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
        
        return info
    
    def clear_history(self):
        """Clear conversation history."""
        self.conversation_history = []
        if self.current_provider and hasattr(self.current_provider, 'conversation_history'):
            self.current_provider.conversation_history = []
    
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
        
        for name, func_info in self.game_context_functions.items():
            try:
                # Only call functions that take no arguments (for context snapshot)
                if func_info['function'].__code__.co_argcount == 0:
                    result = func_info['function']()
                    context[name] = result
                else:
                    logger.debug(f"[LLMHandler] Skipping function {name} in context snapshot (requires arguments)")
            except Exception as e:
                logger.error(f"Error calling game context function {name}: {e}")
                context[name] = {"error": str(e)}
        
        return context

    def _build_system_prompt(self, context: Optional[Dict[str, Any]] = None) -> str:
        """Build a strict system prompt enforcing function calling."""
        prompt = '''You are an AI assistant for a D&D Virtual Tabletop (VTT).
You have access to the following functions:
- get_map_info()
- get_entities()
- get_player_characters()
- get_npcs()
- get_entity_details(entity_name)
- get_battle_status()

IMPORTANT RULES:
1. **NEVER use thinking tags like <think> or reasoning blocks**
2. **NEVER explain your reasoning or thought process**
3. **For any question about the game state, respond ONLY with function calls in this exact format:**
   [FUNCTION_CALL: function_name(arguments_if_any)]
4. **Do NOT answer from your own knowledge or make up information**
5. **Do NOT provide explanations or context - just the function calls**
6. **If multiple functions are needed, list each on a separate line**
7. **For general questions, use get_map_info() and get_entities() to provide context**
8. **For entity details, use get_entity_details("entity_name") with quotes around the name**

EXAMPLES:
User: "Who are the characters?"
Assistant: [FUNCTION_CALL: get_player_characters()]
[FUNCTION_CALL: get_npcs()]

User: "What is the current map?"
Assistant: [FUNCTION_CALL: get_map_info()]

User: "Tell me about the entity named 'Goblin King'"
Assistant: [FUNCTION_CALL: get_entity_details("Goblin King")]

User: "What's the battle status?"
Assistant: [FUNCTION_CALL: get_battle_status()]

User: "Please describe yourself"
Assistant: [FUNCTION_CALL: get_map_info()]
[FUNCTION_CALL: get_entities()]

User: "Hello"
Assistant: [FUNCTION_CALL: get_map_info()]
[FUNCTION_CALL: get_entities()]

User: "Give me basic information about the current game"
Assistant: [FUNCTION_CALL: get_map_info()]
[FUNCTION_CALL: get_entities()]

REMEMBER: 
- Respond ONLY with function calls, no explanations, no thinking, no reasoning
- Use quotes around string arguments like entity names
- Always use the exact function names listed above'''
        
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

    def parse_and_execute_function_calls(self, response: str) -> dict:
        """Parse all [FUNCTION_CALL: ...] in the response and execute them."""
        pattern = r'\[FUNCTION_CALL: ([^\(\\)]+)(?:\(([^\)]*)\))?\]'
        matches = re.findall(pattern, response)
        results = {}
        
        for func_name, arg_str in matches:
            func_name = func_name.strip()
            args = []
            kwargs = {}
            
            # Parse arguments
            if arg_str:
                # Simple argument parsing - split by comma and handle quoted strings
                arg_parts = []
                current_part = ""
                in_quotes = False
                quote_char = None
                
                for char in arg_str:
                    if char in ['"', "'"] and not in_quotes:
                        in_quotes = True
                        quote_char = char
                    elif char == quote_char and in_quotes:
                        in_quotes = False
                        quote_char = None
                    elif char == ',' and not in_quotes:
                        if current_part.strip():
                            arg_parts.append(current_part.strip())
                        current_part = ""
                    else:
                        current_part += char
                
                if current_part.strip():
                    arg_parts.append(current_part.strip())
                
                # Convert arguments to appropriate types
                for part in arg_parts:
                    part = part.strip()
                    if part.startswith('"') and part.endswith('"'):
                        args.append(part[1:-1])
                    elif part.startswith("'") and part.endswith("'"):
                        args.append(part[1:-1])
                    elif part.lower() in ['true', 'false']:
                        args.append(part.lower() == 'true')
                    elif part.isdigit():
                        args.append(int(part))
                    elif part.replace('.', '').isdigit():
                        args.append(float(part))
                    else:
                        args.append(part)
            
            # Check if function exists in registry
            if func_name not in self.game_context_functions:
                result = f'Unknown function: {func_name}'
            else:
                func_info = self.game_context_functions[func_name]
                if 'function' not in func_info:
                    result = f'Invalid function info for: {func_name}'
                else:
                    try:
                        # Call the function with parsed arguments
                        func = func_info['function']
                        result = func(*args, **kwargs)
                    except Exception as e:
                        logger.error(f"Error executing function {func_name}: {e}")
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
        
        # Remove any text before the first function call
        function_call_match = re.search(r'\[FUNCTION_CALL:', response)
        if function_call_match:
            response = response[function_call_match.start():]
        
        # Clean up extra whitespace and newlines
        response = re.sub(r'\n\s*\n', '\n', response)
        response = response.strip()
        
        # If we removed all content and there are no function calls, return a fallback
        if not response.strip() and "[FUNCTION_CALL:" not in response:
            logger.warning(f"[LLMHandler] Cleaned response is empty, original was: {repr(original_response)}")
            # Check if the original response had any useful content
            if "function" in original_response.lower() or "call" in original_response.lower():
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