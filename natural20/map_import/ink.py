"""Detect thin ink walls on tile edges (published floorplans) and snap the grid.

Death House–style battlemaps draw walls as dark lines on the *edge* of a square
while the rest of the cell is floor. Cell-wise "is this a wall?" classification
misses those. This module scores N/E/S/W ink lines with PIL only.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from PIL import Image, ImageFilter, ImageOps

from natural20.map_import.dimensions import GridSpec

SIDES = ("N", "E", "S", "W")
OPPOSITE = {"N": "S", "S": "N", "E": "W", "W": "E"}
CANONICAL = 64
WALL_SCORE_MIN = 0.38
DOOR_GAP_MIN = 0.12
DOOR_GAP_MAX = 0.55


@dataclass
class EdgeBits:
    """Which edges of a tile are walls or doors."""

    N: bool = False
    E: bool = False
    S: bool = False
    W: bool = False
    door_N: bool = False
    door_E: bool = False
    door_S: bool = False
    door_W: bool = False
    scores: dict[str, float] = field(default_factory=dict)
    solid: bool = False

    def wall_tuple(self) -> tuple[int, int, int, int]:
        return int(self.N), int(self.E), int(self.S), int(self.W)

    def any_wall(self) -> bool:
        return bool(self.N or self.E or self.S or self.W or self.solid)

    def any_door(self) -> bool:
        return bool(self.door_N or self.door_E or self.door_S or self.door_W)

    def door_side(self) -> str | None:
        for side in SIDES:
            if getattr(self, f"door_{side}"):
                return side
        return None

    def set_wall(self, side: str, value: bool) -> None:
        setattr(self, side, bool(value))

    def summary(self) -> str:
        walls = "".join(s for s in SIDES if getattr(self, s))
        doors = "".join(s for s in SIDES if getattr(self, f"door_{s}"))
        extra = " solid" if self.solid else ""
        return f"walls={walls or '-'} doors={doors or '-'}{extra}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "N": self.N,
            "E": self.E,
            "S": self.S,
            "W": self.W,
            "door_N": self.door_N,
            "door_E": self.door_E,
            "door_S": self.door_S,
            "door_W": self.door_W,
            "scores": {k: round(float(v), 4) for k, v in self.scores.items()},
            "solid": self.solid,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "EdgeBits":
        if not data:
            return cls()
        bits = cls(
            N=bool(data.get("N")),
            E=bool(data.get("E")),
            S=bool(data.get("S")),
            W=bool(data.get("W")),
            door_N=bool(data.get("door_N")),
            door_E=bool(data.get("door_E")),
            door_S=bool(data.get("door_S")),
            door_W=bool(data.get("door_W")),
            scores=dict(data.get("scores") or {}),
            solid=bool(data.get("solid")),
        )
        return bits


def detect_ink_edges(tile: Image.Image, *, threshold: int = 72) -> EdgeBits:
    """Score thin dark lines on each edge of a tile.

    Compares a rim strip to an inset parallel strip so wood grain / floor
    texture does not count as a wall.
    """
    gray = ImageOps.grayscale(tile.convert("RGB"))
    if min(gray.size) < 8:
        return EdgeBits()
    gray = gray.resize((CANONICAL, CANONICAL), Image.Resampling.BILINEAR)
    # Slight blur so 1px print lines still register after resize.
    gray = gray.filter(ImageFilter.SMOOTH)
    pixels = gray.load()
    band = 8
    inset_at = 18
    bits = EdgeBits()

    interior = []
    for y in range(band + 2, CANONICAL - band - 2):
        for x in range(band + 2, CANONICAL - band - 2):
            interior.append(pixels[x, y])
    interior_mean = (sum(interior) / len(interior)) if interior else 200
    interior_dark = sum(1 for p in interior if p < threshold) / max(1, len(interior))
    bits.solid = interior_dark > 0.58 and interior_mean < 90
    if bits.solid:
        bits.N = bits.E = bits.S = bits.W = True
        bits.scores = {s: 1.0 for s in SIDES}
        return bits

    profiles: dict[str, list[int]] = {}
    for side in SIDES:
        rim, inner = _edge_profile(pixels, side, band=band, inset_at=inset_at)
        profiles[side] = rim
        # Higher score = rim much darker than the inset (a line, not fill).
        rim_dark = _dark_line_score(rim, threshold)
        inner_dark = _dark_line_score(inner, threshold)
        contrast = max(0.0, (sum(inner) / max(1, len(inner)) - sum(rim) / max(1, len(rim))) / 255.0)
        score = max(0.0, rim_dark - 0.45 * inner_dark) + 0.55 * contrast
        bits.scores[side] = round(min(1.0, score), 4)
        is_wall = score >= WALL_SCORE_MIN and rim_dark >= 0.32
        bits.set_wall(side, is_wall)
        if is_wall:
            gap = _central_gap_fraction(rim, threshold)
            if DOOR_GAP_MIN <= gap <= DOOR_GAP_MAX:
                setattr(bits, f"door_{side}", True)

    _drop_weakest_if_crowded(bits)
    return bits


def _edge_profile(pixels, side: str, *, band: int, inset_at: int) -> tuple[list[int], list[int]]:
    """Min brightness in the rim band and in a parallel inset strip, along the edge."""
    rim: list[int] = []
    inner: list[int] = []
    n = CANONICAL
    for i in range(n):
        if side == "N":
            rim.append(min(pixels[i, y] for y in range(band)))
            inner.append(min(pixels[i, y] for y in range(inset_at, inset_at + band)))
        elif side == "S":
            rim.append(min(pixels[i, n - 1 - y] for y in range(band)))
            inner.append(min(pixels[i, n - 1 - inset_at - y] for y in range(band)))
        elif side == "W":
            rim.append(min(pixels[x, i] for x in range(band)))
            inner.append(min(pixels[x, i] for x in range(inset_at, inset_at + band)))
        else:  # E
            rim.append(min(pixels[n - 1 - x, i] for x in range(band)))
            inner.append(min(pixels[n - 1 - inset_at - x, i] for x in range(band)))
    return rim, inner


def _dark_line_score(profile: list[int], threshold: int) -> float:
    if not profile:
        return 0.0
    return sum(1 for p in profile if p < threshold) / len(profile)


def _central_gap_fraction(profile: list[int], threshold: int) -> float:
    """Longest bright run in the middle 70% of an edge, as a fraction of the edge."""
    n = len(profile)
    if n < 8:
        return 0.0
    lo, hi = int(n * 0.15), int(n * 0.85)
    best = cur = 0
    for p in profile[lo:hi]:
        if p >= threshold + 20:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best / n


def _drop_weakest_if_crowded(bits: EdgeBits) -> None:
    """Keep at most two wall edges unless the tile is a solid fill (T-junctions → strongest pair)."""
    active = [s for s in SIDES if getattr(bits, s)]
    if len(active) <= 2:
        return
    ranked = sorted(
        active,
        key=lambda s: (1 if getattr(bits, f"door_{s}") else 0, bits.scores.get(s, 0.0)),
        reverse=True,
    )
    for side in ranked[2:]:
        bits.set_wall(side, False)
        setattr(bits, f"door_{side}", False)


def merge_vlm_edges(cv: EdgeBits, data: dict[str, Any]) -> EdgeBits:
    """Union CV ink lines with VLM wall/door dicts."""
    walls = data.get("walls") if isinstance(data.get("walls"), dict) else {}
    doors = data.get("doors") if isinstance(data.get("doors"), dict) else {}
    out = EdgeBits(
        scores=dict(cv.scores),
        solid=cv.solid or bool(data.get("solid_wall")),
    )
    for side in SIDES:
        cv_wall = getattr(cv, side)
        vlm_wall = _truthy(walls.get(side))
        out.set_wall(side, cv_wall or vlm_wall)
        cv_door = getattr(cv, f"door_{side}")
        vlm_door = _truthy(doors.get(side))
        setattr(out, f"door_{side}", bool(cv_door or vlm_door))
        if getattr(out, f"door_{side}"):
            out.set_wall(side, True)
    if out.solid:
        out.N = out.E = out.S = out.W = True
    else:
        _drop_weakest_if_crowded(out)
    return out


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "wall", "door"}
    return bool(value)


def class_from_edges(bits: EdgeBits) -> tuple[str, str] | None:
    """Return (tile_class, orientation) implied by ink/VLM edges, or None."""
    if bits.solid:
        return "wall", "none"
    if bits.any_door():
        side = bits.door_side()
        orientation = "vertical" if side in {"E", "W"} else "horizontal"
        return "door", orientation
    if bits.any_wall():
        return "wall", "none"
    return None


def apply_edges_to_record(tile: Any) -> None:
    """Overwrite tile_class when edge occupancy is a wall or door."""
    if any(str(flag).startswith("overlay:") for flag in (getattr(tile, "flags", None) or [])):
        return
    kind = class_from_edges(tile.edges)
    if kind is None:
        return
    cls, orientation = kind
    tile.tile_class = cls
    if cls == "door":
        if tile.subtype in {"none", "other"}:
            tile.subtype = "wooden_door"
        if not tile.orientation or tile.orientation == "none":
            tile.orientation = orientation
    elif cls == "wall" and tile.subtype == "wooden_door":
        tile.subtype = "none"


def reconcile_adjacent_edges(grid_tiles, width: int, height: int, *, threshold: float = 0.34) -> int:
    """Agree on shared edges without turning neighboring floor cells into walls.

    The wall token lives on the cell that already has ink; the opposite floor
    cell is left walkable (Death House–style perimeter).
    """
    edits = 0

    def bits_at(x: int, y: int) -> EdgeBits:
        return grid_tiles[x][y].edges

    def fill_owners(here: EdgeBits, here_side: str, other: EdgeBits, other_side: str) -> int:
        here_score = here.scores.get(here_side, 0.0)
        other_score = other.scores.get(other_side, 0.0)
        line = (
            here_score >= threshold
            or other_score >= threshold
            or getattr(here, here_side)
            or getattr(other, other_side)
        )
        if not line:
            return 0
        changed = 0
        here_owner = here.any_wall() or here.any_door()
        other_owner = other.any_wall() or other.any_door()
        if here_owner and not getattr(here, here_side) and (here_score >= other_score or not other_owner):
            here.set_wall(here_side, True)
            changed += 1
        if other_owner and not getattr(other, other_side) and (other_score >= here_score or not here_owner):
            other.set_wall(other_side, True)
            changed += 1
        return changed

    for y in range(height):
        for x in range(width):
            here = bits_at(x, y)
            if x + 1 < width:
                edits += fill_owners(here, "E", bits_at(x + 1, y), "W")
            if y + 1 < height:
                edits += fill_owners(here, "S", bits_at(x, y + 1), "N")
    return edits


def rehome_outline_edges(grid_tiles, width: int, height: int) -> int:
    """Move ink on parchment/margin cells onto the inward neighbor.

    Floorplan art often draws the outer wall on the shared edge between an empty
    margin tile and the first room tile. Natural20 puts the wall token on the
    room tile (Death House row/column 1, not 0).
    """
    edits = 0

    def parchment(x: int, y: int) -> bool:
        tile = grid_tiles[x][y]
        bits = tile.edges
        if bits.solid:
            return False
        feat = getattr(tile, "features", None)
        if feat is None:
            return True
        return feat.brightness >= 0.48 and feat.dark_ratio < 0.28 and not bits.solid

    def transfer(src: EdgeBits, src_side: str, dest: EdgeBits, dest_side: str) -> bool:
        if not getattr(src, src_side) and not getattr(src, f"door_{src_side}"):
            return False
        dest.set_wall(dest_side, True)
        dest.scores[dest_side] = max(dest.scores.get(dest_side, 0.0), src.scores.get(src_side, 0.0))
        if getattr(src, f"door_{src_side}"):
            setattr(dest, f"door_{dest_side}", True)
        src.set_wall(src_side, False)
        setattr(src, f"door_{src_side}", False)
        return True

    if width >= 2:
        for y in range(height):
            if parchment(0, y):
                if transfer(grid_tiles[0][y].edges, "E", grid_tiles[1][y].edges, "W"):
                    edits += 1
            if parchment(width - 1, y):
                if transfer(grid_tiles[width - 1][y].edges, "W", grid_tiles[width - 2][y].edges, "E"):
                    edits += 1
    if height >= 2:
        for x in range(width):
            if parchment(x, 0):
                if transfer(grid_tiles[x][0].edges, "S", grid_tiles[x][1].edges, "N"):
                    edits += 1
            if parchment(x, height - 1):
                if transfer(grid_tiles[x][height - 1].edges, "N", grid_tiles[x][height - 2].edges, "S"):
                    edits += 1

    def clear_margin(x: int, y: int) -> bool:
        if not parchment(x, y):
            return False
        tile = grid_tiles[x][y]
        bits = tile.edges
        changed = bool(bits.any_wall() or bits.any_door() or tile.tile_class in {"wall", "door"})
        bits.N = bits.E = bits.S = bits.W = False
        bits.door_N = bits.door_E = bits.door_S = bits.door_W = False
        if tile.tile_class in {"wall", "door"}:
            tile.tile_class = "floor"
            tile.subtype = "none"
            tile.orientation = "none"
        return changed

    if width >= 2:
        for y in range(height):
            if clear_margin(0, y):
                edits += 1
            if clear_margin(width - 1, y):
                edits += 1
    if height >= 2:
        for x in range(width):
            if clear_margin(x, 0):
                edits += 1
            if clear_margin(x, height - 1):
                edits += 1
    return edits


def calibrate_grid_spec(
    image: Image.Image,
    spec: GridSpec,
    *,
    search: int = 18,
    step: int = 2,
) -> GridSpec:
    """Nudge offset so predicted grid lines sit on dark ink."""
    gray = ImageOps.grayscale(image.convert("RGB"))
    best = spec
    best_score = _grid_line_score(gray, spec)
    radius = max(0, int(search))
    if radius == 0:
        return spec
    for dy in range(-radius, radius + 1, step):
        for dx in range(-radius, radius + 1, step):
            if dx == 0 and dy == 0:
                continue
            candidate = replace(
                spec,
                offset_x=spec.offset_x + dx,
                offset_y=spec.offset_y + dy,
                source=f"{spec.source}+calibrate",
            )
            score = _grid_line_score(gray, candidate)
            if score > best_score:
                best_score = score
                best = candidate
    return best


def _grid_line_score(gray: Image.Image, spec: GridSpec) -> float:
    """Darkness along interior grid lines minus darkness at cell centers."""
    w, h = gray.size
    pixels = gray.load()

    def col_samples(x: float, step: int = 2) -> list[int]:
        xi = int(round(x))
        if xi < 0 or xi >= w:
            return []
        y0 = max(0, spec.offset_y)
        y1 = min(h, int(spec.offset_y + spec.height * spec.tile_h))
        return [pixels[xi, y] for y in range(y0, y1, step)]

    def row_samples(y: float, step: int = 2) -> list[int]:
        yi = int(round(y))
        if yi < 0 or yi >= h:
            return []
        x0 = max(0, spec.offset_x)
        x1 = min(w, int(spec.offset_x + spec.width * spec.tile_w))
        return [pixels[x, yi] for x in range(x0, x1, step)]

    lines: list[int] = []
    for i in range(1, spec.width):
        lines.extend(col_samples(spec.offset_x + i * spec.tile_w))
    for j in range(1, spec.height):
        lines.extend(row_samples(spec.offset_y + j * spec.tile_h))
    mids: list[int] = []
    for i in range(spec.width):
        mids.extend(col_samples(spec.offset_x + (i + 0.5) * spec.tile_w, step=4))
    for j in range(spec.height):
        mids.extend(row_samples(spec.offset_y + (j + 0.5) * spec.tile_h, step=4))

    def mean_dark(xs: list[int]) -> float:
        if not xs:
            return 0.0
        return 1.0 - (sum(xs) / len(xs) / 255.0)

    return mean_dark(lines) - 0.35 * mean_dark(mids)
