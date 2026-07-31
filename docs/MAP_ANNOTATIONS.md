# Map landmarks (`map_annotations`)

Named places on a campaign map for NPC navigation, DM tooling, and LLM context.

## YAML schema

Add a top-level `map_annotations` list to any map YAML (alongside `area_narrations`, `legend`, etc.):

```yaml
map_annotations:
  - id: behind_bar
    label: Behind the bar
    description: Narrow staff corridor; keep guests out unless escorted.
    kind: point
    pos: [8, 12]

  - id: taproom
    label: Main taproom
    description: Open common room with the bar along the north wall.
    kind: area
    bounds: {x1: 4, y1: 6, x2: 14, y2: 16}

  - id: pantry
    label: Pantry
    description: Storage and stairs to the upstairs parlor.
    kind: polygon
    points:
      - [15, 8]
      - [18, 8]
      - [18, 12]
      - [15, 12]

  - id: bar_counter
    label: Bar counter
    description: Service side of the tavern bar.
    kind: object_ref
    entity_uid: tavern_bar_counter
```

### Kinds

| `kind` | Fields | NPC movement |
|--------|--------|----------------|
| `point` | `pos: [x, y]` | Path to exact square |
| `area` | `bounds: {x1,y1,x2,y2}` | Path until inside rect |
| `polygon` | `points: [[x,y], ...]` (≥3) | Path until inside polygon |
| `object_ref` | `entity_uid` | Path toward object like a creature |

`id` is a stable slug used in `[MOVE: target=behind_bar]` and MCP calls. `description` is injected into NPC/DM LLM prompts.

Optional **Detect Magic** fields (map landmarks, campaign `magical_annotations`, entities, and objects):

| Field | Purpose |
|-------|---------|
| `magical: true` | Landmark/object/entity bears a detectable aura |
| `magic_school` | 5e school (`abjuration`, `conjuration`, `divination`, `enchantment`, `evocation`, `illusion`, `necromancy`, `transmutation`) |
| `aura_strength` | `faint` (default) or `strong` for persistent magic items / active spells |

Campaign-level static auras live under `magical_annotations` in `game.yml`, keyed by map id (same geometry as `map_annotations`).

Detect Magic auras are shown for any source within **30 feet**, even when the tile is behind fog of war or walls (dashed border on sensed-only tiles). Line of sight is not required to **sense** magic, but the **school of magic** is only revealed on visible creatures/objects.

Barrier penetration (cumulative along the path from the caster):

| Material | Blocks after |
|----------|----------------|
| Stone | 1 foot |
| Common metal | 1 inch |
| Lead | any thin sheet |
| Wood or dirt | 3 feet |

Objects may override barrier behaviour with `detect_magic_barrier: {material: stone, thickness_ft: 1}` in YAML.

## NPC `known_places`

Optional on NPC YAML (`overrides` or properties):

```yaml
overrides:
  known_places:
    - behind_bar
    - taproom
```

Known landmarks are listed first in conversation/movement prompts.

### Current location in NPC prompts

When an NPC stands inside a `point`, `area`, or `polygon` landmark, the engine injects an
authoritative **Current location** line into:

- Conversation landmark prompts (`map_landmarks_prompt_for_entity`)
- Movement / goal situational context (`build_npc_situational_context`)

Use `kind: area` with `bounds` for guest rooms, taproom, hallways, etc. so staff get
"You are in Standard Room 1" while anywhere in the bedroom, not only on the door tile.
`stack_opening` and `floor_mask` annotations are excluded from location context.

When an NPC with `known_places` is pathing toward one of those landmarks (`[MOVE: target=<id>]`), movement uses **door-aware pathfinding** — they route up to closed doors instead of treating them as impassable walls. If a closed or locked door blocks the route, the NPC LLM receives a movement tick with door state and available interactions (`open`, `unlock`, `lockpick`) so it can `[INTERACT: ...]` and then resume navigation on the next tick.

## Authoring UI (edit mode)

Run the webapp with `N20_EDIT_MODE=1` or `./start_web.sh --edit <campaign>`.

A **Landmarks** panel appears at the bottom-left of the map:

- **+ Point** — click a tile, then fill in id/label/description in the modal
- **+ Rectangle** — click opposite corners, then save in the modal
- **+ Polygon** — click vertices, **Finish polygon**, then save in the modal
- **List** — click a landmark to edit; use **×** or the modal **Delete** button to remove
- **Move** — hold **Shift** and drag a landmark label (same gesture as fixture labels)

Cross-map landmarks (e.g. upstairs guest rooms reached via stairs/teleporters) resolve across all campaign maps. NPCs with the landmark in `known_places` can path via teleporter links using `PathCompute.compute_cross_map_path`.

Landmarks persist to the map YAML via `POST /edit/annotations` (create/update), `POST /edit/annotations/move` (drag reposition), or `DELETE /edit/annotations/<id>` (remove).

## HTTP API (DM)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/edit/annotations` | List landmarks on current map |
| `POST` | `/edit/annotations` | Create/update (`{annotation: {...}}`) |
| `POST` | `/edit/annotations/move` | Reposition (`{id, x, y}` — translates geometry) |
| `DELETE` | `/edit/annotations/<id>` | Remove landmark |

Requires DM role (edit mode not required for these routes).

## MCP

`dm.map_landmark` with `op`:

- `list` — optional `map_name`
- `upsert` — `annotation` object (writes YAML, reloads map)
- `delete` — `annotation_id`

## Distinction from other features

- **`area_narrations`** — player-facing DM text on enter (once per PC)
- **Object `annotations`** — NPC-only staff notes on containers/objects
- **`map_annotations`** — map-level landmarks for navigation and place awareness
