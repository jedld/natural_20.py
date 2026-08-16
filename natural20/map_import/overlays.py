"""Cartographic overlays that must not become walls.

Published battlemaps print titles ("Ground Floor", "Basement"), compass roses,
scale captions, and circled room keys (a, b, c, …). Those ink strokes look like
thin walls to edge detection. This module finds them, maps them onto grid tiles,
and supplies the letters so adventure text can be cross-referenced.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from natural20.map_import.dimensions import GridSpec
from natural20.map_import.ink import EdgeBits
from natural20.map_import.model import ClassificationGrid

_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/liberation/LiberationSerif-BoldItalic.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)

_LETTER_CHARS = "abcdefghijklmnopqrstuvwxyz"


@dataclass
class OverlayMark:
    kind: str
    text: str
    box: tuple[int, int, int, int]
    confidence: float = 0.0
    tiles: list[list[int]] = field(default_factory=list)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["box"] = list(self.box)
        return data


@dataclass
class OverlayReport:
    marks: list[OverlayMark] = field(default_factory=list)

    def keys(self) -> list[OverlayMark]:
        return [m for m in self.marks if m.kind == "key" and m.text]

    def tile_kind(self) -> dict[tuple[int, int], str]:
        out: dict[tuple[int, int], str] = {}
        priority = {"key": 4, "compass": 3, "title": 2, "scale": 2, "caption": 1}
        for mark in self.marks:
            for tile in mark.tiles:
                pos = (int(tile[0]), int(tile[1]))
                if priority.get(mark.kind, 0) >= priority.get(out.get(pos, ""), 0):
                    out[pos] = mark.kind
        return out

    def to_dict(self) -> dict:
        return {"marks": [m.to_dict() for m in self.marks]}

    @classmethod
    def from_dict(cls, data: dict | None) -> "OverlayReport":
        report = cls()
        if not data:
            return report
        for item in data.get("marks") or []:
            box = item.get("box") or [0, 0, 0, 0]
            report.marks.append(
                OverlayMark(
                    kind=str(item.get("kind") or "caption"),
                    text=str(item.get("text") or ""),
                    box=(int(box[0]), int(box[1]), int(box[2]), int(box[3])),
                    confidence=float(item.get("confidence") or 0.0),
                    tiles=[list(t) for t in item.get("tiles") or []],
                )
            )
        return report


def detect_overlays(
    image: Image.Image,
    spec: GridSpec,
    *,
    prefer_letters: Iterable[str] | None = None,
) -> OverlayReport:
    """Find titles, compass roses, scale text, and circled room keys."""
    rgb = image.convert("RGB")
    prefer = {str(ch).lower() for ch in (prefer_letters or []) if str(ch).isalpha()}
    marks: list[OverlayMark] = []
    marks.extend(_detect_key_circles(rgb, spec, prefer_letters=prefer))
    key_boxes = [m.box for m in marks]
    marks.extend(_detect_compass(rgb, spec, exclude=key_boxes))
    marks.extend(_detect_text_captions(rgb, spec, exclude=key_boxes + [m.box for m in marks]))
    for mark in marks:
        pad = 0.55 if mark.kind == "compass" else 0.2
        mark.tiles = [list(t) for t in tiles_for_box(spec, mark.box, pad_tiles=pad)]
    return OverlayReport(marks=marks)


def apply_overlay_mask(grid: ClassificationGrid, report: OverlayReport) -> list[dict]:
    """Clear wall/ink on overlay tiles so printed cartography is not occupancy."""
    fixes: list[dict] = []
    kinds = report.tile_kind()
    for (x, y), kind in kinds.items():
        tile = grid.get(x, y)
        if tile is None:
            continue
        flag = f"overlay:{kind}"
        if flag not in tile.flags:
            tile.flags.append(flag)
        neighbors = [t for t in grid.cardinal(x, y).values() if t]
        voidish = sum(1 for t in neighbors if t.tile_class == "void")
        new_class = "void" if voidish >= 2 and kind != "key" else "floor"
        tile.edges = EdgeBits()
        tile.tile_class = new_class
        if tile.subtype in {"none", "other", "column"}:
            tile.subtype = "none"
        tile.confidence = max(tile.confidence, 0.8)
        tile.source = "overlay"
        grid.set(tile)
        fixes.append({"x": x, "y": y, "class": new_class, "reason": flag})
    return fixes


def tiles_for_box(
    spec: GridSpec,
    box: tuple[int, int, int, int],
    *,
    pad_tiles: float = 0.0,
) -> list[tuple[int, int]]:
    x0, y0, x1, y1 = box
    pad_x = spec.tile_w * pad_tiles
    pad_y = spec.tile_h * pad_tiles
    x0 -= pad_x
    y0 -= pad_y
    x1 += pad_x
    y1 += pad_y
    tx0 = int(np.floor((x0 - spec.offset_x) / max(spec.tile_w, 1e-6)))
    ty0 = int(np.floor((y0 - spec.offset_y) / max(spec.tile_h, 1e-6)))
    tx1 = int(np.floor((x1 - spec.offset_x) / max(spec.tile_w, 1e-6)))
    ty1 = int(np.floor((y1 - spec.offset_y) / max(spec.tile_h, 1e-6)))
    tiles: list[tuple[int, int]] = []
    for y in range(max(0, ty0), min(spec.height, ty1 + 1)):
        for x in range(max(0, tx0), min(spec.width, tx1 + 1)):
            tiles.append((x, y))
    return tiles


def pixel_to_tile(spec: GridSpec, px: float, py: float) -> tuple[int, int] | None:
    x = int((px - spec.offset_x) / max(spec.tile_w, 1e-6))
    y = int((py - spec.offset_y) / max(spec.tile_h, 1e-6))
    if 0 <= x < spec.width and 0 <= y < spec.height:
        return x, y
    return None


def flood_room(
    grid: ClassificationGrid,
    start: tuple[int, int],
    *,
    max_cells: int = 400,
) -> list[tuple[int, int]]:
    """Walkable cells of the room containing `start` (stops at walls/void)."""
    sx, sy = start
    seed = grid.get(sx, sy)
    if seed is None:
        return []
    if seed.tile_class in {"wall", "void"}:
        for tile in grid.neighbors(sx, sy, diagonal=False):
            if tile.tile_class in {"floor", "door", "water", "object"}:
                sx, sy = tile.x, tile.y
                break
        else:
            return [(start[0], start[1])]

    def walkable(tile) -> bool:
        if tile is None:
            return False
        if any(str(f).startswith("overlay:compass") or str(f).startswith("overlay:title") for f in tile.flags):
            return False
        return tile.tile_class in {"floor", "door", "water", "object"} or any(
            str(f).startswith("overlay:key") for f in tile.flags
        )

    origin = grid.get(sx, sy)
    if not walkable(origin):
        return [(sx, sy)]
    seen = {(sx, sy)}
    stack = [(sx, sy)]
    while stack and len(seen) < max_cells:
        x, y = stack.pop()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if (nx, ny) in seen:
                continue
            if not walkable(grid.get(nx, ny)):
                continue
            seen.add((nx, ny))
            stack.append((nx, ny))
    return sorted(seen)


def room_bounds(cells: list[tuple[int, int]]) -> dict[str, int]:
    if not cells:
        return {"x1": 0, "y1": 0, "x2": 0, "y2": 0}
    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    return {"x1": min(xs), "y1": min(ys), "x2": max(xs), "y2": max(ys)}


def _detect_key_circles(
    rgb: Image.Image,
    spec: GridSpec,
    *,
    prefer_letters: set[str],
) -> list[OverlayMark]:
    arr = np.asarray(rgb)
    hsv = np.asarray(rgb.convert("HSV"))
    gray = np.asarray(rgb.convert("L"))
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    red = ((h < 18) | (h > 230)) & (s > 55) & (v > 40) & (v < 245)
    circles = _circular_components(
        red,
        min_size=max(18, int(min(spec.tile_w, spec.tile_h) * 0.55)),
        max_size=int(min(spec.tile_w, spec.tile_h) * 2.4),
        fill_range=(0.10, 0.40),
    )
    boxes = _nms_boxes(circles, iou=0.35)
    if not boxes:
        # Fallback: white discs with a dark rim (keys without a warm drop shadow).
        white = (gray > 200) & (arr.mean(axis=2) > 190)
        discs = _circular_components(
            white,
            min_size=max(16, int(min(spec.tile_w, spec.tile_h) * 0.5)),
            max_size=int(min(spec.tile_w, spec.tile_h) * 2.2),
            fill_range=(0.45, 0.95),
        )
        boxes = _nms_boxes(discs, iou=0.35)
    scored: list[tuple[float, str, tuple[int, int, int, int]]] = []
    leftover: list[tuple[int, int, int, int]] = []
    for box in boxes:
        x0, y0, x1, y1 = box
        crop = rgb.crop((x0, y0, x1 + 1, y1 + 1))
        letter, conf = _read_circled_letter(crop, prefer_letters=prefer_letters)
        if letter and conf >= 0.34 and (not prefer_letters or letter in prefer_letters):
            scored.append((conf, letter, box))
        else:
            leftover.append(box)
    scored.sort(reverse=True)
    marks: list[OverlayMark] = []
    seen_letters: set[str] = set()
    used_boxes: set[tuple[int, int, int, int]] = set()
    for conf, letter, box in scored:
        if letter in seen_letters:
            leftover.append(box)
            continue
        seen_letters.add(letter)
        used_boxes.add(box)
        marks.append(OverlayMark(kind="key", text=letter, box=box, confidence=round(conf, 3)))
    unused = {ch for ch in prefer_letters if ch not in seen_letters}
    pairs: list[tuple[float, str, tuple[int, int, int, int]]] = []
    for box in leftover:
        if box in used_boxes:
            continue
        crop = rgb.crop((box[0], box[1], box[2] + 1, box[3] + 1))
        for ch in unused:
            _letter, conf = _best_letter(crop, allowed={ch}, prefer={ch})
            if conf >= 0.20:
                pairs.append((conf, ch, box))
    pairs.sort(reverse=True)
    for conf, letter, box in pairs:
        if letter not in unused or box in used_boxes:
            continue
        unused.discard(letter)
        used_boxes.add(box)
        marks.append(OverlayMark(kind="key", text=letter, box=box, confidence=round(conf, 3)))
    return marks


def _detect_compass(
    rgb: Image.Image,
    spec: GridSpec,
    *,
    exclude: list[tuple[int, int, int, int]],
) -> list[OverlayMark]:
    gray = np.asarray(rgb.convert("L"))
    step = 2
    dark = gray[::step, ::step] < 55
    tile = max(8.0, (spec.tile_w + spec.tile_h) / 2.0)
    comps = _components(dark, min_area=int((tile * tile * 0.6) / (step * step)), max_area=int((tile * tile * 40) / (step * step)))
    marks: list[OverlayMark] = []
    h, w = gray.shape
    for area, box in comps:
        x0, y0, x1, y1 = (box[0] * step, box[1] * step, box[2] * step, box[3] * step)
        bw, bh = x1 - x0 + 1, y1 - y0 + 1
        if max(bw, bh) < tile * 1.6 or max(bw, bh) > tile * 7:
            continue
        aspect = bw / max(bh, 1)
        if aspect < 0.65 or aspect > 1.55:
            continue
        if _iou(box, exclude) > 0.15:
            continue
        # Corner frame ornaments touch two image edges; a compass sits inset.
        touches = int(x0 <= 4) + int(y0 <= 4) + int(x1 >= w - 5) + int(y1 >= h - 5)
        if touches >= 2:
            continue
        patch = (gray[y0 : y1 + 1, x0 : x1 + 1] < 55)
        if _angular_coverage(patch) < 8:
            continue
        fill = float(patch.mean())
        if fill < 0.06 or fill > 0.55:
            continue
        marks.append(OverlayMark(kind="compass", text="N", box=box, confidence=0.7))
    marks.sort(key=lambda m: (m.box[2] - m.box[0]) * (m.box[3] - m.box[1]), reverse=True)
    return marks[:2]


def _detect_text_captions(
    rgb: Image.Image,
    spec: GridSpec,
    *,
    exclude: list[tuple[int, int, int, int]],
) -> list[OverlayMark]:
    gray = np.asarray(rgb.convert("L"))
    h, w = gray.shape
    tile = max(8.0, (spec.tile_w + spec.tile_h) / 2.0)
    step = 2
    dark = gray[::step, ::step] < 48
    comps = _components(dark, min_area=max(6, 12 // (step * step)), max_area=int((tile * tile * 2.5) / (step * step)))
    glyphs: list[tuple[int, int, int, int]] = []
    for _area, box in comps:
        x0, y0, x1, y1 = (box[0] * step, box[1] * step, box[2] * step, box[3] * step)
        bw, bh = x1 - x0 + 1, y1 - y0 + 1
        if bh < tile * 0.22 or bh > tile * 1.8:
            continue
        if bw < 3 or bw > tile * 1.6:
            continue
        aspect = bw / max(bh, 1)
        if aspect < 0.12 or aspect > 3.2:
            continue
        if _iou(box, exclude) > 0.25:
            continue
        glyphs.append(box)
    glyphs.sort(key=lambda b: (b[1], b[0]))
    words = _cluster_words(glyphs, gap=tile * 0.85)
    marks: list[OverlayMark] = []
    for boxes in words:
        x0 = min(b[0] for b in boxes)
        y0 = min(b[1] for b in boxes)
        x1 = max(b[2] for b in boxes)
        y1 = max(b[3] for b in boxes)
        width_tiles = (x1 - x0) / tile
        height_tiles = (y1 - y0) / tile
        n = len(boxes)
        top = y0 < h * 0.22
        bottom = y1 > h * 0.82
        if n < 3 or height_tiles > 2.2:
            continue
        kind = "caption"
        if bottom and n >= 6:
            kind = "scale"
        elif top or width_tiles >= 2.4:
            kind = "title"
        elif n < 4 and not (top or bottom):
            continue
        marks.append(
            OverlayMark(
                kind=kind,
                text="",
                box=(x0, y0, x1, y1),
                confidence=0.55 if kind == "caption" else 0.7,
            )
        )
    return marks


def _read_circled_letter(crop: Image.Image, *, prefer_letters: set[str]) -> tuple[str, float]:
    return _best_letter(crop, allowed=None, prefer=prefer_letters)


def _best_letter(
    crop: Image.Image,
    *,
    allowed: set[str] | None,
    prefer: set[str] | None = None,
) -> tuple[str, float]:
    gray = np.asarray(crop.convert("L"))
    gh, gw = gray.shape
    yy, xx = np.ogrid[:gh, :gw]
    cy, cx = (gh - 1) / 2.0, (gw - 1) / 2.0
    radius = min(gh, gw) * 0.28
    inner = (yy - cy) ** 2 + (xx - cx) ** 2 <= radius * radius
    dark = inner & (gray < 100)
    if int(dark.sum()) < 10:
        dark = inner & (gray < 135)
    glyph = _to32(dark)
    if int(glyph.sum()) < 8:
        return "", 0.0
    scored: list[tuple[float, str]] = []
    allowed = allowed or set(_LETTER_CHARS)
    for ch, tmpl in _letter_templates():
        if ch not in allowed:
            continue
        inter = int((glyph & tmpl).sum())
        union = int((glyph | tmpl).sum())
        scored.append((inter / max(union, 1), ch))
    scored.sort(reverse=True)
    if not scored:
        return "", 0.0
    best_score, best = scored[0]
    votes = Counter(ch for s, ch in scored[:10] if s > 0.32)
    if votes:
        voted, _n = votes.most_common(1)[0]
        voted_score = max(s for s, ch in scored if ch == voted)
        if voted_score >= best_score - 0.08:
            best, best_score = voted, voted_score
    if prefer:
        preferred = [(s, ch) for s, ch in scored if ch in prefer]
        if preferred and preferred[0][0] >= best_score - 0.12:
            best_score, best = preferred[0]
    return best, float(best_score)


def _letter_templates() -> list[tuple[str, np.ndarray]]:
    cached = getattr(_letter_templates, "_cache", None)
    if cached is not None:
        return cached
    fonts = [p for p in _FONT_CANDIDATES if Path(p).is_file()]
    templates: list[tuple[str, np.ndarray]] = []
    if not fonts:
        font = ImageFont.load_default()
        for ch in _LETTER_CHARS:
            im = Image.new("L", (64, 64), 0)
            ImageDraw.Draw(im).text((16, 16), ch, fill=255, font=font)
            templates.append((ch, _to32(np.asarray(im) > 40)))
        _letter_templates._cache = templates  # type: ignore[attr-defined]
        return templates
    for path in fonts[:3]:
        font = ImageFont.truetype(path, 28)
        for ch in _LETTER_CHARS:
            im = Image.new("L", (64, 64), 0)
            draw = ImageDraw.Draw(im)
            bbox = draw.textbbox((0, 0), ch, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(((64 - tw) // 2 - bbox[0], (64 - th) // 2 - bbox[1]), ch, fill=255, font=font)
            templates.append((ch, _to32(np.asarray(im) > 40)))
    _letter_templates._cache = templates  # type: ignore[attr-defined]
    return templates


def _to32(mask: np.ndarray) -> np.ndarray:
    ys, xs = np.where(mask)
    if len(ys) == 0:
        return np.zeros((32, 32), dtype=bool)
    y0, y1, x0, x1 = int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1
    glyph = mask[y0:y1, x0:x1]
    gh, gw = glyph.shape
    scale = 26 / max(gh, gw)
    nh, nw = max(1, int(round(gh * scale))), max(1, int(round(gw * scale)))
    im = Image.fromarray((glyph.astype(np.uint8) * 255)).resize((nw, nh), Image.Resampling.BILINEAR)
    canvas = Image.new("L", (32, 32), 0)
    canvas.paste(im, ((32 - nw) // 2, (32 - nh) // 2))
    return np.asarray(canvas) > 80


def _circular_components(
    mask: np.ndarray,
    *,
    min_size: int,
    max_size: int,
    fill_range: tuple[float, float],
) -> list[tuple[int, int, int, int]]:
    boxes: list[tuple[int, int, int, int]] = []
    for area, box in _components(mask, min_area=max(20, min_size), max_area=max_size * max_size):
        x0, y0, x1, y1 = box
        bw, bh = x1 - x0 + 1, y1 - y0 + 1
        if abs(bw - bh) > max(10, 0.25 * max(bw, bh)):
            continue
        if not (min_size <= max(bw, bh) <= max_size):
            continue
        fill = area / max(bw * bh, 1)
        if fill_range[0] <= fill <= fill_range[1]:
            boxes.append(box)
    return boxes


def _components(
    mask: np.ndarray,
    *,
    min_area: int,
    max_area: int,
) -> list[tuple[int, tuple[int, int, int, int]]]:
    h, w = mask.shape
    vis = np.zeros(mask.shape, dtype=bool)
    out: list[tuple[int, tuple[int, int, int, int]]] = []
    ys, xs = np.where(mask)
    for y, x in zip(ys.tolist(), xs.tolist()):
        if vis[y, x]:
            continue
        q = deque([(y, x)])
        vis[y, x] = True
        area = 0
        y0 = y1 = y
        x0 = x1 = x
        while q:
            cy, cx = q.popleft()
            area += 1
            if cy < y0:
                y0 = cy
            elif cy > y1:
                y1 = cy
            if cx < x0:
                x0 = cx
            elif cx > x1:
                x1 = cx
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not vis[ny, nx]:
                    vis[ny, nx] = True
                    q.append((ny, nx))
        if min_area <= area <= max_area:
            out.append((area, (x0, y0, x1, y1)))
    return out


def _cluster_words(
    boxes: list[tuple[int, int, int, int]],
    *,
    gap: float,
) -> list[list[tuple[int, int, int, int]]]:
    if not boxes:
        return []
    remaining = sorted(boxes, key=lambda b: (b[1], b[0]))
    words: list[list[tuple[int, int, int, int]]] = []
    while remaining:
        cur = [remaining.pop(0)]
        changed = True
        while changed:
            changed = False
            x0 = min(b[0] for b in cur)
            y0 = min(b[1] for b in cur)
            x1 = max(b[2] for b in cur)
            y1 = max(b[3] for b in cur)
            height = max(y1 - y0, 8)
            nxt: list[tuple[int, int, int, int]] = []
            for box in remaining:
                same_row = abs(((box[1] + box[3]) / 2) - ((y0 + y1) / 2)) < height * 0.7
                close = box[0] <= x1 + gap and box[2] >= x0 - gap
                if same_row and close:
                    cur.append(box)
                    changed = True
                else:
                    nxt.append(box)
            remaining = nxt
        words.append(cur)
    return words


def _angular_coverage(patch: np.ndarray, bins: int = 16) -> int:
    ys, xs = np.where(patch)
    if len(ys) < 20:
        return 0
    cy, cx = float(ys.mean()), float(xs.mean())
    dy = ys - cy
    dx = xs - cx
    radius = np.hypot(dx, dy)
    rmax = float(radius.max()) if len(radius) else 0.0
    if rmax < 4:
        return 0
    ring = (radius > rmax * 0.28) & (radius < rmax * 0.98)
    if int(ring.sum()) < 12:
        return 0
    angles = (np.arctan2(dy[ring], dx[ring]) + np.pi) / (2 * np.pi)
    hits = np.zeros(bins, dtype=bool)
    for a in angles:
        hits[min(bins - 1, int(a * bins))] = True
    return int(hits.sum())


def _nms_boxes(
    boxes: list[tuple[int, int, int, int]],
    *,
    iou: float,
) -> list[tuple[int, int, int, int]]:
    kept: list[tuple[int, int, int, int]] = []
    for box in sorted(boxes, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]), reverse=True):
        if _iou(box, kept) >= iou:
            continue
        kept.append(box)
    return kept


def _iou(box: tuple[int, int, int, int], others: list[tuple[int, int, int, int]]) -> float:
    x0, y0, x1, y1 = box
    best = 0.0
    area = max(1, (x1 - x0 + 1) * (y1 - y0 + 1))
    for ox0, oy0, ox1, oy1 in others:
        ix0, iy0 = max(x0, ox0), max(y0, oy0)
        ix1, iy1 = min(x1, ox1), min(y1, oy1)
        if ix1 < ix0 or iy1 < iy0:
            continue
        inter = (ix1 - ix0 + 1) * (iy1 - iy0 + 1)
        other = (ox1 - ox0 + 1) * (oy1 - oy0 + 1)
        best = max(best, inter / max(1, area + other - inter))
    return best
