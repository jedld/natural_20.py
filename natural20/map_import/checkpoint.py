"""Inspectable workdir for humans and agents (resume between phases)."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from natural20.map_import.dimensions import GridSpec
from natural20.map_import.export import dump_map_yaml
from natural20.map_import.knobs import ImportKnobs
from natural20.map_import.model import ClassificationGrid

PHASE_FILE = {
    "slice": "slice.json",
    "classify": "classifications.json",
    "consistency": "consistency.json",
    "adventure": "adventure.json",
    "refine": "refine.json",
    "export": "map.yml",
}


@dataclass
class Workdir:
    path: Path

    def __post_init__(self) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        (self.path / "tiles").mkdir(exist_ok=True)

    def write_json(self, name: str, data: Any) -> Path:
        dest = self.path / name
        dest.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return dest

    def read_json(self, name: str) -> Any | None:
        dest = self.path / name
        if not dest.exists():
            return None
        return json.loads(dest.read_text(encoding="utf-8"))

    def has_phase(self, phase: str) -> bool:
        name = PHASE_FILE.get(phase)
        return bool(name and (self.path / name).exists())

    def save_knobs(self, knobs: ImportKnobs) -> None:
        self.write_json("knobs.json", knobs.to_dict())

    def save_grid_spec(self, spec: GridSpec) -> None:
        self.write_json("grid_spec.json", spec.to_dict())

    def load_grid_spec(self) -> dict[str, Any] | None:
        return self.read_json("grid_spec.json")

    def save_grid(self, grid: ClassificationGrid) -> None:
        self.write_json("classifications.json", grid.to_dict())
        (self.path / "ascii.txt").write_text(grid.ascii_map() + "\n", encoding="utf-8")

    def load_grid(self) -> ClassificationGrid | None:
        data = self.read_json("classifications.json")
        if not data:
            return None
        return ClassificationGrid.from_dict(data)

    def save_map(self, properties: dict[str, Any]) -> Path:
        dest = self.path / "map.yml"
        dest.write_text(dump_map_yaml(properties), encoding="utf-8")
        self.write_json("map.json", properties)
        return dest

    def copy_image(self, image_path: str | Path) -> Path:
        src = Path(image_path)
        dest = self.path / src.name
        if src.resolve() != dest.resolve():
            shutil.copy2(src, dest)
        return dest
