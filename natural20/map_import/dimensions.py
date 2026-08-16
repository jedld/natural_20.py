"""Infer battlemap grid dimensions from flags, filename, or pixel size."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

_DIM_PATTERNS = (
    re.compile(r"(?P<w>\d+)\s*[xX×]\s*(?P<h>\d+)"),
    re.compile(r"(?P<w>\d+)\s*[xX×by]\s*(?P<h>\d+)\s*(?:tiles?|grid|map)?", re.I),
    re.compile(r"(?:grid|tiles?|size)[-_ ]?(?P<w>\d+)[-_xX×](?P<h>\d+)", re.I),
)


@dataclass(frozen=True)
class GridSpec:
    width: int
    height: int
    tile_w: float
    tile_h: float
    offset_x: int
    offset_y: int
    image_w: int
    image_h: int
    source: str

    def to_dict(self) -> dict:
        return {
            "width": self.width,
            "height": self.height,
            "tile_w": round(self.tile_w, 3),
            "tile_h": round(self.tile_h, 3),
            "offset_x": self.offset_x,
            "offset_y": self.offset_y,
            "image_w": self.image_w,
            "image_h": self.image_h,
            "source": self.source,
        }


def parse_dimensions_from_name(path: str | Path) -> tuple[int, int] | None:
    """Parse `foo_22x17.png`, `map-40x30-grid.webp`, `Tavern 24 x 18.jpg`."""
    text = Path(path).stem
    for pattern in _DIM_PATTERNS:
        match = pattern.search(text)
        if match:
            width = int(match.group("w"))
            height = int(match.group("h"))
            if 2 <= width <= 200 and 2 <= height <= 200:
                return width, height
    return None


def infer_grid_spec(
    image_path: str | Path,
    *,
    width: int | None = None,
    height: int | None = None,
    tile_size: int | None = None,
    offset_px: tuple[int, int] | list[int] = (0, 0),
    image: Image.Image | None = None,
) -> GridSpec:
    image = Image.open(image_path) if image is None else image
    image_w, image_h = image.size
    offset_x = int(offset_px[0] if offset_px else 0)
    offset_y = int(offset_px[1] if offset_px else 0)
    usable_w = max(1, image_w - offset_x)
    usable_h = max(1, image_h - offset_y)
    source = "explicit"

    if width and height:
        source = "explicit"
    elif tile_size:
        width = max(2, round(usable_w / tile_size))
        height = max(2, round(usable_h / tile_size))
        source = "tile_size"
    else:
        parsed = parse_dimensions_from_name(image_path)
        if parsed:
            width, height = parsed
            source = "filename"
        else:
            from natural20.map_import.grid_detect import detect_grid_spec

            auto = detect_grid_spec(
                image if image is not None else Image.open(image_path),
                offset_px=(offset_x, offset_y),
                calibrate=False,
            )
            if auto is not None:
                return auto
            raise ValueError(
                "Could not infer grid size. Pass --width and --height, --tile-size, "
                "or name the file like tavern_22x17.png."
            )

    assert width is not None and height is not None
    if width < 2 or height < 2:
        raise ValueError(f"Grid too small: {width}x{height}")
    return GridSpec(
        width=int(width),
        height=int(height),
        tile_w=usable_w / width,
        tile_h=usable_h / height,
        offset_x=offset_x,
        offset_y=offset_y,
        image_w=image_w,
        image_h=image_h,
        source=source,
    )
