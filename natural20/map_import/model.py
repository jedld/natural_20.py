"""Shared data model for battlemap import."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from natural20.map_import.ink import EdgeBits
from natural20.map_import.taxonomy import ObjectSubtype, TileClass


@dataclass
class TileFeatures:
    brightness: float = 0.0
    contrast: float = 0.0
    edge_score: float = 0.0
    dark_ratio: float = 0.0
    border_dark_ratio: float = 0.0
    hue: float = 0.0
    saturation: float = 0.0
    heuristic_class: TileClass = "unknown"
    heuristic_subtype: ObjectSubtype = "none"
    heuristic_confidence: float = 0.0
    edge_n: float = 0.0
    edge_e: float = 0.0
    edge_s: float = 0.0
    edge_w: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "TileFeatures":
        if not data:
            return cls()
        known = {k: data[k] for k in cls.__dataclass_fields__ if k in data}
        return cls(**known)


@dataclass
class TileRecord:
    x: int
    y: int
    tile_class: TileClass = "unknown"
    subtype: ObjectSubtype = "none"
    orientation: str = "none"
    confidence: float = 0.0
    description: str = ""
    source: str = "unclassified"
    features: TileFeatures = field(default_factory=TileFeatures)
    edges: EdgeBits = field(default_factory=EdgeBits)
    raw_response: str = ""
    flags: list[str] = field(default_factory=list)

    @property
    def pos(self) -> tuple[int, int]:
        return self.x, self.y

    def neighbor_summary(self) -> str:
        label = self.tile_class
        if self.subtype not in {"none", "other"}:
            label = f"{label}/{self.subtype}"
        extra = f" {self.edges.summary()}" if self.edges.any_wall() or self.edges.any_door() else ""
        return f"{label}@{self.confidence:.2f}{extra}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "x": self.x,
            "y": self.y,
            "class": self.tile_class,
            "subtype": self.subtype,
            "orientation": self.orientation,
            "confidence": round(self.confidence, 4),
            "description": self.description,
            "source": self.source,
            "features": self.features.to_dict(),
            "edges": self.edges.to_dict(),
            "raw_response": self.raw_response,
            "flags": list(self.flags),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TileRecord":
        return cls(
            x=int(data["x"]),
            y=int(data["y"]),
            tile_class=data.get("class") or data.get("tile_class") or "unknown",
            subtype=data.get("subtype") or "none",
            orientation=data.get("orientation") or "none",
            confidence=float(data.get("confidence") or 0.0),
            description=str(data.get("description") or ""),
            source=str(data.get("source") or "unclassified"),
            features=TileFeatures.from_dict(data.get("features")),
            edges=EdgeBits.from_dict(data.get("edges")),
            raw_response=str(data.get("raw_response") or ""),
            flags=list(data.get("flags") or []),
        )


@dataclass
class ClassificationGrid:
    width: int
    height: int
    tiles: list[list[TileRecord]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.tiles:
            return
        self.tiles = [
            [TileRecord(x=x, y=y) for y in range(self.height)]
            for x in range(self.width)
        ]

    def get(self, x: int, y: int) -> TileRecord | None:
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            return None
        return self.tiles[x][y]

    def set(self, record: TileRecord) -> None:
        self.tiles[record.x][record.y] = record

    def neighbors(self, x: int, y: int, *, diagonal: bool = True) -> list[TileRecord]:
        found: list[TileRecord] = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                if not diagonal and dx != 0 and dy != 0:
                    continue
                tile = self.get(x + dx, y + dy)
                if tile:
                    found.append(tile)
        return found

    def cardinal(self, x: int, y: int) -> dict[str, TileRecord | None]:
        return {
            "N": self.get(x, y - 1),
            "E": self.get(x + 1, y),
            "S": self.get(x, y + 1),
            "W": self.get(x - 1, y),
        }

    def ascii_map(self, *, show_objects: bool = True) -> str:
        rows: list[str] = []
        for y in range(self.height):
            chars: list[str] = []
            for x in range(self.width):
                tile = self.tiles[x][y]
                chars.append(_ascii_char(tile, show_objects=show_objects))
            rows.append("".join(chars))
        return "\n".join(rows)

    def identification_log(self) -> list[dict[str, Any]]:
        log: list[dict[str, Any]] = []
        for y in range(self.height):
            for x in range(self.width):
                log.append(self.tiles[x][y].to_dict())
        return log

    def uncertain(self, threshold: float) -> list[TileRecord]:
        found: list[TileRecord] = []
        for y in range(self.height):
            for x in range(self.width):
                tile = self.tiles[x][y]
                if tile.confidence < threshold or tile.tile_class == "unknown":
                    found.append(tile)
        return found

    def to_dict(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "ascii": self.ascii_map(),
            "tiles": self.identification_log(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ClassificationGrid":
        grid = cls(width=int(data["width"]), height=int(data["height"]))
        for item in data.get("tiles") or []:
            record = TileRecord.from_dict(item)
            if 0 <= record.x < grid.width and 0 <= record.y < grid.height:
                grid.set(record)
        return grid


def _ascii_char(tile: TileRecord, *, show_objects: bool) -> str:
    from natural20.map_import.taxonomy import mapping_for

    if tile.edges.any_door() or tile.tile_class == "door" or tile.subtype == "wooden_door":
        mapping = mapping_for(tile.tile_class, tile.subtype, orientation=tile.orientation, edges=tile.edges)
        return mapping.base_token
    if tile.edges.any_wall() or tile.tile_class == "wall" or tile.subtype == "column":
        mapping = mapping_for("wall", edges=tile.edges)
        return mapping.base_token
    if tile.tile_class == "void":
        return "_"
    if tile.tile_class == "water":
        return "w"
    if show_objects and tile.subtype not in {"none", "other"}:
        return {
            "chest": "c",
            "barrel": "b",
            "table": "T",
            "chair": "h",
            "bed": "B",
            "fireplace": "f",
            "campfire": "f",
            "tree": "t",
            "pit": "P",
            "window": "W",
            "stairs": "S",
            "switch": "s",
            "note": "n",
        }.get(tile.subtype, "*")
    return "."
