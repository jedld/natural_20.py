"""Static structural validation for campaign configuration and maps."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from natural20.campaign_validator.catalog import CampaignCatalog
from natural20.campaign_validator.report import ValidationReport
from natural20.campaign_validator.yaml_checks import load_yaml_file

BUILTIN_MAP_TOKENS = {"#", ".", "_", "-", "|", "?"}
BUILTIN_LEGEND_TYPES = {
    "npc",
    "spawn_point",
    "mask",
    "teleporter",
    "trap_door",
    "interactive_object",
}
REQUIRED_INDEX_KEYS = {
    "tile_size",
    "title",
    "login_background",
    "map",
    "soundtracks",
    "logins",
    "default_controllers",
}


def campaign_file(campaign: Path, raw_path: Any, suffix: str = "") -> Path | None:
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    candidate = Path(raw_path)
    if suffix and not candidate.suffix:
        candidate = candidate.with_suffix(suffix)
    return candidate if candidate.is_absolute() else campaign / candidate


def map_registry(campaign: Path, game: dict[str, Any], report: ValidationReport) -> dict[str, Path]:
    registry: dict[str, Path] = {}
    raw_maps = game.get("maps")
    if raw_maps is not None:
        if not isinstance(raw_maps, dict) or not raw_maps:
            report.error("game.yml 'maps' must be a non-empty mapping when present")
            return registry
        for key, raw_path in raw_maps.items():
            path = campaign_file(campaign, raw_path, ".yml")
            if not isinstance(key, str) or not key:
                report.error("game.yml map keys must be non-empty strings")
            elif path is None:
                report.error(f"game.yml map '{key}' has an invalid path")
            else:
                registry[key] = path
    else:
        path = campaign_file(campaign, game.get("starting_map"), ".yml")
        if path is None:
            report.error("game.yml requires 'starting_map' when 'maps' is absent")
        else:
            registry["index"] = path
    return registry


def normalize_map_path(raw_path: Any) -> str | None:
    if not isinstance(raw_path, str) or not raw_path:
        return None
    return raw_path[:-4] if raw_path.endswith(".yml") else raw_path


def validate_static_structure(
    campaign: Path,
    catalog: CampaignCatalog,
    report: ValidationReport,
) -> None:
    game = load_yaml_file(campaign / "game.yml", report)
    if game is None:
        return

    index = _load_json(campaign / "index.json", report)
    registry = map_registry(campaign, game, report)
    map_data: dict[str, dict[str, Any]] = {}
    dimensions: dict[str, tuple[int, int]] = {}
    for name, path in registry.items():
        properties = load_yaml_file(path, report)
        if properties is not None:
            map_data[name] = properties
            size = grid_dimensions(name, properties, report)
            if size is not None:
                dimensions[name] = size

    object_types = set(catalog.objects)
    validate_groups(game, report)
    if index is not None:
        validate_index(campaign, index, game, registry, report)
    for name, properties in map_data.items():
        validate_map(
            campaign,
            name,
            registry[name],
            properties,
            registry,
            dimensions,
            object_types,
            catalog,
            report,
        )


def _load_json(path: Path, report: ValidationReport) -> dict[str, Any] | None:
    if not path.is_file():
        report.error(f"missing JSON file: {path}", code="missing_file", path="index.json")
        return None
    try:
        with path.open("r", encoding="utf-8") as stream:
            data = json.load(stream)
    except (OSError, json.JSONDecodeError) as exc:
        report.error(f"cannot parse index.json: {exc}", code="json_syntax", path="index.json")
        return None
    if not isinstance(data, dict):
        report.error("index.json must contain a JSON object at the document root", path="index.json")
        return None
    return data


def validate_index(
    campaign: Path,
    index: dict[str, Any],
    game: dict[str, Any],
    registry: dict[str, Path],
    report: ValidationReport,
) -> None:
    missing = sorted(REQUIRED_INDEX_KEYS - index.keys())
    if missing:
        report.error(f"index.json missing required key(s): {', '.join(missing)}", path="index.json")

    tile_size = index.get("tile_size")
    if not isinstance(tile_size, (int, float)) or tile_size <= 0:
        report.error("index.json 'tile_size' must be a positive number", path="index.json")

    for key in ("soundtracks", "logins", "default_controllers"):
        if key in index and not isinstance(index[key], list):
            report.error(f"index.json '{key}' must be an array", path="index.json")

    registered_paths = {normalize_map_path(str(path.relative_to(campaign))) for path in registry.values()}
    web_start = normalize_map_path(index.get("map"))
    if web_start and web_start not in registered_paths:
        report.error(
            f"index.json starting map '{index.get('map')}' is not registered in game.yml",
            path="index.json",
        )

    game_start = normalize_map_path(game.get("starting_map"))
    if game_start and web_start and game_start != web_start:
        report.warning(
            f"game.yml starting_map '{game.get('starting_map')}' differs from "
            f"index.json map '{index.get('map')}'"
        )

    other_maps = index.get("other_maps", {})
    if not isinstance(other_maps, dict):
        report.error("index.json 'other_maps' must be an object", path="index.json")
    else:
        for key, raw_path in other_maps.items():
            if key not in registry:
                report.error(
                    f"index.json other_maps key '{key}' is not registered in game.yml",
                    path="index.json",
                )
            elif normalize_map_path(raw_path) != normalize_map_path(
                str(registry[key].relative_to(campaign))
            ):
                report.warning(f"index.json path for map '{key}' differs from game.yml")

    selectable = index.get("selectable_characters", [])
    if selectable is not None and not isinstance(selectable, list):
        report.error("index.json 'selectable_characters' must be an array", path="index.json")
        selectable = []
    for position, entry in enumerate(selectable or []):
        if not isinstance(entry, dict):
            report.error(f"selectable_characters[{position}] must be an object", path="index.json")
            continue
        sheet = campaign_file(campaign, entry.get("sheet"))
        if sheet is None:
            report.warning(
                f"selectable character {entry.get('name', position)!r} has no sheet",
                path="index.json",
            )
        elif not sheet.is_file():
            report.error(
                f"selectable character sheet does not exist: {sheet}",
                path="index.json",
            )
        check_asset(
            campaign,
            entry.get("file"),
            f"selectable character {entry.get('name', position)!r}",
            report,
        )

    check_asset(campaign, index.get("login_background"), "login background", report)
    check_asset(
        campaign,
        index.get("character_selection_background"),
        "character selection background",
        report,
    )
    for entry in index.get("soundtracks", []) if isinstance(index.get("soundtracks"), list) else []:
        if isinstance(entry, dict):
            check_asset(campaign, entry.get("file"), f"soundtrack {entry.get('name')!r}", report)


def check_asset(campaign: Path, raw_path: Any, label: str, report: ValidationReport) -> None:
    if not isinstance(raw_path, str) or not raw_path or raw_path.startswith(("http://", "https://", "data:")):
        return
    candidates = [
        campaign / raw_path,
        campaign / "assets" / raw_path,
        campaign / "assets" / "maps" / raw_path,
        campaign / "assets" / "maps" / Path(raw_path).name,
    ]
    if not any(path.is_file() for path in candidates):
        report.warning(f"{label} asset does not exist: {raw_path}")


def grid_dimensions(
    map_name: str, properties: dict[str, Any], report: ValidationReport
) -> tuple[int, int] | None:
    map_data = properties.get("map")
    if not isinstance(map_data, dict):
        report.error(f"map '{map_name}' requires a 'map' mapping")
        return None
    base = map_data.get("base")
    if not isinstance(base, list) or not base or not all(isinstance(row, str) for row in base):
        report.error(f"map '{map_name}' requires a non-empty string array at map.base")
        return None
    width = len(base[0])
    if width == 0 or any(len(row) != width for row in base):
        report.error(f"map '{map_name}' base rows must be non-empty and equal width")
        return None
    inferred = (width, len(base))
    size = map_data.get("size")
    if size is not None:
        if (
            not isinstance(size, list)
            or len(size) != 2
            or not all(isinstance(value, int) and value > 0 for value in size)
        ):
            report.error(f"map '{map_name}' map.size must be [positive_width, positive_height]")
            return inferred
        if tuple(size) != inferred:
            report.error(f"map '{map_name}' map.size {size} does not match base grid {list(inferred)}")
        return size[0], size[1]
    return inferred


def validate_position(
    value: Any, dimensions: tuple[int, int], context: str, report: ValidationReport
) -> None:
    if (
        not isinstance(value, (list, tuple))
        or len(value) < 2
        or not isinstance(value[0], int)
        or not isinstance(value[1], int)
    ):
        report.error(f"{context} must be an integer [x, y] coordinate")
        return
    x, y = value[0], value[1]
    if x < 0 or y < 0 or x >= dimensions[0] or y >= dimensions[1]:
        report.error(f"{context} coordinate [{x}, {y}] is outside map bounds {list(dimensions)}")


def validate_map(
    campaign: Path,
    map_name: str,
    path: Path,
    properties: dict[str, Any],
    registry: dict[str, Path],
    map_dimensions: dict[str, tuple[int, int]],
    object_types: set[str],
    catalog: CampaignCatalog,
    report: ValidationReport,
) -> None:
    dimensions = map_dimensions.get(map_name)
    if dimensions is None:
        return
    map_data = properties["map"]
    legend = properties.get("legend", {})
    if not isinstance(legend, dict):
        report.error(f"map '{map_name}' legend must be a mapping")
        legend = {}

    for layer in ("base", "base_1", "base_2", "meta", "light", "light_map"):
        rows = map_data.get(layer)
        if rows is None:
            continue
        if not isinstance(rows, list) or not all(isinstance(row, str) for row in rows):
            report.error(f"map '{map_name}' map.{layer} must be an array of strings")
            continue
        if len(rows) != dimensions[1] or any(len(row) != dimensions[0] for row in rows):
            report.error(f"map '{map_name}' map.{layer} dimensions must match {list(dimensions)}")
            continue
        if layer in {"base", "base_1", "base_2"}:
            unknown = sorted(
                {
                    token
                    for row in rows
                    for token in row
                    if token not in BUILTIN_MAP_TOKENS and token not in legend
                }
            )
            if unknown:
                report.error(f"map '{map_name}' map.{layer} has undefined token(s): {unknown}")
        elif layer == "meta":
            unknown = sorted({token for row in rows for token in row if token != "." and token not in legend})
            if unknown:
                report.warning(
                    f"map '{map_name}' map.meta has undefined token(s) ignored by the engine: {unknown}"
                )

    for token, entry in legend.items():
        if not isinstance(entry, dict):
            report.error(f"map '{map_name}' legend token {token!r} must map to an object")
            continue
        entry_type = entry.get("type")
        if not entry_type:
            report.error(f"map '{map_name}' legend token {token!r} has no type")
        elif entry_type not in BUILTIN_LEGEND_TYPES and object_types and entry_type not in object_types:
            suggestions = catalog.suggest_object(entry_type)
            report.error(
                f"map '{map_name}' legend token {token!r} references unknown object type '{entry_type}'",
                code="missing_object",
                path=str(path.relative_to(campaign)),
                context={"object_type": entry_type, "map": map_name, "suggestions": suggestions},
                repairable=True,
            )
        if entry_type == "npc":
            subtype = entry.get("sub_type")
            if not subtype:
                report.error(f"map '{map_name}' NPC token {token!r} requires sub_type")
            elif not catalog.npc_exists(subtype):
                suggestions = catalog.suggest_npc(subtype)
                report.error(
                    f"map '{map_name}' NPC token {token!r} references missing npc type {subtype!r}",
                    code="missing_npc",
                    path=str(path.relative_to(campaign)),
                    context={"npc_type": subtype, "map": map_name, "suggestions": suggestions},
                    repairable=True,
                )
        if entry_type in {"teleporter", "trap_door"} or entry.get("target_map"):
            target_map = entry.get("target_map")
            if target_map not in registry:
                report.error(f"map '{map_name}' token {token!r} targets unregistered map '{target_map}'")
            elif target_map in map_dimensions:
                validate_position(
                    entry.get("target_position"),
                    map_dimensions[target_map],
                    f"map '{map_name}' token {token!r} target_position",
                    report,
                )

    for index, entry in enumerate(map_data.get("entities", [])):
        if not isinstance(entry, dict):
            report.error(f"map '{map_name}' map.entities[{index}] must be an object")
            continue
        if entry.get("token") not in legend:
            report.error(
                f"map '{map_name}' map.entities[{index}] uses undefined legend token {entry.get('token')!r}"
            )
        validate_position(
            entry.get("pos"), dimensions, f"map '{map_name}' map.entities[{index}].pos", report
        )

    for collection in ("player_spawn_points", "player", "npc"):
        entries = properties.get(collection) or []
        if not isinstance(entries, list):
            report.error(f"map '{map_name}' {collection} must be an array or null")
            continue
        for index, entry in enumerate(entries):
            position = (
                entry
                if collection == "player_spawn_points" and isinstance(entry, list)
                else entry.get("position")
                if isinstance(entry, dict)
                else None
            )
            validate_position(position, dimensions, f"map '{map_name}' {collection}[{index}]", report)
            if collection == "player" and isinstance(entry, dict):
                sheet = campaign_file(campaign, entry.get("sheet"))
                if sheet is None or not sheet.is_file():
                    report.error(
                        f"map '{map_name}' player[{index}] references missing sheet {entry.get('sheet')!r}"
                    )
            if collection == "npc" and isinstance(entry, dict):
                subtype = entry.get("sub_type")
                if not subtype or not catalog.npc_exists(subtype):
                    suggestions = catalog.suggest_npc(subtype or "")
                    report.error(
                        f"map '{map_name}' npc[{index}] references missing npc type {subtype!r}",
                        code="missing_npc",
                        path=str(path.relative_to(campaign)),
                        context={"npc_type": subtype, "map": map_name, "suggestions": suggestions},
                        repairable=True,
                    )
                if "overrides" not in entry:
                    report.error(
                        f"map '{map_name}' npc[{index}] requires an overrides mapping for the current loader"
                    )

    background = properties.get("background_image")
    if background:
        check_asset(campaign, background, f"map '{map_name}' background", report)


def validate_groups(game: dict[str, Any], report: ValidationReport) -> None:
    groups = game.get("groups", {})
    if groups is None:
        groups = {}
    if not isinstance(groups, dict):
        report.error("game.yml 'groups' must be a mapping")
        return
    defaults = [name for name, value in groups.items() if isinstance(value, dict) and value.get("default")]
    if groups and len(defaults) != 1:
        report.warning(
            f"game.yml should normally define exactly one default group; found {len(defaults)}"
        )
    for name, value in groups.items():
        if not isinstance(value, dict):
            report.error(f"game.yml group '{name}' must be a mapping")
            continue
        for relationship in ("enemies", "neutral", "allies"):
            related = value.get(relationship, [])
            if not isinstance(related, list):
                report.error(f"game.yml group '{name}' {relationship} must be an array")
                continue
            for target in related:
                if target not in groups:
                    report.warning(
                        f"game.yml group '{name}' references undefined {relationship} group '{target}'"
                    )
