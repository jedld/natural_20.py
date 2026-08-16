"""Cross-reference adventure-guide text with the classified map."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from natural20.map_import.json_util import parse_json_object
from natural20.map_import.model import ClassificationGrid
from natural20.map_import.overlays import OverlayReport, flood_room, room_bounds
from natural20.map_import.vlm import HeuristicClient, VlmClient

ADVENTURE_SYSTEM = """You are adapting an adventure guide onto a Natural20 battlemap.
You receive an ASCII transcription of the map, printed room keys from the art,
and adventure text. Place only features the text actually describes.
Coordinates are 0-based [x, y] with origin at the top-left of the ASCII.

Return JSON only:
{
  "spawn": [x, y],
  "npcs": [
    {"name": "short name", "sub_type": "goblin", "pos": [x, y], "group": "b", "reason": "why here"}
  ],
  "objects": [
    {"type": "chest", "name": "label", "pos": [x, y], "notes": "optional", "reason": ""}
  ],
  "notes": [
    {"pos": [x, y], "text": "player-visible note", "reason": ""}
  ],
  "annotations": [
    {"id": "slug", "label": "Room name", "description": "one sentence", "kind": "area",
     "bounds": {"x1": 0, "y1": 0, "x2": 4, "y2": 3}}
  ],
  "fixes": [
    {"x": 0, "y": 0, "class": "floor", "subtype": "none", "reason": "text says this is open"}
  ],
  "unplaced": ["features mentioned in the text that have no plausible tile"]
}

Rules:
- Printed keys (a, b, c, …) match adventure headings like "E5a. Hall" or "Area B".
  Place each NPC/object inside the bounds listed for that key. Do not guess a
  different room when a key match exists.
- sub_type for NPCs must be a Natural20 npc template slug when possible (goblin, skeleton, wolf, human_guard, acolyte, vampire_spawn, ...).
- object type must be one of: chest, barrel, campfire, tree, window, note, switch, water, wooden_door, brazier, bottomless_pit, chasm.
- Place NPCs and objects on floor tiles ('.'), never on '#'.
- kind for annotations: area (bounds), point (pos: [x,y]), or polygon (points).
- Prefer a few high-confidence placements over guessing every prop.
- Do not treat printed titles, compass roses, or circled letters as walls or furniture.
"""

ALLOWED_OBJECT_TYPES = {
    "chest",
    "barrel",
    "campfire",
    "tree",
    "window",
    "note",
    "switch",
    "water",
    "wooden_door",
    "brazier",
    "bottomless_pit",
    "chasm",
}

_HEADING = re.compile(
    r"(?m)^(?:#{1,6}|\*\*)\s*(?P<code>[A-Za-z]?\d+[A-Za-z]?|[A-Za-z]\d+[A-Za-z]?|[A-Za-z])\.\s+"
    r"(?P<title>[^\n*]+?)(?:\*\*)?\s*$"
)
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_NAMED_STATBLOCK = re.compile(
    r"([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?)\s*\([^)]*\*\*([^*]+)\*\*"
)
_OBJECT_HINTS = (
    ("trapdoor", "note", "Trapdoor"),
    ("chest", "chest", "Chest"),
    ("altar", "note", "Altar"),
    ("cabinet", "barrel", "Cabinet"),
    ("bookshelf", "barrel", "Bookshelf"),
    ("bed", "barrel", "Bed"),
    ("desk", "barrel", "Desk"),
    ("rope", "note", "Rope"),
    ("stairs", "note", "Stairs"),
    ("ladder", "note", "Ladder"),
    ("window", "window", "Window"),
)

_NPC_SLUGS = {
    "acolyte": "acolyte",
    "vampire spawn": "vampire_spawn",
    "vampire_spawn": "vampire_spawn",
    "goblin": "goblin",
    "skeleton": "skeleton",
    "zombie": "zombie",
    "wolf": "wolf",
    "guard": "human_guard",
    "human guard": "human_guard",
    "commoner": "commoner",
    "noble": "noble",
    "spy": "spy",
    "veteran": "veteran",
    "ogre": "ogre",
    "bugbear": "bugbear",
    "hobgoblin": "hobgoblin",
    "specter": "specter",
    "ghost": "specter",
    "bat": "bat",
    "rat": "giant_rat",
    "priest": "acolyte",
}


@dataclass
class KeyedArea:
    code: str
    letter: str
    title: str
    body: str

    def excerpt(self, limit: int = 280) -> str:
        text = " ".join((self.body or "").split())
        return text[:limit]


def load_adventure_text(knobs_adventure_text: str, files: list[str] | None) -> str:
    chunks: list[str] = []
    if knobs_adventure_text:
        chunks.append(knobs_adventure_text.strip())
    for path in files or []:
        text = Path(path).read_text(encoding="utf-8")
        chunks.append(f"## {Path(path).name}\n{text.strip()}")
    return "\n\n".join(chunks).strip()


def parse_keyed_areas(adventure_text: str) -> list[KeyedArea]:
    """Headings like `#### E5a. Hall` or `**A. Nave**` plus the following body."""
    matches = list(_HEADING.finditer(adventure_text or ""))
    areas: list[KeyedArea] = []
    for i, match in enumerate(matches):
        code = match.group("code").strip()
        letter = letter_from_code(code)
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(adventure_text)
        areas.append(
            KeyedArea(
                code=code,
                letter=letter,
                title=match.group("title").strip(),
                body=adventure_text[start:end].strip(),
            )
        )
    return areas


def letter_from_code(code: str) -> str:
    text = (code or "").strip()
    trailing = re.search(r"([A-Za-z]+)$", text)
    if trailing and re.search(r"\d", text):
        letters = trailing.group(1)
        if len(letters) == 1:
            return letters.lower()
        return ""
    if len(text) == 1 and text.isalpha():
        return text.lower()
    return ""


def apply_adventure_overlay(
    grid: ClassificationGrid,
    properties: dict[str, Any],
    adventure_text: str,
    client: VlmClient,
    *,
    overlays: OverlayReport | None = None,
) -> dict[str, Any]:
    """Mutate map properties with NPCs, notes, annotations from adventure text."""
    report: dict[str, Any] = {
        "applied": False,
        "npcs": 0,
        "objects": 0,
        "notes": 0,
        "annotations": 0,
        "unplaced": [],
        "keys": [],
    }
    if not adventure_text.strip() and not (overlays and overlays.keys()):
        report["skipped"] = "no adventure text"
        return report

    keyed = parse_keyed_areas(adventure_text)
    key_index = seed_key_annotations(grid, properties, overlays, keyed)
    report["keys"] = [
        {"letter": letter, "id": item.get("id"), "bounds": item.get("bounds")}
        for letter, item in key_index.items()
    ]
    report["annotations"] = len(properties.get("map_annotations") or [])

    if isinstance(client, HeuristicClient):
        heuristic = apply_keyed_heuristic(grid, properties, keyed, key_index)
        report.update(heuristic)
        report["applied"] = True
        report["source"] = "keyed_heuristic"
        report["annotations"] = len(properties.get("map_annotations") or [])
        return report

    prompt = _adventure_prompt(grid, adventure_text, overlays, keyed, key_index)
    raw = client.complete(prompt, system=ADVENTURE_SYSTEM, max_tokens=2048)
    try:
        data = parse_json_object(raw)
    except (ValueError, json.JSONDecodeError):
        report["error"] = "could not parse adventure overlay JSON"
        report["raw"] = raw[:1000]
        heuristic = apply_keyed_heuristic(grid, properties, keyed, key_index)
        report.update(heuristic)
        report["applied"] = True
        report["source"] = "keyed_heuristic_after_parse_error"
        return report

    from natural20.map_import.taxonomy import normalize_class, normalize_subtype

    for item in data.get("fixes") or []:
        if not isinstance(item, dict):
            continue
        try:
            x, y = int(item["x"]), int(item["y"])
        except (KeyError, TypeError, ValueError):
            continue
        tile = grid.get(x, y)
        if tile is None:
            continue
        if any(str(f).startswith("overlay:") for f in tile.flags):
            continue
        tile.tile_class = normalize_class(item.get("class") or tile.tile_class)
        tile.subtype = normalize_subtype(item.get("subtype") or tile.subtype)
        tile.flags.append("adventure_fix")
        tile.source = "adventure"
        grid.set(tile)

    _apply_llm_entities(grid, properties, data, report, key_index)
    report["applied"] = True
    report["unplaced"] = list(data.get("unplaced") or [])
    report["raw_notes"] = data.get("notes")
    report["source"] = "llm"
    report["annotations"] = len(properties.get("map_annotations") or [])
    return report


def seed_key_annotations(
    grid: ClassificationGrid,
    properties: dict[str, Any],
    overlays: OverlayReport | None,
    keyed: list[KeyedArea],
) -> dict[str, dict[str, Any]]:
    """Turn printed keys into map_annotations, filled from matching headings."""
    annotations = properties.setdefault("map_annotations", [])
    existing_ids = {str(a.get("id")) for a in annotations if isinstance(a, dict)}
    existing_keys = {
        str(a.get("map_key") or "").lower(): a
        for a in annotations
        if isinstance(a, dict) and a.get("map_key")
    }
    by_letter = {area.letter: area for area in keyed if area.letter}
    index: dict[str, dict[str, Any]] = dict(existing_keys)
    for mark in (overlays.keys() if overlays else []):
        letter = mark.text.lower()
        if letter in index:
            continue
        if mark.tiles:
            pos = (int(mark.tiles[len(mark.tiles) // 2][0]), int(mark.tiles[len(mark.tiles) // 2][1]))
        else:
            continue
        cells = flood_room(grid, pos)
        if len(cells) > 200:
            continue
        bounds = room_bounds(cells)
        area = by_letter.get(letter)
        slug = _slug(area.code if area else f"area_{letter}")
        label = area.title if area else f"Area {letter}"
        description = area.excerpt() if area else f"Printed map key {letter}."
        item = {
            "id": slug,
            "label": label,
            "description": description,
            "kind": "area",
            "bounds": bounds,
            "map_key": letter,
        }
        if slug not in existing_ids:
            annotations.append(item)
            existing_ids.add(slug)
        index[letter] = item
    return index


def apply_keyed_heuristic(
    grid: ClassificationGrid,
    properties: dict[str, Any],
    keyed: list[KeyedArea],
    key_index: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Place NPCs/objects from keyed headings when no VLM overlay is available."""
    report = {"npcs": 0, "objects": 0, "notes": 0, "unplaced": []}
    by_letter = {area.letter: area for area in keyed if area.letter}
    used: set[tuple[int, int]] = set()
    for letter, ann in key_index.items():
        area = by_letter.get(letter)
        if area is None:
            continue
        cells = _cells_in_bounds(grid, ann.get("bounds") or {})
        walk = [c for c in cells if _walkable(grid, c)]
        if not walk:
            report["unplaced"].append(f"{area.code} has no walkable tile")
            continue
        body = f"{area.title}\n{area.body}"
        for npc in _npcs_in_text(body):
            pos = _take_cell(walk, used, prefer="center")
            if pos is None:
                report["unplaced"].append(npc["name"])
                continue
            _add_npc(properties, npc["name"], npc["sub_type"], pos)
            report["npcs"] += 1
        for obj in _objects_in_text(body):
            pos = _take_cell(walk, used, prefer="edge")
            if pos is None:
                report["unplaced"].append(obj["name"])
                continue
            _add_object(properties, obj["type"], obj["name"], pos, notes=obj.get("notes"))
            if obj["type"] == "note":
                report["notes"] += 1
            else:
                report["objects"] += 1
        if re.search(r"\b(enter|entrance|doors open|hall|foyer)\b", body, re.I):
            if not properties.get("player_spawn_points"):
                spawn = _take_cell(walk, used, prefer="south")
                if spawn:
                    properties["player_spawn_points"] = [{"position": [spawn[0], spawn[1]], "group": "a"}]
    return report


def _adventure_prompt(
    grid: ClassificationGrid,
    adventure_text: str,
    overlays: OverlayReport | None,
    keyed: list[KeyedArea],
    key_index: dict[str, dict[str, Any]],
) -> str:
    lines = [
        "ASCII map:",
        grid.ascii_map(),
        "",
        f"Grid size: {grid.width}x{grid.height}",
        "",
        "Printed keys on THIS floor (match adventure area letters to these rooms):",
    ]
    if key_index:
        for letter, item in sorted(key_index.items()):
            bounds = item.get("bounds") or {}
            lines.append(
                f"- {letter} → {item.get('label')} id={item.get('id')} "
                f"bounds=({bounds.get('x1')},{bounds.get('y1')})-({bounds.get('x2')},{bounds.get('y2')})"
            )
    elif overlays and overlays.keys():
        for mark in overlays.keys():
            lines.append(f"- {mark.text} at tiles {mark.tiles[:4]}")
    else:
        lines.append("- (none detected)")
    if overlays:
        other = [m for m in overlays.marks if m.kind != "key"]
        if other:
            lines.append("Cartography to ignore as walls: " + ", ".join(sorted({m.kind for m in other})))
    if keyed:
        lines.append("")
        lines.append("Keyed headings parsed from the adventure:")
        for area in keyed:
            if area.letter:
                lines.append(f"- {area.code} (letter {area.letter}): {area.title}")
    lines.append("")
    lines.append("Adventure text:")
    lines.append(adventure_text[:12000])
    return "\n".join(lines)


def _apply_llm_entities(
    grid: ClassificationGrid,
    properties: dict[str, Any],
    data: dict[str, Any],
    report: dict[str, Any],
    key_index: dict[str, dict[str, Any]],
) -> None:
    spawn = data.get("spawn")
    if isinstance(spawn, (list, tuple)) and len(spawn) == 2:
        try:
            sx, sy = int(spawn[0]), int(spawn[1])
            if grid.get(sx, sy):
                properties["player_spawn_points"] = [{"position": [sx, sy], "group": "a"}]
        except (TypeError, ValueError):
            pass

    npc_token = 0
    for npc in data.get("npcs") or []:
        if not isinstance(npc, dict):
            continue
        pos = _pos(npc.get("pos"), grid) or _pos_in_key(npc, key_index, grid)
        if pos is None:
            continue
        token = f"N{npc_token}"
        npc_token += 1
        sub_type = str(npc.get("sub_type") or "human_guard")
        properties.setdefault("legend", {})[token] = {
            "name": str(npc.get("name") or sub_type),
            "type": "npc",
            "sub_type": sub_type,
            "group": str(npc.get("group") or "b"),
        }
        properties.setdefault("map", {}).setdefault("entities", []).append(
            {"token": token, "pos": [pos[0], pos[1]]}
        )
        report["npcs"] += 1

    obj_token = 0
    for obj in data.get("objects") or []:
        if not isinstance(obj, dict):
            continue
        pos = _pos(obj.get("pos"), grid) or _pos_in_key(obj, key_index, grid)
        if pos is None:
            continue
        obj_type = str(obj.get("type") or "barrel")
        if obj_type not in ALLOWED_OBJECT_TYPES:
            obj_type = "barrel"
        token = str(obj.get("token") or f"O{obj_token}")
        obj_token += 1
        entry: dict[str, Any] = {
            "name": str(obj.get("name") or obj_type),
            "type": obj_type,
        }
        if obj.get("notes"):
            entry["notes"] = [{"note": str(obj["notes"])}]
        properties.setdefault("legend", {})[token] = entry
        properties.setdefault("map", {}).setdefault("entities", []).append(
            {"token": token, "pos": [pos[0], pos[1]], "layer": "object"}
        )
        report["objects"] += 1

    for note in data.get("notes") or []:
        if not isinstance(note, dict):
            continue
        pos = _pos(note.get("pos"), grid) or _pos_in_key(note, key_index, grid)
        if pos is None:
            continue
        token = f"n{report['notes']}"
        properties.setdefault("legend", {})[token] = {
            "name": "Note",
            "type": "note",
            "notes": [{"note": str(note.get("text") or "")}],
        }
        properties.setdefault("map", {}).setdefault("entities", []).append(
            {"token": token, "pos": [pos[0], pos[1]], "layer": "object"}
        )
        report["notes"] += 1

    annotations = properties.setdefault("map_annotations", [])
    existing = {str(a.get("id")) for a in annotations if isinstance(a, dict)}
    for ann in data.get("annotations") or []:
        if not isinstance(ann, dict) or not ann.get("id"):
            continue
        if str(ann["id"]) in existing:
            continue
        kind = str(ann.get("kind") or "area")
        item: dict[str, Any] = {
            "id": str(ann["id"]),
            "label": str(ann.get("label") or ann["id"]),
            "description": str(ann.get("description") or ""),
            "kind": kind,
        }
        if kind == "point" and _pos(ann.get("pos"), grid):
            p = _pos(ann.get("pos"), grid)
            item["pos"] = [p[0], p[1]]
        elif kind == "polygon" and isinstance(ann.get("points"), list):
            item["points"] = ann["points"]
        else:
            bounds = ann.get("bounds") or {}
            item["kind"] = "area"
            item["bounds"] = {
                "x1": int(bounds.get("x1") or 0),
                "y1": int(bounds.get("y1") or 0),
                "x2": int(bounds.get("x2") or grid.width - 1),
                "y2": int(bounds.get("y2") or grid.height - 1),
            }
        annotations.append(item)
        existing.add(item["id"])
        report["annotations"] += 1


def _npcs_in_text(text: str) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for match in _NAMED_STATBLOCK.finditer(text):
        name = match.group(1).strip()
        slug = _npc_slug(match.group(2))
        if slug and name.lower() not in seen:
            found.append({"name": name, "sub_type": slug})
            seen.add(name.lower())
    for match in _BOLD.finditer(text):
        slug = _npc_slug(match.group(1))
        if slug and slug not in seen:
            found.append({"name": match.group(1).strip().title(), "sub_type": slug})
            seen.add(slug)
    return found


def _objects_in_text(text: str) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    lower = text.lower()
    seen: set[str] = set()
    for word, obj_type, name in _OBJECT_HINTS:
        if word in lower and word not in seen:
            found.append({"type": obj_type, "name": name, "notes": name})
            seen.add(word)
    return found


def _npc_slug(raw: str) -> str | None:
    value = re.sub(r"[^a-z0-9 ]+", "", (raw or "").strip().lower())
    return _NPC_SLUGS.get(value) or _NPC_SLUGS.get(value.replace(" ", "_"))


def _add_npc(properties: dict[str, Any], name: str, sub_type: str, pos: tuple[int, int]) -> None:
    legend = properties.setdefault("legend", {})
    entities = properties.setdefault("map", {}).setdefault("entities", [])
    token = f"N{sum(1 for k in legend if str(k).startswith('N'))}"
    legend[token] = {"name": name, "type": "npc", "sub_type": sub_type, "group": "b"}
    entities.append({"token": token, "pos": [pos[0], pos[1]]})


def _add_object(
    properties: dict[str, Any],
    obj_type: str,
    name: str,
    pos: tuple[int, int],
    *,
    notes: str | None = None,
) -> None:
    legend = properties.setdefault("legend", {})
    entities = properties.setdefault("map", {}).setdefault("entities", [])
    token = f"O{sum(1 for k in legend if str(k).startswith('O'))}"
    entry: dict[str, Any] = {"name": name, "type": obj_type}
    if notes:
        entry["notes"] = [{"note": notes}]
    legend[token] = entry
    entities.append({"token": token, "pos": [pos[0], pos[1]], "layer": "object"})


def _cells_in_bounds(grid: ClassificationGrid, bounds: dict[str, Any]) -> list[tuple[int, int]]:
    try:
        x1, y1 = int(bounds.get("x1", 0)), int(bounds.get("y1", 0))
        x2, y2 = int(bounds.get("x2", x1)), int(bounds.get("y2", y1))
    except (TypeError, ValueError):
        return []
    cells = []
    for y in range(min(y1, y2), max(y1, y2) + 1):
        for x in range(min(x1, x2), max(x1, x2) + 1):
            if grid.get(x, y) is not None:
                cells.append((x, y))
    return cells


def _walkable(grid: ClassificationGrid, pos: tuple[int, int]) -> bool:
    tile = grid.get(pos[0], pos[1])
    return bool(tile and tile.tile_class in {"floor", "door", "water", "object"})


def _take_cell(
    cells: list[tuple[int, int]],
    used: set[tuple[int, int]],
    *,
    prefer: str,
) -> tuple[int, int] | None:
    free = [c for c in cells if c not in used]
    if not free:
        return None
    xs = [c[0] for c in free]
    ys = [c[1] for c in free]
    if prefer == "south":
        pick = max(free, key=lambda c: (c[1], -abs(c[0] - sum(xs) / len(xs))))
    elif prefer == "edge":
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        pick = max(free, key=lambda c: abs(c[0] - cx) + abs(c[1] - cy))
    else:
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        pick = min(free, key=lambda c: abs(c[0] - cx) + abs(c[1] - cy))
    used.add(pick)
    return pick


def _pos_in_key(item: dict[str, Any], key_index: dict[str, dict[str, Any]], grid: ClassificationGrid) -> tuple[int, int] | None:
    key = str(item.get("key") or item.get("area") or item.get("map_key") or "").lower()
    if len(key) > 1:
        key = letter_from_code(key) or key[-1]
    ann = key_index.get(key)
    if not ann:
        return None
    cells = [c for c in _cells_in_bounds(grid, ann.get("bounds") or {}) if _walkable(grid, c)]
    if not cells:
        return None
    return cells[len(cells) // 2]


def _slug(value: str) -> str:
    text = "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")
    return text or "area"


def _pos(value: Any, grid: ClassificationGrid) -> tuple[int, int] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        x, y = int(value[0]), int(value[1])
    except (TypeError, ValueError):
        return None
    if grid.get(x, y) is None:
        return None
    return x, y
