# Entity RAG Handler

The `EntityRAGHandler` is a dedicated module that handles Retrieval-Augmented Generation (RAG) aspects of entity conversations in the D&D Virtual Tabletop. This module was extracted from the main application to improve maintainability and separation of concerns.

## Overview

The EntityRAGHandler processes special commands in entity responses that require real-time game state information, such as:
- Inventory queries (`[INVENTORY]`, `[LIST_INVENTORY]`)
- Observation requests (`[OBSERVE]`)
- Hostile state changes (`[GO_HOSTILE]`)
- Language parsing and validation

## Features

### 1. Response Processing
- **Language Parsing**: Extracts language specifications from AI responses (e.g., `[in elvish]`)
- **RAG Command Processing**: Handles special commands that require game state information
- **Response Cleaning**: Removes bracketed content and processes commands appropriately

### 2. Entity Context Retrieval
- **Comprehensive Entity Information**: Retrieves stats, inventory, position, and other entity data
- **Nearby Entity Detection**: Finds entities within a specified range
- **Language Validation**: Ensures entities can speak the specified language

### 3. Game State Integration
- **Inventory Queries**: Provides real-time inventory information to entities
- **Observation Requests**: Allows entities to "see" nearby entities and their distances
- **State Changes**: Handles entity state transitions (e.g., becoming hostile)

## Usage

### Basic Initialization

```python
from webapp.entity_rag_handler import EntityRAGHandler

# Initialize with game session and current game
entity_rag_handler = EntityRAGHandler(game_session, current_game)
```

### Processing Entity Responses

```python
# Process a response from an LLM for an entity
language, cleaned_response = entity_rag_handler.process_entity_response(
    raw_response, receiver_entity, llm_conversation_handler
)
```

### Getting Entity Context

```python
# Get comprehensive information about an entity
entity_info = entity_rag_handler.get_entity_context(entity)
```

### Finding Nearby Entities

```python
# Get entities within 30 feet
nearby_entities = entity_rag_handler.get_nearby_entities(entity, range_ft=30)
```

### Language Validation

```python
# Validate that an entity can speak a language
valid_language = entity_rag_handler.validate_language_for_entity("elvish", entity)
```

## API Reference

### `EntityRAGHandler(game_session, current_game)`

**Parameters:**
- `game_session`: The current game session instance
- `current_game`: The current game management instance

### `process_entity_response(response, receiver, llm_conversation_handler)`

Processes an entity response for RAG commands and returns the cleaned response and language.

**Parameters:**
- `response`: The raw response from the LLM
- `receiver`: The entity receiving the response
- `llm_conversation_handler`: The LLM conversation handler instance

**Returns:**
- Tuple of `(language, cleaned_response)`

### `parse_language_from_response(response)`

Parses language specification from AI response.

**Parameters:**
- `response`: The raw response from the AI

**Returns:**
- Tuple of `(language, response_text)`

### `get_entity_context(entity)`

Gets comprehensive context information for an entity.

**Parameters:**
- `entity`: The entity to get context for

**Returns:**
- Dictionary containing entity context information

### `get_nearby_entities(entity, range_ft=30)`

Gets nearby entities for an entity.

**Parameters:**
- `entity`: The entity to get nearby entities for
- `range_ft`: The range in feet to search (default: 30)

**Returns:**
- List of nearby entity information dictionaries

### `validate_language_for_entity(language, entity)`

Validates that an entity can speak the specified language.

**Parameters:**
- `language`: The language to validate
- `entity`: The entity to check

**Returns:**
- The validated language (falls back to first available if invalid)

## RAG Commands

The EntityRAGHandler recognizes and processes the following special commands:

### `[INVENTORY]` or `[LIST_INVENTORY]`
Triggers an inventory query for the entity. The handler will:
1. Retrieve the entity's inventory items
2. Add a system message with inventory information
3. Regenerate the response with the inventory context

### `[OBSERVE]`
Triggers an observation request for the entity. The handler will:
1. Get nearby entities and their distances
2. Add a system message with observation information
3. Regenerate the response with the observation context

### `[GO_HOSTILE]`
Triggers a hostile state change for the entity. The handler will:
1. Update the entity's state to 'active'
2. Move the entity to the hostile group ('b')
3. Log the state change

### `[in language]`
Specifies the language for the response. The handler will:
1. Extract the language specification
2. Validate it against the entity's known languages
3. Return the language and cleaned response text

## Integration with Main Application

The EntityRAGHandler is integrated into the main application in the following ways:

### 1. Talk Route (`/talk`)
The main conversation endpoint now uses the EntityRAGHandler to process entity responses:

```python
# Use EntityRAGHandler to process the response
language, response = entity_rag_handler.process_entity_response(
    response, receiver, llm_conversation_handler
)
```

### 2. Nearby Entities Route (`/nearby_entities`)
The nearby entities endpoint uses the EntityRAGHandler:

```python
# Use EntityRAGHandler to get nearby entities
response = entity_rag_handler.get_nearby_entities(entity, range_ft)
```

### 3. Entity Info Route (`/entity_info`)
The entity information endpoint uses the EntityRAGHandler:

```python
# Use EntityRAGHandler to get comprehensive entity context
entity_info = entity_rag_handler.get_entity_context(entity)
```

## Benefits of Extraction

### 1. **Maintainability**
- RAG logic is now centralized in a single, focused module
- Easier to modify and extend RAG functionality
- Clear separation of concerns

### 2. **Testability**
- RAG functionality can be tested independently
- Mock objects can be easily created for testing
- Unit tests are more focused and reliable

### 3. **Reusability**
- RAG functionality can be reused across different parts of the application
- Consistent handling of RAG commands throughout the system
- Easy to add new RAG commands

### 4. **Code Organization**
- Main application file is cleaner and more focused
- RAG-related code is logically grouped together
- Easier to understand and navigate

## Testing

The EntityRAGHandler includes comprehensive unit tests in `test_entity_rag_handler.py`. Run the tests with:

```bash
python -m unittest webapp.test_entity_rag_handler
```

## Future Enhancements

Potential improvements to the EntityRAGHandler:

1. **Additional RAG Commands**: Support for more game state queries
2. **Caching**: Cache frequently requested information for performance
3. **Async Support**: Handle RAG operations asynchronously
4. **Plugin System**: Allow custom RAG commands to be registered
5. **Error Recovery**: Better error handling and recovery mechanisms

## Migration Notes

When migrating from the old inline RAG processing:

1. **Import the EntityRAGHandler**: Add the import statement
2. **Initialize the handler**: Create an instance with game session and current game
3. **Replace inline processing**: Use `process_entity_response()` instead of inline code
4. **Update route handlers**: Use handler methods for entity context and nearby entities
5. **Remove old functions**: Delete the old `parse_language_from_response()` function

The migration maintains backward compatibility while providing a cleaner, more maintainable architecture. 