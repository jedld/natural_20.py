---
name: natural20-import-battlemap
description: >-
  Import an existing D&D battlemap image (png/jpg/webp) into Natural20 map YAML
  via tile-wise VLM/heuristic classification. Prefer this whenever battlemap art
  is already provided (attached image, assets/maps, references/**/map-*, scanned
  floorplan, VTT underlay), including published pages with several floors on one
  sheet — do not invent ASCII from a whole-image glance, do not hand-crop a
  multi-floor page as the first step, and do not run the procedural dungeon
  generator. Use when converting battlemaps, adapting a source-book campaign, or
  building a map from an image plus adventure text.
argument-hint: "path/to/map.png [--adventure guide.md] [--split-panels|--no-split-panels]"
user-invocable: true
disable-model-invocation: false
---

# Natural20 — import a battlemap

Canonical agent instructions: [`.cursor/skills/n20-import-battlemap/SKILL.md`](../../../.cursor/skills/n20-import-battlemap/SKILL.md). Docs: [docs/BATTLEMAP_IMPORTER.md](../../../docs/BATTLEMAP_IMPORTER.md).

**If a battlemap image already exists, prefer this skill.** Do not eyeball-transcribe, do not invent a layout, and do not run `scripts/generate_dungeon.py`.

**Campaign conversion:** glob `assets/maps/*` and `references/**/map-*`, then import **each** image. Follow the cursor skill section **Campaign conversion (source-book maps)** — one published page often becomes several `maps/*.yml` keys (stairs + `game.yml` `maps:`).

**Multi-floor pages** (church + basement, coffin shop, Death House sheet): `--split-panels` (default) crops each floor, shares tile size, and writes `name_<slug>.yml`. Inspect `workdir/panels.json` and `workdir/panels/`. Do **not** pass `--width`/`--height` for the whole page (those apply per crop). Use `--no-split-panels` only when the file is already a single floor, or when re-importing a crop you already saved.

```bash
python scripts/import_battlemap.py path/to/map.png \
  --provider ollama --model llava \
  --adventure path/to/guide.md \
  --workdir /tmp/<id>_import \
  -o /tmp/<id>_import/map.yml

python scripts/compare_map_import.py \
  user_levels/<slug>/maps/gold.yml \
  /tmp/<id>_import/map.yml
```

Do not overwrite hand-authored `user_levels/<slug>/maps/*.yml` unless the user asks. Follow the cursor skill checklist for grid size, floorplan ink walls, `--calibrate-grid`, printed titles/compass/room keys (`overlays.json`), adventure overlay, copying **crops** (not the original page) to `assets/maps/`, registering every floor, wiring teleporters, and `validate_campaign.py`.
