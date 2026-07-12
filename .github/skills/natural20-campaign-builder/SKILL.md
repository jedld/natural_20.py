---
name: natural20-campaign-builder
description: "Build, scaffold, adapt, repair, or expand a playable Natural20 D&D campaign from a user description, adventure outline, source book, PDF, notes, or existing module. Use when asked to create a campaign, one-shot, adventure, dungeon, encounter series, maps, NPC cast, pregenerated party, or source-book conversion for Natural20. Interviews the user for tone, scope, party, safety, automation, and assets; maps the design to supported engine features; writes campaign files; and validates loading, references, and playability."
argument-hint: "Describe the campaign or provide the source, party level/size, tone, and desired scope"
user-invocable: true
disable-model-invocation: false
---

# Natural20 Campaign Builder

Create a working campaign, not merely prose or a speculative plan. Unless the user explicitly asks for design-only output, finish by writing the campaign under `user_levels/<campaign-slug>/`, validating it, and reporting automated versus DM-run elements.

## Load Context

1. Read [docs/CAMPAIGN_BUILDING.md](../../../docs/CAMPAIGN_BUILDING.md) before authoring files. It is the primary format guide.
2. Read [engine capabilities](./references/engine-capabilities.md) and [campaign quality](./references/campaign-quality.md).
3. Inspect relevant implementation and examples before relying on a field:
   - [natural20/session.py](../../../natural20/session.py), [natural20/map.py](../../../natural20/map.py), [natural20/npc.py](../../../natural20/npc.py)
   - [templates](../../../templates), [tests/fixtures](../../../tests/fixtures)
   - [user_levels/wild_sheep_chase](../../../user_levels/wild_sheep_chase) for a feature-rich adaptation
4. Treat repository code and currently loading examples as more authoritative than remembered schema. Never invent YAML fields, action types, conditions, spells, item keys, or event semantics.

## Workflow

### 1. Establish the brief

Extract everything already stated by the user. Ask only for decisions that materially change the implementation. Use the structured question UI when available, in one or two compact batches, and provide recommended defaults.

Ask about these unresolved dimensions:

- **Source and rights**: original description, public/SRD material, user-provided book/PDF/notes, or an existing campaign directory; which chapters/scenes are in scope.
- **Play format**: one-shot, short arc, or campaign; expected session count and duration.
- **Party**: size, starting level, pregenerated characters versus user characters, progression mode.
- **Experience**: tone, themes, exploration/dialogue/combat mix, difficulty, lethality, and content boundaries/lines and veils.
- **Structure**: linear, branching, sandbox; desired maps, important locations, endings, and failure states.
- **Automation**: manual, heuristic AI, or LLM NPCs; whether unsupported mechanics may have explicit DM-run fallbacks.
- **Presentation**: existing or placeholder map art, portraits, music, and login requirements.

Do not repeatedly interview the user. If they delegate choices, choose coherent defaults: four players, level 3, mixed play, medium difficulty, a 3–4 hour one-shot, one hub plus two encounter maps, optional LLM dialogue with deterministic fallbacks, and placeholder-free grid maps.

### 2. Handle source material safely

- Use a source the user supplied or can lawfully access as design input. Do not acquire pirated copies or commit the source document to the repository.
- Do not reproduce substantial protected prose, boxed text, maps, stat blocks, or artwork. Write original summaries, dialogue prompts, room descriptions, maps, and adaptations.
- Preserve names or facts only as needed for the requested private adaptation. For redistributable work, prefer SRD/public-domain/original equivalents and ask when rights are unclear.
- Record source title, author/publisher, edition, scope used, attribution, and adaptation notes in the campaign README. Attribution is not a substitute for permission.
- Keep campaign-specific or non-SRD definitions in the campaign. Add generally reusable SRD definitions to `templates/` only when requested and when their engine implementation is complete.

### 3. Inventory engine support before design

Search exact keys in `templates/` and Python registrations for every proposed NPC type, class, race, spell, item, object, condition, and special action.

Classify each beat or mechanic:

| Classification | Action |
|---|---|
| Supported | Reuse the exact existing key and schema. |
| Configurable | Implement with map legends, objects, checks, events, session state, conversations, or existing scripts. |
| Extension required | Add the smallest reusable Python/YAML implementation plus focused tests, or ask before expanding scope substantially. |
| DM-run fallback | Document the trigger, DC/save, outcome, and exact DM procedure. Never imply it is automated. |

Prefer supported mechanics over one-off Python. Reuse map objects and existing event/state patterns. If new engine code is necessary, follow repository conventions, serialization requirements, and tests; do not hide executable behavior in campaign prose.

### 4. Design a playable scene graph

Before writing YAML, establish a concise campaign model in the README or working notes:

- premise, hook, player goal, stakes, opposition, and expected ending;
- scenes/maps and transitions, including alternate paths and return routes;
- clue/key/state dependencies with at least one recovery path for every required clue;
- encounter purpose, creature groups, terrain, objective, and fail-forward result;
- NPC goals, knowledge, leverage, relationships, and deterministic dialogue facts;
- treasure/rewards, rests, progression, victory, retreat, and TPK/failure behavior;
- an implementation matrix labeling each important beat automated, LLM-assisted, or manual.

Avoid unwinnable state graphs. Required progression must not depend solely on an exact LLM phrase, one hidden check, one fragile object, or one NPC surviving. Provide DM controls or redundant clues.

### 5. Scaffold the campaign

Use `user_levels/<slug>/` unless the user specifies another location. Build the smallest complete vertical slice first, then expand.

Minimum web campaign:

- `game.yml`
- `index.json`
- `README.md`
- at least one `maps/*.yml`
- enough `items/`, `npcs/`, `characters/`, `races/`, `char_classes/`, `backgrounds/`, and `locales/` resources for every reference
- `assets/` only for files actually referenced

Important: current resource loaders often read from the campaign root directly. Do not assume automatic fallback to `templates/`. Follow a proven campaign layout: copy the required shared YAML resources, or use valid repository-relative symlinks where portability permits. Customizing a shared YAML catalogue generally requires a campaign-local complete file, not a partial overlay.

Rules while writing:

- Keep all `entity_uid`, object names used as state targets, map keys, login names, and controller references unique and stable.
- Keep map rows rectangular and all layers dimensionally aligned. Coordinates are zero-based `[x, y]` and must be in bounds.
- Define every non-built-in map token in `legend`; do not use multi-character legend keys inside string layers—place them through `map.entities`.
- Register every teleporter target in `game.yml`; create a safe return path unless intentionally one-way.
- Match `game.yml` starting map, `index.json` map, map registry keys, and player spawn strategy.
- Prefer `player_spawn_points` plus `defer_player_spawn` for selectable pregens. Ensure the number of slots covers the expected party.
- Give conversational NPCs stable UIDs, languages, goals, bounded knowledge, and canned facts/fallbacks. LLM backstories must not be the sole source of progression.
- Use source-derived passwords only if the user explicitly requests them; otherwise use clearly documented development credentials and warn that they are not production authentication.
- Do not reference nonexistent image/audio files. Omit optional assets until supplied rather than fabricating binary files.

### 6. Validate incrementally

After each map or resource cluster:

1. Parse YAML/JSON and run the bundled validator from the repository root:
   `python .github/skills/natural20-campaign-builder/scripts/validate_campaign.py user_levels/<slug>`
2. Fix every error. Review warnings rather than suppressing them blindly.
3. Instantiate `Session(root_path=<campaign>)`; the validator does this by default.
4. Load player characters and inspect key entities/objects by UID when applicable.
5. Run focused repository tests for any engine code changed, then broader affected tests.
6. For new custom entities/items and any engine extension, exercise save/load round-trip behavior.
7. Start the webapp with `TEMPLATE_DIR=../user_levels/<slug>` and verify health/login/map rendering when practical. Use browser tools to walk the critical path.

Do not run the entire test suite before basic campaign validation passes.

### 7. Playability review

Walk through the campaign as four roles:

- **Player**: Can the objective be understood and completed without designer knowledge?
- **DM**: Are manual steps, triggers, credentials, map transitions, recovery paths, and endings documented?
- **Engine**: Does every reference resolve and every automated claim map to implemented behavior?
- **Adversarial tester**: What happens if players miss a clue, kill/ignore an NPC, retreat, split maps, fail checks, revisit areas, save/load, or trigger events out of order?

For an “effective campaign,” require:

- a clear hook and actionable goal early;
- meaningful choice or tactical variation;
- no single fragile progression gate;
- encounters appropriate to party capability, with terrain and objectives beyond attrition where possible;
- explicit automated/manual boundaries;
- a complete happy path plus failure/recovery behavior;
- validated startup, map transitions, and critical interactions.

### 8. Deliver

Update the campaign README with:

- source/provenance and adaptation statement;
- recommended party and expected duration;
- setup and launch command;
- scene flow and map graph;
- player-facing premise without spoilers;
- DM-only secrets, state flags, and manual procedures;
- automated versus LLM-assisted versus manual mechanics;
- credentials and controller setup;
- known limitations, asset placeholders, and validation evidence.

Finish with a concise report listing files created, campaign flow, validation performed and results, unsupported/manual elements, and the exact launch command. Do not call the campaign complete when validation or a critical path remains broken.
