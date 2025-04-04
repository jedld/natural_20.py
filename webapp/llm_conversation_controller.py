class LLMConversationController:
    def __init__(self):
        self.conversations = {}
        self.llm_client = None
        self.api_key = None
        self.model = "gpt-4o"
        self.max_history = 10  # Maximum number of messages to keep in history

    def get_conversation(self, conversation_id):
        return self.conversations.get(conversation_id, None)
    
    def initialize_llm(self, api_key=None, model="gpt-4o"):
        """Initialize the LLM client with the provided API key and model."""
        from openai import OpenAI
        import os
        
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key is required. Set it as an environment variable OPENAI_API_KEY or pass it directly.")
        
        self.model = model
        self.llm_client = OpenAI(api_key=self.api_key)
        return self.llm_client
    
    def create_conversation(self, conversation_id, system_prompt=None):
        """Create a new conversation with the given ID and optional system prompt."""
        if conversation_id not in self.conversations:
            self.conversations[conversation_id] = {
                "messages": [],
                "system_prompt": system_prompt or "You are a helpful assistant in a Dungeons and Dragons game world."
            }
        return self.conversations[conversation_id]
    
    def add_message(self, conversation_id, role, content):
        """Add a message to the conversation history."""
        if conversation_id not in self.conversations:
            self.create_conversation(conversation_id)
        
        self.conversations[conversation_id]["messages"].append({"role": role, "content": content})
        
        # Trim history if it exceeds max_history
        if len(self.conversations[conversation_id]["messages"]) > self.max_history:
            # Keep the system prompt and the most recent messages
            system_prompt = self.conversations[conversation_id]["system_prompt"]
            messages = self.conversations[conversation_id]["messages"]
            self.conversations[conversation_id]["messages"] = messages[-self.max_history:]
    
    def generate_response(self, conversation_id, entity_context=None):
        """Generate a response from the LLM based on the conversation history."""
        if not self.llm_client:
            self.initialize_llm()
        
        if conversation_id not in self.conversations:
            return "I don't have any context for this conversation."
        
        conversation = self.conversations[conversation_id]
        
        # Prepare messages for the API call
        messages = [{"role": "system", "content": conversation["system_prompt"]}]
        
        # Add entity context if provided
        if entity_context:
            context_message = f"You are responding as {entity_context.get('name', 'an entity')}. "
            context_message += f"Your character is a {entity_context.get('race', 'unknown race')} "
            context_message += f"{entity_context.get('class', 'of unknown class')}. "
            context_message += f"Your personality: {entity_context.get('personality', 'unknown')}. "
            context_message += f"Your background: {entity_context.get('background', 'unknown')}. "
            messages.append({"role": "system", "content": context_message})
        
        # Add conversation history
        messages.extend(conversation["messages"])
        
        try:
            response = self.llm_client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=150,
                temperature=0.7
            )
            
            response_content = response.choices[0].message.content
            
            # Add the response to the conversation history
            self.add_message(conversation_id, "assistant", response_content)
            
            return response_content
        except Exception as e:
            print(f"Error generating LLM response: {e}")
            return "I'm having trouble responding right now."
    
    def clear_conversation(self, conversation_id):
        """Clear the conversation history for the given ID."""
        if conversation_id in self.conversations:
            system_prompt = self.conversations[conversation_id]["system_prompt"]
            self.conversations[conversation_id] = {
                "messages": [],
                "system_prompt": system_prompt
            }
