---
name: n20-vtt3d-models
description: >-
  Add or override 3D VTT meshes for campaign objects (secret doors, portcullises,
  windows, trapdoors, pit traps, stairs, custom glTF). Use when a map object should not use the
  default oak door or fixture, when authoring user_levels/<campaign>/vtt3d.yml,
  or when adding a built-in barrier/hatch kind to the Three.js client.
---

# Natural20 — campaign 3D models

The 2D VTT is unchanged. 3D meshes are chosen by a **catalog**, not campaign names in the engine.

## Where to put the mapping

1. **Campaign catalog** (preferred): `user_levels/<campaign>/vtt3d.yml`
2. **Object or legend override**: `vtt3d: { kind: portcullis }`
3. **Built-in inference** (no file needed): type/name contains `portcullis` → grate; `window_` / `corner_window` / `WindowObjectWall` → casement window; `secret` / `secret_door` / `secret_dc` → stone slab; `trap_door` / `trapdoor` → floor hatch (`secret_trapdoor` when secret); `pit_trap` → pit; other `DoorObject` → hinged oak door

Do **not** put adventure names in `natural20/` or generic webapp 3D code.

```yaml
# user_levels/<campaign>/vtt3d.yml
walls:
  style: mansion          # dungeon | cave | mansion | gothic | wood | office
models:
  portcullis_b:
    kind: portcullis
  dungeon_secret_door1:
    kind: secret_door
  stairs:
    kind: stairs
    open_well: true       # spiral: hollow center, no newel
    wall_attached: true   # spiral: treads meet well walls
  my_altar:
    kind: gltf
    src: models/altar.glb   # served as /assets/models/altar.glb
    scale: 1
    y: 0
```

`cave` (aliases `cavern`, `grotto`, `limestone`) is **organic limestone**, not boxed stone: exposed wall faces are subdivided and displaced in world space (wider bases, overhangs, unique FBM per stretch), with stalactites, stalagmites, and occasional columns. The albedo is grainy limestone with mineral stains; a roughness map keeps most of the rock matte and adds smoother flowstone/calcite patches (plus wet seeps). Seed is fixed (`caveStone.js`). Do not point `albedo` at a photo unless you want to replace that look.

Per-map override (for example a cellar under a manor):

```yaml
vtt3d:
  walls:
    style: dungeon   # or cave | mansion | gothic | wood | office
```

Legend-only override:

```yaml
legend:
  "~":
    type: portcullis_b
    vtt3d:
      kind: portcullis
```

## Built-in door kinds

| kind | Mesh |
|---|---|
| `door` | Stone frame + hinged oak panel; adjacent same-edge neighbors auto-pair as a double door unless a wall splits them (`vtt3d.double: false` to skip) |
| `window` | Sill + frame + glass or shutter; casement swing when open; iron bars when barred; wall transom to full wall height |
| `secret_door` | Flush stone slab (looks like wall); slides up when open |
| `portcullis` | Rusted iron frame + spiked grate; raises when open |
| `wall` | Thin stone wall on the door edge (no opening) |
| `skip` | No 3D mesh |

Trapdoors are **not** wall doors (`TrapDoor` is skipped in `geometry.doors`). They are fixtures:

| kind | Mesh |
|---|---|
| `trap_door` | Wooden floor hatch + iron ring; chain/padlock if locked; open = hole + hinged lid |
| `secret_trapdoor` | Same hatch once discovered (undiscovered = omitted from `objects[]`) |
| `pit_trap` | Perceived: cracked cover; activated: hole + spikes; disarmed: hole |
| `chasm` | Open pit shaft (floor omitted); `bottomless_pit` uses the same mesh |
| `stairs` | Cosmetic steps along `squares` (base → top); auto double-wide / circular spiral wedges; `open_well` hollow shaft; `wall_attached` well walls; `height` in feet (default 8; negative = down); `style` matches walls/doors; `solid` (default true) fills under the treads |

`GET /map_state` `geometry.doors[]` includes `kind` and optional `model` (`src`, `scale`, …). Adjacent oak doors on the same wall edge are paired in the 3D client (optional `double: false` skips pairing). Hatch state is on `objects[]` (`opened`, `activated`, `disarmed`, `secret`). Stair runs add `squares`, `height`, and optional `style`. Stairs do not affect 2D movement or cover.

## Adding a new procedural kind

1. Infer or catalog-map the type in `natural20/web/vtt3d_catalog.py` only if the token is **generic** (e.g. `portcullis`, `trapdoor`).
2. Wall barriers: descriptor in `n20-webapp/client-3d/src/geometry.js` (see `portcullisAssemblies`, `windowAssemblies`) + mesh in `scene/barriers.js`, dispatch from `MapScene._buildWalls`.
3. Floor hatches and pits: classify in `vtt3d_catalog.py` / `fixtureKinds.js`, mesh in `scene/fixtures.js`, punch open cells via `hatchHoleCells` + `floorQuads` (`chasm` is always open).
4. Stairs: catalog `type: stairs` + `fixtureKinds.js` / `addStairs`; token height via `stairSurfaceY`; descending holes via `stairHoleCells` (keep hatch holes separate).
5. Tests: `tests/test_map_state.py` + `client-3d/src/geometry.test.js` (+ `fixtureKinds.test.js` for fixtures)
6. `cd n20-webapp/client-3d && npm test && npm run build`
7. Update `docs/VTT_3D.md`

## Custom glTF

Place the file under `user_levels/<campaign>/assets/` (or `assets/models/`). Set `src` in the catalog. The 3D client loads it with `GLTFLoader` at the object's cell center.
