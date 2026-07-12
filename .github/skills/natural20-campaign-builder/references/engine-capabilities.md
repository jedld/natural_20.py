# Natural20 Campaign Engine Capabilities

Use this as a capability index, not a substitute for source inspection. Exact schemas and examples are in [docs/CAMPAIGN_BUILDING.md](../../../../docs/CAMPAIGN_BUILDING.md).

## Campaign composition

- `Session(root_path)` loads `game.yml` and every map registered in `game.yml.maps`; without `maps`, it loads `starting_map` as `index`.
- `index.json` configures the webapp title, tile size, initial and other maps, character selection, controllers, soundtracks, logins, autosave, and deferred player spawning.
- Campaign resource loading is primarily campaign-root based. Proven campaign directories contain the required `items`, `npcs`, `characters`, `races`, `char_classes`, `backgrounds`, and `locales` content or valid links to it.
- Stable entity UIDs are canonical for controller assignment, state updates, MCP operations, conversation context, and save/load.

## Maps and exploration

Supported map features include:

- rectangular grid layers: `base`, `base_1`, `base_2`, `meta`, and `light`;
- explicit `map.size`, grid scale, illumination, background image offset, and web background color;
- walls, floors, doors, terrain movement cost, swimming, hiding terrain, line of sight, and cover;
- direct entities plus legend-driven NPC, object, spawn-point, and mask entries;
- named and player-agnostic spawn points;
- static lights, object lights, fog/effects, point-fire visuals, map-entry narration, and area narration;
- multi-map links through teleporters and trap doors;
- concealed/secret objects, passive discovery, notes, investigation checks, and interaction buttons.

Validate map strings carefully: layer tokens are individual characters. Use `map.entities` for named/multi-character tokens.

## Objects and state

Built-in patterns cover doors, chests/inventories, traps, switches, multi-switches, fireplaces, proximity triggers, teleporters, trap doors, notes, terrain, and destructible/interactable objects.

Object event handlers can emit messages, damage, and state updates on supported events such as activation, open/close, entering a tile, turn boundaries, and ability-check outcomes. Cross-map state updates rely on registered map keys and stable target UIDs/names. Verify the exact handler syntax in a loading example before use.

## Encounters and combat

The core engine supports:

- initiative, rounds, movement/pathfinding, actions/bonus actions/reactions, opportunity and legendary-action windows;
- melee/ranged attacks, multiattack, common tactical actions, damage traits, conditions, death saves, cover, visibility, and resources;
- heuristic, manual, and LLM controllers;
- NPC action lists and battle preferences;
- spells only when their YAML definition and Python loader/class implementation exist;
- XP awards and XP-, DM-, or event-gated progression.

Campaign YAML cannot create a new action resolver, spell behavior, class feature, or condition semantic by naming it. Search registrations first. Complex scripted bosses may need an existing `combat_script` pattern, engine extension, or documented DM procedure.

## Characters, NPCs, and dialogue

- Character sheets use existing races, classes, equipment, spells, and class initialization behavior.
- NPC templates define stats, actions, equipment, traits, dialogue, and optional overrides at placement.
- Conversational NPCs can use canned buffers and LLM backstories. Conversation can direct actions/checks and update state through supported handlers.
- The implementation intentionally uses the historical key `converstation_keywords` in relevant NPC data; copy a current working example rather than correcting the spelling in campaign files.
- LLM output is nondeterministic. Critical clues and transitions need deterministic objects, notes, buffers, redundant routes, or DM controls.
- Conversation item offers can prevent repeat offers and apply supported accept effects.

## Web and DM operation

The Flask VTT supports character selection, map switching, battle management, inventory/equipment, rests, progression, effects/audio, saves, and DM administration. The MCP surface mirrors many world inspection, action, and DM mutation operations. A campaign README should identify which interventions the DM may need.

## Serialization boundary

Maps, entities, UIDs, inventory, battle state, and session state participate in persistence. New Python-backed objects/actions/features must follow existing serialization conventions and be tested through a save/load round trip. Campaign-only YAML should still use stable UIDs and resolvable resource keys.

## High-value examples

- Minimal core fixtures: `tests/fixtures/`
- Baseline general resources: `templates/`
- Multi-map, LLM, state, companion, scripted encounter, and pregens: `user_levels/wild_sheep_chase/`
- Larger multi-map campaign patterns: `user_levels/death_house/`
- Conversation behavior: `docs/CONVERSATION_RAG.md`
- Character and progression rules: `docs/DND_BEYOND_IMPORT.md`, `docs/DND_5E_2014_PROGRESSION.md`
