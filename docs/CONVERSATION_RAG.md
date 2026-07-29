# Conversation-Mode RAG Facilities

This document describes the Retrieval-Augmented Generation facilities used by NPC conversation mode in the web app.

The primary implementation lives in `webapp/entity_rag_handler.py`. Bootstrap wiring is in `webapp/blueprints/helpers/conversation_wiring.py` (called from `webapp/app.py`); route handlers live in `webapp/conversation_service.py`.

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

- `webapp/conversation_service.py` — `/talk` handler and conversation delivery
- `webapp/blueprints/helpers/conversation_wiring.py` — service setup at app startup
- `webapp/entity_rag_handler.py` — RAG plan parsing

## Debugging logs

Conversation traffic uses the `n20.conversation` logger, which shares the Flask/werkzeug console handlers configured in `webapp/app.py`. Grep for these prefixes while reproducing `/talk` issues:

| Prefix | Source | What it tells you |
|--------|--------|-------------------|
| `[Talk]` | `conversation_service.py` | Inbound message, eligible responders, per-NPC timing, emit vs skip |
| `[ConversationPlan]` | `entity_rag_handler.py` | Why a reply plan was built or skipped (NO_RESPONSE, volume, empty line) |
| `[LLMConversation]` | `llm_conversation_controller.py` | NPC `generate_response` start/end and latency |
| `[LLMHandler]` | `llm_handler.py` | Provider round-trips (`label=npc_reply:…`, `narrative_split`, etc.) |

Healthy second-turn flow should look like:

1. `[Talk] inbound speaker=gomerin …`
2. `[Talk] delivered_to=['rose_durst2'] eligible_responders=[…]`
3. `[LLMConversation] generating NPC reply conversation_id=rose_durst2 …`
4. `[LLMHandler] send complete label=npc_reply:rose_durst2 …`
5. `[ConversationPlan] Rose Durst: reply plan ready …`
6. `[Talk] emitted reply from Rose Durst to_usernames=[…]`

If step 5 is missing, check for `[ConversationPlan] … skip …` immediately after the LLM preview. If step 6 is missing but step 5 shows `skip=False`, the failure is after plan build (emit/delivery).

If logs show `[LLMHandler] Cleaned response` but never `[LLMHandler] send complete` / `[Talk] raw LLM response`, the `/talk` request hung inside the LLM handler return path. NPC conversation calls run synchronously in the request greenlet (not eventlet `tpool`) and skip DM session transcript writes to avoid observed post-response stalls under gunicorn+eventlet.

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

### `[EMOTION: <token>]` / `[TTS: <delivery notes>]`

Meaning:
- Steer CosyVoice delivery for the spoken line (stripped before players see the text).

Examples:
- `[EMOTION: fearful]`
- `[EMOTION: angry]`
- `[TTS: trembling, barely holding back tears]`
- `[TTS_INSTRUCT: speak urgently under your breath]`
- `[DELIVERY: soft and hesitant]`

Effect:
- Parsed by `parse_response_controls(...)` into `tts_emotion` / `tts_instruct` on the reply plan.
- Passed into CosyVoice `inference_instruct2` (with the NPC accent) when generating audio.
- Short tokens map to emotion styles; longer free-form text becomes acting notes.
- If omitted, volume may imply a default (`whisper` → whisper, `shout` → shouting), then keyword heuristics on the spoken line.

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
- Let the model request a refreshed snapshot of visible surroundings before answering.

Server behavior:
- `EntityRAGHandler.build_observation_summary(...)` scans the observer's map within 30ft (line of sight).
- Reports **nearby people and creatures** (players, NPCs, and non-conversable entities such as animals) plus **interactable objects**.
- Each entry includes grid position, distance, `@mention` handle, **name if known**, and **outward appearance** when available.
- Open containers (chests, bar counters) also include a `stock:` summary when the observer can see them.
- A name is treated as known when the observer has prior conversation history with that entity, shares owners/group, or the target is flagged `publicly_known` / `always_known` in YAML. Unknown targets use `observe_as` / `unknown_label` when set, otherwise a generic descriptor (for example `an unfamiliar adventurer`, `an unknown wolf`).
- Appearance is resolved from YAML `outward_appearance` (or legacy `appearance`), visible `notes`, then derived attributes (race, subrace, class, size, equipped armor/weapons), then kind fallback.
- The same `outward_appearance` text is injected into NPC conversation system prompts so they know how they look, and surfaces automatically on **Look** / perception checks (zero DC) when authored in YAML.
- A system message is injected into the LLM conversation and the handler regenerates the reply with that observation context.

Notes:
- This uses map LoS and interactable-object visibility, not the local-chat acoustic audience list.

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
  Adjudication is an isolated JSON call (`skip_continuation`, `response_mode=conversation`)
  so fenced ```json blocks are not continued into narrative prose and do not pollute DM chat history.
- Player-facing reasons are parsed from the JSON only (trailing prose / fences are discarded) and
  sanitized to strip DM-only disclosures before display.
- That result is injected back into the NPC conversation as a system message and the response is regenerated.
- Player-initiated insight (`Insight check on @Name…`) emits a private Socket.IO conversation
  payload with `system: true` + `insight_check` for the badge UI in dialog / local conversation.
- The check and adjudication are logged to the scoped player log for the acting NPC and target entity.

Notes:
- If the roll is weak or the context is inconclusive, the adjudication should fall back to `uncertain`.
- The insight result is not broadcast publicly; it is scoped through the normal entity log visibility rules.
- Hard-refresh the VTT after pulling asset changes so `chat.js` / `styles.css` (or their `.min` builds) load the insight badge.

### Player Perception checks in conversation

Purpose:
- Let a player study the scene and an NPC they are talking to, with a DM-authored visual description grounded in the current exchange.

Supported forms:
- Chat: `Perception check on @Pip about her hands`
- Local chat: `@dm perception on @Pip` or `@dm perception on Pip about her apron`
- JRPG dialog: click the **search** button beside Send (uses the open NPC as target; optional focus text from the input box)

Server behavior:
- Rolls `speaker.perception_check(...)`.
- Resolves the target by `@handle`, name, or selected local-chat mention (NPCs, PCs, or visible objects).
- Requires line of sight: `Map.can_see(observer, target)` must succeed or the player gets a private not-visible message.
- `EntityRAGHandler._evaluate_perception_description(...)` calls the DM LLM with conversation snippets, NPC `outward_appearance`, map context, visible health/status cues, and the roll total.
- If the LLM is unavailable or returns a generic empty result, a deterministic fallback still describes the target's physical appearance (gated by roll total for detail).
- Emits a private `system: true` conversation payload with `perception_check.description` for the dialog / local conversation badge.
- Results are deduped per `(target_uid, focus)` and logged to the scoped player log.

Notes:
- Like Insight, perception results are private to the acting player and DM.
- Descriptions are visual-only; hidden motives or stat-block facts must not leak.
- Studying an NPC should always yield at least a basic physical description from `outward_appearance`, race/class gear, visible injuries, and conversation-appropriate expression.

### Player non-verbal actions

Purpose:
- Let players describe physical actions during conversation separately from spoken dialogue.

Supported input forms (in dialog or local chat):
- `*touches her hand*` inline or alone
- `/me leans closer` or `/emote smiles`
- `[action: bows politely]`

Server behavior:
- `parse_player_conversation_input(...)` splits speech vs `actions`.
- Actions are stored on conversation buffer entries and delivered to targeted NPCs even when no words are spoken.
- NPC LLM history uses `performs a non-verbal action` wording instead of `says`.
- JRPG dialog renders actions in a distinct purple action line; speech stays in the normal bubble.

### `[REQUEST_CHECK: ...]`

Purpose:
- Let an NPC explicitly ask a player for a persuasion or intimidation check.

Supported form:
- `[REQUEST_CHECK: skill=persuasion, target=speaker]`
- `[REQUEST_CHECK: skill=intimidation, target=@handle, dc=14]`

Server behavior:
- `EntityRAGHandler.parse_action_directives(...)` resolves the skill and target.
- `EntityRAGHandler.apply_response_plan_directives(...)` logs the requested check to the scoped player log for the acting NPC and target entity.
- JRPG dialog exposes a **Roll** button on the requesting NPC line. Clicking it POSTs to `/talk` with a `skill_check` payload; the server rolls the player's skill, shows the result on that line, and triggers an NPC follow-up reply.

Notes:
- Only `persuasion` and `intimidation` are currently accepted.
- This requests a check and logs it; it does not auto-roll the player's check until the player clicks **Roll** in dialog (or uses the console manually).

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

### Forced conversation mode

Purpose:
- Start a scripted JRPG confrontation when a player walks within talking/shouting range of an NPC (for example Guz blocking the market square), without immediately starting combat.

NPC / map YAML (`properties.forced_conversation` or legend `overrides`):

```yaml
forced_conversation:
  enabled: true
  once_session_key: guz_scene
  volume: shout          # whisper | normal | shout
  distance_ft: 30        # optional override
  require_los: true
  opening: llm           # llm | initial_statement | conversation_buffer
  context: "Open with a threat, but do not attack yet."
  initial_statement: "Hand over the sheep!"
  describe_group_allies: true
```

Campaign `game.yml` can supply defaults, per-map setting (`public` vs `private`), detection notes, impatience, and hostile reveals:

```yaml
forced_conversation_map_settings:
  town_market: public

forced_conversations:
  guz:
    settings:
      public:
        narration:
          title: A Swagger Through the Crowd
          text: A huge half-orc swaggers into the square...
        context: Demand Master Noke's sheep in public.
      private:
        narration:
          title: A Knock That Means Business
          text: Heavy fists hammer the door...
    detect_targets:
      - entity_uid: finethir_shinebright
        presence_note: Your wolves smell the sheep — hiding will not work.
    impatience:
      nudge_after: 3
      max_player_replies: 5
    on_hostile:
      reveal:
        - entity_uid: polymorph_bear
          label: Polymorphed Brown Bear
          remove_statuses: [hidden]
```

Noke's treehouse confrontation (`forced_conversations.ahmed_noke` in `game.yml`) uses `opening: initial_statement` for the scripted demand, injects campaign context (including `session_state_notes` when `wild_sheep_guz_killed` is set after the market fight), and escalates to combat via `[GO_HOSTILE]` or refusal keywords.

Server behavior:
- After an out-of-combat PC move, `ForcedConversationManager` scans dialog NPCs on the map.
- When triggered, it locks movement for nearby PCs, emits `forced_conversation_start` / `open_entity_dialog` with `forced: true`, and calls `initiate_npc_address(...)`.
- NPC replies that include `[GO_HOSTILE]`, `[GO_FRIENDLY]`, or configured keywords resolve the scene (hostile → combat via existing group logic; friendly/neutral → group change + unlock).
- Local chat remains available; JRPG dialog close is disabled until the scene resolves or combat begins.

### Out-of-combat hit reactions

When an NPC is struck by a weapon attack or damaging spell **outside combat**, the server briefly hands control to the NPC LLM so it can shout or react in character.

Behavior:
- Runs after `commit_and_update()` resolves a non-battle action that produced a `damage` or `spell_damage` result item.
- Skips NPCs that are **dead** or **unconscious** after the hit (one-shot kills do not get a reaction line).
- Injects a system note with attack/spell kind, damage type, damage total, and attacker identity when line-of-sight allows (`Map.can_see`).
- Uses the same proactive reply path as item-offer notifications (`handle_npc_out_of_combat_hit` → `_run_single_npc_reply_turn`), including TTS when configured.
- Requires `NPC_LLM_ENABLED` and a working NPC LLM handler; failures are logged and do not block the action.

Implementation: `natural20/utils/npc_hit_reaction.py`, `webapp/npc_damage_reaction.py`, `webapp/conversation_service.py`.

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

### Out-of-combat environment NPC ticks

After each `advance_world_time(..., trigger_environment=True)` while **no battle**
is active, the server schedules **one LLM loop per dialog-enabled NPC** in a
background worker (`webapp/npc_environment_ticks.py`):

1. Active movement task → `execute_scheduled_movement(advance_time=False)`
2. Else active short-term goal → `execute_scheduled_goal(advance_time=False)`
3. Else ambient routine tick (identity + recap + `goal_execution_prompt`)

Disable in `game.yml`:

```yaml
npc_environment_ticks:
  enabled: false
```

Or set `N20_NPC_ENV_TICKS=0`. Set `N20_NPC_BACKGROUND_LLM=0` to keep ticks
scheduled but skip all NPC LLM calls (movement/goal/ambient loops become no-ops).
Per-feature override: `npc_environment_ticks.llm_enabled: false` in `game.yml`.
Ticks are skipped during combat, long-rest NPC
simulation, and realtime UI suppression. A single `refresh_map` is emitted when
the batch completes.

## Witnessed Actions (NPC memory)

Nearby NPCs receive scoped console lines when players accept or decline item offers, use items, and similar actions they could overhear.

- Logging: `natural20.utils.conversation_witness.log_witnessed_action(...)` with entity-scoped visibility.
- Prompt injection: `EntityRAGHandler.witnessed_events_summary(...)` is appended in `conversation_response_prompt(...)` as **Recent events you witnessed nearby**.

Campaigns do not implement this per adventure; the engine surfaces whatever was logged while the NPC was in scope.

## Campaign-Configurable Item Offers

Repeat-offer guards and LLM guidance for `[OFFER_ITEM]` come from the active campaign `game.yml`, not hardcoded adventure logic.

```yaml
conversation_offer_guidance:
  target_has_item: "- {target} already carries the {item_label}; do not offer it again."

conversation_item_offers:
  scroll_speak_animals_modified:
    item_label: modified Speak with Animals scroll
    prefer_player_character: true  # [OFFER_ITEM target=speaker] routes to the /talk PC, not NPC chain relays
    aliases: [scroll_speak_animals]
    block_when: [offer_completed, target_has_item, target_effect_animal_communication]
    accept_effect: animal_communication
```

Optional per-NPC overrides: `conversation_item_offers` on the entity YAML `properties` / map `overrides`.

Implementation: `natural20/utils/conversation_offers.py`, used by `webapp/entity_rag_handler.py`.

### `[PICKUP: item=<slug>, qty=N]`

Picks up a ground-stack item within melee/adjacent reach (same rules as the Ground interact action). No player UI; the server transfers immediately and logs a witnessed outcome.

### `[LIST_CONTAINER: target=@handle]` and `[LIST_CONTAINER]`

Purpose:
- Let tavern staff (or any NPC near an open chest/bar) inspect container stock before answering or serving.

Server behavior:
- `EntityRAGHandler._handle_list_container_query(...)` resolves an optional `target` / `@handle` to a map container (Chest subclass with `inventory`).
- Injects a system message such as `[LIST_CONTAINER] @tavern_bar (Bar Counter): ale mug x24, bread loaf x8, ...` and regenerates the reply.
- Without `target`, lists every accessible open container within 30ft.

Notes:
- `[OBSERVE]` also includes `stock:` on visible open containers when the observer can see them.

### `[RETRIEVE: item=<slug>, target=@container, qty=N]`

Takes items from an open, unlocked container within 15ft into the acting NPC's inventory. Same transfer rules as the chest **loot** interaction. Logs a witnessed outcome.

### `[STORE: item=<slug>, target=@container, qty=N]`

Deposits items from the acting NPC into an open container within 15ft. Same transfer rules as the chest **store** interaction.

`[OFFER_ITEM]` may also draw from a nearby open container when the NPC does not carry the item (for example Mara serving ale from `@tavern_bar`).

### `[ANNOTATIONS: target=@handle]` and `[ANNOTATIONS]`

Purpose:
- Staff-only markings on objects (ledger scratch codes, key locations) that **player characters never see** in conversation or `[OBSERVE]`.

YAML:
- Use `annotations` on map objects (not `notes`). `notes` remain discoverable by PCs via Look / perception.
- Optional `viewers: [entity_uid, ...]` limits which NPCs can read an annotation; omit to allow any NPC.
- No perception DC — allowed NPCs see annotations when the object is in line of sight (enforced by `[OBSERVE]`, Look, and `[ANNOTATIONS]`).

Server behavior:
- `EntityRAGHandler._handle_annotations_query(...)` injects `[ANNOTATIONS] ...` and regenerates the reply.
- `[OBSERVE]` appends `staff annotations:` on interactable objects for NPC observers only (visible objects within range).
- NPC **Look** actions can also record annotation perception targets.

### `[OPEN_SHOP: target=speaker|@handle]`

Opens the **priced merchant shop UI** when the speaking NPC has a `merchant` block in YAML. Use this when the customer asks to buy, browse wares, or see your stock. The player gets the dual-pane shop modal (wares + payment) instead of the free-form item transfer dialog.

Human-controlled customers only. Pair with spoken welcome text, e.g. *"See anything you like?"* plus `[OPEN_SHOP: target=speaker]`.

### `[TRADE: target=speaker|@handle]`

Opens the bidirectional **item transfer dialog** (`loot_items.html`) for human-controlled targets. NPC-to-NPC trades with no human controller are adjudicated in-character by the DM LLM (`webapp/npc_item_exchange.py`).

### `[REQUEST_ITEM: item=<slug>, target=speaker|@handle]`

Asks the target to hand over an item. Human-controlled targets get the transfer dialog in **give** mode; otherwise the DM LLM adjudicates acceptance and item movement.

### `[ACCEPT_GIFT: target=speaker|@handle]`

Use when the speaker offers to give you something, hands an item over (including non-verbal `*action*` lines), or otherwise signals a gift. Opens the **give-item transfer dialog** for human-controlled speakers. Optional `item=<slug>` hints what they offered.

After the player confirms or cancels the transfer UI, the client posts to `/talk/item_transfer_complete` and the NPC LLM receives a system note with the outcome, then may reply in character.

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
- `webapp/conversation_service.py`
- `webapp/blueprints/helpers/conversation_wiring.py`
- `natural20/utils/conversation.py`
- `tests/webapp/test_entity_rag_handler.py`
- `tests/webapp/test_talk_route_recipients.py`