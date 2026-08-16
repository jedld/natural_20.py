"""Cheap PIL priors for tile class. Used as VLM context and as a no-network fallback."""

from __future__ import annotations

from PIL import Image, ImageFilter, ImageStat

from natural20.map_import.ink import EdgeBits, detect_ink_edges
from natural20.map_import.model import TileFeatures
from natural20.map_import.taxonomy import ObjectSubtype, TileClass


def extract_features(tile: Image.Image) -> TileFeatures:
    features, _edges = extract_priors(tile)
    return features


def extract_priors(tile: Image.Image) -> tuple[TileFeatures, EdgeBits]:
    rgb = tile.convert("RGB")
    gray = rgb.convert("L")
    edges = gray.filter(ImageFilter.FIND_EDGES)
    stat = ImageStat.Stat(gray)
    edge_stat = ImageStat.Stat(edges)
    brightness = (stat.mean[0] or 0.0) / 255.0
    contrast = (stat.stddev[0] or 0.0) / 255.0
    edge_score = (edge_stat.mean[0] or 0.0) / 255.0

    pixels = gray.tobytes()
    n = max(1, len(pixels))
    dark_ratio = sum(1 for p in pixels if p < 55) / n

    w, h = gray.size
    border = []
    inset = max(1, min(w, h) // 8)
    for x in range(w):
        for y in range(h):
            if x < inset or y < inset or x >= w - inset or y >= h - inset:
                border.append(gray.getpixel((x, y)))
    border_dark_ratio = (sum(1 for p in border if p < 55) / max(1, len(border))) if border else dark_ratio

    hsv = rgb.convert("HSV")
    hsv_stat = ImageStat.Stat(hsv)
    hue = (hsv_stat.mean[0] or 0.0) / 255.0
    saturation = (hsv_stat.mean[1] or 0.0) / 255.0

    ink = detect_ink_edges(tile)
    tile_class, subtype, confidence = _guess(
        brightness=brightness,
        contrast=contrast,
        edge_score=edge_score,
        dark_ratio=dark_ratio,
        border_dark_ratio=border_dark_ratio,
        saturation=saturation,
        hue=hue,
        ink=ink,
    )
    features = TileFeatures(
        brightness=round(brightness, 4),
        contrast=round(contrast, 4),
        edge_score=round(edge_score, 4),
        dark_ratio=round(dark_ratio, 4),
        border_dark_ratio=round(border_dark_ratio, 4),
        hue=round(hue, 4),
        saturation=round(saturation, 4),
        heuristic_class=tile_class,
        heuristic_subtype=subtype,
        heuristic_confidence=round(confidence, 4),
        edge_n=ink.scores.get("N", 0.0),
        edge_e=ink.scores.get("E", 0.0),
        edge_s=ink.scores.get("S", 0.0),
        edge_w=ink.scores.get("W", 0.0),
    )
    return features, ink


def _guess(
    *,
    brightness: float,
    contrast: float,
    edge_score: float,
    dark_ratio: float,
    border_dark_ratio: float,
    saturation: float,
    hue: float,
    ink: EdgeBits | None = None,
) -> tuple[TileClass, ObjectSubtype, float]:
    bits = ink or EdgeBits()
    if bits.solid:
        return "wall", "none", 0.85
    if bits.any_door():
        return "door", "wooden_door", 0.72
    if bits.any_wall():
        return "wall", "none", 0.78
    # Very dark, low internal contrast → wall or void.
    if dark_ratio > 0.72 and contrast < 0.18:
        return "wall", "none", 0.72 if brightness < 0.22 else 0.55
    if brightness < 0.12 and contrast < 0.08:
        return "void", "none", 0.6
    # Blue-ish mid saturation → water
    if 0.45 < hue < 0.72 and saturation > 0.28 and brightness < 0.55:
        return "water", "none", 0.5
    # Brown-orange saturated blob with edges → door / wood furniture
    brown = hue < 0.12 or hue > 0.92
    if brown and saturation > 0.25 and 0.18 < brightness < 0.62 and edge_score > 0.08:
        if edge_score > 0.16 and contrast > 0.18:
            return "object", "chest", 0.42
        return "door", "wooden_door", 0.4
    # Bright uniform → floor
    if brightness > 0.35 and edge_score < 0.12 and dark_ratio < 0.25:
        return "floor", "none", 0.62
    if dark_ratio > 0.45:
        return "wall", "none", 0.4
    if edge_score > 0.18:
        return "object", "other", 0.35
    return "floor", "none", 0.35
