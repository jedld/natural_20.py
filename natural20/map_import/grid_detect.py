"""Infer square-grid tile size and origin from battlemap art (no filename dims)."""

from __future__ import annotations

from PIL import Image, ImageFilter, ImageOps

from natural20.map_import.dimensions import GridSpec
from natural20.map_import.ink import calibrate_grid_spec

ANALYSIS_MAX = 900
NATIVE_MIN = 12
NATIVE_MAX = 160


def detect_grid_spec(
    image: Image.Image,
    *,
    offset_px: tuple[int, int] | list[int] = (0, 0),
    calibrate: bool = True,
) -> GridSpec | None:
    """Return a GridSpec from edge autocorrelation, or None if no period is found."""
    rgb = image.convert("RGB")
    width, height = rgb.size
    scale = min(1.0, ANALYSIS_MAX / max(width, height))
    if scale < 0.999:
        small = rgb.resize(
            (max(1, int(width * scale)), max(1, int(height * scale))),
            Image.Resampling.BILINEAR,
        )
    else:
        small = rgb
        scale = 1.0
    gray = ImageOps.grayscale(small)
    edges = gray.filter(ImageFilter.FIND_EDGES)
    sw, sh = edges.size
    pix = edges.load()
    col = [sum(pix[x, y] for y in range(sh)) / max(1, sh) for x in range(sw)]
    row = [sum(pix[x, y] for x in range(sw)) / max(1, sw) for y in range(sh)]
    px = _best_period(col, scale)
    py = _best_period(row, scale)
    period = _agree_period(px, py)
    if period is None:
        return None
    offset_x = int(offset_px[0] if offset_px else 0)
    offset_y = int(offset_px[1] if offset_px else 0)
    usable_w = max(1, width - offset_x)
    usable_h = max(1, height - offset_y)
    gw = max(2, min(200, round(usable_w / period)))
    gh = max(2, min(200, round(usable_h / period)))
    spec = GridSpec(
        width=gw,
        height=gh,
        tile_w=usable_w / gw,
        tile_h=usable_h / gh,
        offset_x=offset_x,
        offset_y=offset_y,
        image_w=width,
        image_h=height,
        source="auto_grid",
    )
    if calibrate:
        spec = calibrate_grid_spec(rgb, spec, search=min(24, max(4, int(period * 0.45))), step=1)
        # Recompute tile counts after offset nudge so leftover margin is not a phantom column.
        usable_w = max(1, width - spec.offset_x)
        usable_h = max(1, height - spec.offset_y)
        period_x = spec.tile_w
        period_y = spec.tile_h
        gw = max(2, min(200, round(usable_w / period_x)))
        gh = max(2, min(200, round(usable_h / period_y)))
        spec = GridSpec(
            width=gw,
            height=gh,
            tile_w=usable_w / gw,
            tile_h=usable_h / gh,
            offset_x=spec.offset_x,
            offset_y=spec.offset_y,
            image_w=width,
            image_h=height,
            source=spec.source if "calibrate" in spec.source else "auto_grid+calibrate",
        )
    return spec


def _autocorr(series: list[float]) -> list[tuple[int, float]]:
    n = len(series)
    if n < 24:
        return []
    mean = sum(series) / n
    centered = [v - mean for v in series]
    energy = sum(v * v for v in centered) or 1.0
    out: list[tuple[int, float]] = []
    max_lag = min(n // 3, 220)
    for lag in range(6, max_lag):
        acc = sum(centered[i] * centered[i + lag] for i in range(n - lag))
        out.append((lag, acc / energy))
    return out


def _best_period(series: list[float], scale: float) -> float | None:
    scored: list[tuple[float, float]] = []
    for lag, score in _autocorr(series):
        period = lag / scale
        if NATIVE_MIN <= period <= NATIVE_MAX and score > 0.04:
            scored.append((score, period))
    if not scored:
        return None
    scored.sort(reverse=True)
    best_score, best_period = scored[0]
    # Prefer the fundamental when a harmonic (2x / 3x) scored highest.
    for harmonic in (2.0, 3.0):
        fundamental = best_period / harmonic
        if not (NATIVE_MIN <= fundamental <= NATIVE_MAX):
            continue
        for score, period in scored[1:8]:
            if abs(period - fundamental) / fundamental < 0.12 and score >= 0.32 * best_score:
                return period
    return best_period


def _agree_period(px: float | None, py: float | None) -> float | None:
    if px is None and py is None:
        return None
    if px is None:
        return py
    if py is None:
        return px
    if abs(px - py) / max(px, py) <= 0.18:
        return (px + py) / 2.0
    # Square grids: take the one closer to a common harmonic.
    for a, b in ((px, py), (px, py / 2), (px / 2, py), (px * 2, py), (px, py * 2)):
        if a <= 0 or b <= 0:
            continue
        if NATIVE_MIN <= a <= NATIVE_MAX and abs(a - b) / max(a, b) <= 0.12:
            return (a + b) / 2.0
    return (px + py) / 2.0
