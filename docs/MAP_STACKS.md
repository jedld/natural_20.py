# Multi-Level Map Stacks

Map stacks bind a **base map** and one or more **overlay floors** into a shared world coordinate space. The VTT can render overlays composited on the base (e.g. tavern second floor anchored at `(9, 16)` on `town_market`).

## Campaign configuration (`game.yml`)

```yaml
map_stacks:
  amphail_tavern:
    base: town_market
    default_story_height_ft: 15
    floors:
      - map: tavern_2nd_floor
        anchor: [9, 16]      # overlay origin on base grid (top-left)
        elevation_ft: 15
        edge_exit: descend   # stepping off overlay → base at same world coords
```

## Per-map floor metadata (optional)

```yaml
floor:
  stack: amphail_tavern
  role: overlay          # base | overlay
  parapet_height_ft: 3
  ceiling_height_ft: 10  # room height above this floor's deck; omit = open sky when uncovered
```

### Ceiling height rules

Each world column has an **enclosed volume** bounded above by:

1. **Upper overlay slab** — when a higher floor map covers the column (`has_slab_at`), its deck elevation is the ceiling for everything below (e.g. taproom under `tavern_2nd_floor` caps at 15 ft).
2. **`ceiling_height_ft` on the walkable floor** — when no higher overlay covers the column, an optional finite room height applies (`elevation_ft + ceiling_height_ft`). Guest rooms on `tavern_2nd_floor` use `10` ft ceilings (25 ft absolute).
3. **Open sky (`infinity`)** — when neither applies (outdoor market squares, upper-floor tiles with no floor above and no `ceiling_height_ft`), vertical space is unbounded unless a map author sets `ceiling_height_ft` on the base or overlay map.

Use `floor_mask` with `allows_sight: up` or window tokens to pierce room ceilings (skylights, open windows).

## Shared vertical openings

Annotate stairwells/shafts that pierce all floors at the same world column:

```yaml
map_annotations:
  - id: tavern_stair_shaft
    kind: stack_opening
    stack: amphail_tavern
    shape: point
    pos: [9, 16]
    description: Stairs up to the Prancing Flagon guest rooms.
```

**Important**: Use `shape: point` with `pos` for a single-cell stairwell. `shape: area` with
`bounds` spanning multiple cells causes `MapStack.is_stack_opening()` to match cells where the
entity is not actually standing, breaking `transitions_from()` lookup.

#### Teleporter wiring

Teleporter objects (`target_map`, `target_position`) provide legacy fallback for floor changes.
**Always set `target_position` to the actual teleporter tile on the destination map, not an
interior cell**:

```yaml
# town_market.yml — going up
- token: STAIRS_UP
  pos: [9, 16]
  layer: object
  target_map: tavern_2nd_floor
  target_position: [0, 0]  # Must be the teleporter tile on destination

# tavern_2nd_floor.yml — going down
- token: Teleporter
  pos: [0, 0]
  layer: object
  target_map: town_market
  target_position: [9, 16]  # Back to town_market stairwell
```

## Floor masks

`floor_mask` annotations carve exceptions in the default opaque overlay deck:

- **`allows_sight: up|down|both`** — punch a hole through the floor deck for vertical LOS (e.g. open stairwell without a window token).
- **`blocks_sight: up|down|both`** — add extra blocking on top of the default opaque deck (e.g. solid roof over a taproom).

Mask geometry uses **local map coordinates** on the map where the annotation is defined.

```yaml
  - id: taproom_roof
    kind: floor_mask
    stack: amphail_tavern
    shape: polygon
    points: [[1,2],[5,2],[5,6],[1,6]]
    blocks_sight: up
```

## Window tiles

Legend entry with `type: window`, `peek_through: true`, `fall_through: true` — compositor shows base tiles through the opening; stepping onto it falls to the lower floor.

## Engine API

| Module | Role |
|--------|------|
| `natural20/map_stack.py` | `MapStack`, `WorldCoord`, `ceiling_elevation_ft`, registry, transforms |
| `natural20/map_stack_movement.py` | Edge descent, shaft falls, flying ascent |
| `natural20/map_stack_los.py` | 3D (x, y, z) LOS: opaque overlay decks, volumetric walls, windows/shafts |
| `natural20/web/stack_renderer.py` | Composited VTT tile layers |

Session helpers: `session.map_stacks`, `session.stack_for_map(name)`, `session.stack_for_entity(entity)`.

Entity helpers: `entity.world_position(map)`, `entity.elevation_ft(map)`, `entity.altitude_ft`, `entity.eye_height_ft()`, `entity.sight_world_position(map)`.

**Creature height in 3D LOS:** eye height defaults from size category (tiny through gargantuan) with optional race YAML overrides (`average_height_ft`, `eye_height_ft`). Prone creatures use a 1 ft eye height. Stack LOS uses `sight_world_position` (floor + flying altitude + eye height), not raw deck elevation.

## Movement rules (v1)

- **Overlay edge**: entity moves to base map at same world `(x, y)`.
- **Stack opening**: fall to next lower floor; fall damage from elevation delta (`floor(delta/10)` d6, cap 20d6).
- **Window + fall_through**: forced descent + prone.
- **Flying**: can ascend to upper floor at open columns.

### Voluntary descent (Ctrl / jump mode / `allow_stack_descent`)

By default pathfinding stays on the entity's current floor. Hold **Ctrl** during movement preview or toggle **jump mode (J)** to plan a voluntary drop to a lower floor in the same stack:

- Valid egress: `fall_through` windows, `stack_opening` shafts, and overlay **edge exits**.
- Movement cost includes extra grids for vertical drop (1 grid per 5 ft fallen).
- Preview shows **Jump to lower level** with expected fall damage (mitigated by flying or `feather_fall` status).
- Committing the move applies fall damage, may land **prone**, and continues on the base map segment.
- LLM/NPC path tools: pass `allow_stack_descent=true` (and `target_map` when needed) on `compute_path_to`; read `stack_descent` / `stack_descent_summary` in the response before choosing that route.

## Combat

`Battle.can_see` uses stack LOS when both entities share a stack. Overlay floor slabs block vertical sight by default; pierce only at `stack_opening`, window tiles, or `floor_mask` with `allows_sight`. All stack maps auto-register when battle starts on any member.

**Outdoor sight from an overlay floor** (composited VTT surround): upstairs viewers see outdoors only when the sight ray **exits through a valid overlay opening** (open roof-gap edge cell or window token). Overlay interior walls (including Unicode wall tiles) block rays inside the footprint. Ground cells directly under the overlay deck are ignored; the ground-floor building shell is pierced so you can see over the parapet; normal `town_market` walls/objects beyond the shell apply. Elevated sight does not use ground-level corner peeking on the base map.

## VTT

When the active map is an **overlay floor** in a stack, `/update` renders:

1. **Base layer** — full `town_market` tile grid and background image (canvas size = base map).
2. **Overlay layer** — absolutely positioned `.map-stack-overlay` at the floor `anchor`, containing:
   - the overlay map's **background image** (`.map-stack-overlay-bg`),
   - overlay tiles, fog, entities, and window peek-through.

**Map-edge peek-through** (composited outdoor surround): only non-opaque overlay cells on the border of the overlay grid peek at the base map outdoors (e.g. open roof gaps). Perimeter **walls** on the overlay map block sight and are not treated as peek cells.

Overlay tile grids omit map padding (no fog ring over the base map). Only in-bounds overlay cells are rendered.

When the active map is the **base floor**, the base map is rendered plus:

- **Stack LOS tokens** — overlay-floor creatures visible to the POV (via `Battle.can_see` / `stack_can_see`) appear on the base grid at their world coordinates, styled with a blue outline and elevation badge.
- **Floor focus control** — when a map belongs to a stack, a **Floor** dropdown (top-right, next to coords) switches the view to any stack floor (same as `switch_map` but scoped to the building). Use this to interact with upstairs tokens/targeting in composite mode.

Cross-floor **targeting and attacks** (spells, ranged/melee) use world-space distance and stack LOS on both directions (upstairs→down and down→up). Window/edge peek clicks resolve to world coordinates on the base map.

**Movement and viewport:** In composited overlay view, entities render twice — on the overlay (local coords) and as a projected token on the base layer (world coords). Pathfinding (`/path`) and viewport centering must use **overlay-local** coords for the active floor; the client prefers the `.map-stack-overlay` tile and converts world→local when needed. The server `_resolve_path_source` helper accepts mistaken world coords from the projected base token.

**Window peek visibility:** Overlay tiles only receive the `peek-through` CSS class (transparent + no fog) when the POV entity has line of sight to that tile **and** `stack_base_visible_from_overlay` confirms outdoor sight through that opening. Geometric edge/window candidates alone are not enough.

Edit mode `GET /edit/overlay` includes `map_stack` metadata for the ghost overlay UI. When viewing a composited overlay floor, drag-and-drop placement sends `map_name` and **overlay-local** `(x, y)` to `/edit/layer/place`.

## Cross-Map Navigation for NPCs and LLM Agents

NPCs and LLM-driven agents use `PathCompute.compute_cross_map_path()` to navigate between
maps. The algorithm runs A* over a graph of `(map_id, x, y)` states linked by:

1. **Stack transitions** — `MapStack.transitions_from()` at `stack_opening` cells
2. **Teleporters** — objects with `target_map` + `target_position`

### How it works

```
NPC on town_market [9,19] → path to stack opening [9,16]
  → stack transition → tavern_2nd_floor [0,0]
  → path to annotation target [1,3] (tavern_suite_room)
```

**Key requirements:**

1. **Stack opening must match teleporter position**: `shape: point` with `pos: [9, 16]` on
   `town_market` must align with the STAIRS_UP teleporter at `[9, 16]`.
2. **Teleporter `target_position` must be the destination teleporter tile**: `[0, 0]` on
   `tavern_2nd_floor`, NOT an interior cell.
3. **Destination annotation must be in NPC `known_places`**: NPCs resolve `tavern_suite_room`
   from their YAML `known_places` list, then the pathfinder computes the cross-map route.
4. **`linked_maps` must be bidirectional**: Each `Map` object auto-populates `linked_maps`
   during session load (`Session._load_all_maps`).

### Infinite loop protection

`compute_cross_map_path()` tracks push counts per state `(map_id, x, y)` and skips pushes
that exceed `max_pushes_per_state = 8`. This prevents pathological exploration when two
teleporters swap entities back and forth between maps.

### Diagnostic script

Run `python scripts/diagnose_cross_map_path.py user_levels/<campaign>` to verify:
- Map stack registration and anchor configuration
- Stack opening transitions (must return non-empty list)
- Teleporter target positions
- `linked_maps` bidirectional linking
- Annotation resolution for destination targets

## Wild Sheep Chase example

`amphail_tavern` stack: `town_market` (base) + `tavern_2nd_floor` at anchor `[9, 16]`. STAIRS_UP teleporter targets `[0, 0]` on the overlay.
