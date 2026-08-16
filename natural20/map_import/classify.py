"""Per-tile classification: heuristic first pass, then optional VLM second opinion."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from natural20.map_import.checkpoint import Workdir
from natural20.map_import.dimensions import GridSpec
from natural20.map_import.features import extract_priors
from natural20.map_import.ink import EdgeBits, apply_edges_to_record, merge_vlm_edges
from natural20.map_import.model import ClassificationGrid, TileRecord
from natural20.map_import.overlays import OverlayReport
from natural20.map_import.slicer import crop_tile, mosaic_neighborhood
from natural20.map_import.taxonomy import normalize_class, normalize_subtype
from natural20.map_import.vlm import HeuristicClient, VlmClient

_SEEDED = {"occupancy", "seed"}
_CHECKPOINT_EVERY = 20


def classify_tiles(
    image: Image.Image,
    spec: GridSpec,
    grid: ClassificationGrid,
    client: VlmClient,
    *,
    pad_ratio: float = 0.25,
    confidence_threshold: float = 0.55,
    include_mosaic: bool = True,
    max_tiles: int | None = None,
    workdir: Path | None = None,
    overlays: OverlayReport | None = None,
) -> ClassificationGrid:
    """Heuristic/occupancy first, then a per-tile VLM second opinion when a vision client is set."""
    overlay_kind = overlays.tile_kind() if overlays else {}
    counted = 0
    for y in range(spec.height):
        for x in range(spec.width):
            if max_tiles is not None and counted >= max_tiles:
                break
            _prime_heuristic(
                image,
                spec,
                grid,
                x,
                y,
                overlay_kind=overlay_kind.get((x, y)),
            )
            counted += 1
        else:
            continue
        break

    if isinstance(client, HeuristicClient):
        return grid

    overrides: list[dict] = []
    reviewed = 0
    for y in range(spec.height):
        for x in range(spec.width):
            if max_tiles is not None and reviewed >= max_tiles:
                break
            tile = grid.tiles[x][y]
            if any(str(f).startswith("overlay:") for f in tile.flags):
                continue
            if ":second_opinion" in (tile.source or ""):
                reviewed += 1
                continue
            before = (tile.tile_class, tile.subtype, tile.edges.wall_tuple())
            _classify_one(
                image,
                spec,
                grid,
                client,
                x,
                y,
                pad_ratio=pad_ratio,
                include_mosaic=include_mosaic,
                pass_name="second_opinion",
                overlay_kind=overlay_kind.get((x, y)),
                keep_prior_if_weak=True,
                confidence_threshold=confidence_threshold,
            )
            tile = grid.tiles[x][y]
            after = (tile.tile_class, tile.subtype, tile.edges.wall_tuple())
            if after != before:
                overrides.append({"x": x, "y": y, "from": list(before[:2]), "to": list(after[:2])})
            reviewed += 1
            if reviewed % _CHECKPOINT_EVERY == 0:
                total = spec.width * spec.height
                print(f"vlm second opinion {reviewed}/{total} overrides={len(overrides)}", flush=True)
            if workdir is not None and reviewed % _CHECKPOINT_EVERY == 0:
                Workdir(workdir).save_grid(grid)
        else:
            continue
        break

    if workdir is not None:
        Workdir(workdir).save_grid(grid)
        (workdir / "vlm_second_opinion.json").write_text(
            json.dumps({"reviewed": reviewed, "overrides": overrides}, indent=2),
            encoding="utf-8",
        )
        uncertain = [t.to_dict() for t in grid.uncertain(confidence_threshold) if t.source != "unclassified"]
        (workdir / "uncertain.json").write_text(json.dumps(uncertain, indent=2), encoding="utf-8")
    return grid


def _prime_heuristic(
    image: Image.Image,
    spec: GridSpec,
    grid: ClassificationGrid,
    x: int,
    y: int,
    *,
    overlay_kind: str | None,
) -> TileRecord:
    """Fill CV priors. Keep occupancy/seeded class; otherwise use the heuristic."""
    exact = crop_tile(image, spec, x, y, pad_ratio=0.0)
    features, cv_edges = extract_priors(exact)
    record = grid.tiles[x][y]
    record.features = features
    seeded = record.source in _SEEDED or any(f in _SEEDED for f in record.flags)
    if overlay_kind:
        flag = f"overlay:{overlay_kind}"
        if flag not in record.flags:
            record.flags.append(flag)
        record.edges = EdgeBits()
        record.tile_class = "floor"
        record.subtype = "none"
        record.confidence = 0.86
        record.description = f"printed {overlay_kind}; not a wall"
        record.source = "overlay"
        grid.set(record)
        return record
    if seeded:
        if not record.edges.any_wall() and not record.edges.any_door() and not record.edges.solid:
            record.edges = cv_edges
        grid.set(record)
        return record
    record.edges = cv_edges
    record.tile_class = features.heuristic_class
    record.subtype = features.heuristic_subtype
    record.confidence = features.heuristic_confidence
    record.description = f"heuristic prior; {cv_edges.summary()}"
    record.source = "heuristic"
    apply_edges_to_record(record)
    if record.tile_class == "door" and record.orientation in {"none", ""}:
        record.orientation = _door_orientation(grid, x, y)
    grid.set(record)
    return record


def _classify_one(
    image: Image.Image,
    spec: GridSpec,
    grid: ClassificationGrid,
    client: VlmClient,
    x: int,
    y: int,
    *,
    pad_ratio: float,
    include_mosaic: bool,
    pass_name: str,
    overlay_kind: str | None = None,
    keep_prior_if_weak: bool = False,
    confidence_threshold: float = 0.55,
) -> TileRecord:
    padded = crop_tile(image, spec, x, y, pad_ratio=pad_ratio)
    exact = crop_tile(image, spec, x, y, pad_ratio=0.0)
    features, cv_edges = extract_priors(exact)
    record = grid.tiles[x][y]
    record.features = features
    prior_class = record.tile_class
    prior_subtype = record.subtype
    prior_orientation = record.orientation
    prior_edges = record.edges
    if overlay_kind:
        flag = f"overlay:{overlay_kind}"
        if flag not in record.flags:
            record.flags.append(flag)
        record.edges = EdgeBits()
        record.tile_class = "floor"
        record.subtype = "none"
        record.confidence = 0.86
        record.description = f"printed {overlay_kind}; not a wall"
        record.source = "overlay"
        grid.set(record)
        return record

    if isinstance(client, HeuristicClient):
        record.edges = cv_edges
        record.tile_class = features.heuristic_class
        record.subtype = features.heuristic_subtype
        record.confidence = features.heuristic_confidence
        record.description = f"heuristic prior (no VLM); {cv_edges.summary()}"
        record.source = "heuristic"
        apply_edges_to_record(record)
        if record.tile_class == "door" and record.orientation in {"none", ""}:
            record.orientation = _door_orientation(grid, x, y)
        grid.set(record)
        return record

    prompt = _tile_prompt(grid, x, y, features, spec, edges=cv_edges, prior=record)
    vision = mosaic_neighborhood(image, spec, x, y) if include_mosaic else padded
    data = client.classify_json(prompt, image=vision)
    vlm_class = normalize_class(data.get("class"))
    vlm_subtype = normalize_subtype(data.get("subtype"))
    try:
        confidence = float(data.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.3
    keep_prior = keep_prior_if_weak and not _accept_vlm_override(
        prior_class, vlm_class, data, confidence, threshold=confidence_threshold
    )
    record.raw_response = str(data.get("_raw") or "")[:2000]
    record.source = f"{client.name}:{pass_name}"
    record.edges = merge_vlm_edges(cv_edges if not prior_edges.any_wall() else prior_edges, data)
    if keep_prior:
        record.tile_class = prior_class
        record.subtype = prior_subtype
        record.orientation = prior_orientation
        record.edges = prior_edges
        record.confidence = max(confidence, 0.4)
        record.description = (
            f"kept {prior_class} (VLM {vlm_class} conf={confidence:.2f}); {str(data.get('description') or '')[:200]}"
        )
        record.flags.append("vlm_kept_prior")
        grid.set(record)
        return record
    record.tile_class = vlm_class
    record.subtype = vlm_subtype
    record.orientation = str(data.get("orientation") or prior_orientation or "none").lower()
    record.confidence = confidence
    record.description = str(data.get("description") or "")[:400]
    if (vlm_class, vlm_subtype) != (prior_class, prior_subtype):
        record.flags.append("vlm_override")
    apply_edges_to_record(record)
    if record.tile_class == "door" and record.orientation in {"none", ""}:
        record.orientation = _door_orientation(grid, x, y)
    if record.tile_class == "object" and record.subtype == "none":
        record.subtype = "other"
    grid.set(record)
    return record


def _accept_vlm_override(
    prior_class: str,
    vlm_class: str,
    data: dict,
    confidence: float,
    *,
    threshold: float,
) -> bool:
    """When occupancy was seeded, only take VLM class for doors, props, or a clear opening."""
    if prior_class in {"unknown", "unclassified"}:
        return True
    if vlm_class == "unknown" or confidence < threshold:
        return False
    if vlm_class == prior_class:
        # Confirmation of the occupancy class — do not rewrite edges into door soup.
        return False
    walls = data.get("walls") or {}
    doors = data.get("doors") or {}
    any_door = any(bool(doors.get(side)) for side in ("N", "E", "S", "W"))
    any_wall = any(bool(walls.get(side)) for side in ("N", "E", "S", "W")) or bool(data.get("solid_wall"))
    if vlm_class == "door" and prior_class in {"wall", "floor"} and (any_door or confidence >= 0.75):
        return True
    if vlm_class == "object" and prior_class == "floor" and confidence >= 0.7:
        return True
    if vlm_class == "floor" and prior_class == "wall" and not any_wall and not any_door and confidence >= 0.8:
        return True
    return False


def _door_orientation(grid: ClassificationGrid, x: int, y: int) -> str:
    tile = grid.get(x, y)
    if tile is not None:
        side = tile.edges.door_side()
        if side in {"E", "W"}:
            return "vertical"
        if side in {"N", "S"}:
            return "horizontal"
    n = grid.get(x, y - 1)
    s = grid.get(x, y + 1)
    e = grid.get(x + 1, y)
    w = grid.get(x - 1, y)
    ns_wall = sum(1 for t in (n, s) if t and (t.tile_class == "wall" or t.edges.any_wall()))
    ew_wall = sum(1 for t in (e, w) if t and (t.tile_class == "wall" or t.edges.any_wall()))
    if ns_wall > ew_wall:
        return "vertical"
    if ew_wall > ns_wall:
        return "horizontal"
    return "horizontal"


def _tile_prompt(grid: ClassificationGrid, x: int, y: int, features, spec: GridSpec, *, edges=None, prior=None) -> str:
    cardinal = grid.cardinal(x, y)
    ink = edges.summary() if edges is not None else "walls=- doors=-"
    scores = ""
    if edges is not None and edges.scores:
        scores = " " + ",".join(f"{s}:{edges.scores.get(s, 0):.2f}" for s in ("N", "E", "S", "W"))
    lines = [
        f"Classify the CENTER tile at ({x},{y}) on a {spec.width}x{spec.height} battlemap grid.",
        "Origin is top-left. x increases east, y increases south.",
        "This is a second opinion on an already-classified square. Prefer the prior unless the image clearly disagrees.",
        (
            "Heuristic prior: "
            f"{features.heuristic_class}/{features.heuristic_subtype} "
            f"confidence={features.heuristic_confidence:.2f} "
            f"brightness={features.brightness:.2f} contrast={features.contrast:.2f} "
            f"edges={features.edge_score:.2f} dark_ratio={features.dark_ratio:.2f}"
        ),
        f"Ink edges: {ink}{scores}",
    ]
    if prior is not None and prior.source not in {"unclassified", "heuristic"}:
        lines.append(
            f"Occupancy/seeded prior: {prior.tile_class}/{prior.subtype} "
            f"{prior.edges.summary()} source={prior.source}"
        )
    lines.append("Already classified neighbors:")
    for name, tile in cardinal.items():
        if tile is None:
            lines.append(f"  {name}=off-map")
        elif tile.source == "unclassified":
            lines.append(f"  {name}=pending")
        else:
            lines.append(f"  {name}={tile.neighbor_summary()} {tile.description[:80]}")
    diag = []
    for dx, dy, label in ((-1, -1, "NW"), (1, -1, "NE"), (-1, 1, "SW"), (1, 1, "SE")):
        tile = grid.get(x + dx, y + dy)
        if tile and tile.source != "unclassified":
            diag.append(f"{label}={tile.tile_class}")
    if diag:
        lines.append("Diagonals: " + ", ".join(diag))
    lines.append("Return JSON only.")
    return "\n".join(lines)
