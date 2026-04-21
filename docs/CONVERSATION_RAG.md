# Conversation-Mode RAG Facilities

This document describes the Retrieval-Augmented Generation facilities used by NPC conversation mode in the web app.

The primary implementation lives in `webapp/entity_rag_handler.py`, and the conversation flow is wired through `webapp/app.py`.

## Scope

Conversation-mode RAG is the logic used when an NPC receives a spoken message through `/talk` and the server asks the LLM to generate an in-character reply.

It is separate from the DM-facing AI chat endpoints under `/ai/*`.

## Conversation Reply Pipeline

When a message is posted to `/talk`:

1. The speaker's message is delivered to audible recipients via `Entity.send_conversation(...)`.
2. NPC recipients with `dialog: true` become eligible for LLM response generation.
3. `conversation_response_prompt(...)` appends conversation-control instructions and addressable handles.
4. The LLM response is passed through `EntityRAGHandler.build_conversation_response_plan(...)`.
5. RAG commands and control tags are resolved into a final reply plan:
   - language
   - cleaned message
   - chosen targets
   - chosen volume
   - skip/no-response decision
6. If the plan is valid, the NPC reply is emitted back through normal conversation delivery.

Relevant code:

- `webapp/app.py`
- `webapp/entity_rag_handler.py`

## Inline Control Tags

These are not general tool calls. They are compact tags interpreted by the server after the model responds.

### `[NO_RESPONSE]`

Meaning:
- The NPC chooses to remain silent.

Effect:
- `build_conversation_response_plan(...)` returns `skip=True`.
- No speech is emitted.

### `[TO: ...]`

Meaning:
- Direct the reply to specific recipients.

Supported forms:
- `[TO: speaker]`
- `[TO: you]`
- `[TO: all]`
- `[TO: @handle]`
- `[TO: @handle1, @handle2]`

Resolution behavior:
- `speaker` and `you` resolve to the original speaker when present.
- `all` expands to all conversation targets available from `get_conversation_targets(...)`.
- `@handle` values are resolved by `resolve_mention_targets(...)` using mention handles derived from nearby entities.

### `[VOLUME: whisper|normal|shout]`

Meaning:
- Explicitly choose reply loudness.

Effect:
- The selected volume is normalized by `normalize_speech_mode(...)`.
- Reachability is checked against `conversation_reachability(...)`.
- If the chosen volume cannot reach any selected target, the response is skipped.

Default behavior when omitted:
- The server chooses the quietest volume that still reaches the chosen targets.

### `[in <language>]`

Meaning:
- Speak in a specific language.

Effect:
- Parsed by `parse_language_from_response(...)`.
- Validated against the responding entity's available languages by `validate_language_for_entity(...)`.
- Falls back to the entity's first language, or `common` if needed.

## RAG Commands Processed Inside Conversation Responses

These are the actual RAG facilities for conversation mode.

### `[APPROACH: ...]`

Purpose:
- Let the model move an entity up to one full out-of-combat move so it ends within a requested distance of an entity or object.

Supported form:
- `[APPROACH: target=@handle, distance=5]`
- `[APPROACH: target=Front Door, distance=10]`

Server behavior:
- `EntityRAGHandler.parse_action_directives(...)` resolves the target reference.
- `EntityRAGHandler.build_approach_action(...)` computes a path with `PathCompute`.
- `EntityRAGHandler.apply_response_plan_directives(...)` commits the resulting `MoveAction` through `current_game.commit_and_update(...)`.

Notes:
- Movement is capped to a single out-of-combat move for that 6-second turn.
- If the entity is already within the requested distance, no move action is emitted.

### `[INTERACT: ...]`

Purpose:
- Let the model use an interactable object directly from conversation mode.

Supported form:
- `[INTERACT: target=Front Door, action=open]`
- `[INTERACT: target=@locked-chest, action=unlock]`

Server behavior:
- `EntityRAGHandler.parse_action_directives(...)` resolves the target object.
- `EntityRAGHandler.build_interact_action(...)` validates the named interaction against `available_interactions(...)`.
- `EntityRAGHandler.apply_response_plan_directives(...)` commits the resulting `InteractAction` through `current_game.commit_and_update(...)`.

Notes:
- Only direct interactions that resolve to a concrete action object are executed.
- Multi-step object UIs that still require extra parameters are not auto-filled by the server.

### `[INVENTORY]` and `[LIST_INVENTORY]`

Purpose:
- Let the model request the responding NPC's inventory contents before answering.

Server behavior:
- `EntityRAGHandler._handle_inventory_query(...)` reads `receiver.inventory_items(...)`.
- A system message is injected into the LLM conversation in the form:
  - `[INVENTORY] item1, item2, ...`
- The handler then regenerates the reply with the enriched context.

Notes:
- This is a regeneration step, not an inline replacement.
- The returned response is re-parsed for language afterward.

### `[OBSERVE]`

Purpose:
- Let the model request nearby observed entities before answering.

Server behavior:
- `EntityRAGHandler._handle_observation_request(...)` uses `receiver.observe(...)`.
- A system message is injected into the LLM conversation in the form:
  - `[OBSERVE] <entity> is <distance>ft away`
- The handler regenerates the reply with that observation context.

Notes:
- This uses the entity's observation model, not the local-chat UI audience list.

### `[INSIGHT: ...]`

Purpose:
- Let the model privately assess whether a speaker or nearby target seems truthful before answering.

Supported form:
- `[INSIGHT: target=speaker]`
- `[INSIGHT: target=@handle]`

Server behavior:
- `EntityRAGHandler._handle_insight_request(...)` rolls `receiver.insight_check(...)`.
- The server builds a DM-only context that includes player-character combat logs, recent actions, background, memory, and current state.
- A separate DM adjudication prompt decides `truthful`, `lie`, or `uncertain`.
- That result is injected back into the NPC conversation as a system message and the response is regenerated.
- The check and adjudication are logged to the scoped player log for the acting NPC and target entity.

Notes:
- If the roll is weak or the context is inconclusive, the adjudication should fall back to `uncertain`.
- The insight result is not broadcast publicly; it is scoped through the normal entity log visibility rules.

### `[REQUEST_CHECK: ...]`

Purpose:
- Let an NPC explicitly ask a player for a persuasion or intimidation check.

Supported form:
- `[REQUEST_CHECK: skill=persuasion, target=speaker]`
- `[REQUEST_CHECK: skill=intimidation, target=@handle, dc=14]`

Server behavior:
- `EntityRAGHandler.parse_action_directives(...)` resolves the skill and target.
- `EntityRAGHandler.apply_response_plan_directives(...)` logs the requested check to the scoped player log for the acting NPC and target entity.

Notes:
- Only `persuasion` and `intimidation` are currently accepted.
- This requests a check and logs it; it does not auto-roll the player's check.

### `[GO_HOSTILE]`

Purpose:
- Let the conversation response switch the NPC into a hostile state.

Server behavior:
- Calls `receiver.update_state('active')`.
- Calls `current_game.update_group(receiver, 'b')`.
- Returns an empty response body.

### `[GO_FRIENDLY]`

Purpose:
- Let the conversation response switch the NPC into a friendly state.

Server behavior:
- Calls `receiver.update_state('active')`.
- Calls `current_game.update_group(receiver, 'a')`.
- Returns an empty response body.

### `[SET_GOAL: ...]`

Purpose:
- Let the model create or replace a short-term autonomous objective.

Server behavior:
- `EntityRAGHandler.apply_response_plan_directives(...)` stores the goal through `current_game.schedule_short_term_goal(...)`.
- `GameManagement` keeps the goal active and queues the entity for an autonomous 6-second out-of-combat turn.

Examples:
- `[SET_GOAL: Check the front door for intruders]`
- `[SET_GOAL: Move to the chest and open it]`

### `[GOAL_COMPLETE]`

Purpose:
- Mark the current short-term goal as finished.

Server behavior:
- The goal is closed via `current_game.complete_short_term_goal(..., status='completed')`.

### `[GOAL_GIVE_UP]`

Purpose:
- Mark the current short-term goal as abandoned.

Server behavior:
- The goal is closed via `current_game.complete_short_term_goal(..., status='abandoned')`.

## Autonomous 6-Second Goal Turns

Short-term goals are executed by the web game manager, not by the browser.

Behavior:
- `GameManagement` maintains active goal records per entity.
- A lightweight background worker checks for due goals while no battle is active.
- Every due goal triggers one autonomous out-of-combat turn.
- The goal turn prompt includes:
  - the current goal text
  - entity position/context
  - nearby entities
  - visible interactable objects and their available actions
  - recent goal history
- The model may respond with:
  - movement or interaction tags
  - a replacement goal
  - goal completion/abandonment tags
  - observation/inventory refresh tags

Time and environment integration:
- Each scheduled goal turn advances in-game time by 6 seconds.
- Execution reuses `current_game.commit_and_update(...)` for actions.
- World updates continue to flow through the normal out-of-combat path, including `loop_environment()` and the standard `turn` socket event carrying updated `game_time`.

## Keyword-Triggered Event RAG

Entities may also define `conversation_keywords()` entries.

Behavior:
- `_process_rag_commands(...)` checks whether any configured keyword appears in the model response.
- Matching entries are passed to `GenericEventHandler(...)`.
- The matched keyword text is then removed from the final spoken response.

Use case:
- Triggering scripted events or state changes from conversational output without exposing raw control text to players.

## Target Discovery and Mention Handles

Conversation mode exposes nearby addressable handles to the model via `conversation_response_prompt(...)`.

Source of candidates:
- `EntityRAGHandler.get_conversation_targets(...)`

How candidates are collected:
- The original speaker is included.
- Nearby entities are gathered from `conversation_reachability(...)` with `mode='shout'`.

How handles are displayed:
- `mention_handle_for(...)` converts entity labels into `@handle` values.
- The prompt includes a line like:
  - `Nearby handles you can address right now: @thorn-durst (Thorn Durst), ...`

## Reachability and Volume Planning

Conversation mode uses acoustic reachability rather than simple map distance.

Primary helper:
- `conversation_reachability(...)`

What it considers:
- base speech mode distance
- passive perception / hearing modifier
- acoustic penalties such as doors and walls
- whether a target is reachable now
- whether a louder voice would be enough

Reply planning rules:

- If the model explicitly chooses a volume, only targets reachable at that volume remain.
- If the model omits a volume, the server picks the minimum required mode across the chosen targets.
- If no targets remain reachable, the response is skipped.

## Entity Context Helpers Used by Conversation RAG

### `get_entity_context(entity)`

Returns a compact entity context dictionary with fields such as:
- `name`
- `entity_uid`
- `description`
- `hp`
- `max_hp`
- `ac`
- `level`
- `race`
- `class`
- `inventory`
- `position`

Current usage:
- General helper for RAG and entity inspection.
- Not the main driver of the NPC conversation reply loop today.

### `get_nearby_entities(entity, range_ft, volume=None, include_extended=False)`

Returns nearby entities with conversation-aware metadata.

Returned fields include:
- `id`
- `name`
- `distance`
- `adjusted_distance_ft`
- `effective_distance_ft`
- `passive_perception`
- `hearing_modifier_ft`
- `reachable_now`
- `reachable_with_shout`
- `minimum_volume`
- `status`
- `acoustic_penalty_ft`
- `acoustic_summary`
- `closed_doors`
- `walls`
- `opaque_objects`
- `mention_handle`
- `conversable`

Fallback behavior:
- If acoustic helpers fail or return an unexpected shape, the handler falls back to `entity.observe(...)` and synthesizes compatible entries.

## Conversation-Adjacent Web Endpoints

These routes are relevant to conversation UI and conversation diagnostics.

### `/conversation_presence`

Purpose:
- Return conversation reachability for the current speaker and selected volume.

Used by:
- local chat UI

Response includes:
- `speaker`
- `volume`
- `distance_ft`
- `entities`
- `reachable_entities`
- `requires_louder_voice_entities`
- `heard_only_entities`

### `/nearby_entities`

Purpose:
- Return nearby entities for a speaker and requested volume/range.

Used by:
- talk modal and related audience selection flows

Implementation:
- backed by `entity_rag_handler.get_nearby_entities(...)`

## DM AI RAG Endpoints Nearby But Separate

These endpoints exist in the same app but are not the NPC conversation-mode RAG loop.

### `/ai/chat`
- DM-only chat using `llm_handler.get_game_context()`.

### `/ai/context`
- DM-only inspection of the current AI game context.

### `/ai/entity-details`
- DM-only entity detail lookup.

### `/ai/terrain-info`
- DM-only terrain lookup for map coordinates.

### `/ai/available-actions`
- DM-only available-actions lookup for an entity.

These are general LLM support endpoints, not the inline conversation command system used by NPC replies.

## Current Limitations

- Conversation-mode RAG is tag-based and server-interpreted; it is not a general tool-calling framework.
- Inventory and observe requests trigger one regenerate cycle each; they are not chained planning loops.
- The conversation prompt exposes nearby handles and reply rules, but not arbitrary world querying.
- The broader `/ai/*` RAG endpoints are not currently invoked by the NPC conversation route.

## Source Files

- `webapp/entity_rag_handler.py`
- `webapp/app.py`
- `natural20/utils/conversation.py`
- `tests/webapp/test_entity_rag_handler.py`
- `tests/webapp/test_talk_route_recipients.py`