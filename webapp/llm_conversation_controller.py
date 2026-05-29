import json
import logging
import re
import time

from webapp.llm_handler import LLMHandler

logger = logging.getLogger('werkzeug')


class LLMConversationController:
    def __init__(self, llm_handler: LLMHandler):
        self.conversations = {}
        self.llm_hander = llm_handler
        self.api_key = None
        self.model = "gpt-4o"
        self.max_history = 100  # Maximum number of messages to keep in history

    def get_conversation(self, conversation_id):
        return self.conversations.get(conversation_id, None)

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
            messages = self.conversations[conversation_id]["messages"]
            self.conversations[conversation_id]["messages"] = messages[-self.max_history:]

    def _entity_uid(self, value):
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return getattr(value, 'entity_uid', None)

    def _entity_label(self, value):
        if value is None:
            return ''
        label = getattr(value, 'label', None)
        try:
            if callable(label):
                return str(label() or '')
        except Exception:
            pass
        return str(getattr(value, 'name', '') or getattr(value, 'entity_uid', '') or '')

    def _directed_uids(self, message):
        directed_to = message.get('directed_to') or []
        return [entity_uid for entity_uid in (self._entity_uid(item) for item in directed_to) if entity_uid]

    def _conversation_summary_for_router(self, candidate, limit=5):
        summary = []
        for message in (getattr(candidate, 'conversation_buffer', []) or [])[-limit:]:
            source_uid = self._entity_uid(message.get('source'))
            source_label = self._entity_label(message.get('source'))
            directed_labels = [self._entity_label(item) for item in (message.get('directed_to') or []) if item is not None]
            target_uid = self._entity_uid(message.get('target'))
            if source_uid == getattr(candidate, 'entity_uid', None):
                summary.append(f"{source_label} said: {message.get('message', '')}")
            elif target_uid == getattr(candidate, 'entity_uid', None) and not directed_labels:
                summary.append(f"{source_label} said to {self._entity_label(candidate)}: {message.get('message', '')}")
            elif directed_labels:
                summary.append(f"{source_label} spoke to {', '.join(directed_labels)}: {message.get('message', '')}")
            else:
                summary.append(f"{source_label} said: {message.get('message', '')}")
        return summary

    def _parse_router_response(self, response_text):
        if not response_text:
            return None

        text = str(response_text).strip()
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            text = match.group(0)

        try:
            payload = json.loads(text)
        except Exception:
            return None

        responders = payload.get('responders') or []
        if isinstance(responders, str):
            responders = [responders]
        if not isinstance(responders, list):
            return None
        return [str(item) for item in responders if item]

    def route_conversation_responders(self, speaker, candidates, latest_message, targeted_entities=None, language='common', volume='normal'):
        candidates = [candidate for candidate in (candidates or []) if candidate is not None]
        if len(candidates) <= 1:
            return candidates

        if self.llm_hander is None or not hasattr(self.llm_hander, 'send_message'):
            return None

        payload = {
            'speaker': {
                'entity_uid': getattr(speaker, 'entity_uid', None),
                'name': self._entity_label(speaker),
            },
            'latest_message': latest_message,
            'language': language,
            'volume': volume,
            'targeted_entities': [
                {
                    'entity_uid': getattr(entity, 'entity_uid', None),
                    'name': self._entity_label(entity),
                }
                for entity in (targeted_entities or [])
            ],
            'candidates': [
                {
                    'entity_uid': getattr(candidate, 'entity_uid', None),
                    'name': self._entity_label(candidate),
                    'recent_conversation': self._conversation_summary_for_router(candidate),
                }
                for candidate in candidates
            ],
        }

        messages = [
            {
                'role': 'system',
                'content': (
                    'You are a D&D conversation router deciding which NPC, if any, should reply next. '
                    'Choose at most one responder. Prefer explicitly addressed NPCs. '
                    'If the latest line is ambiguous, pick the candidate whose recent conversation context best fits. '
                    'If nobody should reply, return an empty responders list. '
                    'Avoid picking someone who would only repeat stale information. '
                    'Return JSON only in the form {"responders": ["entity_uid"], "reason": "short reason"}.'
                ),
            },
            {
                'role': 'user',
                'content': json.dumps(payload, ensure_ascii=False),
            },
        ]

        try:
            raw_response = self.llm_hander.send_message(
                messages, context={'response_mode': 'conversation'},
            )
        except Exception:
            return None

        responder_ids = self._parse_router_response(raw_response)
        if responder_ids is None:
            return None

        responder_set = set(responder_ids)
        chosen = [candidate for candidate in candidates if getattr(candidate, 'entity_uid', None) in responder_set]
        return chosen[:1]

    def update_conversation_history(self, conversation_id, new_messages):
        """Update the conversation history with new messages."""
        if conversation_id not in self.conversations:
            self.create_conversation(conversation_id)
        self.conversations[conversation_id]["messages"] = []

        for message in new_messages:
            source_uid = self._entity_uid(message.get('source'))
            target_uid = self._entity_uid(message.get('target'))
            directed_uids = self._directed_uids(message)

            if source_uid == conversation_id:
                role = "assistant"
                message_content = f"{message['message']}"

            elif conversation_id in directed_uids or (target_uid == conversation_id and not directed_uids):
                role = "user"
                # If the message is directed to this conversation controller, format it accordingly
                message_content = f"{self._entity_label(message.get('source'))} says to you (in {message['language']}): {message['message']}"
            else:
                role = message.get("role", "system")
                directed_entities = ", ".join([self._entity_label(e) for e in (message.get("directed_to") or [])])
                if message.get("directed_to"):
                    message_content = f"you overhear {self._entity_label(message.get('source'))} talk to {directed_entities} (in {message['language']}): {message['message']}"
                else:
                    message_content = f"{self._entity_label(message.get('source'))} says (in {message['language']}) to no one in particular: {message['message']}"
            self.add_message(conversation_id, role, message_content)


    def generate_response(self, conversation_id, entity_context=None):
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
            started = time.monotonic()
            history_count = len(conversation.get('messages', []))
            logger.info(
                "[LLMConversation] generating NPC reply conversation_id=%s history_messages=%s",
                conversation_id,
                history_count,
            )
            response_content = self.llm_hander.send_message(
                messages,
                context={
                    'response_mode': 'conversation',
                    'log_label': f'npc_reply:{conversation_id}',
                },
            )
            elapsed_ms = (time.monotonic() - started) * 1000.0
            logger.info(
                "[LLMConversation] NPC reply complete conversation_id=%s elapsed_ms=%.1f preview=%r",
                conversation_id,
                elapsed_ms,
                (response_content or '')[:160],
            )

            # Add the response to the conversation history
            self.add_message(conversation_id, "assistant", response_content)

            return response_content
        except Exception as e:
            logger.exception(
                "[LLMConversation] NPC reply failed conversation_id=%s: %s",
                conversation_id,
                e,
            )
            return "I'm having trouble responding right now."
    
    def clear_conversation(self, conversation_id):
        """Clear the conversation history for the given ID."""
        if conversation_id in self.conversations:
            system_prompt = self.conversations[conversation_id]["system_prompt"]
            self.conversations[conversation_id] = {
                "messages": [],
                "system_prompt": system_prompt
            }
