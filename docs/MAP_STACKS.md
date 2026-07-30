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
    shape: area
    bounds: { x1: 9, y1: 16, x2: 9, y2: 17 }
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

When the active map is the **base floor**, only that map is rendered (no overlay DOM).

Edit mode `GET /edit/overlay` includes `map_stack` metadata for the ghost overlay UI. When viewing a composited overlay floor, drag-and-drop placement sends `map_name` and **overlay-local** `(x, y)` to `/edit/layer/place`.

## Wild Sheep Chase example

`amphail_tavern` stack: `town_market` (base) + `tavern_2nd_floor` at anchor `[9, 16]`. STAIRS_UP teleporter remains as a legacy fallback during migration.
