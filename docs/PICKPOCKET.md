# Pickpocket System

## Overview

The pickpocket system implements D&D 5e (2014) Sleight of Hand theft from creatures. When a PC or NPC attempts to pickpocket another creature, the system performs a contested check between the attacker's **Sleight of Hand** check and the target's **passive Insight**. Nearby NPC witnesses compare their passive **Perception** to the same Sleight of Hand total.

## Rules Summary (PHB 2014)

- **Skill Check**: Sleight of Hand (DEX-based skill check)
- **Contested By**: Target's passive Insight
- **Range**: Target must be within 5 feet (adjacent on the map grid)
- **On Success**: One small item is stolen from the target's inventory
- **On Failure**: The target becomes aware of the attempt
- **Action Type**: Uses an Action (or Bonus Action for Thief Rogue's Fast Hands)

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│  PickpocketAction (natural20/actions/pickpocket_action.py)             │
│       │                                                                 │
│       ▼                                                                 │
│  build_map() → UI: select_target (5 ft) → stealable item modal         │
│       │                                                                 │
│       ▼                                                                 │
│  resolve() → Sleight of Hand vs passive Insight                        │
│       │                                                                 │
│       ▼                                                                 │
│  apply() → steal item (success) or log detection (failure)             │
│       │                                                                 │
│       ▼                                                                 │
│  pickpocket_detection.py → Witness PP vs Sleight of Hand total           │
│       │                                                                 │
│       ▼                                                                 │
│  pickpocket_notification.py → LLM notification templates                │
│       │                                                                 │
│       ▼                                                                 │
│  webapp/pickpocket_reaction.py → Wires detection + notifications       │
│       to ConversationService                                            │
└─────────────────────────────────────────────────────────────────────────┘
```

## Key Components

### 1. [`natural20/actions/pickpocket_action.py`](../natural20/actions/pickpocket_action.py)

Main action class:

- **`PickpocketAction`** - Standard pickpocket action (uses Action)
- **`PickpocketBonusAction`** - Bonus action variant (Thief Rogue Fast Hands)

Key methods:
- **`can(entity, battle, options)`** - Checks action availability and campaign settings
- **`build_map()`** - Returns UI targeting config (creature selection → stealable item modal)
- **`resolve(session, map, opts)`** - Performs Sleight of Hand vs passive Insight
- **`apply(battle, item, session)`** - Executes theft or logs failure

### 2. [`natural20/entity.py`](../natural20/entity.py)

Entity skill methods (added after line 3247):

- **`sleight_of_hand_proficient()`** - Returns True if proficient in Sleight of Hand
- **`sleight_of_hand_check(battle, description)`** - Performs DEX-based Sleight of Hand check

### 3. [`natural20/utils/pickpocket_detection.py`](../natural20/utils/pickpocket_detection.py)

Core NPC witness detection (modeled after [`steal_detection.py`](../natural20/utils/steal_detection.py)):

- **`_resolve_sleight_of_hand_dc(sleight_of_hand_total)`** - Witness notice DC from the pickpocket roll
- **`sleight_of_hand_total_from_roll(roll)`** - Extract total from a DieRoll result
- **`_check_npc_detection(..., sleight_of_hand_total)`** - Evaluates whether a single NPC notices based on:
  - Vision: `battle_map.can_see()` + passive Perception vs Sleight of Hand total
  - Hearing: conversation reachability within 30 ft, same DC
  - Adjacency bonus: +2 to passive Perception if NPC is near both parties
- **`evaluate_pickpocket_detection(..., sleight_of_hand_total)`** - Main entry point; returns list of NPCs that noticed
- **`collect_witness_npcs(pickpocketer, target, session, battle, battle_map)`** - Collects ALL potential witness NPCs (ignores the roll)

### 4. [`natural20/utils/pickpocket_notification.py`](../natural20/utils/pickpocket_notification.py)

LLM notification templates (modeled after [`steal_notification.py`](../natural20/utils/steal_notification.py)):

- **`pickpocket_attempt_note(npc, pickpocketer, target, item_name, success, detection_type, can_see)`** - Generic note for witnessed attempts
- **`pickpocket_success_note(npc, pickpocketer, target, item_name, can_see)`** - Note for successful theft (target unaware)
- **`pickpocket_failed_note(npc, pickpocketer, target, item_name, can_see)`** - Note for detected failure (target aware)
- **`multiple_pickpocket_attempts_note(npc, pickpocketer, target, item_name, success, previous_attempts, can_see)`** - Note for repeated offenses

### 5. [`webapp/pickpocket_reaction.py`](../webapp/pickpocket_reaction.py)

Wires core modules into the conversation service:

- **`pickpocket_attempt_note()`** - Compatibility shim that delegates to `natural20.utils.pickpocket_notification`
- **`evaluate_pickpocket_detection()`** - Delegates to `natural20.utils.pickpocket_detection`
- **`collect_witness_npcs()`** - Delegates to `natural20.utils.pickpocket_detection`
- **`process_pickpocket_reactions(game, action, in_combat)`** - Main entry point called from `webapp/utils.py::commit_and_update()`

### 6. [`webapp/utils.py`](../webapp/utils.py)

Integration point: `process_pickpocket_reactions()` is called from `commit_and_update()` after action resolution (line ~2069).

### 7. [`webapp/blueprints/helpers/campaign_config.py`](../webapp/blueprints/helpers/campaign_config.py)

Configuration helpers:

- **`pickpocket_enabled(pc_to_pc=True, index_data=None)`** - Check if pickpocket is allowed
- **`pickpocket_enabled_direct(pc_to_pc=True, index_data=None)`** - Direct lookup for core engine

## Campaign Configuration

### index.json Settings

Add to campaign `index.json`:

```json
{
  "pickpocket": {
    "enabled": true,
    "allow_pc_to_pc": false
  }
}
```

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `pickpocket.enabled` | boolean | `true` | Global toggle for pickpocket attempts |
| `pickpocket.allow_pc_to_pc` | boolean | `true` | When `false`, PC-to-PC pickpocket is disabled |

### Backwards Compatibility

For campaigns that haven't migrated to the nested structure:

```json
{
  "pickpocket_allow_pc_to_pc": false
}
```

## Detection Logic

### Sleight of Hand Check

The pickpocket attempt uses `sleight_of_hand_check()` which:

1. Rolls `1d20 + DEX mod + proficiency bonus (if proficient)`
2. Applies disadvantage if:
   - Wearing heavy armor (no medium/light armor penalty)
   - Poisoned condition

### Passive Insight Comparison

- Target's passive Insight is used (already implemented in `entity.passive_insight()`)
- Incapacitated targets have passive Insight of 10

### Contested Result

- **Success**: `sleight_of_hand_roll.result() >= passive_insight`
- **Failure**: `sleight_of_hand_roll.result() < passive_insight`

### NPC Witness Detection

When NPCs witness a pickpocket attempt, detection works as follows (see [`pickpocket_detection.py`](../natural20/utils/pickpocket_detection.py)):

1. **Vision**: If the NPC can see the pickpocketer (`battle_map.can_see()`):
   - Compare passive Perception to the **Sleight of Hand check total** from the pickpocket roll
   - Adjacent to both parties: +2 bonus to passive Perception
   - Notice if `passive Perception (+ bonuses) >= Sleight of Hand total`

2. **Hearing**: If the NPC cannot see but is within 30 ft:
   - Same Sleight of Hand total as the notice DC
   - Adjacent to both parties: +2 bonus to passive Perception

3. **Unaware**: If the NPC cannot see or hear, or their passive Perception is below the Sleight of Hand total:
   - No witness reaction is scheduled

**Note:** Stealth is separate in 5e — it governs whether you are hidden at all (`can_see`), not the DC to notice pocket-picking. Container theft (`steal_detection.py`) still uses Stealth DC because that models sneaking up to a chest, not manual trickery at a creature's belt.

### Target vs witness (5e)

| Role | This engine | Common 5e table practice |
|------|-------------|--------------------------|
| **Target** | Sleight of Hand vs passive **Insight** | Often Sleight of Hand vs passive **Perception** |
| **Witnesses** | Sleight of Hand total vs passive **Perception** | Same |

## Action Flow

### UI Targeting

1. Player selects a creature target within 5 feet
2. Server rolls **Sleight of Hand vs passive Insight** immediately (the thief does not yet know what the target is carrying)
3. On success, a modal lists stealable small items from the target's inventory (weight ≤ 1 lb by default)
4. Player picks one item; the action resolves and transfers the item on commit
5. On failure, the attempt ends immediately with combat-log feedback (no item picker)

### Resolution

1. **Attempt step** (`pickpocket_attempt`): PC-to-PC check, range check (Chebyshev distance ≤ 1), then Sleight of Hand vs passive Insight
2. **Item step** (success only): Player chooses `item_name` from stealable inventory
3. **Validate**: `resolve()` requires a stored successful `pickpocket_attempt` and `item_name`
4. **Apply**: Steal item (success) or log detection (failure); entries appear in the combat log via `EventManager` (`pickpocket` / `pickpocket_failed` events)

### NPC Reaction Flow

1. After `PickpocketAction.resolve()` completes, `webapp/utils.py::commit_and_update()` calls `process_pickpocket_reactions()`
2. `process_pickpocket_reactions()` extracts target, item_name, and success/failure from action result
3. Calls `evaluate_pickpocket_detection()` with the Sleight of Hand total to find witness NPCs
4. For each witness, generates appropriate note via `pickpocket_attempt_note()`
5. Injects notes into NPC's LLM context via `ConversationService.inject_npc_llm_system_note()`

### Action Economy

- Standard pickpocket consumes an **Action**
- Thief Rogue's Fast Hands consumes a **Bonus Action**

## NPC Pickpocket

NPCs can pickpocket PCs and other NPCs. The `PickpocketAction` is registered in `Npc.ACTION_LIST` and appears in `available_actions()`.

## Testing

Tests are in:

- [`tests/test_pickpocket_action.py`](../tests/test_pickpocket_action.py): Core action tests
- [`tests/test_pickpocket_detection.py`](../tests/test_pickpocket_detection.py): Detection module tests
- [`tests/test_pickpocket_notification.py`](../tests/test_pickpocket_notification.py): Notification template tests

## Related Documentation

- [Steal Detection](STEAL_DETECTION.md) - Container/item theft detection
