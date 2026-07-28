---
name: natural20-dungeon-generator
description: "Generate procedural Natural20 dungeon maps with LLM-tunable knobs, mission objectives, traversability checks, and aesthetics scoring. Use when asked to create a dungeon, cave, sewer, crypt, or procedurally place quest NPCs/objectives on a map."
argument-hint: "theme, mission, objectives, size, algorithm"
user-invocable: true
---

# Natural20 Procedural Dungeon Generator

Create playable map YAML (not just ASCII sketches) using `natural20.dungeon_gen`.

## Load Context

1. Read [docs/DUNGEON_GENERATOR.md](../../../docs/DUNGEON_GENERATOR.md)
2. Prefer `scripts/generate_dungeon.py` or `generate_from_mission(...)`
3. Print knobs schema when designing LLM tools: `python scripts/generate_dungeon.py --print-schema`

## Workflow

1. **Extract mission intent** — theme, size, linearity, enemies, required objectives.
2. **Map intent → knobs**
   - Linear investigation → higher `linearity`, `bsp` or `hybrid`
   - Organic caves → `cellular` / `cave` theme
   - Hub city / branching → `rooms_graph`, higher `loop_ratio`
3. **Encode objectives** with `room_role` + `depth` (`near`/`mid`/`far`) so quest items land on the critical path sensibly.
4. **Generate** with `ensure_traversable=True`; raise `require_aesthetics_score` (e.g. 0.45) for polished maps.
5. **Register** the YAML in `game.yml` / `index.json`, then optionally render with `scripts/render_map_image.py`.

## Example

```bash
python scripts/generate_dungeon.py \
  --theme sewer \
  --seed 42 \
  --mission "Recover the Outcast symbol" \
  --objective relic:symbol:treasure:far \
  --objective whisper:npc:hub:near \
  -o user_levels/outcasts_path/maps/generated_sewer.yml \
  --render user_levels/outcasts_path/assets/maps/generated_sewer.png
```

## Quality checks

- Inspect `traversability.reachable_ratio` (want ~1.0) and empty `unreachable_objectives`
- Inspect `aesthetics.score` and notes (loops, dead-ends, floor ratio)
- Do not hand-edit giant ASCII grids when knobs can express the intent

## Algorithms (do not invent alternatives)

Use only: `bsp`, `rooms_graph`, `cellular`, `hybrid` — see docs for game-industry provenance.
