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

logger = logging.getLogger(__name__)


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

IMPORTANT:
- For any question about the game state, you MUST respond ONLY with function calls in the format:
  [FUNCTION_CALL: function_name(arguments_if_any)]
- Do NOT answer from your own knowledge or make up information.
- If multiple functions are needed, list each on a separate line.
- After the function call(s), wait for the result before responding further.

Examples:
User: Who are the characters?
Assistant:
[FUNCTION_CALL: get_player_characters()]
[FUNCTION_CALL: get_npcs()]

User: What is the current map?
Assistant:
[FUNCTION_CALL: get_map_info()]

User: Tell me about the entity named "Goblin King"
Assistant:
[FUNCTION_CALL: get_entity_details(Goblin King)]
'''
        if context:
            prompt += f"\nCurrent Map: {context.get('current_map', 'Unknown')}"
            if context.get('battle'):
                prompt += f"\nBattle Status: Active (Current Turn: {context.get('current_turn', 'Unknown')})"
            else:
                prompt += "\nBattle Status: No active battle"
            if context.get('entities'):
                prompt += f"\nEntities on Map: {len(context['entities'])}"
            if context.get('pov_entity'):
                prompt += f"\nCurrent POV: {context['pov_entity']}"
        prompt += "\n\nRemember: For any game state question, respond ONLY with function calls as shown above."
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
        """Build a comprehensive system prompt with RAG context."""
        prompt = """You are an AI assistant for a Dungeons & Dragons Virtual Tabletop (VTT) system. Your role is to help the Dungeon Master (DM) manage and control the game environment.

## Your Capabilities:
1. **Map Information**: Access current map data including terrain, entities, and positioning
2. **Character Management**: Provide information about player characters and NPCs
3. **Game Mechanics**: Help with D&D 5e rules, combat, and gameplay
4. **VTT Control**: Assist with map navigation, entity positioning, and game state management

## IMPORTANT: Function Calling Instructions
When users ask about game state, you MUST use the available functions to get real-time information. Do not make assumptions or provide generic responses.

### Available Functions (USE THESE WHEN NEEDED):
- `get_map_info()`: Get current map details, terrain, and layout
- `get_entities()`: List all entities on the current map with their positions and status
- `get_player_characters()`: Get information about player characters
- `get_npcs()`: Get information about NPCs in the current area
- `get_entity_details(entity_name)`: Get detailed information about a specific entity
- `get_battle_status()`: Get current battle information if combat is active

### Function Calling Protocol:
1. **ALWAYS use functions when asked about game state**
2. **For character questions**: Use `get_player_characters()` and `get_npcs()`
3. **For map questions**: Use `get_map_info()` and `get_entities()`
4. **For battle questions**: Use `get_battle_status()`
5. **For specific entities**: Use `get_entity_details(entity_name)`

### Response Format:
When using functions, format your response like this:
```
[FUNCTION_CALL: function_name]
[RESPONSE: actual response based on function data]
```

## Response Guidelines:
- Be helpful and informative but concise
- When referencing game elements, use their exact names from the function data
- ALWAYS use functions to get current game state - never assume or guess
- Provide actionable advice when appropriate
- Maintain the fantasy atmosphere while being practical

## Current Game Context:"""

        if context:
            prompt += f"\n- Current Map: {context.get('current_map', 'Unknown')}"
            if context.get('battle'):
                prompt += f"\n- Battle Status: Active (Current Turn: {context.get('current_turn', 'Unknown')})"
            else:
                prompt += "\n- Battle Status: No active battle"
            
            if context.get('entities'):
                prompt += f"\n- Entities on Map: {len(context['entities'])}"
            
            if context.get('pov_entity'):
                prompt += f"\n- Current POV: {context['pov_entity']}"
        
        prompt += "\n\nHow can I help you with your D&D game today? Remember to use the available functions to get current game state information."
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
                "stream": False
            }
            
            # Make the API call
            response = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get("message", {}).get("content", "No response content")
            else:
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
        """Build a comprehensive system prompt with RAG context."""
        prompt = """You are an AI assistant for a Dungeons & Dragons Virtual Tabletop (VTT) system. Your role is to help the Dungeon Master (DM) manage and control the game environment.

## Your Capabilities:
1. **Map Information**: Access current map data including terrain, entities, and positioning
2. **Character Management**: Provide information about player characters and NPCs
3. **Game Mechanics**: Help with D&D 5e rules, combat, and gameplay
4. **VTT Control**: Assist with map navigation, entity positioning, and game state management

## IMPORTANT: Function Calling Instructions
When users ask about game state, you MUST use the available functions to get real-time information. Do not make assumptions or provide generic responses.

### Available Functions (USE THESE WHEN NEEDED):
- `get_map_info()`: Get current map details, terrain, and layout
- `get_entities()`: List all entities on the current map with their positions and status
- `get_player_characters()`: Get information about player characters
- `get_npcs()`: Get information about NPCs in the current area
- `get_entity_details(entity_name)`: Get detailed information about a specific entity
- `get_battle_status()`: Get current battle information if combat is active

### Function Calling Protocol:
1. **ALWAYS use functions when asked about game state**
2. **For character questions**: Use `get_player_characters()` and `get_npcs()`
3. **For map questions**: Use `get_map_info()` and `get_entities()`
4. **For battle questions**: Use `get_battle_status()`
5. **For specific entities**: Use `get_entity_details(entity_name)`

### Response Format:
When using functions, format your response like this:
```
[FUNCTION_CALL: function_name]
[RESPONSE: actual response based on function data]
```

## Response Guidelines:
- Be helpful and informative but concise
- When referencing game elements, use their exact names from the function data
- ALWAYS use functions to get current game state - never assume or guess
- Provide actionable advice when appropriate
- Maintain the fantasy atmosphere while being practical

## Current Game Context:"""

        if context:
            prompt += f"\n- Current Map: {context.get('current_map', 'Unknown')}"
            if context.get('battle'):
                prompt += f"\n- Battle Status: Active (Current Turn: {context.get('current_turn', 'Unknown')})"
            else:
                prompt += "\n- Battle Status: No active battle"
            
            if context.get('entities'):
                prompt += f"\n- Entities on Map: {len(context['entities'])}"
            
            if context.get('pov_entity'):
                prompt += f"\n- Current POV: {context['pov_entity']}"
        
        prompt += "\n\nHow can I help you with your D&D game today? Remember to use the available functions to get current game state information."
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
            # Get response from provider
            response = self.current_provider.send_message(messages)
            logger.debug(f"[LLMHandler] Raw response from provider: {response}")
            
            # Check if response contains function calls
            if "[FUNCTION_CALL:" in response:
                logger.debug("[LLMHandler] Detected FUNCTION_CALL in response. Processing function calls...")
                processed_response = self._process_function_calls(response, context)
                logger.debug(f"[LLMHandler] Processed response after function calls: {processed_response}")
                response = processed_response
            
            # Add response to conversation history
            self.conversation_history.append({"role": "assistant", "content": response})
            logger.debug(f"[LLMHandler] Updated conversation history: {self.conversation_history}")
            
            return response
            
        except Exception as e:
            logger.error(f"[LLMHandler] Error communicating with AI: {str(e)}", exc_info=True)
            self.conversation_history.append({"role": "assistant", "content": str(e)})
            return f"Error communicating with AI: {str(e)}"

    def _process_function_calls(self, response: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Process function calls in the LLM response."""
        # Find all function calls in the response
        function_call_pattern = r'\[FUNCTION_CALL:\s*(\w+)(?:\(([^)]*)\))?\]'
        matches = re.findall(function_call_pattern, response)
        
        if not matches:
            return response
        
        # Execute each function call
        function_results = []
        for func_name, args in matches:
            try:
                if func_name in self.game_context_functions:
                    # Parse arguments if provided
                    parsed_args = []
                    if args:
                        # Simple argument parsing - can be enhanced
                        parsed_args = [arg.strip().strip('"\'') for arg in args.split(',')]
                    
                    # Execute the function
                    result = self.game_context_functions[func_name]['function'](*parsed_args)
                    function_results.append(f"Function {func_name} returned: {result}")
                else:
                    function_results.append(f"Unknown function: {func_name}")
            except Exception as e:
                function_results.append(f"Error executing {func_name}: {str(e)}")
        
        # Replace function calls with results
        processed_response = response
        for i, (func_name, args) in enumerate(matches):
            if i < len(function_results):
                # Replace the function call with the result
                old_text = f"[FUNCTION_CALL: {func_name}({args})]" if args else f"[FUNCTION_CALL: {func_name}]"
                processed_response = processed_response.replace(old_text, function_results[i], 1)
        
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

IMPORTANT:
- For any question about the game state, you MUST respond ONLY with function calls in the format:
  [FUNCTION_CALL: function_name(arguments_if_any)]
- Do NOT answer from your own knowledge or make up information.
- If multiple functions are needed, list each on a separate line.
- After the function call(s), wait for the result before responding further.

Examples:
User: Who are the characters?
Assistant:
[FUNCTION_CALL: get_player_characters()]
[FUNCTION_CALL: get_npcs()]

User: What is the current map?
Assistant:
[FUNCTION_CALL: get_map_info()]

User: Tell me about the entity named "Goblin King"
Assistant:
[FUNCTION_CALL: get_entity_details(Goblin King)]
'''
        if context:
            prompt += f"\nCurrent Map: {context.get('current_map', 'Unknown')}"
            if context.get('battle'):
                prompt += f"\nBattle Status: Active (Current Turn: {context.get('current_turn', 'Unknown')})"
            else:
                prompt += "\nBattle Status: No active battle"
            if context.get('entities'):
                prompt += f"\nEntities on Map: {len(context['entities'])}"
            if context.get('pov_entity'):
                prompt += f"\nCurrent POV: {context['pov_entity']}"
        prompt += "\n\nRemember: For any game state question, respond ONLY with function calls as shown above."
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


# Global instance
llm_handler = LLMHandler() 