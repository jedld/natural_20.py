"""Final LLM pass: adventure text + generated map YAML/ASCII to patch remaining issues."""

from __future__ import annotations

import json
from typing import Any

from natural20.map_import.json_util import parse_json_object
from natural20.map_import.model import ClassificationGrid
from natural20.map_import.region_verify import verify_adventure_regions
from natural20.map_import.taxonomy import normalize_class, normalize_subtype
from natural20.map_import.vlm import HeuristicClient, VlmClient

REFINE_SYSTEM = """You are the last quality pass on a Natural20 map imported from a battlemap.
You see the ASCII layout, the YAML excerpt, and the adventure text.
Fix remaining layout errors and add missing adventure features.

Return JSON only:
{
  "tile_fixes": [
    {"x": 0, "y": 0, "class": "wall|floor|void|water|door|object", "subtype": "none", "orientation": "none", "reason": ""}
  ],
  "remove_entities_at": [[x, y]],
  "add_entities": [
    {"token": "G1", "pos": [x, y], "legend": {"name": "...", "type": "npc", "sub_type": "goblin", "group": "b"}}
  ],
  "add_annotations": [
    {"id": "slug", "label": "...", "description": "...", "kind": "area", "bounds": {"x1": 0, "y1": 0, "x2": 3, "y2": 2}}
  ],
  "description": "optional improved map description",
  "summary": "one paragraph of what you changed"
}
Keep changes minimal. Do not wipe a coherent room to redraw it.
Do not turn printed titles, compass roses, or circled room keys into walls.
"""


def refine_map(
    grid: ClassificationGrid,
    properties: dict[str, Any],
    adventure_text: str,
    client: VlmClient,
    *,
    overlays=None,
) -> dict[str, Any]:
    report: dict[str, Any] = {"applied": False, "tile_fixes": 0, "entities_added": 0, "annotations_added": 0}
    if isinstance(client, HeuristicClient):
        report["skipped"] = "heuristic provider cannot refine"
        return report

    region = verify_adventure_regions(
        grid,
        adventure_text,
        client,
        overlays=overlays,
        annotations=list(properties.get("map_annotations") or []),
    )
    report["region_verify"] = region
    report["tile_fixes"] += int(region.get("tile_fixes") or 0)

    yaml_excerpt = _compact_yaml(properties)
    prompt = (
        f"ASCII:\n{grid.ascii_map()}\n\n"
        f"YAML excerpt:\n{yaml_excerpt}\n\n"
        f"Adventure text:\n{(adventure_text or '(none)')[:8000]}\n"
    )
    raw = client.complete(prompt, system=REFINE_SYSTEM, max_tokens=2048)
    try:
        data = parse_json_object(raw)
    except (ValueError, json.JSONDecodeError):
        report["error"] = "could not parse refine JSON"
        report["raw"] = raw[:1000]
        return report

    for item in data.get("tile_fixes") or []:
        if not isinstance(item, dict):
            continue
        try:
            x, y = int(item["x"]), int(item["y"])
        except (KeyError, TypeError, ValueError):
            continue
        tile = grid.get(x, y)
        if tile is None:
            continue
        tile.tile_class = normalize_class(item.get("class") or tile.tile_class)
        tile.subtype = normalize_subtype(item.get("subtype") or tile.subtype)
        if item.get("orientation"):
            tile.orientation = str(item["orientation"])
        tile.flags.append("refine")
        tile.source = "refine"
        grid.set(tile)
        report["tile_fixes"] += 1

    remove_at = {tuple(p) for p in data.get("remove_entities_at") or [] if isinstance(p, (list, tuple)) and len(p) == 2}
    if remove_at:
        entities = properties.get("map", {}).get("entities") or []
        properties["map"]["entities"] = [
            e for e in entities if tuple(e.get("pos") or []) not in {(int(a), int(b)) for a, b in remove_at}
        ]

    legend = properties.setdefault("legend", {})
    entities = properties.setdefault("map", {}).setdefault("entities", [])
    for ent in data.get("add_entities") or []:
        if not isinstance(ent, dict) or "pos" not in ent:
            continue
        token = str(ent.get("token") or f"R{report['entities_added']}")
        if isinstance(ent.get("legend"), dict):
            legend[token] = ent["legend"]
        entities.append({"token": token, "pos": list(ent["pos"]), **({} if "layer" not in ent else {"layer": ent["layer"]})})
        report["entities_added"] += 1

    annotations = properties.setdefault("map_annotations", [])
    for ann in data.get("add_annotations") or []:
        if isinstance(ann, dict) and ann.get("id"):
            annotations.append(ann)
            report["annotations_added"] += 1

    if data.get("description"):
        properties["description"] = str(data["description"])
    report["applied"] = True
    report["summary"] = data.get("summary") or ""
    return report


def _compact_yaml(properties: dict[str, Any]) -> str:
    import yaml

    excerpt = {
        "name": properties.get("name"),
        "description": properties.get("description"),
        "map": {
            "size": (properties.get("map") or {}).get("size"),
            "base": (properties.get("map") or {}).get("base"),
            "entities": (properties.get("map") or {}).get("entities"),
        },
        "legend": properties.get("legend"),
        "map_annotations": properties.get("map_annotations"),
        "player_spawn_points": properties.get("player_spawn_points"),
    }
    return yaml.safe_dump(excerpt, sort_keys=False, allow_unicode=True)[:14000]
