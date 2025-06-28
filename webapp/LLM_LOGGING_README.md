# LLM Logging System

This document describes the session-based logging system for LLM interactions in the D&D VTT chatbot.

## Overview

The logging system creates separate log files for each LLM session, making it easy to debug and analyze LLM interactions. Each log file contains detailed information about:

- Raw requests sent to the LLM
- Raw responses received from the LLM
- Function calls executed
- Errors and exceptions
- Session metadata

## Features

### Session-Based Logging
- Each LLM session gets a unique log file
- Log files are named with session ID and timestamp
- Logs are stored in the `llm_logs/` directory

### Comprehensive Logging
- **RAW REQUEST TO LLM**: Complete JSON messages sent to the LLM
- **RAW RESPONSE FROM LLM**: Complete responses received from the LLM
- **FUNCTION_CALL**: Details of function calls executed
- **ERROR**: Error messages with context
- **PROVIDER_INITIALIZED**: Provider initialization events
- **THINKING_DETECTED**: When thinking patterns are detected
- **CONVERSATION_TRIM**: When conversation history is trimmed

### Metadata Tracking
Each log entry includes:
- Timestamp with millisecond precision
- Provider type and model information
- Message counts and response lengths
- Function names and arguments
- Error types and contexts

## Usage

### Basic Usage

```python
from llm_handler import LLMHandler

# Initialize handler (creates new session automatically)
handler = LLMHandler()

# Get session information
session_info = handler.get_session_info()
print(f"Session ID: {session_info['session_id']}")
print(f"Log File: {session_info['log_file']}")

# Initialize a provider
handler.initialize_provider('mock', {})

# Send messages (automatically logged)
response = handler.send_message("Who are the characters?")
```

### Session Management

```python
# Clear current session and start new one
handler.clear_session()

# Get session duration
session_info = handler.get_session_info()
print(f"Session duration: {session_info['duration']}")
```

## Log File Format

Each log file follows this structure:

```
=== LLM SESSION LOG ===
Session ID: a1b2c3d4
Start Time: 2024-01-31 10:30:15.123
Log File: /path/to/llm_logs/session_a1b2c3d4_20240131_103015.log
==================================================

--- PROVIDER_INITIALIZED ---
Timestamp: 2024-01-31 10:30:15.456
Metadata:
  provider: MockProvider
  current_model: mock-model
  initialized: True
Content:
--------------------------------------------------
Provider mock initialized successfully
==================================================

--- RAW REQUEST TO LLM ---
Timestamp: 2024-01-31 10:30:16.789
Metadata:
  provider: MockProvider
  model: mock-model
  message_count: 3
Content:
--------------------------------------------------
[
  {
    "role": "system",
    "content": "You are an AI assistant for a D&D Virtual Tabletop (VTT)..."
  },
  {
    "role": "user",
    "content": "Who are the characters?"
  }
]
==================================================

--- RAW RESPONSE FROM LLM ---
Timestamp: 2024-01-31 10:30:17.012
Metadata:
  provider: MockProvider
  model: mock-model
  response_length: 245
Content:
--------------------------------------------------
[FUNCTION_CALL: get_player_characters()]
[FUNCTION_CALL: get_npcs()]
==================================================

--- FUNCTION_CALL ---
Timestamp: 2024-01-31 10:30:17.345
Metadata:
  function_name: get_player_characters
  arguments: []
  result_type: list
Content:
--------------------------------------------------
Function: get_player_characters
Arguments: []
Result: [Mock data - would show actual PCs]
==================================================
```

## Configuration

### Log Directory
By default, logs are stored in the `llm_logs/` directory. You can change this when creating a SessionLogger:

```python
# Custom log directory
session_logger = SessionLogger(log_dir="custom_logs")
```

### Log File Naming
Log files are named using the pattern:
```
session_{session_id}_{timestamp}.log
```

Where:
- `session_id`: 8-character unique identifier
- `timestamp`: YYYYMMDD_HHMMSS format

## Testing

Run the test script to see the logging system in action:

```bash
cd webapp
python test_llm_logging.py
```

This will:
1. Create a new session
2. Initialize a mock provider
3. Send test messages
4. Display session information
5. Show a preview of the log file contents

## Debugging

### Common Issues

1. **Empty Log Files**: Check if the `llm_logs/` directory exists and is writable
2. **Missing Logs**: Ensure the LLM handler is properly initialized
3. **Large Log Files**: Consider implementing log rotation for long sessions

### Log Analysis

Use the logs to:
- Debug LLM response issues
- Analyze function call patterns
- Track conversation flow
- Identify error patterns
- Monitor provider performance

## Integration

The logging system is automatically integrated into the LLM handler. No additional configuration is required - all LLM interactions are logged by default.

To disable logging (not recommended), you would need to modify the LLMHandler class to skip logging calls. 