# Describe What I See (NPC Visual Description)

## Overview

During NPC conversations (both JRPG forced conversations and free-form `/talk`), players can ask the NPC to describe what they see. This triggers the NPC LLM to generate a vivid, second-person visual aside about the NPC's appearance, facial expressions, body language, clothing, injuries, and environmental context from the player character's perspective.

## Usage

### Supported Phrases

The system detects these natural language patterns (case-insensitive):

| Pattern | Example |
|---|---|
| `describe what I see` | "describe what I see" |
| `what do I see?` | "what do I see?" |
| `tell me what you see` | "tell me what you see about @Cecilia" |
| `describe what you see` | "describe what you see" |
| `what do you see here?` | "what do you see here?" |
| `give me a description` | "give me a description of @Jim" |
| `take a good look` | "take a good look at the room" |
| `look closely` | "look closely at @Darlene" |

### With Target Specification

```
@dm describe what I see about @Cecilia
describe what I see regarding the vampire
what do you see here about @Jim Halpert?
```

### With Focus

```
@dm describe what I see focusing on her expression
describe what I see regarding his injuries
what do I see about @Cecilia's clothing?
```

## How It Works

### 1. Detection

The `is_player_describe_see_request()` function in [`conversation_service.py`](n20-webapp/webapp/conversation_service.py) checks if the player's message matches any of the detection patterns.

### 2. Target Resolution

The system resolves the target NPC using:
- Explicitly mentioned entities (`@NPC`)
- Mentioned targets from the conversation
- First entity in the conversation context

### 3. Perception Check

An observation (perception) check is rolled to determine detail level:

| Roll Total | Detail Tier | Description |
|---|---|---|
| 18+ | `detailed` | Micro-expressions, fine details, subtle mannerisms |
| 14-17 | `moderate` | Subtle cues, noticeable emotional shifts |
| 10-13 | `basic` | Obvious details, general posture and expression |
| <10 | `vague` | General impressions, obscured details |

### 4. LLM Generation

The NPC LLM receives:
- Target appearance from YAML (`outward_appearance`)
- Current statuses and visible effects
- Recent conversation context (last 6 messages)
- Detail tier from perception check
- Observer and target labels

The LLM generates a second-person present-tense description focusing on:
- **Facial expressions** (emotion, attitude, tension)
- **Body language** (posture, gestures, fidgeting, stillness)
- **Clothing and appearance** (state of dress, dirt, tears, jewelry)
- **Visible injuries/status effects** (bruises, bandages, magical glows)
- **Environmental context** (lighting, proximity, background figures)

### 5. Response

The description is emitted as a perception check payload with:
- `is_describe_see: true` flag
- `detail_tier` indicating observation quality
- `description` containing the generated text

## Implementation Details

### Files Modified

| File | Changes |
|---|---|
| [`n20-webapp/webapp/conversation_service.py`](n20-webapp/webapp/conversation_service.py) | Added detection patterns, parsing functions, handler methods, and `/talk` endpoint wiring |

### New Functions

| Function | Purpose |
|---|---|
| `is_player_describe_see_request(message)` | Detect describe-see intent in player message |
| `parse_player_describe_see_request(message)` | Extract target and focus from message |
| `ConversationService.handle_player_describe_see_request()` | Main handler for describe-see requests |
| `ConversationService._execute_player_describe_see()` | Execute perception check and generate description |
| `ConversationService._get_npc_describe_see_description()` | Generate NPC visual description via LLM |

### New Detection Patterns

```python
PLAYER_DESCRIBE_SEE_PATTERNS = [
    re.compile(r'\b(?:describe|tell|explain)\s+(?:what\s+(?:do|did|would)\s+|)(?:i|me|you)\s+see(?:\??|\!\?!?)\b', re.IGNORECASE),
    re.compile(r'\b(?:what|give\s+me|let\s+me)\s+(?:a\s+)?(?:description|run\??\s*down|sense)\s+(?:of\s+(?:what\s+)?(?:i|me|you)\s+see(?:\??|\!\?!?)?)?\b', re.IGNORECASE),
    re.compile(r'\b(?:take\s+a\s+good\s+look|look\s+(?:carefully|closely|hard|over|at))\s+(?:at|around)?\b', re.IGNORECASE),
    re.compile(r'\b(?:anyone|anything)\s+(?:else|looking|around)?\s*(?:else)?\b', re.IGNORECASE),
]
```

## Examples

### Example 1: Basic Request

Player: "describe what I see"

System: Rolls perception check. If roll = 15 (moderate detail):

> You notice Cecilia's posture is rigid, her fingers nervously tracing the edge of her cloak. Her smile is warm but doesn't quite reach her eyes, which dart briefly toward the door before returning to yours. A faint scar runs along her jawline, partially hidden by shadow.

### Example 2: With Target

Player: "@dm describe what I see about @Jim Halpert"

System: Resolves target as Jim Halpert, rolls perception check, generates description.

### Example 3: With Focus

Player: "describe what I see focusing on his injuries"

System: Focuses the LLM prompt on visible injuries and status effects.

## Testing

Unit tests verify:
1. Pattern detection for various phrase formats
2. Target extraction from messages
3. Handler integration with `/talk` endpoint
4. Perception check roll and detail tier assignment
5. LLM response parsing

See `tests/webapp/test_describe_see.py` for test coverage.

## Related Features

- [Conversation RAG](CONVERSATION_RAG.md) - Retrieval-Augmented Generation for NPC conversations
- [Perception Checks](CONVERSATION_RAG.md#perception-checks) - Core perception check mechanics
- [NPC Conversation Mode](n20-webapp/webapp/npc_conversation_mode.py) - LLM vs manual conversation modes
