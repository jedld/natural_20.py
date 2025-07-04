# LLM Configuration Guide

This guide explains how to configure the Large Language Model (LLM) providers for the Natural20 web application using environment variables.

## Overview

The application supports multiple LLM providers:
- **OpenAI** (GPT models)
- **Anthropic** (Claude models) 
- **Ollama** (Local models)
- **Mock** (For testing)

## Environment Variables

### Provider Selection

Set the `LLM_PROVIDER` environment variable to choose which provider to use:

```bash
export LLM_PROVIDER=openai    # Use OpenAI
export LLM_PROVIDER=anthropic # Use Anthropic
export LLM_PROVIDER=ollama    # Use Ollama (default)
export LLM_PROVIDER=mock      # Use Mock provider for testing
```

### OpenAI Configuration

To use OpenAI models, set the following environment variables:

```bash
export LLM_PROVIDER=openai
export OPENAI_API_KEY=your_openai_api_key_here
export OPENAI_MODEL=gpt-4o-mini                    # Optional, defaults to gpt-4o-mini
export OPENAI_BASE_URL=https://api.openai.com/v1   # Optional, for custom endpoints
```

**Available Models:**
- `gpt-4o-mini` (default)
- `gpt-4o`
- `gpt-4-turbo`
- `gpt-3.5-turbo`
- Any other model available in your OpenAI account

### Anthropic Configuration

To use Anthropic Claude models, set the following environment variables:

```bash
export LLM_PROVIDER=anthropic
export ANTHROPIC_API_KEY=your_anthropic_api_key_here
export ANTHROPIC_MODEL=claude-3-5-sonnet-20241022  # Optional, defaults to claude-3-5-sonnet-20241022
```

**Available Models:**
- `claude-3-5-sonnet-20241022` (default)
- `claude-3-5-haiku-20241022`
- `claude-3-opus-20240229`
- `claude-3-sonnet-20240229`
- Any other model available in your Anthropic account

### Ollama Configuration

To use local Ollama models, set the following environment variables:

```bash
export LLM_PROVIDER=ollama
export OLLAMA_BASE_URL=http://localhost:11434      # Optional, defaults to http://localhost:11434
export OLLAMA_MODEL=gemma3:27b                     # Optional, defaults to gemma3:27b
```

**Popular Models:**
- `gemma3:27b` (default)
- `llama3.2:3b`
- `llama3.2:7b`
- `llama3.2:70b`
- `mistral:7b`
- `codellama:7b`
- `qwen2.5:7b`

## Configuration Examples

### Example 1: OpenAI with GPT-4o

```bash
export LLM_PROVIDER=openai
export OPENAI_API_KEY=sk-your-openai-api-key
export OPENAI_MODEL=gpt-4o
```

### Example 2: Anthropic with Claude

```bash
export LLM_PROVIDER=anthropic
export ANTHROPIC_API_KEY=sk-ant-your-anthropic-api-key
export ANTHROPIC_MODEL=claude-3-5-sonnet-20241022
```

### Example 3: Ollama with Local Model

```bash
export LLM_PROVIDER=ollama
export OLLAMA_BASE_URL=http://localhost:11434
export OLLAMA_MODEL=llama3.2:7b
```

### Example 4: Custom OpenAI Endpoint

```bash
export LLM_PROVIDER=openai
export OPENAI_API_KEY=your-api-key
export OPENAI_BASE_URL=https://your-custom-endpoint.com/v1
export OPENAI_MODEL=gpt-4o-mini
```

## Docker Configuration

When running in Docker, you can pass environment variables using the `-e` flag:

```bash
docker run -e LLM_PROVIDER=openai \
           -e OPENAI_API_KEY=your-api-key \
           -e OPENAI_MODEL=gpt-4o-mini \
           your-app-image
```

Or using a `.env` file:

```bash
# .env file
LLM_PROVIDER=openai
OPENAI_API_KEY=your-api-key
OPENAI_MODEL=gpt-4o-mini
```

Then run with:
```bash
docker run --env-file .env your-app-image
```

## Environment File (.env)

Create a `.env` file in your project root for local development:

```bash
# .env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma3:27b

# Or for OpenAI:
# LLM_PROVIDER=openai
# OPENAI_API_KEY=your-api-key
# OPENAI_MODEL=gpt-4o-mini
```

## Troubleshooting

### Common Issues

1. **"LLM features will be disabled" warning**
   - Check that your API key is set correctly
   - Verify the provider name is correct (case-insensitive)

2. **Ollama connection errors**
   - Ensure Ollama is running locally
   - Check that the base URL is correct
   - Verify the model is installed: `ollama list`

3. **OpenAI/Anthropic API errors**
   - Verify your API key is valid
   - Check your account has sufficient credits
   - Ensure the model name is correct

### Testing Configuration

You can test your configuration using the provided test script:

```bash
cd webapp
python test_llm_config.py
```

This script will:
- Check your environment variables
- Test connections to Ollama (if using Ollama)
- Verify model availability
- Test LLM handler initialization

You can also test your configuration by checking the application logs. Successful initialization will show:

```
INFO: Initialized OpenAI provider with model: gpt-4o-mini
INFO: Initialized Anthropic provider with model: claude-3-5-sonnet-20241022
INFO: Initialized Ollama provider with model: gemma3:27b at http://localhost:11434
```

### Fallback Behavior

- If no provider is configured, the application defaults to Ollama
- If API keys are missing, the application will log warnings but continue running
- If initialization fails, the application will continue without LLM features

## Security Notes

- Never commit API keys to version control
- Use environment variables or secure secret management
- Consider using a `.env` file for local development (add to `.gitignore`)
- For production, use your platform's secret management system (AWS Secrets Manager, Azure Key Vault, etc.) 