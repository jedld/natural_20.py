# Battlemap Importer

Turn a **battlemap image** into playable Natural20 map YAML by reading the art
**tile by tile**, not by asking an LLM to invent a layout from the whole picture.

**Prefer this path whenever an existing battlemap is already provided.** Agents:
`.cursor/skills/n20-import-battlemap/SKILL.md`. Do not use the procedural dungeon
generator, and do not transcribe the image by eye.

Humans and agents use the same CLI: `scripts/import_battlemap.py`.

## Why this exists

Whole-image VLM/LLM layout is unreliable: walls drift, doors float, rooms
distort. This pipeline:

1. Detects multi-floor pages and crops each floor; then determines grid size
   (flags, filename like `tavern_22x17.png`, `--tile-size`, or auto-detect).
2. Slices the image into tiles (with neighbor padding / a 3×3 mosaic).
3. Classifies each tile (heuristic priors + optional VLM) and **keeps an identification log**.
4. Uses neighbor relationships to catch isolated walls, doors without walls, etc.
5. Cross-references adventure-guide text to place NPCs, notes, objects, and `map_annotations`.
6. Runs a final LLM pass over the ASCII map + adventure text + YAML excerpt.

## Quick start

```bash
# Schema for agent tool calling
python scripts/import_battlemap.py --print-schema

# No network — PIL heuristics only (smoke test / CI)
python scripts/import_battlemap.py path/to/tavern_22x17.png \
  --provider heuristic \
  --name "The Weary Candle" \
  --workdir /tmp/tavern_import \
  -o user_levels/my_campaign/maps/tavern.yml

# Local vision model (Ollama)
python scripts/import_battlemap.py path/to/tavern.png \
  --width 40 --height 30 \
  --provider ollama --model llava \
  --adventure path/to/room_text.md \
  --campaign user_levels/my_campaign --map-id tavern \
  --workdir /tmp/tavern_import \
  -o user_levels/my_campaign/maps/tavern.yml
```

Then register **each** map in `game.yml` `maps:` and `index.json` `other_maps`, copy
**crops** (for multi-floor pages, each file under `--workdir/panels/`) to
`assets/maps/`, and run:

```bash
python scripts/validate_campaign.py user_levels/my_campaign
```

## Python API

```python
from natural20.map_import import ImportKnobs, import_battlemap

result = import_battlemap(
    ImportKnobs(
        image="assets/maps/tavern_22x17.png",
        provider="ollama",
        model="llava",
        name="Tavern",
        adventure_files=["notes/tavern.md"],
    ),
    workdir="/tmp/tavern_import",
    output="maps/tavern.yml",
)
print(result.grid.ascii_map())
print(result.to_dict())
```

## Phases

| Phase | What it does | Checkpoint in `--workdir` |
|-------|----------------|---------------------------|
| `slice` | Infer grid, crop tiles + padded tiles | `slice.json`, `tiles/x_y.png`, `tiles/padded/` |
| `classify` | Heuristic/occupancy first, then per-tile VLM second opinion | `classifications.json`, `ascii.txt`, `uncertain.json`, `vlm_second_opinion.json` |
| `consistency` | Deterministic neighbor rules, then optional LLM review of ASCII + uncertain tiles | `consistency.json` |
| `adventure` | Place NPCs / objects / notes / `map_annotations` from guide text | `adventure.json` |
| `refine` | Per-square LLM verify with keyed adventure region context, then a global leftover pass | `refine.json` |
| `export` | Write Natural20 map YAML | `map.yml`, `report.json` |

```bash
# Classify only, inspect ascii.txt, then continue
python scripts/import_battlemap.py IMAGE --phase classify --workdir /tmp/m --provider ollama --model llava
python scripts/import_battlemap.py IMAGE --resume --phase refine --workdir /tmp/m --adventure notes.md
```

`--resume` skips phases that already have checkpoints, except the requested `--phase`.

## Grid size

Resolution order:

1. `--width` and `--height` (applied **per cropped panel** after a multi-floor split)
2. `--tile-size` (pixels per square; width/height = image size ÷ tile size)
3. Filename patterns: `tavern_22x17.png`, `Map-40x30-grid.webp`
4. **Auto-detect** from grid-line autocorrelation + offset calibration

`--offset x,y` crops from that pixel origin before slicing (`image_offset_px` in YAML).

By default `--calibrate-grid` nudges that offset (not tile size) so predicted grid
lines sit on dark ink. Use `--no-calibrate-grid` for filled-cell dungeon art or
when the offset is already known (Death House basements use `image_offset_px`).

## Multiple floors on one page

Published adventure maps often put several floor plans on a single image
(side-by-side church/basement, stacked house floors, a 2×2 of storeys plus a
dungeon). By default `--split-panels` (on) detects this **before** tile
classification:

1. Classical CV (min-pool downsample + thin ink gutters) finds two-up pages
   (church, coffin-maker shop) and nested frames (Death House 2×2 floors + dungeon).
2. Crops without a detectable square grid (front-view illustrations) are dropped.
3. Optional VLM labels each crop (`Ground Floor`, `Basement`, …) and can add a
   panel the CV pass missed.
4. Each crop gets its **own** grid origin; tile size is shared across panels
   from the same page so floors printed at the same scale stay aligned.

Crops land in `--workdir/panels/`. YAML paths gain a slug suffix
(`tavern_left.yml`, `tavern_right.yml`). Use `--no-split-panels` when the file
is already a single floor.

Campaign conversion (register every floor, copy crops, wire stairs):
`.cursor/skills/n20-import-battlemap/SKILL.md` → **Campaign conversion**.

```bash
python scripts/import_battlemap.py \
  user_levels/death_house/references/chapter_5/map-05.05-coffin-makers-shop.png \
  --provider heuristic \
  --workdir /tmp/coffin_import \
  -o /tmp/coffin_import/coffin.yml
```

## Floorplans vs filled walls

Published adventure floorplans (thin **ink lines on cell edges**, walkable floor
filling the rest of the square) are not the same as VTT maps that paint whole
cells as masonry.

The importer:

1. Scores N/E/S/W ink on each tile (`natural20/map_import/ink.py`) versus an
   inset strip so wood grain is not a wall.
2. Treats a thin edge line as `class=wall` even when most of the square is floor art.
3. Exports directional `stone_wall_*` tokens (`┌┬┐├┤└┘`, `H`, `Z`) on the **base**
   layer with a legend entry. Solid filled masonry still becomes `#`.
   One-cell `#` *outlines* from a filled-cell occupancy pass (watercolor color
   classify, leftover solid walls) are converted to those same tokens by
   `natural20/map_import/thin_wall.py` so halls stay walkable. A one-cell `#`
   *between two floor rooms* is opened as a `-`/`|` door (printed floorplans
   often omit door glyphs). Thick blobs and the map frame stay `#`.
4. Detects a gap in an ink edge as a door (`-`/`|`, or `corner_door_*` when the
   door sits on a corner). Consistency no longer drops doors just because the
   neighboring *cell* is not a solid `#`.

The VLM prompt asks for `"walls": {N,E,S,W}` and `"doors": {...}` and merges those
with the CV prior. Adventure/refine JSON uses a 2048-token cap and truncated-JSON
repair so Ollama `num_predict` does not silently discard the overlay.

## Printed labels, compasses, and room keys

Published maps print cartography **on top of** the floorplan: titles ("Ground
Floor", "Basement", "Church"), compass roses, scale bars, and circled room keys
(`a`–`g`). Those ink strokes look like thin walls. Before tile classify, the
importer (`natural20/map_import/overlays.py`):

1. Finds circled keys (white disc + letter, or a warm drop-shadow ring) and reads
   the letter with template matching.
2. Finds compass roses (radial ink that is not a corner frame ornament).
3. Clusters letter-sized dark glyphs into titles/captions/scale text.
4. Forces those tiles to floor/void and clears ink-edge walls (`overlay:key` in
   `classifications.json`).
5. Writes `overlays.json`. Printed keys become `map_annotations` (room flood-fill
   bounds) and are matched to adventure headings like `#### E5a. Hall`.

Heuristic imports still place NPCs/objects from keyed headings (`**acolyte**`,
`**vampire spawn**`, chest, trapdoor, altar, bed, …) inside the matching room.

## Providers

| `--provider` | Behavior |
|--------------|----------|
| `heuristic` | PIL brightness/edges/color priors only. Default. No network. |
| `mock` | Deterministic stand-in for tests (uses the heuristic line in the prompt). |
| `ollama` | `/api/chat` with `images: [base64]`. Model from `--model` / `MAP_IMPORT_VLM_MODEL` / `OLLAMA_MODEL` (default `llava`). |
| `openai` | Chat completions with `image_url`. Needs `OPENAI_API_KEY`. Default model `gpt-4o-mini`. |
| `anthropic` | Messages API with base64 image. Needs `ANTHROPIC_API_KEY`. |

`--skip-vlm` forces `heuristic`. Classification always runs a cheap heuristic/occupancy
first pass, then a **per-tile VLM second opinion** (3×3 mosaic, center outlined in red)
when `--provider` is a vision backend. Pass `--seed-map path.yml` to load an existing
`map.base` occupancy layer as that first pass. After adventure overlay, refine lists
**every square** in each keyed region (E5a, E5b, …) with that region's adventure excerpt
so the LLM can confirm or fix the tile.

Env overrides: `MAP_IMPORT_VLM_PROVIDER` is not required (use `--provider`). `MAP_IMPORT_VLM_MODEL`, `MAP_IMPORT_VLM_BASE_URL`, `MAP_IMPORT_VLM_API_KEY`.

## Tile taxonomy → Natural20

| Class / subtype | Map token | Object type |
|-----------------|-----------|-------------|
| wall (solid fill), column | `#` | — |
| wall (thin ink on edges) | `┌┬┐├┤└┘HZ` | `stone_wall_tl` … `stone_wall_lr` (legend on base) |
| floor | `.` | — |
| void (outside the playable art) | `_` | — |
| water | `.` + `w` on `base_1` | `water` |
| door | `-` or `\|` | wooden door (hard-coded base tokens) |
| corner door | `╒╗╚╝` | `corner_door_tl` … `corner_door_br` |
| chest, barrel, tree, window, switch, note, pit, chasm, campfire, brazier | object layer | matching `templates/items/objects.yml` key |
| table, chair, bed, bookshelf, statue, altar | object layer | `barrel` with a readable `name` (half cover; no dedicated SRD furniture object) |
| stairs | object layer | `note` plus `needs_wiring` in the report — add a `teleporter` once the destination map exists |
| fireplace | object layer | `campfire` (core templates; campaigns may override with a `fireplace` object) |

Every tile is stored in `classifications.json` (`class`, `subtype`, `confidence`,
`description`, `source`, `edges`, neighbor-driven `flags`) so later passes can see
*why* a square was labeled.

## Compare against a gold map

When evaluating an import against a hand-authored YAML (do **not** overwrite
campaign maps), write the importer output elsewhere and run:

```bash
python scripts/compare_map_import.py \
  user_levels/<campaign>/maps/gold.yml \
  /tmp/n20_import/generated.yml
```

Reports wall IoU, occupancy IoU, and door recall using legend types so directional
stone walls count as walls.

## Adventure overlay

Pass `--adventure path.md` (repeatable) and/or `--adventure-text "..."`. The model
receives the ASCII map, **printed room keys**, and the text and may add:

- NPCs (`legend` + `map.entities`, `type: npc`)
- objects / notes
- `map_annotations` areas for NPC navigation (see [MAP_ANNOTATIONS.md](MAP_ANNOTATIONS.md))
- tile `fixes` when the text contradicts the transcription

NPC `sub_type` should be a real template slug (`goblin`, `human_guard`, …). Object
`type` must exist in `templates/items/objects.yml` or the campaign will fail
`validate_campaign.py`.

## Agent / human workdir

`--workdir` is the inspectable paper trail:

```
workdir/
  tiles/0_0.png          # exact cell
  tiles/padded/0_0.png   # cell + neighbors
  ascii.txt              # current transcription
  classifications.json   # full identification log
  consistency.json
  overlays.json          # titles, compass, circled keys (not walls)
  adventure.json
  refine.json
  map.yml                # latest YAML
  report.json            # machine-readable summary
```

CLI always prints `report.json` on stdout (also `--json`). Fields include `ascii`,
`reachable_ratio`, `needs_wiring`, `adventure`, `refine`, `output_yaml`.

## After import

1. Open `ascii.txt` and the YAML side by side with the source image.
2. Wire stairs (`needs_wiring`) to `teleporter` + `game.yml` map keys.
3. Replace furniture `barrel` stand-ins with campaign objects if you have them.
4. Copy the battlemap into `assets/maps/` if it is not already there; YAML
   `background_image` defaults to the source filename.
5. Register the map; validate; optionally render a debug overlay with
   `scripts/render_map_image.py` (this importer is the **inverse** of that tool).

## Tests

```bash
pytest tests/test_map_import.py -q
```

Tests use synthetic PNGs and `heuristic` / `mock` providers — they do not call a live VLM.
