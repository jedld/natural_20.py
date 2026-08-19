# 3D VTT client (Three.js)

Natural20 keeps the existing HTML battlemap at `GET /`. A **sibling Three.js client** lives at `GET /3d`. It renders the same campaign session (Flask cookie + Socket.IO) as an orbit-camera tabletop: draped battlemap floor, extruded walls, token billboards.

The 2D VTT is unchanged. Sheets, login, DM admin, character builder, and merchant stay HTML. Map-edit mode is not in the 3D client.

## Visual model

Maps stay 2D grids. The 3D view **extrudes and drapes**:

| Layer | Source | Mesh |
|---|---|---|
| Floor | `map.background` (`background_image`) | Textured quads; water cells lowered to the pool bed |
| Water | `geometry.water` | Open stone walls; translucent Gerstner-wave surface at floor height |
| Solid walls | `base` `#` cells and `stone_wall` objects | Textured stone boxes (~8 ft); **cave** style uses curving limestone faces, not cubes |
| Thin walls | `stone_wall_*` edge objects | Thin stone boxes on **opaque** cell edges (window/stair-well sides are omitted) |
| Door-walls | `DoorObjectWall` / `corner_door_*` | Door mesh on `door_pos`; remaining opaque `border` edges are thin walls |
| Window-walls | `WindowObjectWall` / `window_*` / `corner_window_*` | Casement window on `door_pos` (sill + glass or shutter); remaining opaque `border` edges are thin walls |
| Wall style | `map.walls.style` (`dungeon` / `cave` / `mansion` / `gothic` / `wood` / `office`) | Cut dungeon stone, **organic cave limestone** (displaced faces, stalactites/stalagmites), cream manor plaster, dark damask gothic manor, timber planks, or painted drywall with aluminum trim |
| Doors | door objects + `door_pos` | Stone frame + hinged oak panel (open swings 90°); two adjacent same-edge doors render as one double door |
| Windows | `geometry.doors[].kind: window` | Sill + frame + glass or shutter; wall transom fills to full wall height; open swings like a casement; iron bars when `barred` |
| Secret doors | `geometry.doors[].kind: secret_door` | Flush stone slab; slides up when open |
| Portcullis | `geometry.doors[].kind: portcullis` | Rusted iron grate; raises when open |
| Chests | object `kind: chest` | Wooden chest; lid open/closed, iron lock when locked |
| Barrels / cover | `kind: barrel`, `cover`, trees | Barrel with hoops, crate, tree, briar |
| Teleporters | `teleporter_marker` | Floor rune/portal (not a solid box) |
| Trapdoors | object `kind: trap_door` / `secret_trapdoor` | Wooden floor hatch + iron ring; open punches a hole and swings the lid |
| Pit traps | object `kind: pit_trap` | Perceived: cracked cover; sprung: hole + spikes; disarmed: hole |
| Chasms | object `kind: chasm` | Open pit: floor omitted, stone shaft sinks below the tile (depth from `fall_distance`) |
| Stairs | object `kind: stairs` | Cosmetic steps along `squares` (base → top); auto-detects double-wide strips and spirals (2×2, compact L/U, or a ring) as circular wedge treads around a newel; `open_well` leaves a hollow shaft; `wall_attached` hugs the well walls; height in feet (default 8; negative descends); `solid` fills under the treads; tokens follow step height |
| Torches / lamps | `lights[]` from YAML `map.light` + `lights:` catalog | Wall sconce or standing torch + `PointLight` |
| Campfire / brazier / fireplace | object `kind` | Mesh + `PointLight` when lit (fireplace unlit = mesh only) |
| Tokens | `/map_state` `entities[]` | Billboard + disc; **prone** lies on the floor; **flying** hovers with a ground shadow; carried torch or spell orb + `PointLight` when `light` is set |
| Fog / light | tile `line_of_sight`, `light` | Dark quads / warm tint (game illumination, unchanged) |
| Move / AoE | `/path`, `/target` | Polyline + floor highlights |
| Combat FX | Socket `spell` / `attack` | Projectiles, beams, cones, bursts, auras (`client-3d/src/fx/`) |
| Map weather | Socket `effect:set` | Fog (scene + ground mist), streaked rain with splashes, snow, terrain-water chop, point fires, wall of fire |
| Status auras | entity `effects[]` | Token rings (bless, shield, invisibility, …) |

Camera: orbit (right-drag rotate, left-drag pan, wheel dolly). Left-click selects a square or token. Optional **Top** button for a high overhead view.

## Backend contract

### `GET /map_state`

JSON twin of `GET /update` (which still returns HTML). Same login/POV/fog rules. Built by [`natural20/web/map_state.py`](../natural20/web/map_state.py) from `JsonRenderer` tiles plus wall/door geometry.

```json
{
  "map": {
    "name": "goblin_cave",
    "size": [10, 10],
    "feet_per_grid": 5,
    "background": "/assets/maps/goblin_cave.webp",
    "image_offset_px": [0, 0],
    "illumination": 0.25,
    "illumination_default": 0.25,
    "illumination_overridden": false,
    "walls": { "style": "dungeon" }
  },
  "tiles": [{ "x": 0, "y": 0, "line_of_sight": true, "light": 0.4, "...": "..." }],
  "geometry": {
    "solid_walls": [[0, 0]],
    "edge_walls": [{ "x": 3, "y": 4, "edges": ["n", "e"] }],
    "doors": [{ "id": "...", "x": 5, "y": 2, "edges": ["n"], "open": false, "kind": "door" }],
    "water": [[1, 2], [2, 2]]
  },
  "entities": [
    { "uid": "...", "x": 8, "y": 12, "token": "token_fighter.png", "size": 1, "hp": 12, "max_hp": 16, "light": { "bright": 20, "dim": 20, "origin": "item" } }
  ],
  "objects": [{ "id": "...", "x": 2, "y": 3, "kind": "chest", "opened": false }],
  "lights": [{ "x": 3, "y": 4, "kind": "torch", "bright": 5, "dim": 5, "edge": "s", "lit": true }],
  "effects": [{ "effect": "fog", "action": "start", "exclusive": false, "config": { "color": "#aab4c8", "opacity": 0.5 } }]
}
```

Gameplay APIs are unchanged: `POST /action`, `GET /path`, `GET /target`, `GET /actions/batch`.

### Socket.IO

Same default namespace `/` and `message` types as the 2D client (`refresh_map`, `refresh_tiles`, `move`, `spell`, `attack`, `turn`, `initiative`, `focus`, `map`). On `refresh_map` the 3D client refetches `/map_state` (debounced). On `move` it tweens token billboards from `animation_log`, then refreshes.

Combat VFX: `spell` and `attack` (and matching `animation_log` entries) go through `playSpellEffect` / `playAttackEffect`. Recipes live in [`n20-webapp/client-3d/src/fx/spellCatalog.js`](../n20-webapp/client-3d/src/fx/spellCatalog.js) (same keys as `webapp/static/spell_effects.js`: fireball, burning hands, thunderwave, weapon styles, …). Unknown spells fall back to an area glow or a generic projectile.

Map special effects: listen for `effect:set` (`start` / `stop` / `update`, same payload as the 2D client). `GET /map_state` also includes `effects[]` from the map YAML `default_effect` / `default_effects`, so fog still starts if the Socket.IO replay is late or several floors share the same display name. Fog is a **raymarched volumetric pass** (scene color + depth, 3D noise, Beer-Lambert extinction). It honors `color` / `density` / `opacity` / `speed` / `noise_scale` and `mask` / `mask_layers` (street fog stays outside a house). `height` is the volume top in world units; `0` or omitted uses a ~6 ft ground mist. Unmasked fog also keeps a light scene distance haze. Rain is streaked line segments with wind, ground splashes, and optional lightning flashes. Persistent status auras are rebuilt from each entity's `effects` list on `/map_state`.

Water **terrain** (`type: water` objects) is not the 2D flood overlay. Those cells keep the battlemap image on the **pool bed** (lowered by ~1 ft), with stone walls around the pool and a translucent Gerstner-wave surface at **y = 0**. Opacity is low enough that the map art shows through. Warm light-tint quads and YAML wall torches skip water cells. Rain or a map `water` effect adds chop and sparkle on that surface.

Optional audio: `index_3d.html` loads `sfx.js`; recipes play the same cue names as 2D when `window.SFX` exists.

Walls use a repeating albedo with world-scaled UVs. The default is dungeon stone (`/assets/vtt3d/dungeon_stone.jpg`). Maps and campaigns can pick a **wall style** without putting adventure names in the engine:

```yaml
# user_levels/<campaign>/vtt3d.yml  (campaign default)
walls:
  style: mansion          # dungeon | cave | mansion | gothic | wood | office
  # albedo: textures/custom_wall.jpg   # optional override

# maps/<name>.yml  (per-map override; wins over the campaign file)
vtt3d:
  walls:
    style: dungeon
```

`render.palette: interior` also selects mansion walls; `dungeon` selects stone; `cave` / `cavern` / `grotto` select **organic cave limestone** (fixed seed `0xC4E57E01`: world-space displaced faces so walls are not boxes, unique FBM per stretch, stalactites / stalagmites / columns, triplanar albedo + roughness — grainy rock with smoother flowstone and wet calcite patches); `gothic` / `haunted` select the dark damask manor; `office` / `modern` / `corporate` select painted drywall with aluminum trim and frosted-glass doors. `gothic` is oxblood wallpaper, ebonized wainscot, and soot — distinct from cream `mansion` plaster. Ordinary doors are a jamb/lintel (stone in dungeons, oak in mansions, aluminum in offices) plus a hinged leaf (oak, or frosted glass in offices). Two oak doors that share an edge on neighboring cells (east/west doors stacked north–south, or north/south doors side by side) become **one double door**: a shared frame spanning both cells, no mullion in the middle, and two leaves hinged on the outer sides. Pairing skips neighbors that are split by a perpendicular wall (two single doors in adjacent rooms). Each leaf still follows its own open/locked state. Set `vtt3d: { double: false }` on a door (or `double: false` in the campaign catalog) to keep two singles. **Windows** are a sill and frame with a glass pane or shutter (`cover_pane`); a matching wall transom fills from the lintel to the same height as adjacent walls; they swing open like a casement and show iron bars when `barred`. **Secret doors** are a flush slab in the current wall style. A **portcullis** is a rusted iron frame and spiked grate that lifts when opened. Corner door-wall and window-wall tiles (`corner_door_*`, `corner_window_*`) extrude the attached wall edges as well as the opening.

Campaigns can override or extend 3D meshes without putting adventure names in the engine:

- `user_levels/<campaign>/vtt3d.yml` maps object `type` → `{ kind, src?, scale? }`
- Legend/object YAML `vtt3d: { kind: portcullis }`
- Built-in inference: `portcullis` in type/name, wall windows (`window_*` / `WindowObjectWall`) → `window`, or a secret door (`secret`, `secret_door`, `secret_dc`); floor hatches from `trap_door` / `trapdoor` / `pit_trap` (secret trapdoors → `secret_trapdoor`); `type: stairs` → stepped 3D mesh

Built-in kinds: `door`, `window`, `secret_door`, `portcullis`, `wall`, `skip`, `trap_door`, `secret_trapdoor`, `pit_trap`, `chasm`, `stairs`, plus existing fixtures. `src` loads a campaign glTF from `/assets/…`. See [`.cursor/skills/n20-vtt3d-models/SKILL.md`](../.cursor/skills/n20-vtt3d-models/SKILL.md).

`GET /map_state` `objects[]` includes `kind`, `opened`, `locked`, `cover`, `facing`, `lit`, `light` (`bright`/`dim` in feet), plus hatch state (`activated`, `disarmed`, `concealed`, `secret`) and stair runs (`squares`, `height` in feet, optional `style`, `solid`, `open_well`, `wall_attached`). Chests, barrels, cover, campfires, braziers, fireplaces, torches, trapdoors, pit traps, and stairs are meshed in [`n20-webapp/client-3d/src/scene/fixtures.js`](../n20-webapp/client-3d/src/scene/fixtures.js). Visible teleporters render as a colored floor portal instead of a cube. Concealed secret hatches and unperceived pits are omitted from `objects[]` (same POV filter as the 2D map), so the floor looks normal until they are found. Open trapdoors and sprung/disarmed pits omit the battlemap floor quad for that cell. **Chasms** (`kind: chasm`) always omit the floor and render a sunken shaft (no spikes). Descending stairs (`height < 0`) omit the floor after the base square so the steps are visible. `solid` (default true) fills the volume under the treads. `open_well` leaves a hollow spiral shaft; `wall_attached` adds well walls and extends treads to meet them. Stairs are **3D-only cosmetics**: they are passable, have no 2D token or wall borders, and do not change movement or cover.

**3D-only lamps:** YAML `map.light` overlays (with the `lights:` catalog) become `lights[]` wall torches. Creature `light_properties()` (equipped torch/lantern/candle, or a `light_override` effect such as Light or Guiding Bolt) is copied onto `entities[].light` (`origin: item|effect`, optional `color`). Generic glowing objects that are not campfires/torches become `kind: lamp`. These Three.js `PointLight`s are visual only — they do **not** write `Map.light_at`, fog, or LOS. Cells that already have a campfire/fireplace/brazier/torch/lamp object, that are solid walls, or that are water terrain skip a duplicate YAML torch. Unlit fireplaces still get a stone surround. Token lamps parent to the billboard so they follow movement. Ambient fill is lowered when `map.illumination` is dark so the sconces read on stone. The DM can override that ambient in `/3d` with the Light slider (`illumination_default` is the YAML value). Cap is 20 decor lights; `point_fire` FX skips a second `PointLight` on a cell that already has one.

## Frontend layout

Source: [`n20-webapp/client-3d/`](../n20-webapp/client-3d/) (Vite + Three.js).

Build output: [`n20-webapp/webapp/static/client-3d/`](../n20-webapp/webapp/static/client-3d/) served same-origin as `/client-3d/client-3d.js`.

Flask: [`blueprints/client_3d.py`](../n20-webapp/webapp/blueprints/client_3d.py) → `GET /3d` → [`templates/index_3d.html`](../n20-webapp/webapp/templates/index_3d.html).

```bash
cd n20-webapp/client-3d
npm install
npm test          # geometry + spell catalog tests (no WebGL)
npm run build     # writes webapp/static/client-3d/
npm run dev       # Vite on :5173, proxies API to :5001
```

Open the 3D view from the 2D hamburger (**3D View**) or go to `/3d` after login.

## Controls

- Left-drag: pan
- Right-drag: orbit
- Wheel: zoom
- Left-click token: action bar (`/actions/batch` HTML)
- Movement / targeting: same `/path` `/target` `/action` flow as 2D. Attack targeting draws a range line from the attacker to the hovered square.
- Hover a fixture: object interaction icons (open, talk, …). Info-sign chips mark objects with notes.
- Esc: cancel mode / close action bar / close note popup
- **DM only:** a **Light** slider under the zoom controls (top-left, below the header) sets 3D global ambient (hemisphere / sun / fill) in real time. Zoom and Light stay out of the bottom action bar. It starts at the map YAML `illumination` (0 = dim dungeon, still readable; 1 = full daylight). Raising it also pushes distance fog back and thins volumetric mist so large maps do not fade to black. **Reset** restores that default. The override is per map, stored in `session.session_state['vtt3d_illumination']`, and is broadcast on Socket.IO (`vtt3d_illumination`) so other 3D clients update without a full map rebuild. It does **not** change LOS or `Map.light_at`. `POST /admin/illumination` / MCP `dm.illumination`.

## Out of scope (v1)

- Replacing the 2D VTT
- First-person exploration
- 3D map editor
- Per-tile heightmaps / glTF furniture
- Map stacks as true floor slabs (see [MAP_STACKS.md](MAP_STACKS.md); later phase)
- Pixel-identical ports of every 2D canvas shader (3D uses Three.js primitives: projectiles, beams, cones, bursts, weather particles)

## Adding a spell VFX

When you add a 2D `SpellEffects.register(...)` entry, also add a recipe in `n20-webapp/client-3d/src/fx/spellCatalog.js` (`kind`: `projectile` | `beam` | `burst` | `cone` | `area` | `heal` | `aura` | `teleport` | `melee` | `look` | `combo`) and an alias if the engine emits a spaced label. Run `cd n20-webapp/client-3d && npm test && npm run build`.
