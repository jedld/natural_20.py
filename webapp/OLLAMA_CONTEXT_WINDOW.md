# Ollama Context Window Configuration

This document explains how to set and configure the context window size for the Ollama provider in the LLM handler.

## What is Context Window?

The context window (also called context length) determines how much text the model can "remember" and process at once. This includes:
- The system prompt
- Conversation history
- Current user message
- Model's response

A larger context window allows for longer conversations and more detailed prompts, but may use more memory and be slower.

## How to Set Context Window Size

### Method 1: During Initialization

You can set the context window size when initializing the Ollama provider:

```python
from llm_handler import llm_handler

config = {
    'base_url': 'http://localhost:11434',
    'model': 'llama3.2:3b',
    'context_window': 8192  # Set custom context window size
}

success = llm_handler.initialize_provider('ollama', config)
```

### Method 2: After Initialization

You can change the context window size after the provider is initialized:

```python
# Set context window to 4096 tokens
success = llm_handler.set_context_window(4096)

# Get current context window size
current_size = llm_handler.get_context_window()
print(f"Current context window: {current_size}")
```

## Available Context Window Sizes

Common context window sizes for different models:

- **2048**: Small context, good for short conversations
- **4096**: Standard context, good balance of performance and memory
- **8192**: Large context, good for longer conversations
- **16384**: Very large context, requires more memory

## Checking Current Configuration

You can get information about the current provider configuration:

```python
provider_info = llm_handler.get_provider_info()
print(f"Provider: {provider_info['provider_type']}")
print(f"Model: {provider_info['current_model']}")
print(f"Context Window: {provider_info.get('context_window', 'Not supported')}")
```

## Example Usage

```python
from llm_handler import llm_handler

# Initialize with large context window
config = {
    'base_url': 'http://localhost:11434',
    'model': 'llama3.2:3b',
    'context_window': 8192
}

llm_handler.initialize_provider('ollama', config)

# Send a message (will use the configured context window)
response = llm_handler.send_message("Hello! Tell me about the current game state.")
print(response)

# Change context window for different use cases
llm_handler.set_context_window(4096)  # Smaller for faster responses
llm_handler.set_context_window(16384)  # Larger for complex conversations
```

## Important Notes

1. **Memory Usage**: Larger context windows use more memory. Make sure your system has enough RAM.

2. **Model Limitations**: Some models have maximum context window limits. Check your model's documentation.

3. **Performance**: Larger context windows may be slower, especially on less powerful hardware.

4. **Provider Support**: Context window setting is currently only supported for the Ollama provider.

## Troubleshooting

### Context Window Not Working
- Make sure you're using the Ollama provider
- Check that the context window size is a positive integer
- Verify that your Ollama model supports the requested context window size

### Memory Issues
- Try reducing the context window size
- Close other applications to free up memory
- Consider using a smaller model

### Performance Issues
- Smaller context windows are generally faster
- Consider the trade-off between context size and speed for your use case

## Running the Example

You can run the provided example script to test context window functionality:

```bash
cd webapp
python ollama_context_example.py
```

This will demonstrate all the features described above. 