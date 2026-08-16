"""JSON-serializable knobs for the battlemap importer (humans and agents)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any, Literal

PhaseName = Literal[
    "slice",
    "classify",
    "consistency",
    "adventure",
    "refine",
    "export",
    "all",
]
VlmProviderName = Literal["ollama", "openai", "anthropic", "mock", "heuristic"]

PHASES: tuple[str, ...] = (
    "slice",
    "classify",
    "consistency",
    "adventure",
    "refine",
    "export",
)


@dataclass
class ImportKnobs:
    image: str = ""
    width: int | None = None
    height: int | None = None
    tile_size: int | None = None
    image_offset_px: list[int] = field(default_factory=lambda: [0, 0])
    pad_ratio: float = 0.25
    provider: VlmProviderName = "heuristic"
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    confidence_threshold: float = 0.55
    max_tiles: int | None = None
    skip_vlm: bool = False
    include_mosaic: bool = True
    name: str = "Imported Map"
    description: str = ""
    map_id: str = ""
    background_image: str | None = None
    adventure_text: str = ""
    adventure_files: list[str] = field(default_factory=list)
    campaign: str | None = None
    illumination: float = 1.0
    timeout: int = 90
    calibrate_grid: bool = True
    split_panels: bool = True
    seed_map: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["api_key"] = "***" if self.api_key else None
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ImportKnobs":
        if not data:
            return cls()
        allowed = {item.name for item in fields(cls)}
        kwargs = {key: value for key, value in data.items() if key in allowed}
        knobs = cls(**kwargs)
        if knobs.skip_vlm:
            knobs.provider = "heuristic"
        return knobs


def knobs_json_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Natural20BattlemapImportKnobs",
        "type": "object",
        "additionalProperties": True,
        "description": (
            "Controls for importing a battlemap image into Natural20 map YAML. "
            "Slice the image into tiles, classify each tile (VLM + neighbor context), "
            "then overlay adventure-guide NPCs/notes/annotations."
        ),
        "properties": {
            "image": {"type": "string", "description": "Path to the battlemap image"},
            "width": {
                "type": ["integer", "null"],
                "minimum": 2,
                "maximum": 200,
                "description": "Grid width in tiles. Inferred from filename (e.g. map_22x17.png) or tile_size if omitted.",
            },
            "height": {
                "type": ["integer", "null"],
                "minimum": 2,
                "maximum": 200,
                "description": "Grid height in tiles.",
            },
            "tile_size": {
                "type": ["integer", "null"],
                "description": "Pixels per tile. Used to infer grid size when width/height omitted.",
            },
            "image_offset_px": {
                "type": "array",
                "items": {"type": "integer"},
                "minItems": 2,
                "maxItems": 2,
                "description": "Crop origin [x, y] before slicing (aligns art to the grid).",
            },
            "pad_ratio": {
                "type": "number",
                "minimum": 0,
                "maximum": 0.5,
                "description": "Extra neighboring pixels included in each tile crop so walls on edges are visible.",
            },
            "provider": {
                "type": "string",
                "enum": ["ollama", "openai", "anthropic", "mock", "heuristic"],
                "description": (
                    "VLM backend. heuristic = cheap PIL priors only (no network). "
                    "mock = deterministic classifier for tests. "
                    "ollama/openai/anthropic send each tile image to a vision model."
                ),
            },
            "model": {"type": ["string", "null"]},
            "confidence_threshold": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "description": "Tiles below this confidence are re-read with full neighbor context.",
            },
            "name": {"type": "string"},
            "description": {"type": "string"},
            "map_id": {"type": "string"},
            "adventure_text": {
                "type": "string",
                "description": "Adventure-guide excerpt used to place NPCs, notes, and area annotations.",
            },
            "adventure_files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Paths to markdown/text adventure notes to load.",
            },
            "campaign": {
                "type": ["string", "null"],
                "description": "Optional campaign root (user_levels/<name>) for output defaults.",
            },
            "illumination": {"type": "number", "minimum": 0, "maximum": 1},
            "calibrate_grid": {
                "type": "boolean",
                "description": (
                    "Nudge image_offset_px so inferred grid lines sit on dark ink. "
                    "Keeps tile size; only the origin shifts. Default true."
                ),
            },
            "split_panels": {
                "type": "boolean",
                "description": (
                    "Detect multiple floor plans on one page, crop each, and import "
                    "them as separate maps with independent grid alignment. Default true. "
                    "Disable when the image is already a single floor."
                ),
            },
            "seed_map": {
                "type": "string",
                "description": (
                    "Optional map YAML whose map.base seeds occupancy before the "
                    "per-tile VLM second opinion (e.g. a heuristic/color first pass)."
                ),
            },
        },
        "required": ["image"],
    }
