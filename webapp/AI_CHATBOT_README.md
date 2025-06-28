# AI Chatbot for D&D VTT - Enhanced RAG System

This document describes the AI chatbot interface integrated into the D&D Virtual Tabletop (VTT) system, featuring advanced RAG (Retrieval-Augmented Generation) capabilities for intelligent game management.

## Overview

The AI chatbot provides intelligent assistance for Dungeon Masters by accessing real-time game state information through a comprehensive RAG system. It can help with:

- **Map Information**: Access current map data, terrain, and entity positioning
- **Character Management**: Get detailed information about player characters and NPCs
- **Battle Management**: Monitor combat status, turn order, and available actions
- **Game Mechanics**: Provide D&D 5e rules assistance and tactical advice
- **VTT Control**: Assist with map navigation and entity positioning

## Features

### 🤖 Multi-Provider Support
- **OpenAI GPT**: GPT-4, GPT-3.5-turbo, GPT-4-turbo
- **Anthropic Claude**: Claude-3 models (Sonnet, Haiku, Opus)
- **Ollama**: Local models (Mistral, Llama, CodeLlama, etc.)
- **Mock Provider**: For testing and development

### 🔍 Advanced RAG System
The AI has access to comprehensive game context through registered functions:

#### Core Game Context Functions
- `get_map_info()`: Current map details, terrain, and layout
- `get_entities()`: All entities with positions and status
- `get_player_characters()`: Player character information and stats
- `get_npcs()`: NPC details and behavior patterns
- `get_battle_status()`: Combat information and turn order
- `get_entity_details(entity_name)`: Detailed entity information
- `get_available_actions(entity_name)`: Available actions for entities
- `get_map_terrain_info(x, y)`: Terrain and lighting at specific locations

#### Real-Time Data Access
- Current map and positioning
- Entity health, status effects, and abilities
- Battle initiative and turn order
- Available actions and spell slots
- Terrain features and lighting conditions
- Inventory and equipment

### 💬 Intelligent Conversation
- Context-aware responses based on current game state
- Memory of conversation history
- Ability to suggest actions based on available options
- Tactical advice for combat situations
- Story development assistance

## Setup Instructions

### 1. Environment Setup

#### For OpenAI
```bash
# Set your OpenAI API key
export OPENAI_API_KEY="your-api-key-here"
```

#### For Anthropic
```bash
# Set your Anthropic API key
export ANTHROPIC_API_KEY="your-api-key-here"
```

#### For Ollama (Local)
```bash
# Install Ollama (https://ollama.ai/)
curl -fsSL https://ollama.ai/install.sh | sh

# Pull a model (e.g., Mistral)
ollama pull mistral

# Start Ollama service
ollama serve
```

### 2. Web Interface Setup

1. **Access the DM Console**: Log in as a DM and click "Send Command" in the floating menu
2. **Open AI Assistant Tab**: Click on the "AI Assistant" tab in the DM Console modal
3. **Configure Provider**: Select your preferred AI provider from the dropdown
4. **Enter API Key**: Provide your API key (or leave empty for Ollama localhost)
5. **Select Model**: Choose your preferred model (for Ollama, models are auto-detected)
6. **Initialize**: Click "Initialize AI" to start the system

### 3. Provider-Specific Configuration

#### OpenAI
- **API Key**: Your OpenAI API key
- **Models**: GPT-4, GPT-3.5-turbo, GPT-4-turbo
- **Cost**: Pay-per-use based on token consumption

#### Anthropic
- **API Key**: Your Anthropic API key
- **Models**: Claude-3-Sonnet, Claude-3-Haiku, Claude-3-Opus
- **Cost**: Pay-per-use based on token consumption

#### Ollama (Local)
- **URL**: Leave empty for localhost:11434 or enter custom URL
- **Models**: Auto-detected from your local Ollama installation
- **Cost**: Free (runs locally on your machine)
- **Performance**: Depends on your hardware and model size

## Usage Guide

### Basic Interaction

1. **Ask about the current situation**:
   ```
   "What's happening on the map right now?"
   "Who are the player characters and what are their stats?"
   "Are there any NPCs nearby?"
   ```

2. **Get tactical information**:
   ```
   "What's the current battle status?"
   "What actions can [character name] take?"
   "What's the terrain like at position (5, 3)?"
   ```

3. **Request game assistance**:
   ```
   "Help me understand the rules for grappling"
   "What spells would be effective against these enemies?"
   "Suggest some tactical options for the current situation"
   ```

### Advanced RAG Queries

The AI can access detailed game information through its RAG system:

#### Entity Information
```
"Tell me about [character name]'s current status"
"What items does [character name] have?"
"What are [character name]'s ability scores?"
```

#### Map and Terrain
```
"What's the terrain like around the party?"
"Are there any difficult terrain areas on the map?"
"What's the lighting condition at position (10, 15)?"
```

#### Combat Assistance
```
"Who's turn is it in the battle?"
"What actions can the current player take?"
"What's the initiative order?"
```

#### Strategic Advice
```
"What would be a good tactical approach for this situation?"
"Which enemies should we prioritize?"
"What spells would be most effective here?"
```

### Function Calling Examples

The AI can suggest using specific functions to get information:

- **Map Analysis**: "Let me check the current map layout and terrain features"
- **Entity Status**: "I'll look up the current status of all entities on the map"
- **Battle Assessment**: "Let me get the current battle status and turn order"
- **Action Planning**: "I'll check what actions are available for the current character"

## API Endpoints

### Core AI Endpoints
- `POST /ai/initialize`: Initialize AI provider
- `POST /ai/chat`: Send message and get response
- `GET /ai/context`: Get current game context
- `POST /ai/clear-history`: Clear conversation history
- `GET /ai/history`: Get conversation history

### RAG-Specific Endpoints
- `GET /ai/entity-details?entity_name=<name>`: Get detailed entity information
- `GET /ai/terrain-info?x=<x>&y=<y>`: Get terrain information for coordinates
- `GET /ai/available-actions?entity_name=<name>`: Get available actions for entity
- `GET /ai/ollama/models`: Get available Ollama models
- `POST /ai/set-model`: Set the current AI model
- `GET /ai/provider-info`: Get current provider information

## Troubleshooting

### Common Issues

#### OpenAI/Anthropic API Errors
- **Invalid API Key**: Check your API key is correct and has sufficient credits
- **Rate Limiting**: Wait a moment and try again
- **Model Unavailable**: Try a different model or check API status

#### Ollama Connection Issues
- **Service Not Running**: Start Ollama with `ollama serve`
- **Model Not Found**: Pull the model with `ollama pull <model-name>`
- **Connection Refused**: Check if Ollama is running on the correct port (11434)

#### General Issues
- **No Response**: Check browser console for errors
- **Context Not Loading**: Ensure you're logged in as a DM
- **Function Errors**: Check server logs for detailed error messages

### Debug Information

Enable debug logging by checking the browser console and server logs:

```python
# Server-side logging
logger.setLevel(logging.DEBUG)
```

### Performance Optimization

#### For Local Ollama
- Use smaller models for faster responses
- Ensure sufficient RAM (4GB+ recommended)
- Consider using GPU acceleration if available

#### For Cloud Providers
- Use appropriate model sizes for your needs
- Monitor API usage and costs
- Consider caching frequently requested information

## Security Considerations

- **API Keys**: Never expose API keys in client-side code
- **DM Access**: AI features are restricted to DM users only
- **Data Privacy**: Local Ollama keeps all data on your machine
- **Session Management**: AI conversations are tied to user sessions

## Future Enhancements

### Planned Features
- **Voice Integration**: Speech-to-text and text-to-speech
- **Image Analysis**: Analyze map images and character tokens
- **Advanced Function Calling**: Direct VTT control through AI
- **Multi-Language Support**: Support for different languages
- **Custom Prompts**: User-defined system prompts
- **Action Execution**: AI can directly execute game actions

### Integration Possibilities
- **Discord Bot**: Extend AI to Discord servers
- **Mobile App**: AI assistant for mobile devices
- **Voice Assistants**: Integration with Alexa/Google Assistant
- **Streaming**: AI commentary for live streams

## Contributing

To contribute to the AI chatbot system:

1. **Code Structure**: Follow the existing patterns in `llm_handler.py` and `game_context.py`
2. **Testing**: Test with the mock provider before implementing real providers
3. **Documentation**: Update this README with new features
4. **Error Handling**: Implement proper error handling and logging

## Support

For issues and questions:
- Check the troubleshooting section above
- Review server logs for detailed error messages
- Test with the mock provider to isolate issues
- Ensure all dependencies are properly installed

---

**Note**: This AI system is designed to assist DMs and enhance the gaming experience. It should not replace human judgment or creativity in running D&D games. 