"""Detect multiple floor-plan panels on a published adventure map page.

Min-pool downsample keeps thin printed rules that bilinear resize would wash
out. Classical CV then splits on *thin* full-span gutters (not thick masonry
walls). Nested frames (2×2 house floors beside a dungeon) recurse the same way.
Panels without a detectable square grid (front-view illustrations) are dropped.
Optional VLM supplies labels and can add a panel the CV pass missed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from PIL import Image

from natural20.map_import.json_util import parse_json_object
from natural20.map_import.vlm import HeuristicClient, VlmClient

ANALYSIS_MAX = 1600
INK = 90
# Thin gutter on the pooled image: printed rules are 1–3 px after min-pool.
MAX_THICKNESS_FRAC = 0.018
MAX_THICKNESS_PX = 6
PANEL_SYSTEM = """You look at a published D&D adventure map PAGE that may contain
several floor plans, plus titles, compass roses, and illustrations.
Return JSON only:
{
  "page_title": "short title or empty",
  "panels": [
    {
      "id": "ground_floor",
      "label": "Ground Floor",
      "kind": "battlemap",
      "bounds": {"x1": 0.0, "y1": 0.0, "x2": 0.5, "y2": 1.0}
    }
  ]
}
Rules:
- bounds are fractions of the full image (0-1), origin top-left.
- kind is battlemap for a playable gridded floor plan, illustration for art
  without a tactical grid (front views, portraits), or other.
- Include every distinct floor/level (ground, upper, basement, attic, dungeon).
- Do not emit separate panels for compass roses, scale bars, or captions.
- A vertical or horizontal rule that splits two maps should fall on a panel edge.
"""


@dataclass
class MapPanel:
    """One cropped floor plan inside a larger page."""

    index: int
    label: str
    slug: str
    box: tuple[int, int, int, int]  # x0,y0,x1,y1 in original pixels
    kind: str = "battlemap"
    source: str = "cv"
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        x0, y0, x1, y1 = self.box
        return {
            "index": self.index,
            "label": self.label,
            "slug": self.slug,
            "kind": self.kind,
            "source": self.source,
            "box": [x0, y0, x1, y1],
            "width": x1 - x0,
            "height": y1 - y0,
            "notes": self.notes,
        }


def detect_map_panels(
    image: Image.Image,
    *,
    client: VlmClient | None = None,
    split: bool = True,
    drop_ungridded: bool = True,
) -> list[MapPanel]:
    """Return one or more panels in reading order (top-to-bottom, left-to-right)."""
    rgb = image.convert("RGB")
    orig_w, orig_h = rgb.size
    if not split:
        return [_whole_page(orig_w, orig_h)]

    ink, factor = _ink_mask(rgb)
    ah, aw = ink.shape
    inset = (
        max(2, int(aw * 0.018)),
        max(2, int(ah * 0.018)),
        aw - max(2, int(aw * 0.018)),
        ah - max(2, int(ah * 0.018)),
    )
    page_like = _has_ornate_frame(ink)
    boxes = _split_region(ink, inset, depth=0, page_like=page_like)
    boxes = _split_equal_grids(ink, boxes, aw, ah)
    boxes = _drop_tiny(boxes, aw, ah, min_frac=0.035)
    boxes = _sort_reading_order(boxes, ah)

    orig_boxes = [_to_original(box, factor, orig_w, orig_h) for box in boxes]
    orig_boxes = [_inset_box(b, orig_w, orig_h, px=4) for b in orig_boxes]
    panels = [
        MapPanel(
            index=i,
            label=_default_label(i, orig_boxes),
            slug=_default_slug(i, orig_boxes),
            box=box,
            source="cv",
            notes="ornate_page" if page_like else "",
        )
        for i, box in enumerate(orig_boxes)
    ]
    if drop_ungridded and len(panels) > 1:
        panels = _drop_header_illustrations(panels, orig_w, orig_h)
        panels = _drop_ungridded(rgb, panels)
    if client is not None and not isinstance(client, HeuristicClient):
        panels = _merge_vlm_labels(rgb, panels, client)
        if drop_ungridded and len(panels) > 1:
            panels = _drop_header_illustrations(panels, orig_w, orig_h)
            panels = _drop_ungridded(rgb, panels)
    if not panels:
        return [_whole_page(orig_w, orig_h)]
    boxes = [p.box for p in panels]
    for i, panel in enumerate(panels):
        panel.index = i
        if panel.source.startswith("cv") and "vlm" not in panel.source:
            if len(panels) != 2 or panel.label in {"Map", "Left", "Right", "Top", "Bottom"} or panel.label.startswith("Panel"):
                panel.label = _default_label(i, boxes)
                panel.slug = _default_slug(i, boxes)
    return panels


def crop_panel(image: Image.Image, panel: MapPanel) -> Image.Image:
    x0, y0, x1, y1 = panel.box
    return image.convert("RGB").crop((x0, y0, x1, y1))


def _whole_page(width: int, height: int) -> MapPanel:
    return MapPanel(index=0, label="Map", slug="map", box=(0, 0, width, height), source="whole")


def _ink_mask(rgb: Image.Image) -> tuple[np.ndarray, int]:
    """Boolean ink mask, min-pooled so thin black rules survive downsampling."""
    gray = np.asarray(rgb.convert("L"), dtype=np.uint8)
    h, w = gray.shape
    factor = max(1, int(np.ceil(max(w, h) / ANALYSIS_MAX)))
    if factor > 1:
        nh, nw = h // factor, w // factor
        gray = gray[: nh * factor, : nw * factor].reshape(nh, factor, nw, factor).min(axis=(1, 3))
    return gray < INK, factor


def _has_ornate_frame(ink: np.ndarray) -> bool:
    """Published module pages draw a *thin* dark rule near all four edges."""
    height, width = ink.shape
    hits = 0
    band = max(2, int(min(width, height) * 0.03))
    inner = max(band + 2, int(min(width, height) * 0.06))

    def thin_vertical(xs: range, inward_x: int) -> bool:
        for x in xs:
            if float(ink[:, x].mean()) >= 0.82:
                inward = min(width - 1, max(0, inward_x))
                return float(ink[:, inward].mean()) < 0.50
        return False

    def thin_horizontal(ys: range, inward_y: int) -> bool:
        for y in ys:
            if float(ink[y, :].mean()) >= 0.82:
                inward = min(height - 1, max(0, inward_y))
                return float(ink[inward, :].mean()) < 0.50
        return False

    if thin_vertical(range(0, min(band, width)), inner):
        hits += 1
    if thin_vertical(range(max(0, width - band), width), width - inner - 1):
        hits += 1
    if thin_horizontal(range(0, min(band, height)), inner):
        hits += 1
    if thin_horizontal(range(max(0, height - band), height), height - inner - 1):
        hits += 1
    return hits >= 3


def _split_region(
    ink: np.ndarray,
    box: tuple[int, int, int, int],
    *,
    depth: int,
    page_like: bool,
) -> list[tuple[int, int, int, int]]:
    x0, y0, x1, y1 = box
    if depth > 1 or (x1 - x0) < 40 or (y1 - y0) < 40:
        return [box]
    # Depth 0: two-up pages (span ~0.9) or a major column on an ornate sheet (~0.6).
    # Nested: only frame-to-frame rules (Front View vs floors). Room walls stay intact.
    if depth == 0:
        min_span = 0.60 if page_like else 0.78
    else:
        min_span = 0.90
    found = _best_divider(ink, box, min_span=min_span)
    if found is None:
        return [box]
    return _apply_split(ink, box, found, depth, page_like)


def _apply_split(
    ink: np.ndarray,
    box: tuple[int, int, int, int],
    found: tuple[str, int],
    depth: int,
    page_like: bool,
) -> list[tuple[int, int, int, int]]:
    x0, y0, x1, y1 = box
    axis, pos = found
    if axis == "v":
        left = _split_region(ink, (x0, y0, pos, y1), depth=depth + 1, page_like=page_like)
        right = _split_region(ink, (pos, y0, x1, y1), depth=depth + 1, page_like=page_like)
        return left + right
    top = _split_region(ink, (x0, y0, x1, pos), depth=depth + 1, page_like=page_like)
    bottom = _split_region(ink, (x0, pos, x1, y1), depth=depth + 1, page_like=page_like)
    return top + bottom


def _best_divider(
    ink: np.ndarray,
    box: tuple[int, int, int, int],
    *,
    min_span: float,
    min_part: float = 0.16,
) -> tuple[str, int] | None:
    vertical = _scan_dividers(ink, box, "v", min_span, min_part=min_part)
    horizontal = _scan_dividers(ink, box, "h", min_span, min_part=min_part)
    if vertical and horizontal:
        return (vertical[0], vertical[1]) if vertical[2] >= horizontal[2] else (horizontal[0], horizontal[1])
    if vertical:
        return vertical[0], vertical[1]
    if horizontal:
        return horizontal[0], horizontal[1]
    return None


def _scan_dividers(
    ink: np.ndarray,
    box: tuple[int, int, int, int],
    axis: str,
    min_span: float,
    *,
    min_part: float = 0.16,
) -> tuple[str, int, float] | None:
    """Return (axis, position, quality) for the best *thin* gutter, or None."""
    x0, y0, x1, y1 = box
    if axis == "v":
        size = x1 - x0
        scores = [float(ink[y0:y1, x].mean()) for x in range(x0, x1)]
        origin = x0
    else:
        size = y1 - y0
        scores = [float(ink[y, x0:x1].mean()) for y in range(y0, y1)]
        origin = y0
    if size < 16 or not scores:
        return None
    margin = max(4, int(size * 0.08))
    max_thick = max(2, min(MAX_THICKNESS_PX, int(size * MAX_THICKNESS_FRAC) or 2))
    side = max(4, int(size * 0.025))
    best: tuple[str, int, float] | None = None
    i = margin
    while i < size - margin:
        span = scores[i]
        if span < min_span:
            i += 1
            continue
        run_start = i
        while i + 1 < size - margin and scores[i + 1] >= min_span:
            i += 1
        run_end = i
        thickness = run_end - run_start + 1
        peak = max(range(run_start, run_end + 1), key=lambda k: scores[k])
        i = run_end + 1
        if thickness > max_thick:
            continue
        frac = peak / size
        if frac < min_part or (1.0 - frac) < min_part:
            continue
        left_idx = max(0, run_start - side)
        right_idx = min(size - 1, run_end + side)
        left_band = scores[left_idx:run_start] or [0.0]
        right_band = scores[run_end + 1 : right_idx + 1] or [0.0]
        left_mean = sum(left_band) / len(left_band)
        right_mean = sum(right_band) / len(right_band)
        # Gutter: dark rule with lighter map art on *both* sides (not a wall edge).
        if left_mean > span - 0.22 or right_mean > span - 0.22:
            continue
        contrast = span - 0.5 * (left_mean + right_mean)
        if contrast < 0.22:
            continue
        quality = span + contrast - 0.04 * thickness
        cand = (axis, origin + peak, quality)
        if best is None or quality > best[2]:
            best = cand
    return best


def _split_equal_grids(
    ink: np.ndarray,
    boxes: list[tuple[int, int, int, int]],
    page_w: int,
    page_h: int,
) -> list[tuple[int, int, int, int]]:
    """Split a large leftover region into a centered 2×1 / 2×2 of similar maps.

    Death House's four house floors sit in one column after the dungeon and
    front-view splits; their internal gutters do not reach span 0.90.
    """
    page = max(1, page_w * page_h)
    out: list[tuple[int, int, int, int]] = []
    for box in boxes:
        x0, y0, x1, y1 = box
        area = max(1, (x1 - x0) * (y1 - y0))
        hfrac = (y1 - y0) / max(1, page_h)
        yfrac = y0 / max(1, page_h)
        if area / page < 0.10 or hfrac >= 0.80 or (hfrac < 0.45 and yfrac < 0.15):
            out.append(box)
            continue
        parts = _equal_grid_parts(ink, box)
        if len(parts) == 4:
            areas = [(p[2] - p[0]) * (p[3] - p[1]) for p in parts]
            if max(areas) / max(1, min(areas)) > 1.7:
                out.append(box)
                continue
        out.extend(parts)
    return out


def _equal_grid_parts(
    ink: np.ndarray, box: tuple[int, int, int, int]
) -> list[tuple[int, int, int, int]]:
    vertical = _scan_dividers(ink, box, "v", 0.55, min_part=0.38)
    horizontal = _scan_dividers(ink, box, "h", 0.55, min_part=0.38)
    if not (vertical and horizontal):
        return [box]
    x0, y0, x1, y1 = box
    vx, hy = vertical[1], horizontal[1]
    return [
        (x0, y0, vx, hy),
        (vx, y0, x1, hy),
        (x0, hy, vx, y1),
        (vx, hy, x1, y1),
    ]


def _drop_tiny(
    boxes: list[tuple[int, int, int, int]],
    width: int,
    height: int,
    *,
    min_frac: float,
) -> list[tuple[int, int, int, int]]:
    page = width * height
    kept = []
    for x0, y0, x1, y1 in boxes:
        area = max(1, (x1 - x0) * (y1 - y0))
        if area / page >= min_frac and (x1 - x0) >= 36 and (y1 - y0) >= 36:
            kept.append((x0, y0, x1, y1))
    return kept or boxes


def _sort_reading_order(
    boxes: list[tuple[int, int, int, int]], page_h: int
) -> list[tuple[int, int, int, int]]:
    if len(boxes) <= 2:
        return sorted(boxes, key=lambda b: ((b[1] + b[3]) // 2, b[0]))
    compact = [b for b in boxes if (b[3] - b[1]) < 0.70 * page_h]
    tall = [b for b in boxes if (b[3] - b[1]) >= 0.70 * page_h]
    if compact:
        heights = sorted(b[3] - b[1] for b in compact)
        med_h = max(1, heights[len(heights) // 2])
        row = max(1, int(med_h * 0.6))
        compact = sorted(compact, key=lambda b: (b[1] // row, b[0]))
    tall = sorted(tall, key=lambda b: (b[0], b[1]))
    return compact + tall


def _to_original(
    box: tuple[int, int, int, int], factor: int, width: int, height: int
) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    factor = max(1, int(factor))
    ox0 = max(0, x0 * factor)
    oy0 = max(0, y0 * factor)
    ox1 = min(width, x1 * factor)
    oy1 = min(height, y1 * factor)
    if ox1 - ox0 < 8 or oy1 - oy0 < 8:
        return (0, 0, width, height)
    return ox0, oy0, ox1, oy1


def _inset_box(box: tuple[int, int, int, int], width: int, height: int, *, px: int) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    x0 = min(x1 - 8, x0 + px)
    y0 = min(y1 - 8, y0 + px)
    x1 = max(x0 + 8, x1 - px)
    y1 = max(y0 + 8, y1 - px)
    return max(0, x0), max(0, y0), min(width, x1), min(height, y1)


def _drop_header_illustrations(
    panels: list[MapPanel], page_w: int, page_h: int
) -> list[MapPanel]:
    """Drop a front-view / title block sitting above other maps in the same column."""
    if len(panels) < 3:
        return panels
    kept: list[MapPanel] = []
    for panel in panels:
        x0, y0, x1, y1 = panel.box
        if y1 < 0.45 * page_h:
            below = [
                other
                for other in panels
                if other is not panel
                and other.box[1] >= y1 - 24
                and _x_overlap(panel.box, other.box) > 0.45 * max(1, x1 - x0)
            ]
            if below:
                panel.kind = "illustration"
                panel.notes = (panel.notes + " header").strip()
                continue
        kept.append(panel)
    return kept or panels


def _x_overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> int:
    return max(0, min(a[2], b[2]) - max(a[0], b[0]))


def _drop_ungridded(image: Image.Image, panels: list[MapPanel]) -> list[MapPanel]:
    """Drop front-view art and empty title blocks that have no tactical grid."""
    from natural20.map_import.grid_detect import detect_grid_spec

    kept: list[MapPanel] = []
    for panel in panels:
        if panel.kind not in {"battlemap", "map", "floorplan", "floor"}:
            continue
        crop = crop_panel(image, panel)
        spec = detect_grid_spec(crop, calibrate=False)
        if spec is None or spec.width < 4 or spec.height < 4:
            panel.kind = "illustration"
            panel.notes = (panel.notes + " no_grid").strip()
            continue
        kept.append(panel)
    return kept or panels


def _default_label(index: int, boxes: list[tuple[int, int, int, int]]) -> str:
    if len(boxes) == 1:
        return "Map"
    if len(boxes) == 2:
        a, b = boxes[0], boxes[1]
        dx = abs((a[0] + a[2]) / 2 - (b[0] + b[2]) / 2)
        dy = abs((a[1] + a[3]) / 2 - (b[1] + b[3]) / 2)
        if dx >= dy:
            return "Left" if index == 0 else "Right"
        return "Top" if index == 0 else "Bottom"
    return f"Panel {index + 1}"


def _default_slug(index: int, boxes: list[tuple[int, int, int, int]]) -> str:
    label = _default_label(index, boxes)
    return _slug(label) or f"panel_{index}"


def _slug(text: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in text).strip("_") or "panel"


def _merge_vlm_labels(image: Image.Image, panels: list[MapPanel], client: VlmClient) -> list[MapPanel]:
    overview = image.copy()
    max_side = 768
    w, h = overview.size
    if max(w, h) > max_side:
        s = max_side / max(w, h)
        overview = overview.resize((max(1, int(w * s)), max(1, int(h * s))), Image.Resampling.LANCZOS)
    prompt = (
        f"Image size {image.size[0]}x{image.size[1]} pixels. "
        f"CV already found {len(panels)} panel(s): "
        + ", ".join(f"{p.slug} box={p.box}" for p in panels)
        + ". Confirm battlemap panels and labels. Return JSON only."
    )
    try:
        raw = client.complete(prompt, image=overview, system=PANEL_SYSTEM, max_tokens=1200)
        data = parse_json_object(raw)
    except (ValueError, TypeError, Exception):
        return panels
    vlm_panels = data.get("panels") or []
    if not isinstance(vlm_panels, list) or not vlm_panels:
        return panels
    ow, oh = image.size
    labeled = list(panels)
    used = set()
    for item in vlm_panels:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "battlemap").lower()
        if kind in {"illustration", "art", "portrait", "other"}:
            continue
        if kind not in {"battlemap", "map", "floorplan", "floor"}:
            continue
        bounds = item.get("bounds") or {}
        try:
            bx0 = int(float(bounds.get("x1", 0)) * ow)
            by0 = int(float(bounds.get("y1", 0)) * oh)
            bx1 = int(float(bounds.get("x2", 1)) * ow)
            by1 = int(float(bounds.get("y2", 1)) * oh)
        except (TypeError, ValueError):
            continue
        vlm_box = (max(0, bx0), max(0, by0), min(ow, bx1), min(oh, by1))
        best_i, best_iou = -1, 0.0
        overlap_any = 0.0
        for i, panel in enumerate(labeled):
            iou = _iou(panel.box, vlm_box)
            overlap_any = max(overlap_any, iou)
            if i in used:
                continue
            if iou > best_iou:
                best_iou, best_i = iou, i
        label = str(item.get("label") or item.get("id") or "").strip() or f"Panel {len(labeled)}"
        slug = _slug(str(item.get("id") or label))
        if best_i >= 0 and best_iou >= 0.25:
            used.add(best_i)
            labeled[best_i].label = label
            labeled[best_i].slug = slug
            labeled[best_i].source = "cv+vlm"
        elif overlap_any < 0.20 and (vlm_box[2] - vlm_box[0]) > 40 and (vlm_box[3] - vlm_box[1]) > 40:
            labeled.append(
                MapPanel(
                    index=len(labeled),
                    label=label,
                    slug=slug,
                    box=_inset_box(vlm_box, ow, oh, px=2),
                    source="vlm",
                )
            )
    battle = [p for p in labeled if p.kind == "battlemap"]
    return battle or labeled


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0, ix1 - ix0), max(0, iy1 - iy0)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(1, (ax1 - ax0) * (ay1 - ay0))
    area_b = max(1, (bx1 - bx0) * (by1 - by0))
    return inter / (area_a + area_b - inter)
