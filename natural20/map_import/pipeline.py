"""Battlemap import pipeline: slice → classify → consistency → adventure → refine → export."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from PIL import Image

from natural20.map_import.adventure import apply_adventure_overlay, load_adventure_text, parse_keyed_areas
from natural20.map_import.checkpoint import Workdir
from natural20.map_import.classify import classify_tiles
from natural20.map_import.consistency import apply_consistency_rules, flood_floor, llm_consistency_review
from natural20.map_import.dimensions import GridSpec, infer_grid_spec
from natural20.map_import.export import grid_to_map_properties, write_map_yaml
from natural20.map_import.ink import calibrate_grid_spec
from natural20.map_import.knobs import ImportKnobs, PHASES
from natural20.map_import.model import ClassificationGrid
from natural20.map_import.overlays import OverlayReport, apply_overlay_mask, detect_overlays
from natural20.map_import.panels import MapPanel, crop_panel, detect_map_panels
from natural20.map_import.refine import refine_map
from natural20.map_import.seed import seed_grid_from_map_yaml, seed_map_properties
from natural20.map_import.slicer import slice_tiles
from natural20.map_import.vlm import build_client


@dataclass
class ImportResult:
    knobs: ImportKnobs
    spec: GridSpec
    grid: ClassificationGrid
    properties: dict[str, Any]
    workdir: Path
    phases_run: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    consistency_fixes: list[dict[str, Any]] = field(default_factory=list)
    adventure_report: dict[str, Any] = field(default_factory=dict)
    refine_report: dict[str, Any] = field(default_factory=dict)
    overlay_report: dict[str, Any] = field(default_factory=dict)
    reachable_ratio: float = 0.0
    output_yaml: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "map_id": self.knobs.map_id or _slug(self.knobs.name),
            "name": self.knobs.name,
            "grid": self.spec.to_dict(),
            "phases_run": self.phases_run,
            "messages": self.messages,
            "reachable_ratio": round(self.reachable_ratio, 4),
            "consistency_fixes": len(self.consistency_fixes),
            "adventure": self.adventure_report,
            "refine": self.refine_report,
            "overlays": self.overlay_report,
            "workdir": str(self.workdir),
            "output_yaml": self.output_yaml,
            "ascii": self.grid.ascii_map(),
            "needs_wiring": (self.properties.get("_importer") or {}).get("needs_wiring") or [],
            "spawn": (self.properties.get("player_spawn_points") or [{}])[0].get("position"),
        }


@dataclass
class ImportBundle:
    """Multi-floor page: one ImportResult per cropped panel."""

    source_image: str
    panels: list[MapPanel]
    results: list[ImportResult]
    workdir: Path
    messages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_image": self.source_image,
            "panel_count": len(self.results),
            "panels": [panel.to_dict() for panel in self.panels],
            "maps": [result.to_dict() for result in self.results],
            "workdir": str(self.workdir),
            "messages": self.messages,
            "output_yaml": [result.output_yaml for result in self.results],
        }


def import_battlemap(
    knobs: ImportKnobs,
    *,
    workdir: str | Path | None = None,
    stop_after: str = "all",
    resume: bool = False,
    output: str | Path | None = None,
) -> ImportResult | ImportBundle:
    image_path = Path(knobs.image).expanduser().resolve()
    if not image_path.is_file():
        raise FileNotFoundError(f"Battlemap image not found: {image_path}")

    dest = Path(workdir) if workdir else image_path.parent / f".n20_import_{image_path.stem}"
    if knobs.split_panels:
        page = Image.open(image_path).convert("RGB")
        client = build_client(knobs)
        panels = detect_map_panels(page, client=client, split=True)
        store = Workdir(dest)
        store.write_json("panels.json", {"panels": [panel.to_dict() for panel in panels]})
        if len(panels) > 1:
            return _import_panels(
                knobs,
                image_path,
                page,
                panels,
                dest,
                stop_after=stop_after,
                resume=resume,
                output=output,
            )
    return _import_single(
        knobs,
        workdir=dest,
        stop_after=stop_after,
        resume=resume,
        output=output,
    )


def _import_panels(
    knobs: ImportKnobs,
    image_path: Path,
    page: Image.Image,
    panels: list[MapPanel],
    dest: Path,
    *,
    stop_after: str,
    resume: bool,
    output: str | Path | None,
) -> ImportBundle:
    panel_dir = dest / "panels"
    panel_dir.mkdir(parents=True, exist_ok=True)
    results: list[ImportResult] = []
    messages = [f"split {len(panels)} panels from {image_path.name}"]
    base_id = knobs.map_id or _slug(knobs.name)
    crops: list[tuple[MapPanel, Image.Image, Path]] = []
    for panel in panels:
        crop = crop_panel(page, panel)
        crop_path = panel_dir / f"{panel.index:02d}_{panel.slug}.png"
        crop.save(crop_path)
        crops.append((panel, crop, crop_path))
    shared_tile = knobs.tile_size or _shared_tile_size([crop for _, crop, _ in crops])
    if shared_tile:
        messages.append(f"shared tile size {shared_tile}px across {len(crops)} panels")
    for panel, _crop, crop_path in crops:
        child = replace(
            knobs,
            image=str(crop_path),
            name=_panel_name(knobs.name, panel.label),
            map_id=f"{base_id}_{panel.slug}" if base_id else panel.slug,
            background_image=crop_path.name,
            split_panels=False,
            tile_size=shared_tile or knobs.tile_size,
            width=None if shared_tile and not knobs.width else knobs.width,
            height=None if shared_tile and not knobs.height else knobs.height,
        )
        child_out = _panel_output_path(output, panel, child, count=len(panels))
        result = _import_single(
            child,
            workdir=dest / panel.slug,
            stop_after=stop_after,
            resume=resume,
            output=child_out,
        )
        result.messages.insert(0, f"panel {panel.slug} box={list(panel.box)}")
        results.append(result)
        messages.append(f"{panel.slug}: grid {result.spec.width}x{result.spec.height} from {result.spec.source}")
    return ImportBundle(
        source_image=str(image_path),
        panels=panels,
        results=results,
        workdir=dest,
        messages=messages,
    )


def _shared_tile_size(images: list[Image.Image]) -> int | None:
    """One pixel-per-square for every crop from the same printed page."""
    from natural20.map_import.grid_detect import detect_grid_spec

    periods: list[float] = []
    for image in images:
        spec = detect_grid_spec(image, calibrate=False)
        if spec is None:
            continue
        period = (spec.tile_w + spec.tile_h) / 2.0
        if 12 <= period <= 160:
            periods.append(period)
    if not periods:
        return None
    lifted: list[float] = []
    for period in periods:
        best = period
        for other in periods:
            for harmonic in (2, 3, 4):
                if abs(other - period * harmonic) / max(other, 1.0) < 0.14:
                    best = max(best, other)
        lifted.append(best)
    lifted.sort()
    mid = lifted[len(lifted) // 2]
    return max(8, int(round(mid)))


def _panel_name(base: str, label: str) -> str:
    if not base or base == "Imported Map":
        return label
    if label.lower() in {"map", "panel"}:
        return base
    return f"{base} — {label}"


def _panel_output_path(
    output: str | Path | None,
    panel: MapPanel,
    knobs: ImportKnobs,
    *,
    count: int,
) -> Path | None:
    if output:
        dest = Path(output)
        if dest.suffix.lower() in {".yml", ".yaml"}:
            if count == 1:
                return dest
            return dest.with_name(f"{dest.stem}_{panel.slug}{dest.suffix}")
        dest.mkdir(parents=True, exist_ok=True)
        return dest / f"{panel.slug}.yml"
    if knobs.campaign and knobs.map_id:
        return Path(knobs.campaign) / "maps" / f"{knobs.map_id}.yml"
    return None


def _import_single(
    knobs: ImportKnobs,
    *,
    workdir: str | Path | None = None,
    stop_after: str = "all",
    resume: bool = False,
    output: str | Path | None = None,
) -> ImportResult:
    image_path = Path(knobs.image).expanduser().resolve()
    if not image_path.is_file():
        raise FileNotFoundError(f"Battlemap image not found: {image_path}")

    dest = Path(workdir) if workdir else image_path.parent / f".n20_import_{image_path.stem}"
    store = Workdir(dest)
    store.save_knobs(knobs)
    store.copy_image(image_path)

    spec = infer_grid_spec(
        image_path,
        width=knobs.width,
        height=knobs.height,
        tile_size=knobs.tile_size,
        offset_px=knobs.image_offset_px or (0, 0),
    )
    image = Image.open(image_path).convert("RGB")
    extra_messages: list[str] = []
    if knobs.calibrate_grid:
        before = (spec.offset_x, spec.offset_y)
        spec = calibrate_grid_spec(image, spec)
        knobs.image_offset_px = [spec.offset_x, spec.offset_y]
        if (spec.offset_x, spec.offset_y) != before:
            extra_messages.append(
                f"calibrated offset {before[0]},{before[1]} -> {spec.offset_x},{spec.offset_y}"
            )
    store.save_grid_spec(spec)
    store.write_json("slice.json", {"tiles": spec.width * spec.height, "spec": spec.to_dict()})

    slice_tiles(image_path, spec, dest_dir=store.path / "tiles", pad_ratio=knobs.pad_ratio)

    grid = store.load_grid() if resume else None
    if grid is None or grid.width != spec.width or grid.height != spec.height:
        grid = ClassificationGrid(spec.width, spec.height)
    if knobs.seed_map and all(tile.source == "unclassified" for row in grid.tiles for tile in row):
        seeded = seed_grid_from_map_yaml(grid, knobs.seed_map)
        extra_messages.append(f"seeded {seeded} tiles from {knobs.seed_map}")

    client = build_client(knobs)
    adventure_text = load_adventure_text(knobs.adventure_text, knobs.adventure_files)
    phases = _phases_to_run(stop_after)
    terminal = phases[-1] if phases else "export"
    result = ImportResult(
        knobs=knobs,
        spec=spec,
        grid=grid,
        properties={},
        workdir=store.path,
        messages=[f"grid {spec.width}x{spec.height} from {spec.source}", f"vlm={client.name}", *extra_messages],
    )
    result.phases_run.append("slice")

    keyed = parse_keyed_areas(adventure_text)
    prefer_letters = {area.letter for area in keyed if area.letter}
    overlays = OverlayReport()
    if resume:
        saved_overlays = store.read_json("overlays.json")
        if saved_overlays:
            overlays = OverlayReport.from_dict(saved_overlays)
    if not overlays.marks:
        overlays = detect_overlays(image, spec, prefer_letters=prefer_letters)
        store.write_json("overlays.json", overlays.to_dict())
    result.overlay_report = overlays.to_dict()
    if overlays.marks:
        result.messages.append(
            "overlays: "
            + ", ".join(f"{m.kind}:{m.text or 'ink'}" for m in overlays.marks[:12])
        )

    if "classify" in phases and not _skip_completed(resume, store, "classify", terminal):
        classify_tiles(
            image,
            spec,
            grid,
            client,
            pad_ratio=knobs.pad_ratio,
            confidence_threshold=knobs.confidence_threshold,
            include_mosaic=knobs.include_mosaic,
            max_tiles=knobs.max_tiles,
            workdir=store.path,
            overlays=overlays,
        )
        apply_overlay_mask(grid, overlays)
        store.save_grid(grid)
        result.phases_run.append("classify")
    elif "classify" in phases:
        result.messages.append("resume: skipped classify")

    if "consistency" in phases and not _skip_completed(resume, store, "consistency", terminal):
        rule_fixes = apply_consistency_rules(grid)
        overlay_fixes = apply_overlay_mask(grid, overlays)
        llm_fixes = llm_consistency_review(grid, client, threshold=knobs.confidence_threshold)
        apply_overlay_mask(grid, overlays)
        result.consistency_fixes = rule_fixes + overlay_fixes + llm_fixes
        store.write_json("consistency.json", {"fixes": result.consistency_fixes})
        store.save_grid(grid)
        result.phases_run.append("consistency")
    elif "consistency" in phases:
        result.messages.append("resume: skipped consistency")

    reachable = flood_floor(grid)
    floors = [
        (x, y)
        for y in range(grid.height)
        for x in range(grid.width)
        if grid.tiles[x][y].tile_class in {"floor", "door", "water", "object"}
    ]
    result.reachable_ratio = (len(reachable) / len(floors)) if floors else 0.0

    bg = knobs.background_image or image_path.name
    properties = grid_to_map_properties(
        grid,
        name=knobs.name,
        description=knobs.description,
        illumination=knobs.illumination,
        background_image=bg,
        image_offset_px=list(knobs.image_offset_px or [0, 0]),
    )
    result.properties = properties
    if knobs.seed_map:
        seeded_props = seed_map_properties(knobs.seed_map)
        anns = (seeded_props or {}).get("map_annotations") or []
        if anns:
            properties["map_annotations"] = list(anns)
            result.messages.append(f"seeded {len(anns)} map_annotations from {knobs.seed_map}")
    if resume:
        saved = store.read_json("map.json")
        if isinstance(saved, dict):
            properties.setdefault("map", {}).setdefault("entities", [])
            seen = {(tuple(e.get("pos") or []), e.get("token")) for e in properties["map"]["entities"]}
            for ent in saved.get("map", {}).get("entities") or []:
                key = (tuple(ent.get("pos") or []), ent.get("token"))
                if key not in seen:
                    properties["map"]["entities"].append(ent)
            properties.setdefault("legend", {}).update(saved.get("legend") or {})
            if saved.get("map_annotations") and not properties.get("map_annotations"):
                properties["map_annotations"] = list(saved["map_annotations"])
            if saved.get("player_spawn_points"):
                properties["player_spawn_points"] = saved["player_spawn_points"]
            result.properties = properties

    if "adventure" in phases and adventure_text and not _skip_completed(resume, store, "adventure", terminal):
        result.adventure_report = apply_adventure_overlay(
            grid, properties, adventure_text, client, overlays=overlays
        )
        # Rebuild base layers after tile fixes, keeping overlay entities.
        overlay_entities = list(properties.get("map", {}).get("entities") or [])
        overlay_legend = dict(properties.get("legend") or {})
        overlay_ann = list(properties.get("map_annotations") or [])
        spawn = None
        pts = properties.get("player_spawn_points") or []
        if pts and pts[0].get("position"):
            spawn = tuple(pts[0]["position"])
        properties = grid_to_map_properties(
            grid,
            name=knobs.name,
            description=knobs.description or properties.get("description", ""),
            illumination=knobs.illumination,
            background_image=bg,
            image_offset_px=list(knobs.image_offset_px or [0, 0]),
            spawn=spawn,  # type: ignore[arg-type]
            extra_entities=overlay_entities,
            extra_legend=overlay_legend,
            map_annotations=overlay_ann,
            needs_wiring=(properties.get("_importer") or {}).get("needs_wiring"),
        )
        result.properties = properties
        store.write_json("adventure.json", result.adventure_report)
        store.save_grid(grid)
        result.phases_run.append("adventure")
    elif "adventure" in phases:
        if _skip_completed(resume, store, "adventure", terminal):
            result.adventure_report = store.read_json("adventure.json") or {"skipped": "resume"}
            result.messages.append("resume: skipped adventure")
        else:
            result.adventure_report = {"skipped": "no adventure text"}
            result.phases_run.append("adventure")

    if "refine" in phases and not _skip_completed(resume, store, "refine", terminal):
        result.refine_report = refine_map(grid, properties, adventure_text, client, overlays=overlays)
        overlay_entities = list(properties.get("map", {}).get("entities") or [])
        overlay_legend = dict(properties.get("legend") or {})
        overlay_ann = list(properties.get("map_annotations") or [])
        spawn = None
        pts = properties.get("player_spawn_points") or []
        if pts and pts[0].get("position"):
            spawn = tuple(pts[0]["position"])
        properties = grid_to_map_properties(
            grid,
            name=knobs.name,
            description=properties.get("description") or knobs.description,
            illumination=knobs.illumination,
            background_image=bg,
            image_offset_px=list(knobs.image_offset_px or [0, 0]),
            spawn=spawn,  # type: ignore[arg-type]
            extra_entities=overlay_entities,
            extra_legend=overlay_legend,
            map_annotations=overlay_ann,
            needs_wiring=(properties.get("_importer") or {}).get("needs_wiring"),
        )
        result.properties = properties
        store.write_json("refine.json", result.refine_report)
        store.save_grid(grid)
        result.phases_run.append("refine")
    elif "refine" in phases:
        result.refine_report = store.read_json("refine.json") or {"skipped": "resume"}
        result.messages.append("resume: skipped refine")

    store.save_map(properties)
    result.phases_run.append("export")

    out_path = Path(output) if output else None
    if out_path is None and knobs.campaign and knobs.map_id:
        out_path = Path(knobs.campaign) / "maps" / f"{knobs.map_id}.yml"
    if out_path:
        write_map_yaml(str(out_path), properties)
        result.output_yaml = str(out_path)
        result.messages.append(f"wrote {out_path}")

    store.write_json("report.json", result.to_dict())
    return result


def _skip_completed(resume: bool, store: Workdir, phase: str, terminal: str) -> bool:
    """On --resume, skip a phase that already has a checkpoint unless it is the requested terminal phase."""
    if not resume:
        return False
    if phase == terminal:
        return False
    return store.has_phase(phase)


def _phases_to_run(stop_after: str) -> list[str]:
    if stop_after in {"all", "export", ""}:
        return list(PHASES)
    if stop_after not in PHASES:
        raise ValueError(f"Unknown phase {stop_after!r}; expected one of {PHASES}")
    end = PHASES.index(stop_after)
    return list(PHASES[: end + 1])


def _slug(name: str) -> str:
    text = "".join(ch.lower() if ch.isalnum() else "_" for ch in name).strip("_")
    return text or "imported_map"
