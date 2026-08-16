---
name: n20-import-battlemap
description: >-
  Import an existing D&D battlemap image (png/jpg/webp) into Natural20 map YAML
  by slicing it tile-by-tile (VLM or heuristics), detecting thin ink walls,
  splitting multi-floor pages into separate maps, overlaying adventure-guide
  NPCs/notes/map_annotations, and comparing against gold YAML. Prefer this
  whenever the user already provided battlemap art, a scanned floorplan, a VTT
  background, or an image under assets/maps or references/ — including published
  pages with several floors on one sheet. Do not invent ASCII from a whole-image
  glance, do not hand-crop a multi-floor page as the first step, and do not run
  the procedural dungeon generator. Use when converting battlemaps, adapting a
  source-book campaign, or building a map from an image plus adventure text.
---

# Natural20 — import a battlemap

**If a battlemap image already exists, use this skill.** Do not transcribe the
art by eye, do not invent a layout from a whole-image LLM glance, and do not
run `scripts/generate_dungeon.py`.

Read [docs/BATTLEMAP_IMPORTER.md](../../../docs/BATTLEMAP_IMPORTER.md) for flags,
taxonomy, floorplan vs filled walls, multi-floor splits, and workdir layout.

## Prefer this first

Use the importer when **any** of these are true:

- The user attached or named a map image (`png` / `jpg` / `jpeg` / `webp`)
- The campaign already has art under `user_levels/<slug>/assets/maps/`
- Adventure notes include a floorplan (`user_levels/<slug>/references/**/map-*`)
- The page shows **several floors on one image** (church + basement, 2×2 house
  floors + dungeon, ground/upper shop)
- The user says to use an existing map, VTT underlay, or scanned dungeon

Skip the importer only when there is **no source image** and the user wants a
procedural or hand-authored layout (then `.github/skills/natural20-dungeon-generator`).

Do **not** overwrite hand-authored campaign YAML (`user_levels/<slug>/maps/*.yml`)
unless the user explicitly asks. Write first drafts to `--workdir` / `/tmp/` and
compare.

## Campaign conversion (source-book maps)

When scaffolding or adapting a campaign from published maps, **import every
battlemap image** instead of drawing ASCII. Follow this loop per image:

1. Find art: `assets/maps/*` and `references/**/map-*.{jpg,png,jpeg,webp}`.
2. Run the importer with `--split-panels` (default **on**). Do **not**
   ImageMagick/PIL-crop the page by eye as the first step, and do not transcribe
   the whole sheet into YAML.
3. If panel count is unknown, stop after slice and inspect:
   - `workdir/panels.json`
   - `workdir/panels/*.png`
   - stdout `panel_count` / `maps[]`
4. **`--width` / `--height` apply per crop**, not to the full page. Omit them on
   a multi-floor sheet (auto-detect + shared tile size). Pass `--tile-size` only
   when you have measured one square on a crop. Use `--width`/`--height` after
   `--no-split-panels` on a **single** floor, or when gold YAML already has size.
5. `panel_count > 1` means **N campaign maps** from one file. Rename slugs from
   the adventure (e.g. `ground_floor`, `basement`, `first_floor`, `attic`,
   `dungeon`) — heuristic labels are `left`/`right` or `panel_1`…`panel_n`.
   A vision provider can attach labels (`Ground Floor`, `Basement`, …).
6. Front-view elevations and title art are dropped automatically. Keep the
   playable floor plans.
7. Copy **each crop** (not the original page) to `assets/maps/<id>.png` and set
   that file as `background_image` on the corresponding YAML.
8. Register **every** floor in `game.yml` `maps:` and `index.json` `other_maps`.
   Link stairs with `teleporter` objects (`target_map` + `target_position`);
   importer `needs_wiring` lists stair tiles until destinations exist. See
   [docs/CAMPAIGN_BUILDING.md](../../../docs/CAMPAIGN_BUILDING.md) → Linking Maps.
9. Pass `--adventure` / `--adventure-text` for the matching chapter. Overlay
   runs per crop under `workdir/<slug>/`. Resume with
   `--resume --phase refine --workdir <same>`.
10. If CV **over-splits**, re-run `--no-split-panels` or import only the good
    files in `workdir/panels/`. If it **under-splits** (one panel but the page
    clearly has several floors), save manual crops of those floors and import
    each with `--no-split-panels` — still do not invent ASCII.

Do not treat a multi-floor page as a single `maps/*.yml`. Players need one map
key per floor so stairs and fog work.

## Checklist

```text
- [ ] Source image identified (do not invent a substitute layout)
- [ ] Multi-floor page? leave --split-panels on; inspect workdir/panels/
- [ ] Do not pass --width/--height for the whole multi-floor page
- [ ] Grid: --tile-size, filename like map_22x17.png, gold YAML, or auto-detect
- [ ] python scripts/import_battlemap.py IMAGE --workdir <dir> --provider ...
- [ ] Inspect workdir/ascii.txt (or each workdir/<slug>/ascii.txt) vs the crop
- [ ] Pass --adventure / --adventure-text and --resume --phase refine if needed
- [ ] Inspect overlays.json — titles/compass/keys must not be walls; keys match E5a / Area B headings
- [ ] Floorplan walls are `┌┬┐├┤└┘HZ` (thin directional), not solid `#` outlines that seal halls
- [ ] Per-tile VLM second opinion ran (not heuristic-only) when a vision model is available
- [ ] Refine listed every square against keyed adventure regions (E5a / Area B …)
- [ ] If gold YAML exists, compare — do not overwrite gold:
      python scripts/compare_map_import.py gold.yml generated.yml
- [ ] Copy each crop to assets/maps/<id>.png; set background_image
- [ ] Write YAML into user_levels/<campaign>/maps/<id>.yml only when the user wants that path
- [ ] Register every floor in game.yml maps: and index.json other_maps
- [ ] Wire stairs/teleporters between floors (report needs_wiring)
- [ ] python scripts/validate_campaign.py user_levels/<campaign>
```

## Command

```bash
python scripts/import_battlemap.py --print-schema

# Single floor (size known)
python scripts/import_battlemap.py path/to/map.png \
  --width W --height H \
  --provider ollama --model llava \
  --adventure path/to/guide.md \
  --campaign user_levels/<slug> --map-id <id> \
  --workdir /tmp/<id>_import \
  --name "Map Name" \
  -o /tmp/<id>_import/map.yml

# Multi-floor published page (do not pass --width/--height)
python scripts/import_battlemap.py path/to/map-church.jpg \
  --provider ollama --model llava \
  --adventure path/to/chapter.md \
  --workdir /tmp/church_import \
  --name "Church" \
  -o /tmp/church_import/church.yml
# → church_left.yml / church_right.yml (or labeled slugs) plus workdir/panels/
```

Providers: `heuristic` (no network, smoke test), `mock` (tests), `ollama`, `openai`, `anthropic`. Prefer a vision model when art is a published floorplan or when floors need labels.

Floorplans (thin **ink on cell edges**, not filled masonry): the importer scores N/E/S/W edges, exports `stone_wall_*` directional tokens, and keeps doors in an ink gap. `--calibrate-grid` (default) nudges `image_offset_px` onto dark grid lines; `--no-calibrate-grid` when the offset is already known (e.g. gold `image_offset_px`).

After the cheap occupancy/heuristic pass, run a vision provider so **every tile** gets a VLM second opinion, then `--phase refine` so the LLM checks each square against the keyed adventure region (`E5a. Hall`, …). Resume with `--seed-map` pointing at the first-pass YAML.

Printed **titles, compass roses, and circled room keys** are detected before classify and masked so they are not walls. Keys (`a`, `b`, `c`, …) become `map_annotations` and are matched to adventure headings (`#### E5a. Hall`). Place NPCs and objects from that keyed text, not by guessing a random floor tile.

Crops from one page share a tile size so floors printed at the same scale stay aligned. Each crop still gets its own `image_offset_px`. Use `--no-split-panels` only when the file is already a single map.

```bash
python scripts/compare_map_import.py \
  user_levels/<slug>/maps/gold.yml \
  /tmp/<id>_import/map.yml
```

Resume:

```bash
python scripts/import_battlemap.py IMAGE --resume --workdir /tmp/<id>_import --phase refine --adventure guide.md
```

Stdout is a JSON report. Single map: `ascii`, `reachable_ratio`, `needs_wiring`, `output_yaml`. Multi-floor bundle: `panel_count`, `panels`, `maps[]`, `output_yaml[]`. Tiles live in `workdir/tiles/` (or `workdir/<slug>/tiles/`).

## After the script

- Prefer `ascii.txt` + `classifications.json` over re-guessing walls.
- Furniture without an SRD object becomes `type: barrel` with a readable name — replace if the campaign defines tables/beds.
- Stairs are notes plus `needs_wiring`; add a `teleporter` only when `game.yml` has the destination map.
- NPC `sub_type` must exist under `npcs/` or `templates/npcs/`.
- Do not commit copyrighted adventure prose; keep guide files out of the repo unless the user already stored them in the campaign.

## Related

- Map YAML: [docs/CAMPAIGN_BUILDING.md](../../../docs/CAMPAIGN_BUILDING.md)
- Landmarks: [docs/MAP_ANNOTATIONS.md](../../../docs/MAP_ANNOTATIONS.md)
- Inverse (YAML → image): [docs/MAP_IMAGE_GENERATOR.md](../../../docs/MAP_IMAGE_GENERATOR.md)
- Procedural maps (**no** source art): [docs/DUNGEON_GENERATOR.md](../../../docs/DUNGEON_GENERATOR.md)
- Campaign scaffold: [`.github/skills/natural20-campaign-builder/SKILL.md`](../../../.github/skills/natural20-campaign-builder/SKILL.md)
