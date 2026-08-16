"""Slice a battlemap image into per-tile crops (with optional neighbor padding)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from natural20.map_import.dimensions import GridSpec


def tile_box(spec: GridSpec, x: int, y: int, *, pad_ratio: float = 0.0) -> tuple[int, int, int, int]:
    left = spec.offset_x + x * spec.tile_w
    top = spec.offset_y + y * spec.tile_h
    right = spec.offset_x + (x + 1) * spec.tile_w
    bottom = spec.offset_y + (y + 1) * spec.tile_h
    pad_x = spec.tile_w * pad_ratio
    pad_y = spec.tile_h * pad_ratio
    box = (
        int(round(left - pad_x)),
        int(round(top - pad_y)),
        int(round(right + pad_x)),
        int(round(bottom + pad_y)),
    )
    return (
        max(0, box[0]),
        max(0, box[1]),
        min(spec.image_w, box[2]),
        min(spec.image_h, box[3]),
    )


def crop_tile(image: Image.Image, spec: GridSpec, x: int, y: int, *, pad_ratio: float = 0.0) -> Image.Image:
    return image.crop(tile_box(spec, x, y, pad_ratio=pad_ratio)).convert("RGB")


def slice_tiles(
    image_path: str | Path,
    spec: GridSpec,
    *,
    dest_dir: str | Path | None = None,
    pad_ratio: float = 0.25,
) -> dict[tuple[int, int], Path | None]:
    """Crop every tile. When dest_dir is set, write `<x>_<y>.png` and padded copies."""
    image = Image.open(image_path).convert("RGB")
    written: dict[tuple[int, int], Path | None] = {}
    dest = Path(dest_dir) if dest_dir else None
    padded_dir = dest / "padded" if dest else None
    if dest:
        dest.mkdir(parents=True, exist_ok=True)
        if padded_dir:
            padded_dir.mkdir(parents=True, exist_ok=True)

    for y in range(spec.height):
        for x in range(spec.width):
            exact = crop_tile(image, spec, x, y, pad_ratio=0.0)
            path: Path | None = None
            if dest:
                path = dest / f"{x}_{y}.png"
                exact.save(path)
                if pad_ratio > 0 and padded_dir:
                    crop_tile(image, spec, x, y, pad_ratio=pad_ratio).save(padded_dir / f"{x}_{y}.png")
            written[(x, y)] = path
    return written


def mosaic_neighborhood(
    image: Image.Image,
    spec: GridSpec,
    x: int,
    y: int,
    *,
    radius: int = 1,
    cell_size: int = 64,
) -> Image.Image:
    """3x3 (or larger) collage of neighboring tiles with the center tile outlined."""
    size = 2 * radius + 1
    canvas = Image.new("RGB", (size * cell_size, size * cell_size), (20, 20, 20))
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            nx, ny = x + dx, y + dy
            px = (dx + radius) * cell_size
            py = (dy + radius) * cell_size
            if 0 <= nx < spec.width and 0 <= ny < spec.height:
                tile = crop_tile(image, spec, nx, ny, pad_ratio=0.0).resize(
                    (cell_size, cell_size), Image.Resampling.LANCZOS
                )
            else:
                tile = Image.new("RGB", (cell_size, cell_size), (8, 8, 8))
            canvas.paste(tile, (px, py))
    # Red border around the center cell.
    from PIL import ImageDraw

    draw = ImageDraw.Draw(canvas)
    cx = radius * cell_size
    cy = radius * cell_size
    draw.rectangle([cx + 1, cy + 1, cx + cell_size - 2, cy + cell_size - 2], outline=(220, 40, 40), width=3)
    return canvas
