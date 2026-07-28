# Steal Detection System

## Overview

The steal detection system automatically evaluates whether NPCs notice when a PC steals items from containers, objects, or surfaces (e.g., bar counters, chests, shops). Detected thefts are communicated to the NPC LLM so NPCs can react in character.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  InteractAction (loot/store/transfer)                          │
│       │                                                         │
│       ▼                                                         │
│  Container.transfer() ──────────────────────────────────────┐   │
│       │                                                     │   │
│       ▼                                                     │   │
│  evaluate_steal_detection()                                 │   │
│       │                                                     │   │
│       ▼                                                     │   │
│  For each NPC on the map:                                   │   │
│    ├─ Vision check (can_see)                                │   │
│    ├─ Stealth DC vs Passive Perception                      │   │
│    └─ Hearing check (acoustic profile)                      │   │
│       │                                                     │   │
│       ▼                                                     │   │
│  process_steal_reactions()                                  │   │
│       │                                                     │   │
│       ▼                                                     │   │
│  inject_npc_llm_system_note() → NPC LLM conversation       │   │
└─────────────────────────────────────────────────────────────────┘
```

## Key Components

### 1. [`natural20/utils/steal_detection.py`](../natural20/utils/steal_detection.py)

Core detection logic:

- **`evaluate_steal_detection(session, pc, container, items_taken, battle, battle_map)`**
  - Main entry point called after item transfers.
  - Returns a list of detection results for NPCs that noticed the theft.
  - Each result includes: `noticed`, `reason`, `detection_type`, `npc_passive_perception`, `pc_stealth_dc`, `can_see_pc`, `can_hear_pc`.

- **`_check_npc_detection(npc, pc, battle_map, battle)`**
  - Evaluates a single NPC's ability to detect the PC's suspicious activity.
  - **Vision path**: If NPC can see PC, checks `passive_perception` vs `stealth_dc`.
  - **Hearing path**: If NPC can hear but not see, applies +2 hearing bonus to passive perception.

- **`collect_witness_npcs(...)`**
  - Collects all NPCs that should be notified (regardless of stealth check outcome).
  - Used for context gathering and ownership-based notifications.

### 2. [`natural20/utils/steal_notification.py`](../natural20/utils/steal_notification.py)

LLM note generation:

- **`steal_detection_note(npc, pc, container, items, detection_type, ...)`**
  - Generates a system note for NPCs that directly noticed a theft.
  - Includes observation description, ownership context, and reaction suggestions.

- **`attempted_steal_note(...)`**
  - For NPCs who heard suspicious activity but didn't see it.

- **`multiple_steals_note(...)`**
  - For repeated thefts by the same PC — heightened reactions.

### 3. [`webapp/steal_reaction.py`](../webapp/steal_reaction.py)

Webapp integration:

- **`process_steal_reactions(game, action, in_combat)`**
  - Called from `commit_and_update()` after action resolution.
  - Extracts items from `InteractAction` results.
  - Calls `evaluate_steal_detection()` and injects notes via `ConversationService`.

### 4. [`natural20/concern/container.py`](../natural20/concern/container.py)

Modified `transfer()` method:

- Tracks items taken FROM the container (the steal direction).
- After transfers complete, calls `evaluate_steal_detection()` if source is a PC.
- Stores detection results on `source._steal_detections` for potential UI consumption.

## Detection Logic

### Vision-Based Detection

1. **NPC can see PC**: 
   - If PC is hiding (has a stealth roll): detection succeeds if `npc_passive_perception >= pc_stealth_dc`.
   - If PC is not hiding (`stealth_dc == 0`): NPC always notices.

2. **NPC cannot see PC**:
   - Check hearing via acoustic profile.

### Hearing-Based Detection

1. **NPC can hear PC** (via `conversation_reachability` + acoustic profile):
   - Hearing gives +2 to passive perception (instinct bonus).
   - Detection succeeds if `npc_passive_perception + 2 >= pc_stealth_dc`.

2. **NPC cannot hear PC**:
   - No detection possible.

### Detection Types

| Type | Description |
|------|-------------|
| `seen` | NPC saw PC acting suspiciously (PC not hiding) |
| `passive_perception` | NPC noticed PC despite stealth (PP beats DC) |
| `hidden` | NPC saw PC but stealth was successful |
| `heard` | NPC heard suspicious activity |
| `heard_but_missed` | NPC heard but didn't detect the theft |
| `unaware` | NPC couldn't see or hear anything |

## NPC Reaction Context

The system note sent to the NPC LLM includes:

- **Observation**: What the NPC saw/heard
- **Item details**: Names and quantities of stolen items
- **Container info**: What was stolen from (e.g., "the bar counter")
- **Ownership context**: Resolved via `_resolve_container_ownership()` — see below
- **Reaction guidance**: Suggested in-character responses based on ownership

## Container Ownership Resolution

The system automatically determines ownership for containers/objects using these strategies (in order):

| Priority | YAML Property | Description |
|----------|---------------|-------------|
| 1 | `owner` | Entity UID of the owner (e.g., `mara_bartender`) |
| 2 | `owner_uid` | Alias for `owner` |
| 3 | `owner_name` | Human-readable fallback name |
| 4 | `staff_viewers` | List of entity UIDs treated as authorised staff |
| 5 | `location` | Map/context name used for ownership context |

### Defining Ownership in YAML

To define ownership for a container/object:

```yaml
tavern_bar_counter:
  name: Bar Counter
  owner: mara_bartender          # Primary owner (entity UID)
  location: tavern                # Context/location name
  staff_viewers: [mara_bartender, pip_barmaid]  # Staff with access
  inventory:
    - type: ale_mug
      qty: 24
    - type: bread_loaf
      qty: 8
```

The ownership info is passed to `steal_detection_note()` as `ownership_info` with keys `owner` and `location`, enabling NPCs to react appropriately based on whether they own the items or location.

### Ownership in Wild Sheep Chase Campaign

| Container | Owner | Map |
|-----------|-------|-----|
| `tavern_bar_counter` | `mara_bartender` | `town_market` |
| `tavern_till_safe` | `mara_bartender` | `town_market` |

### Disabling Steal Detection

Steal detection runs on all PC-container interactions. To disable for specific containers, set:

```yaml
- name: public_chest
  type: chest
  steal_detection: false  # Skips detection for this container
```

## Testing

### Unit Tests

Create tests in `tests/webapp/test_steal_reaction.py`:

```python
def test_steal_detection_notices_visible_pc():
    """NPC should notice PC acting suspiciously when visible."""
    ...

def test_steal_detection_hidden_low_stealth():
    """NPC with low PP should NOT notice hidden PC with low stealth DC."""
    ...

def test_steal_detection_hidden_high_pp():
    """NPC with high PP should notice hidden PC even with stealth."""
    ...
```

### Manual Testing

1. Spawn an NPC on a map with a container.
2. As a PC, use the loot/transfer UI to take items from the container.
3. Check the NPC's conversation log / journal for the detection note.
4. Talk to the NPC — they should reference the theft if they noticed.

## Integration Points

### Action Flow

1. Player clicks "transfer" on a container
2. UI sends `POST /action` with `InteractAction`
3. `battle.py:action()` resolves the action
4. `Container.transfer()` processes item movement
5. `commit_and_update()` calls `process_steal_reactions()`
6. `ConversationService.inject_npc_llm_system_note()` queues the note
7. NPC's next LLM turn includes the theft context

### Related Files

| File | Purpose |
|------|---------|
| [`natural20/utils/steal_detection.py`](../natural20/utils/steal_detection.py) | Detection logic |
| [`natural20/utils/steal_notification.py`](../natural20/utils/steal_notification.py) | Note generation |
| [`webapp/steal_reaction.py`](../webapp/steal_reaction.py) | Webapp integration |
| [`natural20/concern/container.py`](../natural20/concern/container.py) | Transfer hook |
| [`webapp/utils.py`](../webapp/utils.py) | `commit_and_update` wiring |
| [`webapp/conversation_service.py`](../webapp/conversation_service.py) | NPC LLM injection |
| [`natural20/utils/conversation.py`](../natural20/utils/conversation.py) | Acoustic profile, passive perception |
| [`natural20/utils/conversation_witness.py`](../natural20/utils/conversation_witness.py) | Witness entity resolution |

## Future Enhancements

- **Witness propagation**: NPCs who witness a theft can alert other NPCs via conversation.
- **Evidence system**: Physical evidence (footprints, dropped items) that can be investigated.
- **Reputation impact**: Stealing affects NPC attitudes/faction reputation.
- **Pursuit mechanics**: Detected thieves can be chased by NPCs.
- **Skill-based detection**: `Investigation` checks for NPCs trying to find evidence.
- **Environmental factors**: Lighting, noise, crowds affecting detection chances.
