import threading
import time
from webapp.llm_conversation_controller import LLMConversationController
import os
class LLMConversationHandler:
    """
    Handler for integrating LLM conversations with Entity objects.
    This class manages the connection between the game's conversation system and the LLM.
    """

    def __init__(self, entity, system_prompt):
        self.controller = LLMConversationController()
        self.response_threads = {}
        self.initialized = False
        self.entity = entity
        self.system_prompt = system_prompt
        self.initialize(api_key=os.environ.get('OPENAI_API_KEY'))

    def initialize(self, api_key=None, model="gpt-4o"):
        """Initialize the LLM controller with the provided API key and model."""
        try:
            self.controller.initialize_llm(api_key=api_key, model=model)
            self.initialized = True
            return True
        except Exception as e:
            print(f"Failed to initialize LLM: {e}")
            return False

    def process_message(self, entity, source, message, language, memory_buffer, directed_to=None):
        if not self.initialized:
            print("LLM conversation handler not initialized")
            return None

        # Create a conversation ID based on the entity's unique ID
        conversation_id = str(entity.entity_uid)

    
    def _generate_response_thread(self, conversation_id, entity, entity_context):
        """Background thread to generate LLM responses."""
        try:
            # Add a small delay to make the response feel more natural
            time.sleep(1)
            
            # Generate the response
            response = self.controller.generate_response(conversation_id, entity_context)
            
            # Send the response as a conversation from the entity
            if response:
                entity.send_conversation(response)
        except Exception as e:
            print(f"Error in LLM response thread: {e}")
    
    def clear_conversation(self, entity):
        """Clear the conversation history for the given entity."""
        conversation_id = str(entity.entity_uid)
        self.controller.clear_conversation(conversation_id) 