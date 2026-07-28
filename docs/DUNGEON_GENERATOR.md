# Procedural Dungeon Generator

Generate playable Natural20 map YAML using industry-standard procedural techniques,
with **LLM-controllable knobs**, mission objective placement, and quality gates for
**traversability** and **aesthetics**.

## Techniques (research-backed)

| Algorithm | Inspiration | Best for |
|-----------|-------------|----------|
| `bsp` | Rogue, classic roguelikes (BSP rooms + sibling corridors) | Structured dungeons, prisons, cathedrals |
| `rooms_graph` | Binding of Isaac–style scatter → nearest-neighbor graph → **MST + loops** | Branching hubs, manors, streets |
| `cellular` | Dwarf Fortress / Spelunky caves (CA + largest-component keep) | Organic caves, crypts |
| `hybrid` | BSP rooms + optional cellular wing | Mixed “built + wild” spaces |

**Semantics:** After carving, rooms are BFS-tagged from the entrance (`entrance`, `combat`, `elite`, `treasure`, `shrine`, `boss`, `exit`, `hub`). Enemies, traps, chests, and mission objectives are placed by **role + depth** so quests stay coherent.

**Quality gates:**

- Traversability — flood-fill from spawn; require reachable floor ratio and reachable objectives
- Aesthetics — composite score (floor ratio, aspect, loops, critical path, dead-ends, features, span)

## Quick start

```bash
# Schema for LLM tool calling
python scripts/generate_dungeon.py --print-schema

# Sewer mission with objectives
python scripts/generate_dungeon.py \
  --theme sewer \
  --seed 42 \
  --rooms 9 \
  --mission "Recover the black-rose symbol and escape" \
  --objective relic:symbol:treasure:far \
  --objective informant:npc:hub:near \
  --objective escape:teleporter:exit:far \
  -o /tmp/sewer_run.yml \
  --report /tmp/sewer_run_report.json \
  --render /tmp/sewer_run.png
```

## Python API

```python
from natural20.dungeon_gen import (
    GeneratorKnobs,
    ObjectiveSpec,
    generate_dungeon,
    generate_from_mission,
    knobs_json_schema,
)

result = generate_from_mission(
    theme="cathedral",
    mission="Confront the magistrate beneath the altar",
    seed=7,
    width=40,
    height=30,
    objectives=[
        {"id": "altar", "kind": "altar", "room_role": "shrine", "depth": "mid"},
        {"id": "volo", "kind": "enemy", "room_role": "boss", "depth": "far", "npc_type": "bugbear"},
    ],
)

print(result.traversability.to_dict())
print(result.aesthetics.to_dict())
result.write_yaml("user_levels/my_campaign/maps/ritual_crypt.yml")
```

## LLM knobs (high-signal)

| Knob | Effect |
|------|--------|
| `algorithm` | `bsp` / `rooms_graph` / `cellular` / `hybrid` |
| `loop_ratio` | Extra corridors beyond MST (more shortcuts) |
| `linearity` | Higher → fewer loops / more forced path |
| `theme` | Preset densities + atmosphere (`sewer`, `cave`, …) |
| `enemy_density` / `trap_density` / `chest_density` | Dressing intensity |
| `objectives[]` | Guaranteed mission placements by `room_role` + `depth` |
| `ensure_traversable` | Reject disconnected maps |
| `require_aesthetics_score` | Reject low-scoring layouts (0–1) |

Full JSON Schema: `knobs_json_schema()` or `--print-schema`.

## Objective string format (CLI)

```
id:kind[:room_role[:depth]]
```

Kinds: `npc`, `enemy`, `chest`, `trap`, `teleporter`, `interactive_object`, `altar`, `note`, `symbol`, `spawn`  
Depths: `near`, `mid`, `far`, `any`

## Package layout

```
natural20/dungeon_gen/
  knobs.py        # GeneratorKnobs + theme presets + JSON schema
  layout.py       # BSP / rooms_graph / cellular / hybrid
  placement.py    # Semantics + content + objectives
  topology.py     # Traversability flood-fill / path length
  aesthetics.py   # Layout quality score
  export.py       # Natural20 map YAML
  pipeline.py     # Retries until gates pass
```

## Integrating with campaigns

1. Generate YAML into `user_levels/<campaign>/maps/`.
2. Register the map in `game.yml` `maps:` and `index.json` `other_maps`.
3. Optionally batch-render: `python scripts/render_map_image.py --campaign … --batch-missing`.

## Tests

```bash
pytest tests/test_dungeon_gen.py -q
```
